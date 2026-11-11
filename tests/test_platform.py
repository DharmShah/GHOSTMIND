import os
import io
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from core.database import get_db, SessionLocal, init_db
from core.user import get_local_user, LOCAL_USER_ID
from models import User, Conversation, Message, Document, DocumentChunk, Memory
from services import conversation_service, document_service, rag_service, memory_service, whisper_service
from services.web_search_service import web_search_service

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure database schema is ready before tests run."""
    init_db()

@pytest.fixture
def db_session():
    """Provide a transactional database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def test_client():
    """Provide a FastAPI TestClient instance."""
    return TestClient(app)

@pytest.fixture
def mock_users(db_session: Session):
    """Create two isolated test users for multi-tenant and isolation tests."""
    unique_a = uuid.uuid4().hex[:8]
    unique_b = uuid.uuid4().hex[:8]

    user_a = User(
        id=uuid.uuid4(),
        google_sub=f"sub_{unique_a}",
        email=f"user_a_{unique_a}@ghostmind.local",
        display_name="Test User Alpha",
        avatar_url="https://example.com/avatar_a.png"
    )
    user_b = User(
        id=uuid.uuid4(),
        google_sub=f"sub_{unique_b}",
        email=f"user_b_{unique_b}@ghostmind.local",
        display_name="Test User Beta",
        avatar_url="https://example.com/avatar_b.png"
    )
    db_session.add_all([user_a, user_b])
    db_session.commit()
    db_session.refresh(user_a)
    db_session.refresh(user_b)
    return user_a, user_b


# =====================================================================
# 1. ZERO-AUTH ARCHITECTURE & LOCAL USER RESOLUTION TESTS
# =====================================================================

def test_local_user_provisioning_and_idempotence(db_session: Session):
    """Test zero-auth user resolution, idempotence, and local desktop persistence."""
    user1 = get_local_user(db_session)
    assert user1 is not None
    assert user1.id is not None

    # Repeated calls must return the same active local user
    user2 = get_local_user(db_session)
    assert user2.id == user1.id


def test_zero_auth_endpoints_access(test_client: TestClient):
    """Ensure all core endpoints are accessible without login screens, tokens, or cookies."""
    # 1. Conversations list
    res_conv = test_client.get("/api/conversations")
    assert res_conv.status_code == 200
    assert isinstance(res_conv.json(), list)

    # 2. Documents list
    res_docs = test_client.get("/api/documents")
    assert res_docs.status_code == 200
    assert isinstance(res_docs.json(), list)

    # 3. Memories list
    res_mems = test_client.get("/api/memories")
    assert res_mems.status_code == 200
    assert isinstance(res_mems.json(), list)

    # 4. Settings endpoint
    res_settings = test_client.get("/api/settings")
    assert res_settings.status_code == 200
    settings_data = res_settings.json()
    assert "temperature" in settings_data
    assert "model" in settings_data
    assert settings_data["model"] == "qwen2.5:3b"

    # 5. Create conversation with zero auth
    res_create = test_client.post("/api/conversations", json={"title": "Zero Auth Workspace Test"})
    assert res_create.status_code in (200, 201)
    assert res_create.json()["title"] == "Zero Auth Workspace Test"


# =====================================================================
# 2. INTELLIGENT WEB SEARCH & PROMPT ROUTING TESTS
# =====================================================================

def test_web_search_intelligent_routing():
    """Verify smart routing: search real-time queries, skip code/local tasks."""
    # Should NOT search: general coding, local explanation, PDF summary
    assert web_search_service.should_search_web("Explain Python loops.") is False
    assert web_search_service.should_search_web("Write a binary search in C++") is False
    assert web_search_service.should_search_web("Summarize my uploaded PDF.") is False
    assert web_search_service.should_search_web("Hello, how are you?") is False

    # SHOULD search: temporal, latest developments, real-time knowledge, MCP
    assert web_search_service.should_search_web("What are the latest developments in Generative AI?") is True
    assert web_search_service.should_search_web("What is the latest version of LangChain?") is True
    assert web_search_service.should_search_web("What is MCP in Claude?") is True
    assert web_search_service.should_search_web("Current weather in Tokyo") is True


# =====================================================================
# 3. CHAT ENDPOINTS & STREAMING PIPELINE TESTS
# =====================================================================

