import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from models import User
from routes.auth import get_current_user
from schemas.conversation import (
    ConversationSummarySchema,
    ConversationDetailSchema,
    CreateConversationRequest,
    UpdateConversationRequest
)
from services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

@router.get("", response_model=List[ConversationSummarySchema])
def list_conversations(
    search: Optional[str] = Query(None, description="Search term for titles or messages"),
    include_archived: bool = Query(False, description="Include archived chats"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists conversations for the authenticated user."""
    items = conversation_service.list_conversations_for_user(
        db=db,
        user_id=current_user.id,
        search=search,
        include_archived=include_archived,
        limit=limit,
        offset=offset
    )
    return items

@router.post("", response_model=ConversationDetailSchema, status_code=status.HTTP_201_CREATED)
def create_new_conversation(
    payload: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Creates a new empty conversation."""
    conv = conversation_service.create_conversation(
        db=db,
        user_id=current_user.id,
        title=payload.title
    )
    conv.messages = []
    return conv

@router.get("/{conversation_id}", response_model=ConversationDetailSchema)
def get_conversation_details(
    conversation_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Loads a conversation and its messages."""
    conv = conversation_service.get_conversation_for_user(
        db=db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        message_limit=limit,
        message_offset=offset
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")
    return conv

@router.patch("/{conversation_id}", response_model=ConversationSummarySchema)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: UpdateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Renames or archives a conversation."""
    conv = conversation_service.update_conversation(
        db=db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        title=payload.title,
        is_archived=payload.is_archived
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")
    return {
        "id": conv.id,
        "title": conv.title,
        "is_archived": conv.is_archived,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "message_count": len(conv.messages),
        "last_message_preview": None
    }

@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Permanently deletes a conversation and all its messages."""
    deleted = conversation_service.delete_conversation(
        db=db,
        user_id=current_user.id,
        conversation_id=conversation_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied.")
    return {"message": "Conversation deleted successfully."}
