import json
import uuid
import re
import asyncio
import concurrent.futures
import logging
from typing import Dict, Any, List, Optional, Generator
from sqlalchemy.orm import Session
from langchain_ollama import ChatOllama

from core.config import settings
import ollama_service
from models import User
from services import conversation_service, rag_service, memory_service, web_search_service
from services.query_classifier import classify_query, QueryCategory
from services.research_agent import research_agent
from services.answer_validation_service import validate_citations_and_format
from mcp.manager import mcp_manager
from mcp.tool_registry import tool_registry
from mcp.models import ToolExecutionRequest, ConnectionStatus

logger = logging.getLogger("ghostmind.chat")

def get_chat_model(temperature: Optional[float] = None) -> ChatOllama:
    """
    Creates or returns a CPU-optimized LangChain ChatOllama instance.
    Uses configurable temperature (default 0.7), context window, and max tokens.
    """
    temp = temperature if temperature is not None else settings.DEFAULT_TEMPERATURE
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=temp,
        num_ctx=settings.OLLAMA_NUM_CTX,
        num_predict=settings.MAX_OUTPUT_TOKENS,
        top_k=settings.OLLAMA_TOP_K,
        top_p=settings.OLLAMA_TOP_P,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS
    )

def prepare_chat_turn_stream(
    db: Session,
    user: User,
    message: str,
    conversation_id: Optional[uuid.UUID] = None,
    document_ids: Optional[List[uuid.UUID]] = None,
    enable_web_search: bool = True,
    enable_rag: bool = True
) -> Generator[tuple, None, None]:
    """
    Common preparation pipeline generator:
    - Normalizes prompt
    - Retrieves or creates conversation
    - Persists user turn
    - Auto-extracts memory
    - Retrieves RAG chunks (if enabled)
    - Runs hybrid internet research with real-time stage status updates
    - Assembles bounded context payload with grounding instructions
    Yields ("status", message) during research, and finally ("prep", prep_dict).
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

    # 1b. Check for Natural Language MCP Integration Discovery Intent (e.g. "Connect Figma", "Connect GitHub")
    integration_intent = mcp_manager.detect_intent(cleaned_prompt)
    if integration_intent and integration_intent.get("catalog_item"):
        catalog_item = integration_intent["catalog_item"]
        is_disconnect = (integration_intent.get("action") == "disconnect")
        if is_disconnect:
            discovery_reply = f"To disconnect **{catalog_item.display_name}**, you can click Disconnect in the Connected Services panel in the sidebar."
        else:
            is_connected = bool(mcp_manager.connection_manager.get_server_status(catalog_item.name) == ConnectionStatus.CONNECTED)
            discovery_reply = mcp_manager.format_discovery_response(catalog_item, is_connected=is_connected)

        # Persist user message
        conversation_service.add_message(
            db=db,
            user_id=user.id,
            conversation_id=conv.id,
            role="user",
            content=cleaned_prompt
        )

        yield ("prep", {
            "conv": conv,
            "bounded_messages": [],
            "sources_metadata": [],
            "active_memory_texts": [],
            "web_search_performed": False,
            "rag_performed": False,
            "direct_reply": discovery_reply,
            "classification_category": "intent_discovery",
            "verification_status": "Verified"
        })
        return

    # 2. Persist user message in PostgreSQL
    user_msg = conversation_service.add_message(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        role="user",
        content=cleaned_prompt
    )

    # 3. Auto-extract stable facts/preferences
    memory_service.auto_extract_and_save_memory(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        user_message=cleaned_prompt
    )

    # 4. Local RAG retrieval
    retrieved_chunks = []
    rag_prompt_block = ""
    if enable_rag:
        retrieved_chunks = rag_service.retrieve_relevant_chunks(
            db=db,
            user_id=user.id,
            query=cleaned_prompt,
            top_k=settings.MAX_RAG_CHUNKS,
            min_similarity=settings.RAG_SIMILARITY_THRESHOLD,
            filter_document_ids=document_ids
        )
        rag_prompt_block = rag_service.build_rag_context_prompt(retrieved_chunks)

    # 5. Hybrid Research with Intelligent Query Classification
    internet_online = web_search_service.is_internet_available()
    web_prompt_block = ""
    web_sources = []
    has_doc_context = bool(document_ids or retrieved_chunks)

    classification = classify_query(cleaned_prompt, has_document_context=has_doc_context)
    verification_status = "Local Model Knowledge"

    if enable_web_search and classification.requires_web_search:
        for item_type, data in research_agent.execute_research_stream(cleaned_prompt, classification):
            if item_type == "status":
                yield ("status", data)
            elif item_type == "result":
                research_result = data
                if research_result and research_result.get("success"):
                    web_prompt_block = research_result.get("research_context", "")
                    web_sources = research_result.get("sources", [])
                    verif = research_result.get("verification")
                    verification_status = verif.overall_status if verif else "Verified"
                elif research_result and research_result.get("offline"):
                    web_prompt_block = research_result.get("research_context", "")
                    verification_status = "Offline"
                else:
                    verification_status = "Unverified"
    elif enable_web_search and not classification.requires_web_search:
        # Local knowledge sufficient for stable concepts (General Knowledge / Personal Context)
        verification_status = "Local Knowledge Sufficient"

    # 6. Assemble bounded context
    bounded_messages, active_memory_texts = memory_service.build_bounded_context(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        current_prompt=cleaned_prompt,
        rag_context=rag_prompt_block,
        web_context=web_prompt_block,
        internet_online=internet_online,
        exclude_message_id=user_msg.id
    )

    # 6b. Ensure active MCP tools are synchronized and inject relevant tools
    mcp_manager.ensure_tools_loaded(user.id, db)
    relevant_tools = tool_registry.filter_relevant_tools(cleaned_prompt, max_tools=3)
    if relevant_tools:
        tools_block = tool_registry.format_tools_for_llm(relevant_tools)
        if bounded_messages and bounded_messages[0]["role"] == "system":
            bounded_messages[0]["content"] += "\n" + tools_block

    # 7. Collect sources metadata
    sources_metadata = [
        {
            "filename": c["filename"],
            "title": c["filename"],
            "url": None,
            "domain": "local_document",
            "page": c.get("page"),
            "score": c["score"],
            "preview": c["text"][:120] + "..." if len(c["text"]) > 120 else c["text"]
        }
        for c in retrieved_chunks
    ]
    if web_sources:
        sources_metadata.extend(web_sources)

    yield ("prep", {
        "conv": conv,
        "bounded_messages": bounded_messages,
        "sources_metadata": sources_metadata,
        "active_memory_texts": active_memory_texts,
        "web_search_performed": bool(web_sources),
        "rag_performed": bool(retrieved_chunks),
        "classification_category": classification.category.value,
        "verification_status": verification_status,
        "web_sources": web_sources
    })

def prepare_chat_turn(
    db: Session,
    user: User,
    message: str,
    conversation_id: Optional[uuid.UUID] = None,
    document_ids: Optional[List[uuid.UUID]] = None,
    enable_web_search: bool = True,
    enable_rag: bool = True
) -> Dict[str, Any]:
    """Synchronous wrapper for prepare_chat_turn_stream."""
    final_prep = None
    for event_type, payload in prepare_chat_turn_stream(
        db=db,
        user=user,
        message=message,
        conversation_id=conversation_id,
        document_ids=document_ids,
        enable_web_search=enable_web_search,
        enable_rag=enable_rag
    ):
        if event_type == "prep":
            final_prep = payload
    return final_prep or {}

def extract_tool_invocation(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extracts tool invocation JSON from various LLM formatting styles."""
    if not text:
        return None

    # 1. Standard pattern: <<<TOOL_INVOCATION: {...}>>> or with loose closing brackets
    match = re.search(r'<<<TOOL_INVOCATION:\s*(\{.*?\})\s*(?:>{1,4}|$|=|"|\')', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # 2. Markdown fenced block: ```json {"server": ...} ```
    block_match = re.search(r'```(?:json|tool)?\s*(\{[\s\S]*?"server"[\s\S]*?"tool"[\s\S]*?\})\s*```', text)
    if block_match:
        try:
            return json.loads(block_match.group(1))
        except Exception:
            pass

    # 3. Direct JSON structure containing server and tool keys
    json_match = re.search(r'(\{[\s\S]*?"server"\s*:\s*"[^"]+"\s*,\s*"tool"\s*:\s*"[^"]+"[\s\S]*?\})', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except Exception:
            pass

    return None

def handle_tool_call_interception(reply: str, user: User, conv: Any, db: Session) -> str:
    """Detects and intercepts tool calls emitted by Qwen 2.5 3B."""
    data = extract_tool_invocation(reply)
    if not data:
        return reply

    try:
        server_name = data.get("server")
        tool_name = data.get("tool")
        arguments = data.get("arguments", {})

        req = ToolExecutionRequest(
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            conversation_id=str(conv.id)
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(asyncio.run, mcp_manager.execute_tool(req, user.id, db)).result(timeout=35.0)

        if result.requires_confirmation:
            formatted_args = "\n".join([f"- **{k.replace('_', ' ').capitalize()}**: `{v}`" for k, v in arguments.items()])
            return (
                f"### ⚠️ Action Confirmation Required\n\n"
                f"I have prepared the requested action:\n\n"
                f"• **Action:** {tool_name.replace('_', ' ').title()}\n"
                f"• **Service:** {server_name.title()}\n\n"
                f"**Parameters:**\n{formatted_args}\n\n"
                f"Please confirm to proceed with this operation.\n\n"
                f"[CONFIRM_ACTION:{result.pending_action_id}]"
            )
        elif result.success:
            return f"**{server_name.title()} Tool Output (`{tool_name}`):**\n\n{result.data}"
        else:
            return f"Notice: Tool execution error on `{tool_name}`: {result.error}"
    except Exception as e:
        logger.error(f"Error executing intercepted tool: {e}")
        return reply

def execute_chat_turn(
    db: Session,
    user: User,
    message: str,
    conversation_id: Optional[uuid.UUID] = None,
    document_ids: Optional[List[uuid.UUID]] = None,
    temperature: Optional[float] = None,
    enable_web_search: bool = True,
    enable_rag: bool = True
) -> Dict[str, Any]:
    """Synchronous chat turn execution."""
    prep = prepare_chat_turn(
        db=db,
        user=user,
        message=message,
        conversation_id=conversation_id,
        document_ids=document_ids,
        enable_web_search=enable_web_search,
        enable_rag=enable_rag
    )
    conv = prep["conv"]
    bounded_messages = prep["bounded_messages"]
    sources_metadata = prep["sources_metadata"]
    active_memory_texts = prep["active_memory_texts"]

    # Direct integration discovery reply
    if prep.get("direct_reply"):
        direct_reply = prep["direct_reply"]
        conversation_service.add_message(
            db=db,
            user_id=user.id,
            conversation_id=conv.id,
            role="assistant",
            content=direct_reply
        )
        return {
            "conversation_id": str(conv.id),
            "title": conv.title,
            "response": direct_reply,
            "sources": [],
            "memories": active_memory_texts
        }

    # Check Ollama readiness
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

    # Invoke local model
    try:
        llm = get_chat_model(temperature=temperature)
        result = llm.invoke(bounded_messages)
        assistant_reply = result.content if hasattr(result, "content") else str(result)
    except Exception as e:
        logger.error(f"Ollama invocation error: {e}")
        assistant_reply = f"Sorry, I encountered an issue communicating with your local model: {e}"

    # Intercept tool calls or confirmation requests
    intercepted = handle_tool_call_interception(assistant_reply, user, conv, db)
    badge = "Local Knowledge"
    val_status = prep.get("verification_status", "Unverified")

    if intercepted != assistant_reply:
        assistant_reply = intercepted
    else:
        # Validate citations and format response
        val_res = validate_citations_and_format(
            raw_response=assistant_reply,
            retrieved_sources=sources_metadata,
            query_category=prep.get("classification_category")
        )
        assistant_reply = val_res["sanitized_response"]
        badge = val_res["knowledge_source_badge"]

    # Persist assistant reply
    conversation_service.add_message(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        role="assistant",
        content=assistant_reply,
        metadata={
            "sources": sources_metadata,
            "knowledge_source_badge": badge,
            "verification_status": val_status
        } if sources_metadata or badge else None
    )

    db.refresh(conv)

    return {
        "conversation_id": str(conv.id),
        "title": conv.title,
        "response": assistant_reply,
        "sources": sources_metadata,
        "memories": active_memory_texts,
        "knowledge_source_badge": badge,
        "verification_status": val_status
    }

def execute_chat_turn_stream(
    db: Session,
    user: User,
    message: str,
    conversation_id: Optional[uuid.UUID] = None,
    document_ids: Optional[List[uuid.UUID]] = None,
    temperature: Optional[float] = None,
    enable_web_search: bool = True,
    enable_rag: bool = True
) -> Generator[str, None, None]:
    """Streaming chat turn execution using Server-Sent Events (SSE)."""
    prep = None
    for event_type, payload in prepare_chat_turn_stream(
        db=db,
        user=user,
        message=message,
        conversation_id=conversation_id,
        document_ids=document_ids,
        enable_web_search=enable_web_search,
        enable_rag=enable_rag
    ):
        if event_type == "status":
            yield f"data: {json.dumps({'type': 'status', 'message': payload})}\n\n"
        elif event_type == "prep":
            prep = payload

    if not prep:
        return

    conv = prep["conv"]
    bounded_messages = prep["bounded_messages"]
    sources_metadata = prep["sources_metadata"]
    active_memory_texts = prep["active_memory_texts"]
    val_status = prep.get("verification_status", "Unverified")

    # Yield initial start event with metadata
    start_payload = {
        "type": "start",
        "conversation_id": str(conv.id),
        "title": conv.title,
        "sources": sources_metadata,
        "memories": active_memory_texts,
        "web_search_performed": prep.get("web_search_performed", False),
        "rag_performed": prep.get("rag_performed", False),
        "verification_status": val_status
    }
    yield f"data: {json.dumps(start_payload)}\n\n"

    # Direct integration discovery response
    if prep.get("direct_reply"):
        direct_reply = prep["direct_reply"]
        conversation_service.add_message(
            db=db,
            user_id=user.id,
            conversation_id=conv.id,
            role="assistant",
            content=direct_reply
        )
        yield f"data: {json.dumps({'type': 'delta', 'text': direct_reply})}\n\n"
        done_payload = {
            "type": "done",
            "conversation_id": str(conv.id),
            "title": conv.title,
            "response": direct_reply,
            "sources": [],
            "knowledge_source_badge": "Local Knowledge",
            "verification_status": "Verified"
        }
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    # Check Ollama readiness
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
        err_payload = {"type": "delta", "text": error_reply}
        yield f"data: {json.dumps(err_payload)}\n\n"
        done_payload = {
            "type": "done",
            "conversation_id": str(conv.id),
            "title": conv.title,
            "response": error_reply,
            "sources": [],
            "knowledge_source_badge": "Local Knowledge",
            "verification_status": "Unavailable"
        }
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    # Yield status that LLM generation is starting
    yield f"data: {json.dumps({'type': 'status', 'message': 'Generating grounded response...'})}\n\n"

    # Stream from ChatOllama
    collected_tokens = []
    try:
        llm = get_chat_model(temperature=temperature)
        for chunk in llm.stream(bounded_messages):
            token_text = chunk.content if hasattr(chunk, "content") else str(chunk)
            collected_tokens.append(token_text)
            delta_payload = {"type": "delta", "text": token_text}
            yield f"data: {json.dumps(delta_payload)}\n\n"
    except Exception as e:
        logger.error(f"Streaming invocation error: {e}")
        err_text = f"\n\n[Error communicating with local model: {e}]"
        collected_tokens.append(err_text)
        yield f"data: {json.dumps({'type': 'delta', 'text': err_text})}\n\n"

    full_response = "".join(collected_tokens)

    # Intercept tool calls
    intercepted = handle_tool_call_interception(full_response, user, conv, db)
    badge = "Local Knowledge"
    if intercepted != full_response:
        full_response = intercepted
        yield f"data: {json.dumps({'type': 'replace', 'text': full_response})}\n\n"
    else:
        # Validate citations and clean hallucinations
        val_res = validate_citations_and_format(
            raw_response=full_response,
            retrieved_sources=sources_metadata,
            query_category=prep.get("classification_category")
        )
        sanitized = val_res["sanitized_response"]
        badge = val_res["knowledge_source_badge"]
        if sanitized != full_response:
            full_response = sanitized
            yield f"data: {json.dumps({'type': 'replace', 'text': full_response})}\n\n"

    # Persist assistant reply
    conversation_service.add_message(
        db=db,
        user_id=user.id,
        conversation_id=conv.id,
        role="assistant",
        content=full_response,
        metadata={
            "sources": sources_metadata,
            "knowledge_source_badge": badge,
            "verification_status": val_status
        } if sources_metadata or badge else None
    )

    db.refresh(conv)

    done_payload = {
        "type": "done",
        "conversation_id": str(conv.id),
        "title": conv.title,
        "response": full_response,
        "sources": sources_metadata,
        "knowledge_source_badge": badge,
        "verification_status": val_status,
        "web_search_performed": prep.get("web_search_performed", False),
        "rag_performed": prep.get("rag_performed", False)
    }
    yield f"data: {json.dumps(done_payload)}\n\n"
