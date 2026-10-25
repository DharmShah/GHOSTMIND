import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from models import User
from routes.auth import get_optional_user
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
    response: Response,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Unified chat endpoint integrating RAG, long-term memory, and conversation persistence.
    If running locally without auth, establishes a local session and persists conversation.
    """
    if not current_user:
        current_user = auth_service.get_or_create_user(
            db=db,
            google_sub="local_guest_offline_sub",
            email="local_user@ghostmind.local",
            display_name="GHOSTMIND User"
        )
        # Establish session cookie so conversations persist and load into sidebar
        raw_session_token = auth_service.create_session(db, current_user.id)
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=raw_session_token,
            max_age=settings.SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/"
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
