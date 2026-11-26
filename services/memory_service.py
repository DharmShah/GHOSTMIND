import uuid
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from models import User, Memory, Message, Conversation, UserPreference
from core.config import settings

def list_memories_for_user(db: Session, user_id: uuid.UUID, active_only: bool = False) -> List[Memory]:
    """Retrieves long-term memories scoped to the local user."""
    stmt = select(Memory).where(Memory.user_id == user_id)
    if active_only:
        stmt = stmt.where(Memory.is_active == True)
    stmt = stmt.order_by(desc(Memory.updated_at))
    return list(db.scalars(stmt).all())

def add_memory(
    db: Session,
    user_id: uuid.UUID,
    memory_text: str,
    category: str = "project_context",
    source_conversation_id: Optional[uuid.UUID] = None
) -> Memory:
    """Adds a validated long-term memory for the user."""
    cleaned = memory_text.strip()
    if not cleaned:
        raise ValueError("Memory text cannot be empty.")

    now = datetime.now(timezone.utc)
    mem = Memory(
        id=uuid.uuid4(),
        user_id=user_id,
        source_conversation_id=source_conversation_id,
        memory_text=cleaned,
        category=category,
        is_active=True,
        created_at=now,
        updated_at=now
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem

def update_memory(
    db: Session,
    user_id: uuid.UUID,
    memory_id: uuid.UUID,
    memory_text: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Optional[Memory]:
    """Edits or toggles an existing memory."""
    mem = db.scalar(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    )
    if not mem:
        return None

    if memory_text is not None:
        mem.memory_text = memory_text.strip()
    if category is not None:
        mem.category = category
    if is_active is not None:
        mem.is_active = is_active

    mem.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mem)
    return mem

def delete_memory(db: Session, user_id: uuid.UUID, memory_id: uuid.UUID) -> bool:
    """Permanently deletes a long-term memory."""
    mem = db.scalar(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    )
    if not mem:
        return False
    db.delete(mem)
    db.commit()
    return True

def auto_extract_and_save_memory(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_message: str
) -> Optional[Memory]:
    """
    Detects stable project declarations or key preferences in the user message
    and saves them as a user memory.
    Example: 'My project is GHOSTMIND, and I am using Qwen2.5 3B locally.'
    """
    patterns = [
        r'(?:my project is|i am building|we are developing|i work on)\s+([^.!?\n]{5,100})',
        r'(?:my tech stack is|i am using|we use)\s+([^.!?\n]{5,100})',
        r'(?:i prefer|always use|never use|remember that)\s+([^.!?\n]{5,100})',
    ]

    for p in patterns:
        m = re.search(p, user_message, re.IGNORECASE)
        if m:
            extracted_text = user_message.strip()
            # Avoid duplicate memories
            existing = db.scalar(
                select(Memory)
                .where(
                    Memory.user_id == user_id,
                    Memory.memory_text == extracted_text
                )
            )
            if not existing:
                return add_memory(
                    db=db,
                    user_id=user_id,
                    memory_text=extracted_text,
                    category="project_context",
                    source_conversation_id=conversation_id
                )
    return None

def filter_relevant_memories(memories: List[Memory], current_prompt: str, max_count: int = 3) -> List[Memory]:
    """
    Selects only memories relevant to the current user prompt, saving context tokens.
    """
    if not memories:
        return []

    prompt_lower = current_prompt.lower()
    prompt_tokens = set(re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', prompt_lower))

    # Check if prompt explicitly asks about user identity, project, or memories
    identity_triggers = {"who", "my", "me", "remember", "memory", "project", "name", "prefer", "preference", "stack", "about"}
    asks_about_self = bool(prompt_tokens.intersection(identity_triggers))

    scored_mems = []
    for m in memories:
        mem_tokens = set(re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', m.memory_text.lower()))
        overlap = len(prompt_tokens.intersection(mem_tokens))
        if asks_about_self:
            overlap += 2
        if overlap > 0:
            scored_mems.append((overlap, m))

    if not scored_mems and asks_about_self:
        return memories[:max_count]

    scored_mems.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_mems[:max_count]]

def build_bounded_context(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_prompt: str,
    rag_context: str = "",
    web_context: str = "",
    internet_online: bool = True,
    exclude_message_id: Optional[uuid.UUID] = None,
    web_search_enabled: bool = True
) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Assembles a token-optimized, multi-layered context window:
    1. System instructions with anti-hallucination & live web/offline guardrails
    2. Relevant user memories (filtered to minimize token consumption)
    3. Document RAG Evidence (if available)
    4. Live Web Search Evidence (if online and applicable)
    5. Bounded recent conversation turns
    6. Current user prompt
    """
    # 1. Check user preferences for memory
    pref = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    memory_enabled = pref.memory_enabled if pref else True

    active_memories = []
    relevant_memories = []
    if memory_enabled:
        active_memories = list_memories_for_user(db, user_id, active_only=True)
        relevant_memories = filter_relevant_memories(active_memories, current_prompt, max_count=settings.MAX_MEMORIES)

    # 2. System Prompt Assembly with strict anti-hallucination, acronym accuracy, & internet awareness
    if not web_search_enabled:
        internet_status_block = (
            "4. REAL-TIME INTERNET STATUS: Web Search is currently OFF. Do NOT make external claims of web verification, "
            "do NOT fabricate citations or URLs, and answer using your local model knowledge only. "
            "If asked for current or historical market prices, exchange rates, live data, or recent events, explicitly state that "
            "current/historical external pricing cannot be retrieved because Web Search is disabled, and ask the user to enable Web Search."
        )
    elif internet_online:
        internet_status_block = (
            "4. REAL-TIME INTERNET STATUS: Internet access is currently ACTIVE. Real-time web search results have been fetched and provided below when needed to ensure your knowledge is foolproof and up-to-date.\n"
            "5. GROUNDED ANSWER GENERATION:\n"
            "   - When research evidence is supplied below, use it to support current and externally verifiable claims.\n"
            "   - Preserve numerical precision, dates, currencies, purity (e.g. 24K/22K/18K), and units exactly as retrieved. Never invent missing values or blindly average conflicting market prices (e.g. IBJA vs retail).\n"
            "   - If essential context such as location or currency is missing and ambiguous for a local commodity price, ask the user for clarification instead of silently assuming.\n"
            "   - Do not invent facts, statistics, versions, dates, quotations, or URLs.\n"
            "   - Do not claim that a source confirms something unless the retrieved content actually supports it.\n"
            "   - Attach citations [1], [2], etc., to claims derived from external research.\n"
            "   - Clearly distinguish verified facts from explanations and inferences.\n"
            "   - If sources disagree, explain the disagreement (timestamps, units, purity, market type) rather than choosing an unsupported answer.\n"
            "   - If evidence is insufficient, explicitly state: 'I couldn't find enough reliable data to answer this accurately.'\n"
            "   - Never fabricate citations or URLs. Prefer a transparent incomplete answer over a confident but unsupported answer."
        )
    else:
        internet_status_block = (
            "4. REAL-TIME INTERNET STATUS: The system is currently OFFLINE (no internet connection). You cannot search the web. "
            "If you do not have confident knowledge of an external factual question, state: "
            "'I do not have knowledge of that, and without an active internet connection, I cannot search for it. I will not give you wrong output because I don't know.'"
        )

    system_parts = [
        "You are GHOSTMIND, an intelligent, private local AI operating system.",
        "You are a technically accurate AI assistant. Truth and correctness are more important than agreement.\n\n"
        "Never fabricate technical definitions, acronyms, APIs, protocols, citations, or facts.\n\n"
        "Do not change a factual answer merely because the user challenges it or proposes another answer. Re-evaluate the claim independently.\n\n"
        "Distinguish established facts, reasonable inferences, and uncertainty.\n\n"
        "When uncertain, say what you know and what you cannot verify. Never manufacture confidence.\n\n"
        "For technical questions, prioritize established industry terminology and authoritative documentation.",
        "CRITICAL KNOWLEDGE, ACRONYM & HONESTY POLICY:\n"
        "1. FACTUAL & ACRONYM ACCURACY: Resolve technical acronyms using conversation context and established terminology in the relevant domain (e.g., in AI agents, MCP stands for Model Context Protocol — never invent expansions like 'Machine Configuration Protocol' or 'Master Control Panel'). If multiple meanings are genuinely possible across industries, explain the ambiguity or ask for clarification.\n"
        "2. RESIST CONFIRMATION BIAS & ANTI-HALLUCINATION: Never treat a user's suggested answer as proof that it is correct. If a user's claim conflicts with established facts, politely correct them and explain briefly. If asked about an unverified real-world event, obscure person, or unknown claim (with no facts in documents or web search), do not guess or fabricate facts.\n"
        "3. CODE, SVG & UI GENERATION: You are an expert software engineer and UI architect. You CAN and MUST generate complete code, UI structures, SVG vector markup, SwiftUI, Flutter, React, and scripts when requested. NEVER refuse code, SVG, or UI requests with 'I don't have knowledge of that' or 'beyond my capabilities as a text-based AI'. Produce the complete, clean code or SVG directly.\n"
        + internet_status_block
    ]

    # Only inject memory section if relevant memories exist
    if relevant_memories:
        memory_lines = [f"- {m.memory_text}" for m in relevant_memories]
        system_parts.append(
            "[RELEVANT USER FACTS & PREFERENCES]\n" + "\n".join(memory_lines)
        )

    if rag_context:
        system_parts.append(rag_context)

    if web_context:
        system_parts.append(web_context)

    system_message = "\n\n".join(system_parts)

    messages_payload: List[Dict[str, str]] = [
        {"role": "system", "content": system_message}
    ]

    # 3. Load bounded recent messages from conversation history (limited to MAX_RECENT_MESSAGES)
    history_query = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.user_id == user_id
        )
    )
    if exclude_message_id:
        history_query = history_query.where(Message.id != exclude_message_id)

    recent_msgs = db.scalars(
        history_query.order_by(desc(Message.created_at)).limit(settings.MAX_RECENT_MESSAGES)
    ).all()

    # Reorder chronologically
    for msg in reversed(recent_msgs):
        if msg.role in ["user", "assistant"]:
            messages_payload.append({
                "role": msg.role,
                "content": msg.content
            })

    # 4. Append current prompt as active final turn
    messages_payload.append({
        "role": "user",
        "content": current_prompt
    })

    memory_citations = [m.memory_text for m in relevant_memories]
    return messages_payload, memory_citations
