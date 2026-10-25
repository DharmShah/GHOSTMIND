import os
import io
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from core.database import SessionLocal, init_db
from models import User, Conversation, Message, Document, Memory
from services import auth_service, conversation_service, document_service, memory_service, chat_service

@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def test_client():
    return TestClient(app)

@pytest.fixture
def test_user(db_session: Session):
    unique = uuid.uuid4().hex[:8]
    return auth_service.get_or_create_user(
        db=db_session,
        google_sub=f"test_sub_ext_{unique}",
        email=f"ext_user_{unique}@ghostmind.ai",
        display_name="Extended Test User"
    )

def test_long_conversation_message_pagination(db_session: Session, test_user: User):
    """Test pagination, message ordering, and bounds handling for high-volume chats."""
    convo = conversation_service.create_conversation(db_session, test_user.id, title="Large Chat")
    
    # Insert 40 messages
    for i in range(1, 41):
        role = "user" if i % 2 == 1 else "assistant"
        conversation_service.add_message(
            db=db_session,
            user_id=test_user.id,
            conversation_id=convo.id,
            role=role,
            content=f"Turn message sequence {i}"
        )

    # Fetch page 1 (first 20)
    page1 = conversation_service.get_conversation_for_user(
        db=db_session,
        user_id=test_user.id,
        conversation_id=convo.id,
        message_limit=20,
        message_offset=0
    )
    assert len(page1.messages) == 20
    assert page1.messages[0].content == "Turn message sequence 1"
    assert page1.messages[19].content == "Turn message sequence 20"

    # Fetch page 2 (remaining 20)
    page2 = conversation_service.get_conversation_for_user(
        db=db_session,
        user_id=test_user.id,
        conversation_id=convo.id,
        message_limit=20,
        message_offset=20
    )
    assert len(page2.messages) == 20
    assert page2.messages[0].content == "Turn message sequence 21"
    assert page2.messages[19].content == "Turn message sequence 40"

    # Cleanup
    conversation_service.delete_conversation(db_session, test_user.id, convo.id)

def test_file_upload_validation_rejects_disallowed_types(db_session: Session, test_user: User):
    """Test that unauthorized formats (e.g. .exe, .bat, .sh) are safely rejected."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        document_service.ingest_document(
            db=db_session,
            user_id=test_user.id,
            filename="malicious.exe",
            content_type="application/octet-stream",
            file_bytes=b"MZ\x90\x00\x03\x00\x00\x00"
        )

def test_chat_pipeline_with_mocked_ollama(test_client: TestClient, db_session: Session, test_user: User):
    """Test the complete end-to-end chat pipeline: user -> RAG & Memory -> Ollama -> persistent response."""
    token = auth_service.create_session(db_session, test_user.id)
    cookies = {"ghostmind_session": token}

    mock_llm_response = "GHOSTMIND has processed your request locally."

    mock_llm = MagicMock()
    mock_result = MagicMock()
    mock_result.content = mock_llm_response
    mock_llm.invoke.return_value = mock_result

    with patch("services.chat_service.ollama_service.check_system_readiness", return_value={"ready": True}), \
         patch("services.chat_service.get_chat_model", return_value=mock_llm):
        res = test_client.post(
            "/api/chat",
            json={"message": "Can you explain our tech stack?"},
            cookies=cookies
        )
        assert res.status_code == 200
        data = res.json()
        assert data["response"] == mock_llm_response
        assert data["conversation_id"] is not None

        # Verify message was stored in database
        convo_id = uuid.UUID(data["conversation_id"])
        conv = conversation_service.get_conversation_for_user(db_session, test_user.id, convo_id)
        assert conv is not None
        assert len(conv.messages) == 2
        assert conv.messages[0].role == "user"
        assert conv.messages[0].content == "Can you explain our tech stack?"
        assert conv.messages[1].role == "assistant"
        assert conv.messages[1].content == mock_llm_response

        # Cleanup
        conversation_service.delete_conversation(db_session, test_user.id, convo_id)
