# GHOSTMIND — System Knowledge Base & AI Context File (`ai.md`)

> **Note for AI Assistants / Future Sessions**:  
> Read this file at the start of any new session to obtain instant, comprehensive context of the architecture, stack, runtime environment, token optimizations, and past bug fixes without needing to scan the entire repository.  
> **RULE**: After making any architectural change, new feature, or bug fix, update this file so it remains the single source of truth.

---

## 1. Executive Summary & Mission
**GHOSTMIND** is a 100% private, local-first AI Operating System for Windows. It provides local LLM inference (Qwen 2.5 3B via Ollama), a **Universal Dynamic Model Context Protocol (MCP) Ecosystem**, a **Universal OAuth 2.0 / 2.1 integration engine**, a **Mandatory Action Confirmation System** for mutations, persistent cross-conversation long-term memory, document vector RAG (pgvector), intelligent live web search (zero-key DuckDuckGo), local speech-to-text (Whisper), real-time SSE streaming, and a zero-auth single-user desktop architecture, all wrapped in a Pastel Futuristic glassmorphic desktop interface.

- **Primary Goal**: Complete data privacy on user hardware—local prompt evaluations, encrypted credential persistence, and dynamic standard-compliant tool execution.
- **Hardware Profile**: Target is Windows 10/11 (64-bit) systems with 8GB RAM and CPU-only execution (no dedicated GPU required).
- **Zero App Authentication**: No login or signup screens, no passwords. Launches directly into the main conversational workspace (`get_local_user()` architecture).
- **External Service Authorization**: Secure OAuth 2.0 loopback flows (Google, GitHub, Figma, Slack, Notion) and custom API token injection, associating tools with the local single-user installation.
- **Dynamic Tool Discovery**: Zero hardcoded integration routines. Services expose standard MCP tools; GHOSTMIND discovers, registers, classifies, and executes them dynamically.

---

## 2. Complete Technology Stack

| Layer | Technologies & Libraries | Purpose & Details |
| :--- | :--- | :--- |
| **Desktop Shell** | `pywebview (6.2.1)`, `Win32 Named Mutex` | Native desktop window using Windows Edge/WebView2 runtime with single-instance enforcement (`GhostMindSingleInstanceMutex_v2`). |
| **Frontend UI** | HTML5, CSS3, Vanilla JavaScript | Pastel Futuristic theme, translucent glassmorphism (`backdrop-filter: blur(20px)`), collapsible sidebar, SSE streaming renderer, syntax-highlighted code blocks, interactive Action Confirmation Cards, and Connected Services modal. |
| **Backend Web Server** | `FastAPI (0.162.0)`, `uvicorn[standard] (0.54.0)` | Async REST API, Server-Sent Events (`text/event-stream`), CORS, background thread pools, and lifespan shutdown hooks. |
| **Language & Runtime** | Python 3.10 - 3.13 (`venv`) | Isolated Python virtual environment with pinned dependencies in `requirements.txt`. |
| **Model Context Protocol**| `mcp (2.3.0)`, `mcp-types`, `jsonschema` | Official Model Context Protocol SDK for Python. Handles JSON-RPC 2.0 client initialization, tool listing, and tool invocation over `stdio` and `sse`. |
| **Security & Cryptography**| `cryptography (Fernet + PBKDF2 HMAC-SHA256)` | Military-grade AES-128-CBC / HMAC-SHA256 credential encryption at rest with random nonces. Zero plaintext token exposure over APIs or logs. |
| **Universal OAuth 2.0** | `UniversalOAuthManager` with PKCE & CSRF | RFC 7636 PKCE (`code_verifier`/`code_challenge`), RFC 6749 state verification, token refresh concurrency locking, and loopback redirects. |
| **Action Confirmation** | `ActionConfirmationService` | Mandatory user confirmation barrier for write/mutation tools (`create_issue`, `post_message`, `send_email`). Features unique UUIDs, 15-min expiration, and idempotency guarantees. |
| **Database & ORM** | `PostgreSQL 14+`, `SQLAlchemy (2.1.6)`, `psycopg 3 (3.3.6)` | Central relational persistence across users, conversations, messages, documents, memories, credentials, MCP servers, and pending actions. |
| **Database Migrations** | `Alembic (1.20.1)` | Schema migrations with versioning in `alembic/versions/` (including `7a89fbc3012d_mcp_and_oauth_tables.py`). |
| **Vector Storage & Search** | `pgvector (0.5.1)` with Python Cosine Fallback | 768-dimensional dense vector embeddings. Uses native pgvector extension if available, otherwise automatic Python-side cosine similarity. |
| **Local LLM Engine** | `Ollama` running `qwen2.5:3b` | 3B parameter local language model communicating over `http://127.0.0.1:11434`. Configured with `num_ctx=4096`, `num_predict=1024`, and default temperature `0.7`. |
| **Embedding Engine** | `Ollama` running `nomic-embed-text` | 768-dim embeddings with 8192-token context window for chunking & retrieval. |
| **AI Orchestration** | `langchain (1.4.7)`, `langchain-ollama (1.1.0)` | Chat model wrappers, streaming chunk generators, prompt templating, and intent-based dynamic tool filtering. |
| **Live Web Search** | Custom zero-key DuckDuckGo Engine | Real-time web search for up-to-date facts, intelligent query classification routing (`should_search_web`), URL deduplication, and compact citation formatting. |
| **Speech-to-Text** | `faster-whisper (1.2.1)`, `av (13.1.0)` | Local audio transcription on CPU using `int8` quantization (`base` model). |
| **Document Processing** | `pypdf (6.9.1)`, `python-docx (1.2.0)`, `openpyxl (3.1.5)` | Ingestion and text extraction for PDF, DOCX, XLSX, CSV, TXT, MD, and JSON files. |
| **Local User Architecture**| `core/user.py` (`get_local_user`) | Zero-auth resolver reusing existing user records or provisioning `LOCAL_USER_ID = 00000000-0000-0000-0000-000000000001` without cookies or tokens. |
| **Packaging & Distribution**| `pyinstaller (6.22.3)` | Freezes Python environment into standalone executable (`GhostMind.spec`). |
| **Testing Framework** | `pytest (9.1.1)`, `httpx (0.28.1)` | Automated integration suite (32 tests) covering zero-auth, streaming, routing, RAG, memory, voice, OAuth, encryption, MCP discovery, and action confirmation. |

