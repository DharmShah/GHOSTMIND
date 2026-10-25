import json
import uuid
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from langchain_ollama import ChatOllama

from core.config import settings
import ollama_service
from models import User
from services import conversation_service, rag_service, memory_service

logger = logging.getLogger("ghostmind.chat")

_chat_model = None

def get_chat_model():
    """Lazy loads and caches the LangChain ChatOllama model."""
    global _chat_model
    if _chat_model is None:
        _chat_model = ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0.3
        )
    return _chat_model

def execute_chat_turn(
    db: Session,
    user: User,
    message: str,
    conversation_id: Optional[uuid.UUID] = None,
    document_ids: Optional[List[uuid.UUID]] = None
) -> Dict[str, Any]:
    """
    Executes the full GHOSTMIND AI pipeline:
    User Message -> DB Persistence -> Memory Extraction -> RAG Retrieval
    -> Bounded Context Assembly -> Local LLM Generation -> Assistant DB Persistence
    -> Output with Source Attribution
    """
    cleaned_prompt = message.strip()
    if not cleaned_prompt:
        raise ValueError("Message cannot be empty.")

    # 1. Get or create conversation
    if conversation_id:
        conv = conversation_service.get_conversation_for_user(db, user.id, conversation_id)
        if not conv:
            conv = conversation_service.create_conversation(db, user.id)
    else:
        conv = conversation_service.create_conversation(db, user.id)

    # 2. Persist user message in PostgreSQL
    user_msg = conversation_service.add_message(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        role="user",
        content=cleaned_prompt
    )

    # 3. Auto-extract stable project/preference memory if detected
    extracted_mem = memory_service.auto_extract_and_save_memory(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        user_message=cleaned_prompt
    )

    # 4. Local RAG retrieval from user's indexed documents
    retrieved_chunks = rag_service.retrieve_relevant_chunks(
        db=db,
        user_id=user.id,
        query=cleaned_prompt,
        top_k=settings.MAX_RAG_CHUNKS,
        filter_document_ids=document_ids
    )
    rag_prompt_block = rag_service.build_rag_context_prompt(retrieved_chunks)

    # 5. Assemble bounded context
    bounded_messages, active_memory_texts = memory_service.build_bounded_context(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        current_prompt=cleaned_prompt,
        rag_context=rag_prompt_block,
        exclude_message_id=user_msg.id
    )

    # 6. Check Ollama system readiness
    readiness = ollama_service.check_system_readiness()
    if not readiness.get("ready"):
        error_reply = (
            f"Local model unavailable ({readiness.get('message')}). "
            "Please ensure Ollama is running on http://127.0.0.1:11434 with model 'qwen2.5:3b'."
        )
        conversation_service.add_message(
            db=db,
            user_id=user.id,
            conversation_id=conv.id,
            role="assistant",
            content=error_reply
        )
        return {
            "conversation_id": str(conv.id),
            "title": conv.title,
            "response": error_reply,
            "sources": [],
            "memories": active_memory_texts
        }

    # 7. Invoke local LLM
    try:
        llm = get_chat_model()
        result = llm.invoke(bounded_messages)
        assistant_reply = result.content if hasattr(result, "content") else str(result)
    except Exception as e:
        logger.error(f"Ollama invocation error: {e}")
        assistant_reply = f"Sorry, I encountered an issue communicating with your local model: {e}"

    # 8. Save assistant reply in PostgreSQL with source metadata
    sources_metadata = [
        {
            "filename": c["filename"],
            "page": c.get("page"),
            "score": c["score"],
            "preview": c["text"][:120] + "..." if len(c["text"]) > 120 else c["text"]
        }
        for c in retrieved_chunks
    ]

    conversation_service.add_message(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        role="assistant",
        content=assistant_reply,
        metadata={"sources": sources_metadata} if sources_metadata else None
    )

    # Refresh conversation to get updated title
    db.refresh(conv)

    return {
        "conversation_id": str(conv.id),
        "title": conv.title,
        "response": assistant_reply,
        "sources": sources_metadata,
        "memories": active_memory_texts
    }
