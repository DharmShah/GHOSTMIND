import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.user import get_local_user
from models import User
from mcp.models import MCPServerSpec, TransportType, ToolExecutionRequest
from mcp.manager import mcp_manager

router = APIRouter(prefix="/api/mcp", tags=["MCP Server Management"])

class CustomServerRequest(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = ""
    transport: str = "stdio"
    command: Optional[str] = None
    args: Optional[List[str]] = []
    env: Optional[Dict[str, str]] = {}
    url: Optional[str] = None

class DirectToolExecuteRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: Optional[Dict[str, Any]] = {}
    conversation_id: Optional[str] = None

@router.get("/servers")
def list_servers(
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Lists registered MCP servers and connection states."""
    from services.integration_service import integration_service
    return integration_service.list_connected_integrations(db, current_user.id)

@router.post("/servers")
async def register_custom_server(
    payload: CustomServerRequest,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Registers and connects a custom user-defined MCP server."""
    try:
        spec = MCPServerSpec(
            name=payload.name.strip().lower(),
            display_name=payload.display_name,
            description=payload.description or "",
            transport=TransportType(payload.transport.lower()),
            command=payload.command,
            args=payload.args or [],
            env=payload.env or {},
            url=payload.url,
            is_enabled=True
        )
        saved_spec = await mcp_manager.connect_custom_server(spec, current_user.id, db)
        tools = mcp_manager.connection_manager.get_tools_for_server(saved_spec.name)
        return {
            "success": True,
            "name": saved_spec.name,
            "display_name": saved_spec.display_name,
            "tool_count": len(tools),
            "status": "connected"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register MCP server: {e}")

@router.post("/servers/{server_name}/connect")
async def connect_server(
    server_name: str,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Connects an established server configuration."""
    from services.integration_service import integration_service
    try:
        return await integration_service.connect_integration(db, current_user.id, server_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/servers/{server_name}/disconnect")
async def disconnect_server(
    server_name: str,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Disconnects an active MCP server."""
    from services.integration_service import integration_service
    try:
        return await integration_service.disconnect_integration(db, current_user.id, server_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/servers/{server_name}/tools")
def get_tools_for_server(
    server_name: str,
    current_user: User = Depends(get_local_user)
):
    """Returns all discovered tools for a server."""
    tools = mcp_manager.connection_manager.get_tools_for_server(server_name)
    return [
        {
            "name": t.name,
            "description": t.description,
            "classification": t.classification.value,
            "requires_confirmation": t.requires_confirmation,
            "input_schema": t.input_schema
        }
        for t in tools
    ]

@router.post("/tools/execute")
async def execute_tool(
    payload: DirectToolExecuteRequest,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Executes a tool with strict read-only / write action confirmation enforcement."""
    req = ToolExecutionRequest(
        server_name=payload.server_name,
        tool_name=payload.tool_name,
        arguments=payload.arguments or {},
        conversation_id=payload.conversation_id
    )
    result = await mcp_manager.execute_tool(req, current_user.id, db)
    return {
        "success": result.success,
        "requires_confirmation": result.requires_confirmation,
        "pending_action_id": result.pending_action_id,
        "data": result.data,
        "error": result.error
    }

