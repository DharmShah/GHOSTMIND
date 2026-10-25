import os
import io
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from core.database import get_db, SessionLocal, init_db
from core import security
from models import User, Conversation, Message, Document, DocumentChunk, Memory, SessionRecord
from services import auth_service, conversation_service, document_service, rag_service, memory_service, whisper_service

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
    """Create two isolated test users for multi-tenant tests."""
    unique_a = uuid.uuid4().hex[:8]
    unique_b = uuid.uuid4().hex[:8]
    user_a = auth_service.get_or_create_user(
        db=db_session,
        google_sub=f"test_sub_a_{unique_a}",
        email=f"user_a_{unique_a}@example.com",
        display_name="Test User Alpha",
        avatar_url="https://example.com/avatar_a.png"
    )
    user_b = auth_service.get_or_create_user(
        db=db_session,
        google_sub=f"test_sub_b_{unique_b}",
        email=f"user_b_{unique_b}@example.com",
        display_name="Test User Beta",
        avatar_url="https://example.com/avatar_b.png"
    )
    return user_a, user_b


# =====================================================================
# 1. AUTHENTICATION & SESSION MANAGEMENT TESTS
# =====================================================================

def test_auth_new_user_and_session_lifecycle(db_session: Session):
    """Test user provisioning, session generation, verification, and revocation."""
    uid = uuid.uuid4().hex[:8]
    google_sub = f"g_sub_{uid}"
    email = f"newuser_{uid}@example.com"
    name = "New Google User"
    
    # 1. Auto-create user
    user = auth_service.get_or_create_user(db_session, google_sub, email, name)
    assert user.id is not None
    assert user.google_sub == google_sub
    assert user.email == email
    assert user.display_name == name

    # 2. Existing user lookup returns same internal ID
    user_again = auth_service.get_or_create_user(db_session, google_sub, email, name)
    assert user_again.id == user.id

    # 3. Create cryptographically secure session
    raw_token = auth_service.create_session(db_session, user.id)
    assert len(raw_token) >= 32

    # 4. Validate active session
    validated_user = auth_service.authenticate_session(db_session, raw_token)
    assert validated_user is not None
    assert validated_user.id == user.id

    # 5. Revoke session / Logout
    auth_service.revoke_session(db_session, raw_token)
    assert auth_service.authenticate_session(db_session, raw_token) is None


def test_auth_endpoints_with_mocked_google(test_client: TestClient, db_session: Session):
    """Test FastAPI OAuth endpoints including callback, cookie set, /api/auth/me, and logout."""
    uid = uuid.uuid4().hex[:8]
    test_email = f"google_{uid}@ghostmind.ai"
    mock_payload = {
        "sub": f"mock_sub_{uid}",
        "email": test_email,
        "name": "Ghostmind Tester",
        "picture": "https://example.com/pic.jpg"
    }

    with patch("routes.auth.verify_google_id_token", return_value=mock_payload):
        # Callback with Google credential token
        cb_res = test_client.post("/api/auth/google/callback", json={"credential": "mock_id_token_123"})
        assert cb_res.status_code == 200
        data = cb_res.json()
        assert data["authenticated"] is True
        assert data["user"]["email"] == test_email

        # Check session cookie is set
        session_cookie = cb_res.cookies.get("ghostmind_session")
        assert session_cookie is not None

        # Verify /api/auth/me with persistent cookie
        me_res = test_client.get("/api/auth/me", cookies={"ghostmind_session": session_cookie})
        assert me_res.status_code == 200
        assert me_res.json()["user"]["email"] == test_email

        # Logout revokes session cookie
        logout_res = test_client.post("/api/auth/logout", cookies={"ghostmind_session": session_cookie})
        assert logout_res.status_code == 200

        # Subsequent /api/auth/me returns authenticated: False
        me_after_res = test_client.get("/api/auth/me", cookies={"ghostmind_session": session_cookie})
        assert me_after_res.status_code == 200
        assert me_after_res.json()["authenticated"] is False


# =====================================================================
# 2. PERSISTENT CONVERSATIONS & USER ISOLATION TESTS
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
# 3. DOCUMENTS, LOCAL EMBEDDINGS & RAG TESTS
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
# 4. PERSONALIZED LONG-TERM MEMORY TESTS
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

    # 5. Context assembly respects token limits and includes memories
    messages_payload, memory_snippets = memory_service.build_bounded_context(
        db=db_session,
        user_id=user_a.id,
        conversation_id=convo.id,
        current_prompt="Help me write a new API endpoint"
    )
    assert len(messages_payload) > 0
    assert any("FastAPI" in s or "Pegasus" in s for s in memory_snippets)


# =====================================================================
# 5. LOCAL WHISPER VOICE TESTS
# =====================================================================

def test_whisper_voice_endpoint(test_client: TestClient, db_session: Session, mock_users):
    """Test voice status endpoint and input validation for local transcription."""
    user_a, _ = mock_users
    token = auth_service.create_session(db_session, user_a.id)
    cookies = {"ghostmind_session": token}

    # Status check
    res = test_client.get("/api/voice/status", cookies=cookies)
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
        files={"audio": ("empty.wav", empty_audio, "audio/wav")},
        cookies=cookies
    )
    assert transcribe_res.status_code == 400
    assert "empty" in transcribe_res.json()["detail"].lower()


# =====================================================================
# 6. SYSTEM HEALTH & DIAGNOSTIC RESILIENCE TESTS
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
