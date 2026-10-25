import uuid
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from models import Memory, Message, Conversation, UserPreference
from core.config import settings

def list_memories_for_user(db: Session, user_id: uuid.UUID, active_only: bool = False) -> List[Memory]:
    """Retrieves long-term memories scoped strictly to the authenticated user."""
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
        r'(?:i prefer|always use|never use)\s+([^.!?\n]{5,100})',
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

def build_bounded_context(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_prompt: str,
    rag_context: str = ""
) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Assembles a bounded, multi-layered context window:
    1. System instructions + Active User Memories + RAG Evidence
    2. Bounded recent conversation message history
    3. Current user prompt
    """
    # 1. Check user preferences for memory
    pref = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    memory_enabled = pref.memory_enabled if pref else True

    active_memories = []
    if memory_enabled:
        active_memories = list_memories_for_user(db, user_id, active_only=True)

    # 2. System Prompt Assembly
    system_parts = [
        "You are GHOSTMIND, an intelligent, private local AI operating system.",
        "You provide concise, accurate, and deeply knowledgeable answers."
    ]

    if active_memories:
        memory_lines = [f"- {m.memory_text}" for m in active_memories[:settings.MAX_MEMORIES]]
        system_parts.append(
            "\n[SAVED USER MEMORY & PROJECT CONTEXT]\n" + "\n".join(memory_lines)
        )

    if rag_context:
        system_parts.append(rag_context)

    system_message = "\n\n".join(system_parts)

    messages_payload: List[Dict[str, str]] = [
        {"role": "system", "content": system_message}
    ]

    # 3. Load bounded recent messages from conversation history
    recent_msgs = db.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.user_id == user_id
        )
        .order_by(desc(Message.created_at))
        .limit(settings.MAX_RECENT_MESSAGES)
    ).all()

    # Reorder chronologically
    for msg in reversed(recent_msgs):
        if msg.role in ["user", "assistant"]:
            messages_payload.append({
                "role": msg.role,
                "content": msg.content
            })

    # 4. Append current prompt
    messages_payload.append({
        "role": "user",
        "content": current_prompt
    })

    memory_citations = [m.memory_text for m in active_memories]
    return messages_payload, memory_citations
