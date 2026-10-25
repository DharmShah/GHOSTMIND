import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from models import User
from routes.auth import get_current_user
from schemas.memory import MemorySchema, CreateMemoryRequest, UpdateMemoryRequest
from services import memory_service

router = APIRouter(prefix="/api/memories", tags=["Personalized Memory"])

@router.get("", response_model=List[MemorySchema])
def list_user_memories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieves all saved long-term memories for the authenticated user."""
    return memory_service.list_memories_for_user(db=db, user_id=current_user.id)

@router.post("", response_model=MemorySchema, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: CreateMemoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Adds a manual long-term memory."""
    try:
        mem = memory_service.add_memory(
            db=db,
            user_id=current_user.id,
            memory_text=payload.memory_text,
            category=payload.category or "project_context",
            source_conversation_id=payload.source_conversation_id
        )
        return mem
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{memory_id}", response_model=MemorySchema)
def update_memory(
    memory_id: uuid.UUID,
    payload: UpdateMemoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Updates memory text or toggles active state."""
    mem = memory_service.update_memory(
        db=db,
        user_id=current_user.id,
        memory_id=memory_id,
        memory_text=payload.memory_text,
        category=payload.category,
        is_active=payload.is_active
    )
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found or access denied.")
    return mem

@router.delete("/{memory_id}")
def delete_memory(
    memory_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deletes a long-term memory permanently."""
    success = memory_service.delete_memory(
        db=db,
        user_id=current_user.id,
        memory_id=memory_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or access denied.")
    return {"message": "Memory deleted successfully."}
