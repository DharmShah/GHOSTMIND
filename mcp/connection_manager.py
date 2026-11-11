import asyncio
import logging
from typing import Dict, List, Optional
from mcp.models import MCPServerSpec, ConnectionStatus, MCPToolDefinition
from mcp.client import MCPClient
from mcp.tool_registry import tool_registry

logger = logging.getLogger("ghostmind.mcp.connection_manager")

class MCPConnectionManager:
    """
    Manages active MCP client instances, connection lifecycles, and graceful shutdowns.
    Implements lazy on-demand initialization.
    """

    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._specs: Dict[str, MCPServerSpec] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, server_name: str) -> asyncio.Lock:
        if server_name not in self._locks:
            self._locks[server_name] = asyncio.Lock()
        return self._locks[server_name]

    def register_spec(self, spec: MCPServerSpec) -> None:
        """Stores a server configuration for lazy on-demand connection."""
        self._specs[spec.name] = spec

    def unregister_spec(self, server_name: str) -> None:
        """Removes a server spec."""
        self._specs.pop(server_name, None)

    async def get_or_connect(self, server_name: str) -> MCPClient:
        """Returns an active client, connecting on demand if not already connected."""
        async with self._get_lock(server_name):
            if server_name in self._clients:
                client = self._clients[server_name]
                if client.is_connected():
                    return client
                else:
                    logger.warning(f"Reconnecting stale MCP client for '{server_name}'")
                    await self._safe_disconnect(server_name)

            if server_name not in self._specs:
                raise ValueError(f"Unknown MCP server spec: '{server_name}'")

            spec = self._specs[server_name]
            client = MCPClient(spec)
            try:
                await client.connect()
                self._clients[server_name] = client
                spec.status = ConnectionStatus.CONNECTED
                spec.last_error = None

                # Register discovered tools with tool registry
                tool_registry.register_tools(server_name, client.tools)
                return client
            except Exception as e:
                spec.status = ConnectionStatus.ERROR
                spec.last_error = str(e)
                logger.error(f"Failed to connect MCP server '{server_name}': {e}")
                raise RuntimeError(f"Connection to MCP server '{server_name}' failed: {e}")

    async def _safe_disconnect(self, server_name: str) -> None:
        if server_name in self._clients:
            client = self._clients.pop(server_name)
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting '{server_name}': {e}")
            tool_registry.unregister_tools(server_name)

    async def disconnect(self, server_name: str) -> None:
        """Disconnects a specific server and updates its status."""
        async with self._get_lock(server_name):
            await self._safe_disconnect(server_name)
            if server_name in self._specs:
                self._specs[server_name].status = ConnectionStatus.DISCONNECTED

    async def disconnect_all(self) -> None:
        """Stops all running MCP client transports during application shutdown."""
        logger.info("Disconnecting all active MCP servers...")
        tasks = [self._safe_disconnect(name) for name in list(self._clients.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._clients.clear()

    def get_server_status(self, server_name: str) -> ConnectionStatus:
        if server_name in self._clients and self._clients[server_name].is_connected():
            return ConnectionStatus.CONNECTED
        if server_name in self._specs:
            return self._specs[server_name].status
        return ConnectionStatus.DISCONNECTED

    def get_connected_server_names(self) -> List[str]:
        return [
            name for name, client in self._clients.items()
            if client.is_connected()
        ]

    def get_tools_for_server(self, server_name: str) -> List[MCPToolDefinition]:
        if server_name in self._clients:
            return self._clients[server_name].tools
        return []


connection_manager = MCPConnectionManager()

