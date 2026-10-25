import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from models import User
from routes.auth import get_current_user, get_optional_user
from services import chat_service, auth_service

router = APIRouter(prefix="/api/chat", tags=["Chat & RAG"])

class ChatTurnRequest(BaseModel):
    message: str
    conversation_id: Optional[uuid.UUID] = None
    document_ids: Optional[List[uuid.UUID]] = None

class ChatTurnResponse(BaseModel):
    conversation_id: str
    title: str
    response: str
    sources: List[Dict[str, Any]] = []
    memories: List[str] = []

@router.post("", response_model=ChatTurnResponse)
def chat_turn(
    payload: ChatTurnRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Unified chat endpoint integrating RAG, long-term memory, and conversation persistence.
    If running locally without auth, falls back gracefully to a default local profile.
    """
    if not current_user:
        # Auto-create or obtain local guest/offline user profile
        current_user = auth_service.get_or_create_user(
            db=db,
            google_sub="local_guest_offline_sub",
            email="local_user@ghostmind.local",
            display_name="GHOSTMIND User"
        )

    try:
        result = chat_service.execute_chat_turn(
            db=db,
            user=current_user,
            message=payload.message,
            conversation_id=payload.conversation_id,
            document_ids=payload.document_ids
        )
        return ChatTurnResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {e}")
