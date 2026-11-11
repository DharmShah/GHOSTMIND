import os
import uuid
import json
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from core.database import SessionLocal, init_db
from core.user import get_local_user, LOCAL_USER_ID
from models import User, IntegrationCredential, MCPServerConfig, PendingAction
from mcp.models import (
    TransportType,
    ConnectionStatus,
    ActionClassification,
    MCPToolDefinition,
    MCPServerSpec,
    ToolExecutionRequest
)
from mcp.security import (
    encrypt_secret,
    decrypt_secret,
    validate_remote_url,
    validate_stdio_command
)
from mcp.client import READ_ONLY_PREFIXES
from mcp.registry import registry
from mcp.discovery import detect_integration_intent, format_discovery_message
from mcp.tool_registry import MCPToolRegistry
from mcp.manager import UniversalMCPManager
from services.credential_service import credential_service
from services.oauth_service import oauth_manager, PROVIDER_ADAPTERS
from services.action_confirmation_service import action_confirmation_service
from services.integration_service import integration_service


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Ensure database tables are initialized."""
    init_db()


@pytest.fixture
def db():
    """Provide a database session per test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    """Provide FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def local_user(db: Session):
    """Ensure local user exists."""
    return get_local_user(db)


# =====================================================================
# 1. Credential Encryption & Decryption (Fernet + PBKDF2)
# =====================================================================

def test_credential_encryption_roundtrip():
    """Tests that token encryption and decryption preserves plaintext with salted nonces."""
    raw_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyzSECRET"
    ciphertext = encrypt_secret(raw_token)

    assert ciphertext != raw_token
    assert len(ciphertext) > len(raw_token)

    # Different runs must produce different ciphertexts (random salt/IV)
    ciphertext_2 = encrypt_secret(raw_token)
    assert ciphertext != ciphertext_2

    # Decryption recovers exact plaintext
    decrypted = decrypt_secret(ciphertext)
    assert decrypted == raw_token
    assert decrypt_secret(ciphertext_2) == raw_token


def test_credential_decryption_tamper():
    """Tests that tampered ciphertexts fail to decrypt safely."""
    raw_token = "my_secret_api_key"
    ciphertext = encrypt_secret(raw_token)
    tampered = ciphertext[:-4] + "xxxx"

    with pytest.raises(Exception):
        decrypt_secret(tampered)


# =====================================================================
# 2. Secure Credential Storage & Safe Listing (Zero Leakage)
# =====================================================================

def test_safe_credential_listing_never_leaks_tokens(db: Session, local_user: User):
    """Tests that listing credentials never exposes plaintext or encrypted tokens."""
    provider = f"test_provider_{uuid.uuid4().hex[:6]}"
    secret_token = "super_secret_access_token_xyz"
    secret_refresh = "refresh_token_abc"

    credential_service.store_credentials(
        db=db,
        user_id=local_user.id,
        provider=provider,
        service_name="Test Service",
        access_token=secret_token,
        refresh_token=secret_refresh,
        account_identifier="user@example.com",
        scopes=["read:user", "repo"]
    )

    # 1. Check database level encryption
    raw_db_cred = db.query(IntegrationCredential).filter(
        IntegrationCredential.user_id == local_user.id,
        IntegrationCredential.provider == provider
    ).first()
    assert raw_db_cred is not None
    assert raw_db_cred.encrypted_access_token != secret_token

    # 2. Check safe listing
    safe_list = credential_service.list_safe_credentials(db, local_user.id)
    matched = [c for c in safe_list if c["provider"] == provider]
    assert len(matched) == 1
    safe_cred = matched[0]

    assert safe_cred["provider"] == provider
    assert safe_cred["account_identifier"] == "user@example.com"
    assert safe_cred["scopes"] == ["read:user", "repo"]
    assert "access_token" not in safe_cred
    assert "refresh_token" not in safe_cred
    assert "encrypted_access_token" not in safe_cred

    # 3. Decrypted lookup recovers tokens
    decrypted = credential_service.get_decrypted_credentials(db, local_user.id, provider)
    assert decrypted["access_token"] == secret_token
    assert decrypted["refresh_token"] == secret_refresh


# =====================================================================
# 3. OAuth 2.0 PKCE & CSRF State Security
# =====================================================================

def test_oauth_authorization_url_generation(local_user: User):
    """Tests authorization URL generation with provider adapter, PKCE and state."""
    auth_data = oauth_manager.generate_authorization_url(
        provider_name="github",
        user_id=local_user.id,
        redirect_uri="http://localhost:8000/api/oauth/callback",
        custom_client_id="test_mock_github_client_id"
    )

    assert auth_data["provider"] == "github"
    assert auth_data["configured"] is True
    assert "github.com/login/oauth/authorize" in auth_data["authorization_url"]
    assert "state=" in auth_data["authorization_url"]
    assert "client_id=test_mock_github_client_id" in auth_data["authorization_url"]
    assert auth_data["state"] in oauth_manager._states

    # Verify cached state structure
    cached_state = oauth_manager._states[auth_data["state"]]
    assert cached_state["user_id"] == str(local_user.id)
    assert cached_state["provider"] == "github"
    assert "code_verifier" in cached_state


def test_oauth_unsupported_provider():
    """Tests rejection of invalid or untrusted OAuth providers."""
    with pytest.raises(ValueError, match="Unsupported OAuth provider"):
        oauth_manager.generate_authorization_url(
            provider_name="malicious_provider",
            user_id=uuid.uuid4(),
            redirect_uri="http://localhost:8000/api/oauth/callback"
        )


def test_oauth_state_validation_and_consumption():
    """Tests CSRF state validation and one-time consumption."""
    state = "state_" + uuid.uuid4().hex
    import time
    oauth_manager._states[state] = {
        "user_id": str(uuid.uuid4()),
        "provider": "figma",
        "redirect_uri": "http://localhost:8000/api/oauth/callback",
        "code_verifier": "test_verifier",
        "created_at": time.time()
    }

    # First validation succeeds and consumes the state
    validated = oauth_manager.validate_state(state)
    assert validated["provider"] == "figma"

    # Second validation fails (state already consumed)
    with pytest.raises(ValueError, match="Invalid or expired"):
        oauth_manager.validate_state(state)


# =====================================================================
# 4. MCP Discovery & Natural Language Intent Matching
# =====================================================================

def test_mcp_discovery_natural_language_intents():
    """Tests natural language intent detection for connecting and disconnecting services."""
    # Connect intents
    intent_figma = detect_integration_intent("Connect Figma")
    assert intent_figma is not None
    assert intent_figma["action"] == "connect"
    assert intent_figma["catalog_item"].name == "figma"

    intent_gh = detect_integration_intent("please integrate with github")
    assert intent_gh is not None
    assert intent_gh["action"] == "connect"
    assert intent_gh["catalog_item"].name == "github"

    intent_slack = detect_integration_intent("add slack service")
    assert intent_slack is not None
    assert intent_slack["action"] == "connect"
    assert intent_slack["catalog_item"].name == "slack"

    # Disconnect intents
    intent_disc = detect_integration_intent("disconnect from Notion")
    assert intent_disc is not None
    assert intent_disc["action"] == "disconnect"
    assert intent_disc["catalog_item"].name == "notion"

    # Non-integration query
    assert detect_integration_intent("What is the capital of France?") is None
    assert detect_integration_intent("How do I sort a list in Python?") is None


def test_mcp_catalog_completeness():
    """Tests that official trusted catalog contains required target services."""
    catalog = registry.list_catalog()
    catalog_names = {item.name for item in catalog}

    assert "github" in catalog_names
    assert "figma" in catalog_names
    assert "slack" in catalog_names
    assert "notion" in catalog_names
    assert "google-workspace" in catalog_names


def test_format_discovery_card():
    """Tests interactive discovery card formatting."""
    gh = registry.get_catalog_item("github")
    assert gh is not None

    card = format_discovery_message(gh, is_connected=False)
    assert gh.display_name in card
    assert gh.description in card
    assert "[CONNECT_INTEGRATION_ACTION:github]" in card


# =====================================================================
# 5. Security Validations: SSRF and Stdio Shell Injections
# =====================================================================

def test_remote_url_ssrf_prevention():
    """Tests that SSRF attacks against private/loopback IPs and cloud metadata return False."""
    # Loopback & private IPs
    assert validate_remote_url("http://127.0.0.1:8000/sse") is False
    assert validate_remote_url("http://localhost:3000/mcp") is False
    assert validate_remote_url("http://10.0.0.1/sse") is False
    assert validate_remote_url("http://192.168.1.1/sse") is False

    # Cloud metadata endpoint
    assert validate_remote_url("http://169.254.169.254/latest/meta-data") is False

    # Insecure schemes
    assert validate_remote_url("file:///etc/passwd") is False
    assert validate_remote_url("ftp://example.com/data") is False

    # Valid HTTPS public URL
    assert validate_remote_url("https://mcp.example.com/api/sse") is True


def test_stdio_command_injection_prevention():
    """Tests that shell command injection operators and untrusted binaries are rejected."""
    assert validate_stdio_command("npx", ["; rm -rf /"]) is False
    assert validate_stdio_command("node", ["| cat"]) is False
    assert validate_stdio_command("python", ["&& echo hacked"]) is False
    assert validate_stdio_command("npx", ["`whoami`"]) is False
    assert validate_stdio_command("python", ["$(id)"]) is False
    assert validate_stdio_command("curl", []) is False

    # Allowed safe binary and valid arguments
    assert validate_stdio_command("npx", ["-y", "@modelcontextprotocol/server-sqlite"]) is True
    assert validate_stdio_command("python", ["-m", "mcp_server"]) is True
    assert validate_stdio_command("node", ["index.js"]) is True


# =====================================================================
# 6. Tool Classification & Qwen 2.5 3B Intent Filtering
# =====================================================================

def test_tool_classification_read_vs_write():
    """Tests classification of tools into read-only vs. write/mutation."""
    def classify(tool_name: str):
        low = tool_name.lower()
        if any(low.startswith(p) for p in READ_ONLY_PREFIXES):
            return ActionClassification.READ_ONLY, False
        return ActionClassification.WRITE, True

    cls_read, req_read = classify("get_issue")
    assert cls_read == ActionClassification.READ_ONLY
    assert req_read is False

    cls_write, req_write = classify("create_issue")
    assert cls_write == ActionClassification.WRITE
    assert req_write is True

    cls_search, req_search = classify("search_repositories")
    assert cls_search == ActionClassification.READ_ONLY
    assert req_search is False

    cls_send, req_send = classify("send_email")
    assert cls_send == ActionClassification.WRITE
    assert req_send is True


def test_intent_tool_filtering_caps_for_qwen():
    """Tests that dynamic tool filtering limits tools to max 3 relevant tools for Qwen 2.5 3B."""
    tool_reg = MCPToolRegistry()

    # Register 10 tools
    tools = [
        MCPToolDefinition(name="search_repositories", description="Search repositories", input_schema={}, server_name="github"),
        MCPToolDefinition(name="create_issue", description="Create an issue", input_schema={}, server_name="github"),
        MCPToolDefinition(name="get_issue", description="Get an issue by number", input_schema={}, server_name="github"),
        MCPToolDefinition(name="send_slack_message", description="Send a message to a Slack channel", input_schema={}, server_name="slack"),
        MCPToolDefinition(name="get_channel_history", description="Read messages in Slack", input_schema={}, server_name="slack"),
        MCPToolDefinition(name="get_figma_file", description="Get Figma document node tree", input_schema={}, server_name="figma"),
        MCPToolDefinition(name="post_figma_comment", description="Post a comment on Figma canvas", input_schema={}, server_name="figma"),
        MCPToolDefinition(name="create_notion_page", description="Create a new Notion page", input_schema={}, server_name="notion"),
        MCPToolDefinition(name="search_notion", description="Search Notion workspace", input_schema={}, server_name="notion"),
        MCPToolDefinition(name="send_gmail", description="Send an email via Gmail", input_schema={}, server_name="google_workspace"),
    ]
    tool_reg.register_tools("all", tools)

    # Query for GitHub issue
    relevant = tool_reg.filter_relevant_tools("Please create a new issue for the login bug", max_tools=3)
    assert len(relevant) <= 3
    tool_names = [t.name for t in relevant]
    assert "create_issue" in tool_names

    # Formatted prompt instructions are compact and structured
    prompt_block = tool_reg.format_tools_for_llm(relevant)
    assert "<<<TOOL_INVOCATION:" in prompt_block
    assert "create_issue" in prompt_block


# =====================================================================
# 7. Mandatory Action Confirmation & Idempotent Execution
# =====================================================================

def test_write_action_intercepted_and_confirmed(db: Session, local_user: User):
    """
    Tests that a write/mutation action:
    1. Is intercepted without executing.
    2. Creates a pending action record in DB.
    3. User confirms -> tool executes and status becomes 'executed'.
    4. Re-confirming raises an error (idempotency).
    """
    # 1. Create a pending write action
    tool_args = {"repo": "ghostmind/app", "title": "Crash on launch", "body": "Details here"}
    action = action_confirmation_service.create_pending_action(
        db=db,
        user_id=local_user.id,
        server_name="github",
        tool_name="create_issue",
        arguments=tool_args
    )

    assert action.status == "pending"
    assert action.tool_name == "create_issue"
    assert json.loads(action.parameters_json) == tool_args

    # 2. Mock MCP execution when confirmed
    mock_exec_result = {"issue_number": 42, "url": "https://github.com/ghostmind/app/issues/42"}
    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=mock_exec_result)

    with patch("mcp.connection_manager.connection_manager.get_or_connect", new=AsyncMock(return_value=mock_client)):
        result = asyncio.run(action_confirmation_service.confirm_and_execute(
            db=db,
            user_id=local_user.id,
            action_id=action.id
        ))

        assert result["status"] == "executed"
        assert result["result"] == mock_exec_result

    # 3. Check DB status updated
    db.refresh(action)
    assert action.status == "executed"
    assert action.executed_at is not None

    # 4. Idempotency: Attempting to confirm again reports already executed
    second_run = asyncio.run(action_confirmation_service.confirm_and_execute(
        db=db,
        user_id=local_user.id,
        action_id=action.id
    ))
    assert second_run["status"] == "already_executed"


def test_action_cancellation(db: Session, local_user: User):
    """Tests that pending actions can be explicitly cancelled."""
    action = action_confirmation_service.create_pending_action(
        db=db,
        user_id=local_user.id,
        server_name="slack",
        tool_name="post_message",
        arguments={"channel": "general", "text": "Deploying now!"}
    )

    success = action_confirmation_service.cancel_action(
        db=db,
        user_id=local_user.id,
        action_id=action.id,
        reason="Aborted by user"
    )
    assert success is True

    db.refresh(action)
    assert action.status == "cancelled"


# =====================================================================
# 8. REST API Endpoints Verification
# =====================================================================

def test_api_list_catalog(client: TestClient):
    """Verifies GET /api/integrations/catalog endpoint."""
    res = client.get("/api/integrations/catalog")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 5

    item_ids = [d["id"] for d in data]
    assert "github" in item_ids
    assert "figma" in item_ids
    assert "slack" in item_ids


def test_api_discover_endpoint(client: TestClient):
    """Verifies POST /api/integrations/discover intent parsing."""
    res = client.post("/api/integrations/discover", json={"query": "Connect Figma"})
    assert res.status_code == 200
    data = res.json()
    assert data["matched"] is True
    assert data["service_id"] == "figma"
    assert "🔌 Figma Integration Found" in data["card_message"]


def test_api_pending_actions_endpoints(client: TestClient, db: Session, local_user: User):
    """Verifies listing and cancelling pending actions over HTTP API."""
    action = action_confirmation_service.create_pending_action(
        db=db,
        user_id=local_user.id,
        server_name="notion",
        tool_name="create_page",
        arguments={"title": "Q3 Planning"}
    )

    # 1. List
    list_res = client.get("/api/actions/pending")
    assert list_res.status_code == 200
    pending_list = list_res.json()
    assert any(a["id"] == str(action.id) for a in pending_list)

    # 2. Cancel
    cancel_res = client.post(f"/api/actions/{action.id}/cancel", json={"reason": "Not needed"})
    assert cancel_res.status_code == 200
    assert cancel_res.json()["success"] is True

    # 3. Verify no longer pending
    db.refresh(action)
    assert action.status == "cancelled"
