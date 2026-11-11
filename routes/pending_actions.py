import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.user import get_local_user
from models import User
from services.action_confirmation_service import action_confirmation_service

router = APIRouter(prefix="/api/actions", tags=["Mandatory Action Confirmation"])

class ConfirmActionRequest(BaseModel):
    override_arguments: Optional[Dict[str, Any]] = None

class CancelActionRequest(BaseModel):
    reason: Optional[str] = None

@router.get("/pending")
def list_pending_actions(
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Lists active actions awaiting explicit user confirmation."""
    actions = action_confirmation_service.list_pending_actions(db, current_user.id)
    return [
        {
            "id": str(a.id),
            "server_name": a.server_name,
            "tool_name": a.tool_name,
            "title": a.title,
            "description": a.description,
            "parameters": a.parameters_json,
            "status": a.status,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        for a in actions
    ]

@router.post("/{action_id}/confirm")
async def confirm_action(
    action_id: uuid.UUID,
    payload: Optional[ConfirmActionRequest] = None,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """
    Explicit user confirmation trigger.
    Executes the pending write/external action idempotently.
    """
    try:
        overrides = payload.override_arguments if payload else None
        result = await action_confirmation_service.confirm_and_execute(
            db=db,
            user_id=current_user.id,
            action_id=action_id,
            override_arguments=overrides
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Action execution error: {e}")

@router.post("/{action_id}/cancel")
def cancel_action(
    action_id: uuid.UUID,
    payload: Optional[CancelActionRequest] = None,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Rejects and cancels a pending action."""
    try:
        reason = payload.reason if payload else None
        success = action_confirmation_service.cancel_action(
            db=db,
            user_id=current_user.id,
            action_id=action_id,
            reason=reason
        )
        if not success:
            raise HTTPException(status_code=404, detail="Pending action not found.")
        return {"success": True, "message": "Action cancelled by user."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

