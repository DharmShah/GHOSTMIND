import logging
from typing import List, Dict, Optional
from mcp.models import MCPCatalogItem, TransportType, MCPServerSpec
from mcp.security import validate_stdio_command, validate_remote_url

logger = logging.getLogger("ghostmind.mcp.registry")

TRUSTED_CATALOG: Dict[str, MCPCatalogItem] = {
    "github": MCPCatalogItem(
        id="github",
        name="github",
        display_name="GitHub",
        description="Search repositories, read source code, inspect commits, create issues, and manage pull requests.",
        publisher="Model Context Protocol Official",
        category="developer",
        icon="github",
        transport=TransportType.STDIO,
        default_command="npx",
        default_args=["-y", "@modelcontextprotocol/server-github"],
        auth_provider="github",
        requested_scopes=["repo", "read:user"],
        read_only_tools=["search_repositories", "get_file_contents", "list_issues", "search_issues", "get_issue"],
        write_tools=["create_issue", "update_issue", "create_pull_request", "create_or_update_file", "fork_repository"],
        is_official=True
    ),
    "figma": MCPCatalogItem(
        id="figma",
        name="figma",
        display_name="Figma",
        description="Inspect Figma design files, components, styles, design tokens, and review comment threads.",
        publisher="Figma Official",
        category="design",
        icon="figma",
        transport=TransportType.STDIO,
        default_command="npx",
        default_args=["-y", "figma-developer-mcp"],
        auth_provider="figma",
        requested_scopes=["file_read", "comments:read", "comments:write"],
        read_only_tools=["get_file", "get_comments", "get_image", "get_components", "get_styles"],
        write_tools=["post_comment", "delete_comment"],
        is_official=True
    ),
    "slack": MCPCatalogItem(
        id="slack",
        name="slack",
        display_name="Slack",
        description="Query workspace channels, read team conversations, search message history, and post messages.",
        publisher="Model Context Protocol Official",
        category="communication",
        icon="slack",
        transport=TransportType.STDIO,
        default_command="npx",
        default_args=["-y", "@modelcontextprotocol/server-slack"],
        auth_provider="slack",
        requested_scopes=["channels:read", "channels:history", "chat:write"],
        read_only_tools=["list_channels", "get_channel_history", "get_thread_replies", "search_messages"],
        write_tools=["post_message", "add_reaction", "post_reply"],
        is_official=True
    ),
    "notion": MCPCatalogItem(
        id="notion",
        name="notion",
        display_name="Notion",
        description="Search workspace databases, read documents and meeting notes, and create structured pages.",
        publisher="Notion Labs",
        category="productivity",
        icon="notion",
        transport=TransportType.STDIO,
        default_command="npx",
        default_args=["-y", "@modelcontextprotocol/server-notion"],
        auth_provider="notion",
        requested_scopes=["read", "write"],
        read_only_tools=["search_pages", "get_page", "query_database", "get_block_children"],
        write_tools=["create_page", "update_page", "append_block_children"],
        is_official=True
    ),
    "google-workspace": MCPCatalogItem(
        id="google-workspace",
        name="google-workspace",
        display_name="Google Workspace (Gmail, Calendar, Drive)",
        description="Read & send Gmail emails, schedule Google Calendar events, and search Google Drive cloud files.",
        publisher="Google Workspace Verified",
        category="productivity",
        icon="google",
        transport=TransportType.STDIO,
        default_command="python",
        default_args=["-m", "mcp.servers.google_workspace_server"],
        auth_provider="google",
        requested_scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/drive.readonly"
        ],
        read_only_tools=["search_emails", "get_email", "list_calendar_events", "list_drive_files", "get_drive_file"],
        write_tools=["send_email", "create_calendar_event", "delete_calendar_event", "upload_drive_file"],
        is_official=True
    )
}

# Alias map for natural-language resolution
SERVICE_ALIASES: Dict[str, str] = {
    "github": "github",
    "git": "github",
    "figma": "figma",
    "slack": "slack",
    "notion": "notion",
    "google": "google-workspace",
    "gmail": "google-workspace",
    "google mail": "google-workspace",
    "google calendar": "google-workspace",
    "calendar": "google-workspace",
    "google drive": "google-workspace",
    "drive": "google-workspace",
    "gdrive": "google-workspace",
    "workspace": "google-workspace"
}

class MCPRegistry:
    """Manages the catalog of trusted MCP servers and validates server registrations."""

    def __init__(self):
        self._catalog = dict(TRUSTED_CATALOG)

    def list_catalog(self) -> List[MCPCatalogItem]:
        """Returns all available trusted catalog integrations."""
        return list(self._catalog.values())

    def get_catalog_item(self, item_id: str) -> Optional[MCPCatalogItem]:
        """Looks up a catalog item by ID or common alias."""
        clean_id = item_id.strip().lower()
        target_id = SERVICE_ALIASES.get(clean_id, clean_id)
        return self._catalog.get(target_id)

    def search_catalog(self, query: str) -> List[MCPCatalogItem]:
        """Fuzzy matches query against catalog names, keywords, and descriptions."""
        q = query.strip().lower()
        if not q:
            return self.list_catalog()

        # Check aliases first
        if q in SERVICE_ALIASES:
            item = self._catalog.get(SERVICE_ALIASES[q])
            if item:
                return [item]

        results = []
        for item in self._catalog.values():
            if (
                q in item.name.lower()
                or q in item.display_name.lower()
                or q in item.description.lower()
                or q in item.publisher.lower()
                or q in item.category.lower()
            ):
                results.append(item)
        return results

    def validate_server_spec(self, spec: MCPServerSpec) -> bool:
        """Validates security, command arguments, and network endpoints."""
        if spec.transport == TransportType.STDIO:
            if not spec.command:
                raise ValueError("Command is required for stdio transport")
            if not validate_stdio_command(spec.command, spec.args):
                raise ValueError(f"Command or arguments failed security validation: {spec.command}")
        elif spec.transport in (TransportType.SSE, TransportType.HTTP):
            if not spec.url:
                raise ValueError("URL is required for HTTP/SSE transport")
            if not validate_remote_url(spec.url, allow_local_dev=True):
                raise ValueError(f"Remote URL failed security validation: {spec.url}")
        return True


registry = MCPRegistry()

