import json
import uuid
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from models import MCPServerConfig, IntegrationCredential
from mcp.models import MCPServerSpec, MCPCatalogItem, TransportType
from mcp.registry import SERVICE_ALIASES
from mcp.manager import mcp_manager
from services.credential_service import credential_service

logger = logging.getLogger("ghostmind.services.integration")

# Map of auth environment variable names expected by official stdio servers
ENV_TOKEN_MAP = {
    "github": "GITHUB_PERSONAL_ACCESS_TOKEN",
    "figma": "FIGMA_ACCESS_TOKEN",
    "slack": "SLACK_BOT_TOKEN",
    "notion": "NOTION_API_KEY",
    "google-workspace": "GOOGLE_WORKSPACE_ACCESS_TOKEN"
}

class IntegrationService:
    """High-level service managing user integrations, server lifecycles, and tool availability."""

    def list_connected_integrations(self, db: Session, user_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Returns all registered MCP servers and their active connection states."""
        configs = db.query(MCPServerConfig).filter(MCPServerConfig.user_id == user_id).all()
        credentials = db.query(IntegrationCredential).filter(IntegrationCredential.user_id == user_id).all()
        creds_by_service: Dict[str, IntegrationCredential] = {}
        for c in credentials:
            if c.service_name:
                creds_by_service[c.service_name.lower()] = c
            if c.provider:
                creds_by_service[c.provider.lower()] = c
                alias = SERVICE_ALIASES.get(c.provider.lower())
                if alias:
                    creds_by_service[alias.lower()] = c

        results = []
        for cfg in configs:
            cred = creds_by_service.get(cfg.name.lower())
            live_status = mcp_manager.connection_manager.get_server_status(cfg.name).value

            tools_count = 0
            if cfg.tools_cache_json:
                try:
                    tools_count = len(json.loads(cfg.tools_cache_json))
                except Exception:
                    pass

            catalog_item = mcp_manager.get_catalog_item(cfg.name)

            results.append({
                "id": str(cfg.id),
                "name": cfg.name,
                "display_name": cfg.display_name,
                "description": cfg.description,
                "transport": cfg.transport,
                "status": live_status if live_status != "disconnected" else cfg.status,
                "is_enabled": cfg.is_enabled,
                "tool_count": tools_count,
                "has_credentials": cred is not None,
                "account_identifier": cred.account_identifier if cred else None,
                "icon": catalog_item.icon if catalog_item else "plug",
                "category": catalog_item.category if catalog_item else "custom",
                "publisher": catalog_item.publisher if catalog_item else "Custom MCP",
                "last_connected_at": cfg.last_connected_at.isoformat() if cfg.last_connected_at else None
            })
        return results

    async def connect_integration(
        self,
        db: Session,
        user_id: uuid.UUID,
        service_id: str,
        custom_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Connects a catalog service, injecting stored or supplied auth credentials."""
        item = mcp_manager.get_catalog_item(service_id)
        if not item:
            raise ValueError(f"Unknown service '{service_id}' in catalog.")

        auth_env: Dict[str, str] = {}

        # 1. Retrieve stored token from credential service or custom token
        token_to_use = custom_token
        if not token_to_use:
            creds = credential_service.get_decrypted_credentials(db, user_id, item.auth_provider or service_id)
            if creds:
                token_to_use = creds.get("access_token")

        if token_to_use:
            env_var_name = ENV_TOKEN_MAP.get(item.name.lower(), "ACCESS_TOKEN")
            auth_env[env_var_name] = token_to_use
            # For servers using Bearer auth
            auth_env["BEARER_TOKEN"] = token_to_use

        # If custom token was supplied directly, store it securely
        if custom_token:
            credential_service.store_credentials(
                db=db,
                user_id=user_id,
                provider=item.auth_provider or service_id,
                service_name=item.name,
                access_token=custom_token,
                scopes=item.requested_scopes
            )

        spec = await mcp_manager.connect_catalog_service(
            service_id=item.name,
            user_id=user_id,
            db=db,
            auth_env=auth_env
        )

        tools = mcp_manager.connection_manager.get_tools_for_server(spec.name)

        return {
            "success": True,
            "name": spec.name,
            "display_name": spec.display_name,
            "status": "connected",
            "tool_count": len(tools),
            "tools": [{"name": t.name, "description": t.description} for t in tools]
        }

    async def disconnect_integration(
        self,
        db: Session,
        user_id: uuid.UUID,
        server_name: str
    ) -> Dict[str, Any]:
        """Disconnects the MCP server and revokes stored credentials."""
        await mcp_manager.disconnect_server(server_name, user_id, db)
        credential_service.revoke_credentials(db, user_id, server_name)
        return {
            "success": True,
            "message": f"Integration '{server_name}' disconnected and credentials removed."
        }


integration_service = IntegrationService()