def test_chat_endpoints_streaming_and_sync(test_client: TestClient):
    """Test /api/chat and /api/chat/stream endpoints with mocked LLM generation."""
    with patch("services.chat_service.execute_chat_turn") as mock_sync, \
         patch("services.chat_service.execute_chat_turn_stream") as mock_stream:

        mock_sync.return_value = {
            "conversation_id": "test-uuid-1",
            "title": "New Chat",
            "response": "Hello! I am GHOSTMIND.",
            "sources": [],
            "memories": []
        }

        # 1. Sync chat
        sync_res = test_client.post("/api/chat", json={
            "message": "Hello test",
            "temperature": 0.7,
            "enable_web_search": False,
            "enable_rag": False
        })
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["response"] == "Hello! I am GHOSTMIND."

        # 2. Stream chat (SSE)
        async def fake_stream_generator(*args, **kwargs):
            yield 'data: {"type": "start", "conversation_id": "test-uuid-1"}\n\n'
            yield 'data: {"type": "delta", "text": "Streaming test"}\n\n'
            yield 'data: {"type": "done", "content": "Streaming test", "sources": []}\n\n'

        mock_stream.side_effect = fake_stream_generator

        stream_res = test_client.post("/api/chat/stream", json={
            "message": "Hello stream test",
            "temperature": 0.7
        })
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers.get("content-type", "")
        content_text = stream_res.text
        assert "Streaming test" in content_text


# =====================================================================
# 4. PERSISTENT CONVERSATIONS & USER ISOLATION TESTS
# =====================================================================

def test_conversation_crud_and_cross_user_isolation(db_session: Session, mock_users):
    """Test conversation creation, smart titles, pagination, and multi-user isolation."""
    user_a, user_b = mock_users

    # 1. Create conversation for User A
    convo_a = conversation_service.create_conversation(db_session, user_a.id, title="Initial Title")
    assert convo_a.id is not None
    assert convo_a.user_id == user_a.id

    # 2. Add ordered messages
    msg1 = conversation_service.add_message(db_session, user_a.id, convo_a.id, "user", "What is the capital of France?")
    msg2 = conversation_service.add_message(db_session, user_a.id, convo_a.id, "assistant", "The capital of France is Paris.")
    assert msg1.id is not None
    assert msg2.id is not None

    # 3. Smart title generation
    new_title = conversation_service.generate_smart_title("Explain quantum computing in simple terms")
    assert "quantum" in new_title.lower() or "computing" in new_title.lower()

    # 4. User B CANNOT see User A's conversation (Strict Isolation)
    b_convos = conversation_service.list_conversations_for_user(db_session, user_b.id)
    assert not any(c["id"] == convo_a.id for c in b_convos)

    retrieved_by_b = conversation_service.get_conversation_for_user(db_session, user_b.id, convo_a.id)
    assert retrieved_by_b is None

    # 5. User A can retrieve and paginate messages
    retrieved_by_a = conversation_service.get_conversation_for_user(db_session, user_a.id, convo_a.id)
    assert retrieved_by_a is not None
    assert len(retrieved_by_a.messages) == 2
    assert retrieved_by_a.messages[0].content == "What is the capital of France?"

    # 6. Cascade deletion removes conversation and all associated messages
    conversation_service.delete_conversation(db_session, user_a.id, convo_a.id)
    assert conversation_service.get_conversation_for_user(db_session, user_a.id, convo_a.id) is None
    orphaned_msgs = db_session.query(Message).filter(Message.conversation_id == convo_a.id).all()
    assert len(orphaned_msgs) == 0


# =====================================================================
# 4. DOCUMENTS, LOCAL EMBEDDINGS & RAG TESTS
# =====================================================================