---

## 3. Repository File Structure & Module Map

```text
PersonalAI/
├── core/
│   ├── config.py              # Central settings loaded from .env (DB, Ollama, Whisper, token limits, encryption key)
│   ├── database.py            # SQLAlchemy engine, session maker, init_db(), pgvector checks
│   └── user.py                # Zero-auth local single-user resolver (get_local_user)
├── models/
│   └── __init__.py            # SQLAlchemy ORM models (User, Conversation, Message, Document, Chunk, Memory,
│                              # IntegrationCredential, MCPServerConfig, PendingAction)
├── mcp/
│   ├── __init__.py            # Package exports
│   ├── models.py              # Pydantic models (MCPServerSpec, MCPToolDefinition, MCPCatalogItem, ToolExecutionRequest/Result)
│   ├── security.py            # Fernet + PBKDF2 token encryption, SSRF validator, stdio command validator
│   ├── transports.py          # BaseTransport, StdioTransport (async subprocess JSON-RPC), HttpSseTransport
│   ├── client.py              # Standard MCP client (initialize, tools/list with read/write classification, tools/call)
│   ├── registry.py            # Trusted catalog (GitHub, Figma, Slack, Notion, Google Workspace), search & aliases
│   ├── discovery.py           # Natural language intent detection ("Connect Figma", "Disconnect Slack"), interactive card formatter
│   ├── tool_registry.py       # In-memory tool repository with dynamic intent-based filtering (max 3 tools for Qwen 2.5 3B)
│   ├── connection_manager.py  # Lazy on-demand connections, reconnects, server health, graceful shutdown
│   ├── manager.py             # UniversalMCPManager orchestrator (catalog connection, tool execution, interception)
│   └── servers/
│       └── google_workspace_server.py # Built-in local MCP server for Gmail, Google Calendar, and Google Drive
├── routes/
│   ├── chat.py                # POST /api/chat (sync) and POST /api/chat/stream (SSE streaming)
│   ├── conversations.py       # CRUD for conversations, pagination, rename, delete
│   ├── documents.py           # Document upload, parsing, vector embedding, chunk retrieval
│   ├── health.py              # Health check (/api/health) for DB, pgvector, and Ollama readiness
│   ├── integrations.py        # /api/integrations (list, catalog, discover, connect, disconnect, tools)
│   ├── mcp.py                 # /api/mcp (servers, connect, disconnect, tools, direct execute)
│   ├── memories.py            # Manual & automated persistent long-term memory management
│   ├── oauth.py               # /api/oauth (provider authorize, callback, revoke, safe credentials listing)
│   ├── pending_actions.py     # /api/actions (list pending, confirm and execute, cancel)
│   └── voice.py               # Audio upload & local Faster-Whisper transcription
├── schemas/
│   └── __init__.py            # Pydantic v2 schemas for request validation & API responses
├── services/
│   ├── action_confirmation_service.py # Mandatory user action confirmation barrier (expiration, idempotency, execution)
│   ├── chat_service.py        # ChatOllama turn executor, SSE generator, intent tool prompt injection, tool interception
│   ├── conversation_service.py# Conversation & message database operations, smart titles
│   ├── credential_service.py  # Encrypted token storage, safe listing (zero plaintext exposure), revocation
│   ├── document_service.py    # Multi-format document parser, chunk splitter, deduplication
│   ├── embedding_service.py   # Ollama nomic-embed-text dense embeddings generator
│   ├── integration_service.py # High-level integration management, catalog connections, env token injection
│   ├── memory_service.py      # Long-term memory extraction, relevance filtering, anti-hallucination prompt
│   ├── oauth_service.py       # UniversalOAuthManager (Google, GitHub, Figma, Slack, Notion adapters, PKCE, state)
│   ├── rag_service.py         # Vector similarity search (pgvector or cosine fallback)
│   ├── web_search_service.py  # Internet connectivity check, query routing, zero-key live web search
│   └── whisper_service.py     # Faster-Whisper local CPU int8 audio transcription
├── tests/
│   ├── test_platform.py       # Core integration tests (Zero-auth, streaming, RAG, memory, voice, health)
│   ├── test_extended.py       # Extended pagination, file validation, and offline policy tests
│   └── test_mcp_ecosystem.py  # Comprehensive MCP & OAuth suite (Encryption, SSRF, state, intent, tools, actions)
├── alembic/
│   └── versions/
│       └── 7a89fbc3012d_mcp_and_oauth_tables.py # Migration for credentials, MCP configs, and pending actions
├── desktop_app.py             # Desktop launcher (Named Mutex, Uvicorn thread, PyWebView window)
├── main.py                    # FastAPI application, lifespan Ollama check + MCP disconnect, router mounts
├── ollama_service.py          # Ollama background launcher, process check, model verification
├── index.html                 # Pastel Futuristic desktop frontend (Modals, Integrations tab, Action cards, SSE streaming)
├── style.css                  # Pastel Futuristic glassmorphic stylesheet with service & action card styles
├── run.bat                    # 1-Click launcher (starts Ollama, verifies qwen2.5:3b, runs desktop_app.py)
├── setup.bat                  # Initial setup script (installs venv, runs migrations, creates shortcut)
├── build.bat                  # PyInstaller executable builder
├── requirements.txt           # Pinned Python package dependencies (includes mcp>=2.3.0)
├── .env                       # Local secrets, database credentials, Ollama & token settings
└── ai.md                      # THIS FILE (Single source of truth for AI context)
```

