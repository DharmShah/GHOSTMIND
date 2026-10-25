import uuid
import json
import re
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func, or_

from models import Conversation, Message

def generate_smart_title(first_message: str) -> str:
    """Generates a clean, readable 3-6 word title from the initial user prompt."""
    cleaned = re.sub(r'[\r\n\t]+', ' ', first_message).strip()
    # Strip common filler prefixes
    cleaned = re.sub(r'^(please\s+)?(can\s+you\s+)?(help\s+me\s+)?(to\s+)?', '', cleaned, flags=re.IGNORECASE)
    words = cleaned.split()
    if not words:
        return "New Chat"
    title_words = words[:6]
    title = " ".join(title_words)
    if len(words) > 6:
        title += "..."
    # Capitalize first character
    return title[0].upper() + title[1:] if len(title) > 1 else title.upper()

def create_conversation(db: Session, user_id: uuid.UUID, title: Optional[str] = None) -> Conversation:
    """Creates a new conversation record for the authenticated user."""
    now = datetime.now(timezone.utc)
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title or "New Chat",
        is_archived=False,
        created_at=now,
        updated_at=now
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

def get_conversation_for_user(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_limit: int = 100,
    message_offset: int = 0
) -> Optional[Conversation]:
    """Retrieves conversation and chronological messages scoped strictly to user."""
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if not conv:
        return None

    # Load messages chronologically
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.user_id == user_id)
        .order_by(Message.created_at.asc())
        .offset(message_offset)
        .limit(message_limit)
    ).all()
    conv.messages = list(messages)
    return conv

def list_conversations_for_user(
    db: Session,
    user_id: uuid.UUID,
    search: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0
) -> List[dict]:
    """Returns list of conversations with message counts and previews."""
    query = select(Conversation).where(Conversation.user_id == user_id)

    if not include_archived:
        query = query.where(Conversation.is_archived == False)

    if search and search.strip():
        term = f"%{search.strip()}%"
        # Search either conversation title or message content within user conversations
        subquery_msgs = (
            select(Message.conversation_id)
            .where(Message.user_id == user_id, Message.content.ilike(term))
            .scalar_subquery()
        )
        query = query.where(
            or_(
                Conversation.title.ilike(term),
                Conversation.id.in_(subquery_msgs)
            )
        )

    query = query.order_by(desc(Conversation.updated_at)).offset(offset).limit(limit)
    conversations = db.scalars(query).all()

    results = []
    for c in conversations:
        # Count messages and get last message preview
        msg_count = db.scalar(
            select(func.count(Message.id)).where(Message.conversation_id == c.id)
        ) or 0
        last_msg = db.scalar(
            select(Message.content)
            .where(Message.conversation_id == c.id)
            .order_by(desc(Message.created_at))
            .limit(1)
        )
        preview = (last_msg[:80] + "...") if last_msg and len(last_msg) > 80 else last_msg
        results.append({
            "id": c.id,
            "title": c.title,
            "is_archived": c.is_archived,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "message_count": msg_count,
            "last_message_preview": preview
        })
    return results

def add_message(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    metadata: Optional[dict] = None
) -> Message:
    """Appends a message to the conversation and updates conversation timestamp."""
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if not conv:
        raise ValueError("Conversation not found or access denied.")

    now = datetime.now(timezone.utc)

    # If first user message, generate smart title if default
    if role == "user" and (conv.title == "New Chat" or not conv.title):
        conv.title = generate_smart_title(content)

    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        user_id=user_id,
        role=role,
        content=content,
        metadata_json=json.dumps(metadata) if metadata else None,
        created_at=now
    )
    db.add(msg)
    conv.updated_at = now
    db.commit()
    db.refresh(msg)
    return msg

def update_conversation(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    title: Optional[str] = None,
    is_archived: Optional[bool] = None
) -> Optional[Conversation]:
    """Updates title or archive status."""
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if not conv:
        return None

    if title is not None:
        conv.title = title.strip() or "Untitled Chat"
    if is_archived is not None:
        conv.is_archived = is_archived

    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conv)
    return conv

def delete_conversation(db: Session, user_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
    """Deletes conversation and all cascading messages."""
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if not conv:
        return False
    db.delete(conv)
    db.commit()
    return True
