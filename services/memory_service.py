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
    exclude_message_id: Optional[uuid.UUID] = None
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

    # 2. System Prompt Assembly with strict anti-hallucination & internet awareness
    system_parts = [
        "You are GHOSTMIND, an intelligent, private local AI operating system.",
        "You provide concise, accurate, and deeply knowledgeable answers on technology, software engineering, and modern artificial intelligence.",
        "CRITICAL KNOWLEDGE & HONESTY POLICY:\n"
        "1. FACTUAL ACCURACY: If you have verified knowledge from your training, local documents, or live web search results, answer accurately, clearly, and directly.\n"
        "2. ANTI-HALLUCINATION: If you do NOT possess verified, factual knowledge about a specific topic, acronym, person, or technical standard (and no relevant facts exist in the provided documents or web search results), you MUST NEVER guess, fabricate, or make up plausible-sounding explanations. You MUST explicitly state: 'I don't have knowledge of that, and I will not give you incorrect information.'\n"
        + (
            "3. REAL-TIME INTERNET STATUS: Internet access is currently ACTIVE. Real-time web search results have been fetched and provided below when needed to ensure your knowledge is foolproof and up-to-date."
            if internet_online else
            "3. REAL-TIME INTERNET STATUS: The system is currently OFFLINE (no internet connection). You cannot search the web. If you do not have confident knowledge of the user's question, you MUST say: 'I do not have knowledge of that, and without an active internet connection, I cannot search for it. I will not give you wrong output because I don't know.'"
        )
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