---

## 4. Key Subsystems & Architectural Workflows

### A. Universal Dynamic MCP Integration Architecture
GHOSTMIND connects external tools and services without hardcoding individual tool functions:
1. **Catalog Definition**: Official/verified services (GitHub, Figma, Slack, Notion, Google Workspace) are registered in `mcp/registry.py` with publisher info, transport types, requested permissions, and tool classifications.
2. **Multi-Transport Support**:
   - `stdio`: Executes MCP server as an isolated subprocess (e.g. `npx -y @modelcontextprotocol/server-github`), communicating over JSON-RPC 2.0 via standard input/output.
   - `sse` / Streamable HTTP: Connects to remote MCP HTTP endpoints using `httpx` async clients with SSRF protection against private IP spaces.
3. **Dynamic Discovery**: When a server connects, GHOSTMIND performs JSON-RPC protocol initialization (`initialize`, `notifications/initialized`), sends `tools/list`, and reads tool names, descriptions, and JSON Schema argument specifications.
4. **Natural Language Discovery**: Phrases like *"Connect Figma"* or *"Add Slack integration"* are detected by `detect_integration_intent()`, generating an interactive card in chat with publisher details, requested permissions, and a one-click `[CONNECT_INTEGRATION_ACTION:...]` pill.
5. **Custom MCP Servers**: Users can register any arbitrary stdio or SSE server via the UI modal or `POST /api/mcp/servers`.

