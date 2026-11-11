import json
import uuid
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from mcp.models import (
    MCPServerSpec, MCPCatalogItem, MCPToolDefinition,
    ActionClassification, ToolExecutionRequest, ToolExecutionResult,
    ConnectionStatus, TransportType
)
from mcp.registry import registry
from mcp.discovery import detect_integration_intent, format_discovery_message
from mcp.tool_registry import tool_registry
from mcp.connection_manager import connection_manager

logger = logging.getLogger("ghostmind.mcp.manager")

class UniversalMCPManager:
    """
    Universal orchestrator managing the full MCP ecosystem:
    catalog discovery, server lifecycle, dynamic tool execution,
    and action confirmation interception.
    """

    def __init__(self):
        self.registry = registry
        self.tool_registry = tool_registry
        self.connection_manager = connection_manager

    def detect_intent(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Scans prompt for natural-language service integration triggers."""
        return detect_integration_intent(prompt)

    def format_discovery_response(self, catalog_item: MCPCatalogItem, is_connected: bool = False) -> str:
        """Formats the chat response card for an integration discovery."""
        return format_discovery_message(catalog_item, is_connected=is_connected)

    def list_catalog(self) -> List[MCPCatalogItem]:
        """Returns all official and trusted catalog integrations."""
        return self.registry.list_catalog()

    def get_catalog_item(self, item_id: str) -> Optional[MCPCatalogItem]:
        return self.registry.get_catalog_item(item_id)

    def ensure_tools_loaded(self, user_id: uuid.UUID, db: Session) -> None:
        """
        Ensures all enabled MCP servers and their discovered tools for the user
        are loaded from PostgreSQL into the in-memory tool_registry and connection_manager.
        """
        from models import MCPServerConfig
        configs = db.query(MCPServerConfig).filter(
            MCPServerConfig.user_id == user_id,
            MCPServerConfig.is_enabled == True,
            MCPServerConfig.status == "connected"
        ).all()

        for cfg in configs:
            # 1. Register spec in connection_manager
            if cfg.name not in self.connection_manager._specs:
                try:
                    args = json.loads(cfg.args_json) if cfg.args_json else []
                except Exception:
                    args = []

                # Inject auth tokens if available
                from services.credential_service import credential_service
                from services.integration_service import ENV_TOKEN_MAP
                creds = credential_service.get_decrypted_credentials(db, user_id, cfg.name)
                auth_env = {}
                if creds and creds.get("access_token"):
                    env_name = ENV_TOKEN_MAP.get(cfg.name.lower(), "ACCESS_TOKEN")
                    auth_env[env_name] = creds["access_token"]
                    auth_env["BEARER_TOKEN"] = creds["access_token"]

                spec = MCPServerSpec(
                    name=cfg.name,
                    display_name=cfg.display_name or cfg.name,
                    description=cfg.description or "",
                    transport=TransportType(cfg.transport),
                    command=cfg.command,
                    args=args,
                    env=auth_env,
                    url=cfg.url,
                    is_enabled=True,
                    status=ConnectionStatus.CONNECTED
                )
                self.connection_manager.register_spec(spec)

            # 2. Populate tool_registry from cached tools
            if cfg.tools_cache_json:
                try:
                    cached_tools = json.loads(cfg.tools_cache_json)
                    tool_defs = [
                        MCPToolDefinition(
                            name=t["name"],
                            description=t.get("description", ""),
                            input_schema=t.get("input_schema", {}),
                            server_name=cfg.name,
                            classification=ActionClassification(t.get("classification", "read_only")),
                            requires_confirmation=(t.get("classification") == "write")
                        )
                        for t in cached_tools
                    ]
                    self.tool_registry.register_tools(cfg.name, tool_defs)
                except Exception as e:
                    logger.warning(f"Error loading cached tools for '{cfg.name}': {e}")

    async def connect_catalog_service(
        self,
        service_id: str,
        user_id: uuid.UUID,
        db: Session,
        auth_env: Optional[Dict[str, str]] = None
    ) -> MCPServerSpec:
        """
        Connects an official catalog service for the user, persists the configuration,
        and initializes the MCP connection to discover tools.
        """
        item = self.registry.get_catalog_item(service_id)
        if not item:
            raise ValueError(f"Unknown catalog service: '{service_id}'")

        spec = MCPServerSpec(
            name=item.name,
            display_name=item.display_name,
            description=item.description,
            transport=item.transport,
            command=item.default_command,
            args=item.default_args,
            env=auth_env or {},
            url=item.default_url,
            auth_provider=item.auth_provider,
            required_scopes=item.requested_scopes,
            is_enabled=True
        )

        # Validate spec
        self.registry.validate_server_spec(spec)

        # Register in connection manager and connect
        self.connection_manager.register_spec(spec)
        client = await self.connection_manager.get_or_connect(spec.name)

        # Sync with database
        self._persist_server_config(db, user_id, spec, client.tools)
        return spec

    async def connect_custom_server(
        self,
        spec: MCPServerSpec,
        user_id: uuid.UUID,
        db: Session
    ) -> MCPServerSpec:
        """Validates and connects a user-supplied custom MCP server."""
        self.registry.validate_server_spec(spec)
        self.connection_manager.register_spec(spec)
        client = await self.connection_manager.get_or_connect(spec.name)
        self._persist_server_config(db, user_id, spec, client.tools)
        return spec

    async def disconnect_server(self, server_name: str, user_id: uuid.UUID, db: Session) -> None:
        """Disconnects an active server and marks it as disconnected in PostgreSQL."""
        await self.connection_manager.disconnect(server_name)

        # Update database record
        from models import MCPServerConfig
        server_record = db.query(MCPServerConfig).filter(
            MCPServerConfig.user_id == user_id,
            MCPServerConfig.name == server_name
        ).first()

        if server_record:
            server_record.status = "disconnected"
            db.commit()

    def _persist_server_config(
        self,
        db: Session,
        user_id: uuid.UUID,
        spec: MCPServerSpec,
        tools: List[MCPToolDefinition]
    ) -> None:
        """Saves or updates MCPServerConfig in PostgreSQL."""
        from models import MCPServerConfig
        server_record = db.query(MCPServerConfig).filter(
            MCPServerConfig.user_id == user_id,
            MCPServerConfig.name == spec.name
        ).first()

        tools_cache = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "classification": t.classification.value
            }
            for t in tools
        ]

        if not server_record:
            server_record = MCPServerConfig(
                user_id=user_id,
                name=spec.name,
                display_name=spec.display_name,
                description=spec.description,
                transport=spec.transport.value,
                command=spec.command,
                args_json=json.dumps(spec.args),
                env_json=json.dumps({k: "***" for k in spec.env.keys()}),
                url=spec.url,
                status="connected",
                is_enabled=True,
                tools_cache_json=json.dumps(tools_cache)
            )
            db.add(server_record)
        else:
            server_record.status = "connected"
            server_record.tools_cache_json = json.dumps(tools_cache)

        db.commit()

    async def execute_tool(
        self,
        request: ToolExecutionRequest,
        user_id: uuid.UUID,
        db: Session
    ) -> ToolExecutionResult:
        """
        Executes a requested tool:
        - If READ_ONLY: Executes immediately via MCP client.
        - If WRITE / ACTION: Intercepts and creates a PendingAction for explicit confirmation!
        """
        tool = self.tool_registry.get_tool(request.server_name, request.tool_name)
        if not tool:
            # Try reloading tools from database cache in case server was restarted
            self.ensure_tools_loaded(user_id, db)
            tool = self.tool_registry.get_tool(request.server_name, request.tool_name)
        if not tool:
            # Fallback search across servers
            tool = self.tool_registry.find_tool(request.tool_name, candidate_server=request.server_name)

        if not tool:
            return ToolExecutionResult(
                success=False,
                error=f"Tool '{request.tool_name}' not found on server '{request.server_name}'"
            )

        # Enforce Mandatory Action Confirmation for write operations
        if tool.classification == ActionClassification.WRITE or tool.requires_confirmation:
            from services.action_confirmation_service import action_confirmation_service
            pending_action = action_confirmation_service.create_pending_action(
                db=db,
                user_id=user_id,
                server_name=request.server_name,
                tool_name=request.tool_name,
                arguments=request.arguments,
                conversation_id=uuid.UUID(request.conversation_id) if request.conversation_id else None
            )
            return ToolExecutionResult(
                success=True,
                requires_confirmation=True,
                pending_action_id=str(pending_action.id),
                data={
                    "pending_action_id": str(pending_action.id),
                    "action_title": pending_action.title,
                    "server_name": request.server_name,
                    "tool_name": request.tool_name,
                    "arguments": request.arguments
                }
            )

        # Execute read-only tool directly
        try:
            client = await self.connection_manager.get_or_connect(request.server_name)
            result_data = await client.call_tool(request.tool_name, request.arguments)
            return ToolExecutionResult(
                success=True,
                data=result_data
            )
        except Exception as e:
            logger.error(f"Error executing tool '{request.tool_name}': {e}")
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


mcp_manager = UniversalMCPManager()