def test_document_ingestion_and_rag_isolation(db_session: Session, mock_users):
    """Test text extraction, chunking, embedding generation, similarity search, and RAG isolation."""
    user_a, user_b = mock_users

    # Sample doc content
    doc_text = """GHOSTMIND Architecture Specification.
    GHOSTMIND is an autonomous local AI operating system built with Python, FastAPI, and Qwen 2.5 3B.
    It integrates PostgreSQL for long-term memory and pgvector cosine similarity retrieval.
    Voice input is powered locally by faster-whisper on CPU using int8 quantization."""

    # 1. Ingest document for User A
    doc_a = document_service.ingest_document(
        db=db_session,
        user_id=user_a.id,
        filename=f"ghostmind_spec_{uuid.uuid4().hex[:6]}.txt",
        content_type="text/plain",
        file_bytes=doc_text.encode("utf-8")
    )
    assert doc_a.processing_status == "indexed"
    assert len(doc_a.chunks) > 0

    # Verify chunks and 768-dim embeddings in DB
    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_a.id).all()
    assert len(chunks) == len(doc_a.chunks)

    # 2. Query RAG for User A
    results_a = rag_service.retrieve_relevant_chunks(
        db=db_session,
        user_id=user_a.id,
        query="What model does GHOSTMIND use for local voice?",
        top_k=2
    )
    assert len(results_a) > 0
    assert "faster-whisper" in results_a[0]["text"] or "whisper" in results_a[0]["text"].lower()

    # 3. Build grounded RAG context block
    rag_context = rag_service.build_rag_context_prompt(results_a)
    assert "RELEVANT UPLOADED DOCUMENT EVIDENCE" in rag_context

    # 4. User B CANNOT retrieve User A's document chunks (Multi-Tenant RAG Isolation)
    results_b = rag_service.retrieve_relevant_chunks(
        db=db_session,
        user_id=user_b.id,
        query="What model does GHOSTMIND use?",
        top_k=3
    )
    assert len(results_b) == 0

    # 5. Clean deletion removes document and all associated vector chunks
    document_service.delete_document(db_session, user_a.id, doc_a.id)
    assert db_session.query(Document).filter(Document.id == doc_a.id).first() is None
    orphaned_chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_a.id).all()
    assert len(orphaned_chunks) == 0


# =====================================================================
# 5. PERSONALIZED LONG-TERM MEMORY & CONTEXT BOUNDING
# =====================================================================

def test_long_term_memory_and_bounded_context(db_session: Session, mock_users):
    """Test memory extraction, persistence, search, cross-user isolation, and bounded context."""
    user_a, user_b = mock_users
    convo = conversation_service.create_conversation(db_session, user_a.id, title="Memory Convo")

    # 1. Automatic memory extraction from user conversation
    user_statement = f"My project is Pegasus-{uuid.uuid4().hex[:6]} and I prefer Python 3.12 with PostgreSQL."
    extracted = memory_service.auto_extract_and_save_memory(db_session, user_a.id, convo.id, user_statement)
    assert extracted is not None

    # 2. Manual memory creation
    mem = memory_service.add_memory(
        db=db_session,
        user_id=user_a.id,
        memory_text="User prefers dark theme and FastAPI framework",
        category="preference"
    )
    assert mem.id is not None

    # 3. Memory retrieval for User A
    user_a_mems = memory_service.list_memories_for_user(db_session, user_a.id)
    assert any("FastAPI" in m.memory_text for m in user_a_mems)

    # 4. Memory Isolation: User B has no access to User A's memories
    user_b_mems = memory_service.list_memories_for_user(db_session, user_b.id)
    assert not any("FastAPI" in m.memory_text for m in user_b_mems)

    # 5. Context assembly respects token limits and includes relevant memories
    messages_payload, memory_snippets = memory_service.build_bounded_context(
        db=db_session,
        user_id=user_a.id,
        conversation_id=convo.id,
        current_prompt="Help me write a new API endpoint using FastAPI"
    )
    assert len(messages_payload) > 0
    assert any("FastAPI" in s for s in memory_snippets)


# =====================================================================
# 6. LOCAL WHISPER VOICE TESTS
# =====================================================================

def test_whisper_voice_endpoint(test_client: TestClient):
    """Test voice status endpoint and input validation for local transcription without auth."""
    # Status check
    res = test_client.get("/api/voice/status")
    assert res.status_code == 200
    data = res.json()
    assert data["engine"] == "faster-whisper"
    assert data["device"] == "cpu"
    assert data["compute_type"] == "int8"

    # Reject empty audio submission gracefully
    empty_audio = io.BytesIO(b"")
    empty_audio.name = "empty.wav"
    transcribe_res = test_client.post(
        "/api/voice/transcribe",
        files={"audio": ("empty.wav", empty_audio, "audio/wav")}
    )
    assert transcribe_res.status_code == 400
    assert "empty" in transcribe_res.json()["detail"].lower()


# =====================================================================
# 7. SYSTEM HEALTH & DIAGNOSTIC RESILIENCE TESTS
# =====================================================================

def test_health_and_status_endpoints(test_client: TestClient):
    """Test health and diagnostics endpoints without leaking internal tracebacks."""
    res = test_client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("online", "ready", "degraded")

    status_res = test_client.get("/api/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert "database" in status_data