### B. Universal OAuth 2.0 / 2.1 & Credential Security
- **Providers Supported**: Google, GitHub, Figma, Slack, Notion.
- **Security Best Practices**:
  - **PKCE Enforcement**: Uses SHA-256 code verifier and code challenge for providers supporting PKCE.
  - **CSRF State Validation**: Generates cryptographically secure one-time tokens (`secrets.token_urlsafe(32)`) with a 10-minute expiration. States are strictly consumed upon first use.
  - **Encryption at Rest**: Stored tokens (`access_token`, `refresh_token`) are encrypted with AES-128-CBC using Fernet and PBKDF2 HMAC derivation (`TOKEN_ENCRYPTION_KEY`).
  - **Zero Plaintext Token Exposure**: Listing endpoints (`/api/oauth/credentials`, `/api/integrations`) return only metadata (`account_identifier`, `scopes`, `created_at`). Tokens are never sent to the frontend or written to logs.
  - **Concurrency Locks**: Token refreshes use per-provider async locks to prevent race conditions during parallel requests.

### C. Mandatory Action Confirmation System
To safeguard user data and prevent unintended external modifications:
1. **Tool Classification**:
   - **Read-Only Tools**: (`get_*`, `list_*`, `read_*`, `search_*`, `fetch_*`, `query_*`, `inspect_*`) execute automatically when authorized.
   - **Write / Mutation Tools**: (`create_issue`, `post_message`, `create_page`, `post_comment`, `send_email`, `delete_*`, etc.) are classified as `requires_confirmation = True`.
2. **Interception**: When Qwen 2.5 3B outputs a write tool invocation, execution is intercepted. A `PendingAction` is stored in PostgreSQL with status `"pending"`, parameter snapshot, and a 15-minute expiration timestamp.
3. **User Experience**: The chatbot presents an interactive **Action Confirmation Card** with full parameter details, a `✓ Confirm & Execute` button, and a `✕ Cancel` button.
4. **Execution & Idempotency**: Clicking `Confirm` calls `POST /api/actions/{id}/confirm`. If already executed, duplicate execution is blocked. Upon completion, status becomes `"executed"`, and output is presented dynamically in the chat.

### D. Token Consumption & CPU Optimization for Qwen 2.5 3B (8GB RAM Target)
1. **Dynamic Intent-Based Tool Filtering**: Instead of injecting dozens of MCP tool schemas into the prompt (which exhausts context and slows CPU generation), `MCPToolRegistry.filter_relevant_tools()` analyzes the user's prompt and selects only the **top-3 most relevant tools**.
2. **Compact Tool Prompts**: Discovered tools are rendered in a compact, structured format instructing the LLM to output `<<<TOOL_INVOCATION: {"server": "...", "tool": "...", "arguments": {...}}>>>` only when needed.
3. **Bounded Conversation History**: Only the **most recent 6 messages** (`MAX_RECENT_MESSAGES = 6`) are included in generation turns.
4. **Targeted Memory & RAG Retrieval**: Long-term memories capped at top-3 relevant facts; RAG document chunks capped at top-3 chunks meeting the 0.45 cosine threshold.
5. **Inference Parameters**: Default temperature `0.7`, context window `4096`, and max output `1024` tokens.

### E. Zero-Authentication Local Architecture ([`core/user.py`](core/user.py))
- Zero login or signup requirements. Application launches straight into the desktop workspace.
- `get_local_user(db)` resolves the local user:
  1. Queries the first existing user in PostgreSQL to preserve all existing data.
  2. If empty, creates deterministic local user `00000000-0000-0000-0000-000000000001` (`local@ghostmind.app`).
- All integrations, credentials, and pending actions are associated with this local user ID.

---

