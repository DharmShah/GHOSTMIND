<p align="center">
  <img src="app_icon.png" width="120" height="120" alt="GHOSTMIND AI OS logo" style="border-radius: 24px; box-shadow: 0 8px 24px rgba(140, 115, 190, 0.25);" />
</p>

<h1 align="center">GHOSTMIND</h1>

<p align="center">
  <strong>A Persistent, Personalized Local AI Operating System for Windows</strong>
</p>

<p align="center">
  100% Local Inference (Ollama & Faster-Whisper) • Google OAuth 2.0 • PostgreSQL Central Storage & RAG • Personalized Long-Term Memory
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-core-features">Features</a> •
  <a href="#-architecture--pipeline">Architecture</a> •
  <a href="#-prerequisites">Prerequisites</a> •
  <a href="#-google-oauth-setup">Google OAuth</a> •
  <a href="#-postgresql--alembic-setup">Database Setup</a> •
  <a href="#-local-ai-models">Local Models</a> •
  <a href="#-windows-executable-packaging">Packaging</a> •
  <a href="#-automated-testing">Testing</a>
</p>

<p align="center">
  <strong><em>You command. GHOSTMIND executes.</em></strong>
</p>

---

## ⚡ Quick Start

### 1. Automated Setup (One-Click)
Run `setup.bat` from Command Prompt or PowerShell:
```cmd
setup.bat
```
*(Or in PowerShell: `.\setup.bat`)*

**What this script does automatically:**
1. 🦙 Verifies Ollama is installed and pulls `qwen2.5:3b` and `nomic-embed-text`.
2. 🐍 Creates an isolated Python virtual environment (`venv`) and installs all pinned dependencies.
3. 🐘 Initializes `.env` and executes Alembic schema migrations (`alembic upgrade head`).
4. 🖥️ Creates a branded `GHOSTMIND` desktop shortcut on your Windows Desktop.
5. 🚀 Launches the GHOSTMIND desktop application!

---

## 🌟 Core Features

- 🔐 **Google OAuth 2.0-Only Authentication**: Secure server-side identity validation using Google's verified subject identifier (`sub`). No passwords stored, zero OTP, HttpOnly SameSite cookie sessions with SHA-256 token hashing at rest.
- 🐘 **PostgreSQL Central Storage**: Complete relational persistence with SQLAlchemy 2.x and Alembic migrations across 9 models (`users`, `user_preferences`, `sessions`, `conversations`, `messages`, `documents`, `document_chunks`, `memories`, `background_jobs`).
- 💬 **Persistent Conversation History**: Left collapsible sidebar featuring dynamic conversation retrieval, automatic smart title generation, full-text conversation search, rename, archive, and cascading deletion.
- 🧠 **Personalized Long-Term AI Memory**: Bounded multi-layered context window combining recent messages, relevant user preferences, cross-conversation project context, and grounded RAG citations.
- 🎙️ **Local Whisper Speech Recognition**: Zero-cloud local audio transcription powered by `faster-whisper` running on CPU with `int8` quantization. Real-time microphone capture with browser `MediaRecorder`.
- 📁 **Multi-Format Document Uploads & RAG**: Secure parsing and vector indexing for `PDF`, `DOCX`, `TXT`, `MD`, `CSV`, `XLSX`, and `JSON`. SHA-256 content deduplication and user-isolated similarity search using 768-dimensional local embeddings via `nomic-embed-text`.
- 🎨 **Modern Pastel Desktop Interface**: Built with modern CSS glassmorphism, responsive collapsible sidebar, document library modal, memory bank manager, and status indicators.

---

## 🏗️ Architecture & Pipeline

```mermaid
graph TD
    Client["Windows Desktop / Webview (Chromium)"] -->|HttpOnly Cookie / API| Router["FastAPI Server (main.py)"]
    Router --> AuthRoute["/api/auth (Google OAuth / Sessions)"]
    Router --> ChatRoute["/api/chat (LangChain + Ollama Qwen 2.5 3B)"]
    Router --> ConvoRoute["/api/conversations (PostgreSQL History)"]
    Router --> DocRoute["/api/documents (Upload & Extraction)"]
    Router --> VoiceRoute["/api/voice (faster-whisper int8 CPU)"]
    Router --> MemRoute["/api/memories (Cross-Conversation Memory)"]

    ChatRoute --> Pipeline["Bounded Context Pipeline"]
    Pipeline -->|1. Scoped History| DB[(PostgreSQL 14+)]
    Pipeline -->|2. Cosine Similarity| Chunks[(768-dim Vector Chunks)]
    Pipeline -->|3. Active Memories| Memory[(User Memory Bank)]
    Pipeline -->|4. Prompt + Context| Ollama["Local Ollama Engine (qwen2.5:3b)"]
```

### Complete Request Pipeline
1. **Authenticated User**: Request verified through cryptographically hashed session token in HttpOnly cookie.
2. **Context Assembly**:
   - Fetch last $N$ turns from the conversation in PostgreSQL.
   - Detect stable project context and preferences (auto-extracted or manually saved).
   - Generate query embedding using local `nomic-embed-text` (768-dim) and retrieve top-$K$ document chunks matching the user's files.
   - Assemble bounded context under the model's token limits.
