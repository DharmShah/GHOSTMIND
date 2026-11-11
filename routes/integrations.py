import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.user import get_local_user
from models import User
from services.integration_service import integration_service
from mcp.manager import mcp_manager

router = APIRouter(prefix="/api/integrations", tags=["MCP Integrations & Ecosystem"])

class ConnectRequest(BaseModel):
    service_id: str
    token: Optional[str] = None

class DiscoverRequest(BaseModel):
    query: str

@router.get("")
def list_connected_integrations(
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Lists all registered MCP services and their live connection status for the local user."""
    return integration_service.list_connected_integrations(db, current_user.id)

@router.get("/catalog")
def get_catalog():
    """Returns the trusted catalog of official and verified MCP integrations."""
    items = mcp_manager.list_catalog()
    return [
        {
            "id": i.id,
            "name": i.name,
            "display_name": i.display_name,
            "description": i.description,
            "publisher": i.publisher,
            "category": i.category,
            "icon": i.icon,
            "transport": i.transport.value,
            "auth_provider": i.auth_provider,
            "requested_scopes": i.requested_scopes,
            "is_official": i.is_official,
            "read_only_tools": i.read_only_tools,
            "write_tools": i.write_tools
        }
        for i in items
    ]

@router.post("/discover")
def discover_integration_intent(
    payload: DiscoverRequest,
    current_user: User = Depends(get_local_user)
):
    """Parses natural-language queries (e.g. 'Connect Figma') and returns matched integration cards."""
    intent_data = mcp_manager.detect_intent(payload.query)
    if not intent_data or not intent_data.get("catalog_item"):
        # Fuzzy search catalog as fallback
        search_matches = mcp_manager.registry.search_catalog(payload.query)
        if search_matches:
            item = search_matches[0]
            return {
                "matched": True,
                "action": "connect",
                "service_id": item.id,
                "display_name": item.display_name,
                "card_message": mcp_manager.format_discovery_response(item)
            }
        return {
            "matched": False,
            "message": f"No supported MCP integration found for '{payload.query}'."
        }

    catalog_item = intent_data["catalog_item"]
    return {
        "matched": True,
        "action": intent_data.get("action", "connect"),
        "service_id": catalog_item.id,
        "display_name": catalog_item.display_name,
        "card_message": mcp_manager.format_discovery_response(catalog_item)
    }

@router.post("/connect")
async def connect_integration(
    payload: ConnectRequest,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Initializes and connects an MCP service from the catalog."""
    try:
        result = await integration_service.connect_integration(
            db=db,
            user_id=current_user.id,
            service_id=payload.service_id,
            custom_token=payload.token
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect integration: {e}")

@router.delete("/{server_name}")
async def disconnect_integration(
    server_name: str,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Disconnects an active MCP server and revokes credentials."""
    try:
        return await integration_service.disconnect_integration(db, current_user.id, server_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to disconnect: {e}")

@router.get("/{server_name}/tools")
def get_server_tools(
    server_name: str,
    current_user: User = Depends(get_local_user)
):
    """Lists all dynamically discovered tools for a connected server."""
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