## 5. Complete API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves `index.html` (single-page desktop UI). |
| `GET` | `/status`, `/api/status` | Diagnostics for Ollama, models, PostgreSQL, and internet connectivity. |
| `POST` | `/api/ollama/start` | Explicitly triggers background launch of Ollama if offline. |
| `GET` | `/api/health` | Comprehensive health report (DB latency, pgvector status, Ollama engine). |
| `GET` | `/api/settings` | Returns active runtime settings (`temperature`, `max_output_tokens`, `model`). |
| `GET` | `/api/conversations` | Lists user's conversations ordered by last updated. |
| `POST` | `/api/conversations` | Creates a new conversation. |
| `GET` | `/api/conversations/{id}` | Fetches message history for a conversation. |
| `PATCH`| `/api/conversations/{id}` | Renames conversation title. |
| `DELETE`| `/api/conversations/{id}`| Deletes conversation and all associated messages. |
| `POST` | `/api/chat` | Synchronous chat turn endpoint with MCP tool interception. |
| `POST` | `/api/chat/stream` | **Real-time SSE streaming chat turn** with live tool interception. |
| `GET` | `/api/documents` | Lists uploaded and indexed documents. |
| `POST` | `/api/documents/upload` | Uploads, parses, chunks, and vector-embeds documents. |
| `DELETE`| `/api/documents/{id}` | Deletes document and its vector chunks. |
| `GET` | `/api/memories` | Lists active persistent long-term memories. |
| `POST` | `/api/memories` | Adds a new persistent memory manually. |
| `DELETE`| `/api/memories/{id}` | Deletes a persistent memory. |
| `GET` | `/api/voice/status` | Returns local Whisper configuration (`faster-whisper`, CPU int8). |
| `POST` | `/api/voice/transcribe` | Transcribes recorded audio file using local Faster-Whisper. |
| **`GET`** | **`/api/integrations`** | **Lists connected MCP services, live connection status, and tool counts.** |
| **`GET`** | **`/api/integrations/catalog`** | **Returns trusted MCP catalog (GitHub, Figma, Slack, Notion, Google Workspace).** |
| **`POST`**| **`/api/integrations/discover`**| **Parses natural language ("Connect Figma") into interactive discovery cards.** |
| **`POST`**| **`/api/integrations/connect`** | **Connects an MCP catalog service, injecting stored or supplied auth credentials.** |
| **`DELETE`**|**`/api/integrations/{server}`**| **Disconnects an MCP server and securely revokes credentials.** |
| **`GET`** | **`/api/integrations/{server}/tools`**| **Lists dynamically discovered tools for a connected MCP server.** |
| **`GET`** | **`/api/oauth/{provider}/authorize`**| **Generates secure OAuth authorization URL with CSRF state and PKCE.** |
| **`GET`** | **`/api/oauth/callback`** | **Unified OAuth loopback callback handler (exchanges code & encrypts tokens).** |
| **`DELETE`**|**`/api/oauth/{provider}`**| **Revokes stored OAuth credentials for a provider.** |
| **`GET`** | **`/api/oauth/credentials`** | **Lists active OAuth authorizations safely without exposing plaintext tokens.** |
| **`GET`** | **`/api/mcp/servers`** | **Lists registered MCP server configurations and live statuses.** |
| **`POST`**| **`/api/mcp/servers`** | **Registers and connects a custom stdio or SSE MCP server.** |
| **`POST`**| **`/api/mcp/servers/{server}/connect`** | **Connects an established MCP server.** |
| **`POST`**| **`/api/mcp/servers/{server}/disconnect`**| **Disconnects an active MCP server.** |
| **`GET`** | **`/api/mcp/servers/{server}/tools`** | **Lists all discovered tools and schemas for an MCP server.** |
| **`POST`**| **`/api/mcp/tools/execute`** | **Directly invokes an MCP tool (subject to action confirmation).** |
| **`GET`** | **`/api/actions/pending`** | **Lists active pending actions awaiting explicit user confirmation.** |
| **`POST`**| **`/api/actions/{id}/confirm`**| **Explicit user confirmation trigger: executes pending write action idempotently.** |
| **`POST`**| **`/api/actions/{id}/cancel`** | **Rejects and cancels a pending action.** |

---

## 6. Solved Problems & Maintenance Log

### Issue 1: "Could not start Google Sign-In: Failed to fetch" & Duplicate Processes
- **Cause**: Clicking the app twice caused two instances of `desktop_app.py` to run. Both grabbed port `8000`. One crashed on `WinError 10048`, and closing duplicate windows killed Uvicorn.
- **Fix**: Added Windows Named Mutex (`GhostMindSingleInstanceMutex_v2`) in `desktop_app.py`. Duplicate launches bring existing window to front and terminate safely.

