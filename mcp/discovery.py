import re
from typing import Optional, Dict, Any
from mcp.registry import registry, SERVICE_ALIASES
from mcp.models import MCPCatalogItem

CONNECT_PATTERNS = [
    r'^(?:please\s+)?connect(?:\s+to)?\s+([a-zA-Z0-9_\-\s]+)',
    r'^(?:please\s+)?integrate(?:\s+with)?\s+([a-zA-Z0-9_\-\s]+)',
    r'^(?:please\s+)?link(?:\s+to)?\s+([a-zA-Z0-9_\-\s]+)',
    r'^(?:please\s+)?add(?:\s+the)?\s+([a-zA-Z0-9_\-\s]+)(?:\s+integration|\s+mcp|\s+service)?',
    r'^(?:how\s+do\s+i\s+)?connect\s+([a-zA-Z0-9_\-\s]+)',
    r'^setup\s+([a-zA-Z0-9_\-\s]+)'
]

DISCONNECT_PATTERNS = [
    r'^(?:please\s+)?disconnect(?:\s+from)?\s+([a-zA-Z0-9_\-\s]+)',
    r'^(?:please\s+)?unlink\s+([a-zA-Z0-9_\-\s]+)',
    r'^(?:please\s+)?remove(?:\s+the)?\s+([a-zA-Z0-9_\-\s]+)(?:\s+integration|\s+mcp|\s+service)?'
]

def detect_integration_intent(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Parses natural language prompts to detect integration connection or disconnection intents.
    Returns matched catalog item or candidate service name.
    """
    cleaned = prompt.strip().lower()

    # 1. Check disconnect intent
    for pattern in DISCONNECT_PATTERNS:
        match = re.search(pattern, cleaned)
        if match:
            target = match.group(1).strip()
            item = registry.get_catalog_item(target)
            return {
                "action": "disconnect",
                "target_raw": target,
                "catalog_item": item,
                "service_id": item.id if item else target
            }

    # 2. Check connect intent
    for pattern in CONNECT_PATTERNS:
        match = re.search(pattern, cleaned)
        if match:
            target = match.group(1).strip()
            # Clean trailing words like "mcp", "integration", "app", "service"
            target = re.sub(r'\s+(mcp|integration|app|server|account|service)$', '', target).strip()
            item = registry.get_catalog_item(target)
            return {
                "action": "connect",
                "target_raw": target,
                "catalog_item": item,
                "service_id": item.id if item else target
            }

    return None


def format_discovery_message(catalog_item: MCPCatalogItem, is_connected: bool = False) -> str:
    """Formats an interactive natural language response card for the requested integration."""
    if is_connected:
        return (
            f"**{catalog_item.display_name}** is already connected and active on your system.\n\n"
            f"• **Publisher:** {catalog_item.publisher}\n"
            f"• **Category:** {catalog_item.category.capitalize()}\n"
            f"• **Tools Available:** {len(catalog_item.read_only_tools) + len(catalog_item.write_tools)} registered tools\n\n"
            f"You can ask me to run queries (e.g., search or inspect items), or disconnect it anytime from the Connected Services sidebar."
        )

    scopes_list = ", ".join(f"`{s}`" for s in catalog_item.requested_scopes) if catalog_item.requested_scopes else "Default API access"
    tools_preview = ", ".join(catalog_item.read_only_tools[:3] + catalog_item.write_tools[:2])

    return (
        f"### 🔌 {catalog_item.display_name} Integration Found\n\n"
        f"{catalog_item.description}\n\n"
        f"• **Publisher:** {catalog_item.publisher}\n"
        f"• **Transport:** {catalog_item.transport.value.upper()}\n"
        f"• **Authentication:** {catalog_item.auth_provider.capitalize() if catalog_item.auth_provider else 'None Required'}\n"
        f"• **Requested Permissions:** {scopes_list}\n"
        f"• **Tools Discovered upon connect:** {tools_preview}...\n\n"
        f"Would you like to authorize and connect **{catalog_item.display_name}** now?\n\n"
        f"[CONNECT_INTEGRATION_ACTION:{catalog_item.id}]"
    )
