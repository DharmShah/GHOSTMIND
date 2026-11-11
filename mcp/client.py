import logging
from typing import List, Dict, Any, Optional
from mcp.models import MCPToolDefinition, ActionClassification, MCPServerSpec, TransportType
from mcp.transports import BaseTransport, StdioTransport, HttpSseTransport

logger = logging.getLogger("ghostmind.mcp.client")

# Conventional prefixes for read-only actions
READ_ONLY_PREFIXES = (
    "get_", "list_", "read_", "search_", "fetch_", "find_", "query_",
    "inspect_", "show_", "check_", "view_", "download_"
)

class MCPClient:
    """
    Standard Model Context Protocol client managing protocol handshakes,
    dynamic tool discovery, and remote execution.
    """

    def __init__(self, spec: MCPServerSpec, transport: Optional[BaseTransport] = None):
        self.spec = spec
        self.transport = transport or self._create_transport(spec)
        self.server_info: Dict[str, Any] = {}
        self.tools: List[MCPToolDefinition] = []
        self._is_initialized = False

    def _create_transport(self, spec: MCPServerSpec) -> BaseTransport:
        if spec.transport == TransportType.STDIO:
            if not spec.command:
                raise ValueError(f"Stdio transport requires a command for server '{spec.name}'")
            return StdioTransport(
                command=spec.command,
                args=spec.args,
                env=spec.env
            )
        elif spec.transport in (TransportType.SSE, TransportType.HTTP):
            if not spec.url:
                raise ValueError(f"HTTP/SSE transport requires a URL for server '{spec.name}'")
            headers = {}
            if "BEARER_TOKEN" in spec.env:
                headers["Authorization"] = f"Bearer {spec.env['BEARER_TOKEN']}"
            return HttpSseTransport(url=spec.url, headers=headers)
        else:
            raise ValueError(f"Unsupported transport type: {spec.transport}")

    async def connect(self) -> None:
        """Starts transport and conducts MCP initialization handshake."""
        if self._is_initialized:
            return

        await self.transport.start()

        # 1. Send initialize request
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "clientInfo": {
                "name": "ghostmind",
                "version": "1.0.0"
            }
        }
        resp = await self.transport.send_request("initialize", init_params, timeout=20.0)
        self.server_info = resp.get("serverInfo", {})

        # 2. Send initialized notification
        await self.transport.send_notification("notifications/initialized")
        self._is_initialized = True
        logger.info(f"Connected and initialized MCP server: {self.spec.name}")

        # 3. Discover available tools
        await self.refresh_tools()

    async def refresh_tools(self) -> List[MCPToolDefinition]:
        """Queries the server for registered tools and updates the local cache."""
        if not self._is_initialized:
            await self.connect()

        resp = await self.transport.send_request("tools/list", {}, timeout=20.0)
        raw_tools = resp.get("tools", [])

        discovered: List[MCPToolDefinition] = []
        for t in raw_tools:
            name = t.get("name", "")
            desc = t.get("description", "")
            schema = t.get("inputSchema", {})

            # Determine read-only vs write classification
            classification = ActionClassification.READ_ONLY
            low_name = name.lower()
            if not any(low_name.startswith(p) for p in READ_ONLY_PREFIXES):
                classification = ActionClassification.WRITE

            requires_confirm = (classification == ActionClassification.WRITE)

            tool_def = MCPToolDefinition(
                name=name,
                description=desc,
                input_schema=schema,
                server_name=self.spec.name,
                classification=classification,
                requires_confirmation=requires_confirm
            )
            discovered.append(tool_def)

        self.tools = discovered
        logger.info(f"Discovered {len(self.tools)} tools for server '{self.spec.name}'")
        return self.tools

    async def call_tool(self, name: str, arguments: Dict[str, Any], timeout: float = 30.0) -> Any:
        """Executes a tool on the MCP server and returns the parsed result."""
        if not self._is_initialized:
            await self.connect()

        params = {
            "name": name,
            "arguments": arguments
        }
        resp = await self.transport.send_request("tools/call", params, timeout=timeout)
        content_items = resp.get("content", [])

        # Extract text or structured data
        results = []
        for item in content_items:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    results.append(item.get("text", ""))
                elif item.get("type") == "resource":
                    results.append(str(item.get("resource", "")))
            elif isinstance(item, str):
                results.append(item)

        if not results:
            return resp

        if len(results) == 1:
            return results[0]
        return "\n".join(results)

    async def disconnect(self) -> None:
        """Gracefully disconnects and stops transport."""
        self._is_initialized = False
        await self.transport.stop()
        logger.info(f"Disconnected MCP server: {self.spec.name}")

    def is_connected(self) -> bool:
        return self._is_initialized and self.transport.is_alive()