3. **Local LLM Execution**: Invokes local Qwen 2.5 3B through LangChain with zero cloud data transmission.
4. **Persistence**: Saves assistant reply with source document citations and timestamps.

---

## 📋 Prerequisites

1. **Operating System**: Windows 10 or 11 (64-bit).
2. **Python**: 3.10 to 3.13 installed and added to `PATH`.
3. **PostgreSQL**: PostgreSQL 14+ running locally (default port `5432`).
4. **Ollama**: Local Ollama runtime installed from [ollama.com](https://ollama.com).

---

## 🔑 Google OAuth Setup

GHOSTMIND requires Google OAuth 2.0 for single-click sign-in:

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project named **GHOSTMIND**.
3. Go to **APIs & Services** > **OAuth consent screen**:
   - User Type: **External**
   - App Name: **GHOSTMIND**
   - User Support Email: your email
   - Scopes: `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`
4. Go to **APIs & Services** > **Credentials** > **Create Credentials** > **OAuth 2.0 Client ID**:
   - Application Type: **Web application**
   - Name: **GHOSTMIND Desktop**
   - Authorized JavaScript origins: `http://127.0.0.1:8000`, `http://localhost:8000`
   - Authorized redirect URIs: `http://127.0.0.1:8000/auth/google/callback`
5. Copy your **Client ID** and **Client Secret** into your `.env` file:
   ```env
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
   ```

*(Note: In local offline mode without credentials, GHOSTMIND allows seamless "Continue as Local User" for local evaluation).*

---

## 🐘 PostgreSQL & Alembic Setup

1. Make sure your local PostgreSQL service is running.
2. Create the central database:
   ```cmd
   psql -U postgres -c "CREATE DATABASE ghostmind;"
   ```
3. Set your connection string in `.env`:
   ```env
   DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ghostmind
   ```
4. Run schema migrations to HEAD:
   ```cmd
   venv\Scripts\python.exe -m alembic upgrade head
   ```

*(GHOSTMIND natively handles vector embeddings using dense 768-dimensional vectors stored in PostgreSQL. If the native C `pgvector` extension is installed, it uses hardware-accelerated HNSW/IVFFlat indexes; otherwise, it automatically utilizes seamless cosine similarity computation).*

---

## 🧠 Local AI Models

### 1. Generative LLM: Qwen 2.5 3B
```cmd
ollama pull qwen2.5:3b
```
Fast, resource-efficient 3-billion parameter model capable of deep instruction following and context reasoning.

### 2. Embedding Model: Nomic Embed Text (768-dim)
```cmd
ollama pull nomic-embed-text
```
High-accuracy 768-dimensional local embedding model with 8192 context window.

### 3. Speech-to-Text: Faster-Whisper
Model files are stored in `~/.ghostmind/models/whisper/`. On first speech interaction, the `base` model (or model configured in `WHISPER_MODEL_SIZE`) downloads automatically and runs entirely offline on CPU with `int8` quantization.

---

## 🧪 Automated Testing

Run the test suite with `pytest`:
```cmd
venv\Scripts\python.exe -m pytest tests/ -v
```

### Verified Test Matrix:
- ✅ `test_auth_new_user_and_session_lifecycle`: User creation, session generation, verification, and revocation.
- ✅ `test_auth_endpoints_with_mocked_google`: OAuth callback, cookie set, `/api/auth/me`, and logout.
- ✅ `test_conversation_crud_and_cross_user_isolation`: CRUD, message ordering, smart titles, and cross-user data isolation.
- ✅ `test_document_ingestion_and_rag_isolation`: Multi-format parsing, 768-dim embeddings, RAG retrieval, and document isolation.
- ✅ `test_long_term_memory_and_bounded_context`: Auto memory extraction, persistence, and bounded context window assembly.
- ✅ `test_whisper_voice_endpoint`: Local transcription endpoint, audio validation, and engine status.
- ✅ `test_health_and_status_endpoints`: Database health check and diagnostic readiness.
- ✅ `test_long_conversation_message_pagination`: High-volume chat pagination and ordering bounds.
- ✅ `test_file_upload_validation_rejects_disallowed_types`: Path traversal and extension rejection.
- ✅ `test_chat_pipeline_with_mocked_ollama`: Complete end-to-end user-to-response generation.

---

## 📦 Windows Executable Packaging

To build the standalone Windows executable using PyInstaller:
```cmd
build.bat
```
The output directory will be created at `dist\GHOSTMIND\GHOSTMIND.exe`. Persistent application data (uploaded documents, vector chunks, whisper models) is saved to `%USERPROFILE%\.ghostmind\` so user data survives application upgrades.

---

## 🛠️ Troubleshooting

| Issue | Resolution |
| :--- | :--- |
| **Ollama connection failed** | Run `ollama serve` in a terminal or check that port 11434 is open. |
| **PostgreSQL connection refused** | Verify PostgreSQL service is running in `services.msc` and credentials in `.env` match. |
| **Microphone not working** | Grant audio/microphone permissions when prompted in the application window or browser. |
| **Google Sign-In Error** | Ensure `http://127.0.0.1:8000/auth/google/callback` is added to Authorized Redirect URIs in Google Cloud Console. |
| **PyAV Audio Error** | Ensure `av==13.1.0` is installed (`pip install av==13.1.0`). |

---

## 📄 License
Private & Local-First Personal AI Assistant. All processing stays on your hardware.
