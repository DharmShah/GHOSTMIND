import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from models import PendingAction

logger = logging.getLogger("ghostmind.services.action_confirmation")

def utc_now():
    return datetime.now(timezone.utc)

# Human-readable title mapping for write actions
ACTION_TITLE_MAP = {
    "send_email": "Send Email",
    "create_draft": "Create Email Draft",
    "create_calendar_event": "Schedule Calendar Event",
    "delete_calendar_event": "Delete Calendar Event",
    "create_issue": "Create GitHub Issue",
    "create_pull_request": "Open Pull Request",
    "create_or_update_file": "Commit File to GitHub",
    "post_message": "Post Slack Message",
    "add_reaction": "Add Slack Reaction",
    "post_comment": "Post Figma Comment",
    "delete_comment": "Delete Figma Comment",
    "create_page": "Create Notion Page",
    "update_page": "Update Notion Page",
    "upload_drive_file": "Upload File to Google Drive"
}

class ActionConfirmationService:
    """
    Centralized Action Permission and Confirmation Engine.
    Prevents unauthorized LLM writes, mutations, or external transmissions.
    Guarantees user-driven execution with idempotency and audit logs.
    """

    def create_pending_action(
        self,
        db: Session,
        user_id: uuid.UUID,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        conversation_id: Optional[uuid.UUID] = None,
        expiration_minutes: int = 15
    ) -> PendingAction:
        """Creates a new pending action requiring explicit user confirmation."""
        clean_title = ACTION_TITLE_MAP.get(
            tool_name.lower(),
            f"Execute {tool_name.replace('_', ' ').title()}"
        ) + f" via {server_name.title()}"

        description = self._generate_description(tool_name, arguments)
        expires_at = utc_now() + timedelta(minutes=expiration_minutes)

        action = PendingAction(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation_id,
            server_name=server_name,
            tool_name=tool_name,
            action_type="write",
            title=clean_title,
            description=description,
            parameters_json=json.dumps(arguments),
            status="pending",
            expires_at=expires_at
        )

        db.add(action)
        db.commit()
        db.refresh(action)

        logger.info(f"Created PendingAction {action.id}: '{clean_title}' for user {user_id}")
        return action

    def _generate_description(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Builds a human-readable summary of the action parameters."""
        parts = []
        for key, val in args.items():
            if isinstance(val, str) and len(val) > 80:
                display_val = val[:77] + "..."
            else:
                display_val = str(val)
            parts.append(f"{key.replace('_', ' ').capitalize()}: {display_val}")
        return " | ".join(parts) if parts else "No parameters supplied."

    def get_pending_action(
        self,
        db: Session,
        user_id: uuid.UUID,
        action_id: uuid.UUID
    ) -> Optional[PendingAction]:
        """Retrieves a pending action strictly scoped to the user."""
        return db.query(PendingAction).filter(
            PendingAction.id == action_id,
            PendingAction.user_id == user_id
        ).first()

    def list_pending_actions(
        self,
        db: Session,
        user_id: uuid.UUID,
        include_completed: bool = False
    ) -> List[PendingAction]:
        """Lists active pending actions for the user."""
        query = db.query(PendingAction).filter(PendingAction.user_id == user_id)
        if not include_completed:
            query = query.filter(
                PendingAction.status == "pending",
                PendingAction.expires_at > utc_now()
            )
        return query.order_by(PendingAction.created_at.desc()).all()

    async def confirm_and_execute(
        self,
        db: Session,
        user_id: uuid.UUID,
        action_id: uuid.UUID,
        override_arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes a pending action upon explicit user confirmation.
        Enforces idempotency, single-execution guarantee, and audit tracking.
        """
        action = self.get_pending_action(db, user_id, action_id)
        if not action:
            raise ValueError("Pending action not found or unauthorized.")

        # 1. Duplicate execution prevention
        if action.status == "executed":
            logger.warning(f"Duplicate execution blocked for action {action_id}")
            return {
                "success": True,
                "status": "already_executed",
                "message": "Action has already been executed.",
                "result": json.loads(action.result_json) if action.result_json else None
            }

        # 2. Expiration check
        if action.expires_at <= utc_now():
            action.status = "expired"
            db.commit()
            raise ValueError("This pending action has expired. Please make a new request.")

        # 3. Status validity
        if action.status not in ("pending", "failed"):
            raise ValueError(f"Cannot execute action with status '{action.status}'.")

        # Parse parameters
        params = json.loads(action.parameters_json)
        if override_arguments:
            params.update(override_arguments)
            action.parameters_json = json.dumps(params)

        # 4. Execute tool via MCP Connection Manager
        from mcp.connection_manager import connection_manager
        from mcp.manager import mcp_manager
        try:
            mcp_manager.ensure_tools_loaded(user_id, db)
            client = await connection_manager.get_or_connect(action.server_name)
            result = await client.call_tool(action.tool_name, params)

            action.status = "executed"
            action.executed_at = utc_now()
            action.result_json = json.dumps(result if isinstance(result, (dict, list)) else {"output": str(result)})
            action.error_message = None
            db.commit()

            logger.info(f"Successfully executed confirmed action {action_id} on {action.server_name}")
            return {
                "success": True,
                "status": "executed",
                "action_id": str(action.id),
                "title": action.title,
                "result": result
            }
        except Exception as e:
            action.status = "failed"
            action.error_message = str(e)
            db.commit()
            logger.error(f"Failed to execute confirmed action {action_id}: {e}")
            raise RuntimeError(f"Action execution failed: {e}")

    def cancel_action(
        self,
        db: Session,
        user_id: uuid.UUID,
        action_id: uuid.UUID,
        reason: Optional[str] = None
    ) -> bool:
        """Rejects and cancels a pending action."""
        action = self.get_pending_action(db, user_id, action_id)
        if not action:
            return False

        if action.status == "executed":
            raise ValueError("Cannot cancel an already executed action.")

        action.status = "cancelled"
        if reason:
            action.error_message = f"Cancelled by user: {reason}"
        db.commit()
        logger.info(f"Cancelled pending action {action_id}")
        return True


action_confirmation_service = ActionConfirmationService()