### Issue 2: Qwen 2.5 3B Hallucinating on Post-Cutoff Topics (e.g. MCP)
- **Cause**: Qwen 2.5 3B training data cutoff was before the release of Anthropic's Model Context Protocol (MCP).
- **Fix**: Integrated zero-key live web search service (`web_search_service.py`) and strict anti-hallucination guardrails in `memory_service.py`. When online, GHOSTMIND fetches live DuckDuckGo web snippets and cites sources. When offline, it safely refuses to hallucinate.

### Issue 3: Inefficient Token Consumption & CPU Latency
- **Cause**: Full conversation histories were passed on every request, inflating prompt tokens.
- **Fix**: Implemented smart context bounding: capped recent messages to 6, keyword-filtered memories to top-3, applied cosine threshold (0.45) to RAG chunks, and set default temperature to 0.7.

### Issue 4: Authentication Removal & Data Preservation
- **Cause**: User requested removing login/signup while keeping all existing conversations and documents intact.
- **Fix**: Created `core/user.py` (`get_local_user`), which queries the first existing user in PostgreSQL. All database records stay intact without schema collisions.

### Issue 5: Dynamic MCP Tool & Universal OAuth Integration
- **Cause**: The platform needed universal support for external tool execution (GitHub, Figma, Slack, Notion, Google Workspace) without hardcoding logic, while ensuring data privacy, encrypted credentials, and mandatory confirmation on write operations.
- **Fix**: Built the complete `mcp/` subsystem, Fernet PBKDF2 credential encryption, `UniversalOAuthManager` with PKCE, `ActionConfirmationService` with idempotency, dynamic intent-based tool filtering, and Pastel UI modal with tabs and confirmation cards.

### Issue 6: Built-in Google Workspace MCP Server & End-to-End Action Execution
- **Cause**: Third-party external npm packages (`@modelcontextprotocol/server-google-workspace`) were unavailable or threw `[WinError 2]` on Windows because `npx` was not resolved to `npx.cmd`. In addition, on server reboot, in-memory tool registries were unpopulated, preventing Qwen 2.5 3B from seeing the tools, and provider aliases (`google-workspace` vs `google`) prevented credential lookups.
- **Fix**:
  1. Developed a 100% native Python JSON-RPC 2.0 MCP server (`mcp/servers/google_workspace_server.py`) using official Google REST APIs (`gmail/v1`, `calendar/v3`, `drive/v3`), running via `sys.executable` with zero npm/Node dependencies.
  2. Implemented `ensure_tools_loaded()` in `mcp/manager.py` to hydrate in-memory `tool_registry` and `connection_manager` from PostgreSQL `MCPServerConfig` on startup, before chat turns, and before confirmed action execution.
  3. Added provider alias normalization in `services/credential_service.py` (`google-workspace` -> `google`).
  4. Added tolerant regex parsing in `extract_tool_invocation()` supporting unclosed or loose brackets (`>>=`, `>>>`, JSON blocks).
  5. Refined the connection UX in `index.html` to clearly distinguish OAuth 2.0 automatic browser authorization from API key entry (e.g. GitHub PAT, Notion Integration Secret), avoiding misleading prompts.
  6. Added automatic latest-message resolution and full body extraction in `google_workspace_server.py` so requests like "read my last mail" gracefully fetch the latest message without failing on `400: Invalid id value`.

---

## 7. Operational Commands

### Launching the Application
```cmd
# Recommended 1-Click Launch (starts Ollama + backend + UI):
run.bat

# Or run directly via virtual environment:
venv\Scripts\python.exe desktop_app.py

# Or create Desktop shortcut:
venv\Scripts\python.exe make_shortcut.py
```

### Running Automated Verification Tests
```cmd
# Run complete test suite (32 tests):
venv\Scripts\python.exe -m pytest tests/ -v

# Run MCP ecosystem tests only:
venv\Scripts\python.exe -m pytest tests/test_mcp_ecosystem.py -v
```

---

## 8. Rule for Future AI Sessions
> When modifying files or adding features to this repository:
> 1. Always inspect `ai.md` first to understand existing architecture and constraints.
> 2. Keep this `ai.md` updated with any newly introduced routes, configuration keys, or bug fixes.
