from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class TransportType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class ConnectionStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    EXPIRED = "expired"


class ActionClassification(str, Enum):
    READ_ONLY = "read_only"
    WRITE = "write"


class MCPToolDefinition(BaseModel):
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    server_name: str
    classification: ActionClassification = ActionClassification.READ_ONLY
    requires_confirmation: bool = False


class MCPServerSpec(BaseModel):
    id: Optional[str] = None
    name: str
    display_name: str
    description: str = ""
    transport: TransportType = TransportType.STDIO
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    auth_provider: Optional[str] = None
    required_scopes: List[str] = Field(default_factory=list)
    is_enabled: bool = True
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    last_error: Optional[str] = None


class MCPCatalogItem(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    publisher: str
    category: str = "productivity"
    icon: str = "plug"
    transport: TransportType = TransportType.STDIO
    default_command: Optional[str] = None
    default_args: List[str] = Field(default_factory=list)
    default_url: Optional[str] = None
    auth_provider: Optional[str] = None  # e.g., "google", "github", "figma", "slack", "notion"
    requested_scopes: List[str] = Field(default_factory=list)
    read_only_tools: List[str] = Field(default_factory=list)
    write_tools: List[str] = Field(default_factory=list)
    is_official: bool = True


class ToolExecutionRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    conversation_id: Optional[str] = None


class ToolExecutionResult(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    requires_confirmation: bool = False
    pending_action_id: Optional[str] = None

