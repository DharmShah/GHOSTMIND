import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.user import get_local_user
from models import User
from services import chat_service

router = APIRouter(prefix="/api/chat", tags=["Chat & RAG"])

class ChatTurnRequest(BaseModel):
    message: str
    conversation_id: Optional[uuid.UUID] = None
    document_ids: Optional[List[uuid.UUID]] = None
    temperature: Optional[float] = None
    enable_web_search: Optional[bool] = True
    enable_rag: Optional[bool] = True

class ChatTurnResponse(BaseModel):
    conversation_id: str
    title: str
    response: str
    sources: List[Dict[str, Any]] = []
    memories: List[str] = []

@router.post("", response_model=ChatTurnResponse)
def chat_turn(
    payload: ChatTurnRequest,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """
    Unified synchronous chat turn integrating RAG, long-term memory,
    intelligent web search, and local Qwen 2.5 3B inference.
    """
    try:
        result = chat_service.execute_chat_turn(
            db=db,
            user=current_user,
            message=payload.message,
            conversation_id=payload.conversation_id,
            document_ids=payload.document_ids,
            temperature=payload.temperature,
            enable_web_search=payload.enable_web_search if payload.enable_web_search is not None else True,
            enable_rag=payload.enable_rag if payload.enable_rag is not None else True
        )
        return ChatTurnResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {e}")

@router.post("/stream")
def chat_stream(
    payload: ChatTurnRequest,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """
    Real-time streaming chat endpoint using Server-Sent Events (SSE).
    Streams tokens as they are produced by Qwen 2.5 3B via Ollama.
    """
    try:
        stream_gen = chat_service.execute_chat_turn_stream(
            db=db,
            user=current_user,
            message=payload.message,
            conversation_id=payload.conversation_id,
            document_ids=payload.document_ids,
            temperature=payload.temperature,
            enable_web_search=payload.enable_web_search if payload.enable_web_search is not None else True,
            enable_rag=payload.enable_rag if payload.enable_rag is not None else True
        )
        return StreamingResponse(
            stream_gen,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming error: {e}")
