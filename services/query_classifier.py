import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from services.web_intelligence_service import (
    SearchIntent,
    extract_financial_entities,
    classify_search_intent,
    build_authoritative_search_queries,
)

class QueryCategory(str, Enum):
    GENERAL_KNOWLEDGE = "general_knowledge"       # A. Stable CS/math/science concepts (local LLM sufficient)
    LATEST_INFO = "latest_info"                   # B. Recent/post-cutoff developments (mandatory search)
    TIME_SENSITIVE = "time_sensitive"             # C. Live/temporal data like news, weather, stock, releases
    RESEARCH_COMPARISON = "research_comparison"   # D. In-depth comparisons of frameworks, models, benchmarks
    PERSONAL_PROJECT_CONTEXT = "personal_context" # E. Local codebase, architecture, personal docs/memories
    MIXED = "mixed"                               # F. Foundational concept + latest external state

@dataclass
class QueryClassification:
    category: QueryCategory
    requires_web_search: bool
    requires_rag: bool
    required_freshness: str  # "current", "recent", "stable"
    search_topics: List[str] = field(default_factory=list)
    verification_targets: List[str] = field(default_factory=list)
    reason: str = ""
    search_intent: str = SearchIntent.LOCAL_KNOWLEDGE_QUERY.value
    extracted_entities: Dict[str, Any] = field(default_factory=dict)

def clean_query_text(query: str) -> str:
    """Strips common greeting fluff and conversational prefixes."""
    q = query.strip()
    patterns = [
        r'^(?:can you|could you|please|kindly)\s+(?:tell me|search for|find out|explain|check)\s+',
        r'^(?:what is|what are|who is|who are|explain|define|tell me about)\s+',
        r'^(?:search for|google|look up|find online|browse)\s+'
    ]
    for p in patterns:
        q = re.sub(p, '', q, flags=re.IGNORECASE).strip()
    return q if q else query.strip()

def classify_query(
    query: str,
    has_document_context: bool = False,
    has_memories: bool = False,
    recent_history: Optional[List[Dict[str, str]]] = None
) -> QueryClassification:
    """
    Intelligent query classification layer.
    Categorizes the user request and determines:
    - Whether web search is required
    - Whether local RAG is required
    - Freshness requirements
    - Search topics and verification targets
    """
    cleaned = query.strip().lower()

    # 1. Personal / Project Context / Local Document Indicators
    doc_markers = [
        "in the pdf", "in my document", "in the file", "summarize my",
        "uploaded file", "uploaded document", "attached document", "this document",
        "uploaded pdf", "my pdf", "from the file", "my architecture",
        "my existing implementation", "my application", "how does my",
        "in our codebase", "in my project", "explain my"
    ]
    if has_document_context or any(m in cleaned for m in doc_markers):
        return QueryClassification(
            category=QueryCategory.PERSONAL_PROJECT_CONTEXT,
            requires_web_search=False,
            requires_rag=True,
            required_freshness="stable",
            search_topics=[],
            verification_targets=["local_document", "project_context"],
            reason="Query references local documents, project context, or uploaded files."
        )

    # 2. Chit-Chat / Simple Pleasantries
    chit_chat = {
        "hi", "hello", "hey", "hola", "howdy", "sup", "good morning",
        "good afternoon", "good evening", "good night", "how are you",
        "what's up", "thanks", "thank you", "thx", "bye", "goodbye",
        "ok", "okay", "cool", "nice", "yes", "no", "sure", "clear"
    }
    if cleaned in chit_chat or len(cleaned) < 3:
        return QueryClassification(
            category=QueryCategory.GENERAL_KNOWLEDGE,
            requires_web_search=False,
            requires_rag=False,
            required_freshness="stable",
            search_topics=[],
            verification_targets=[],
            reason="Conversational greeting or short acknowledgement."
        )

    # 3. Explicit Web Search Intent
    explicit_search = any(cleaned.startswith(p) for p in [
        "search for", "search web for", "google", "look up", "browse online", "find online"
    ]) or "search the internet" in cleaned or "search the web" in cleaned

    # 3b. Real-Time, Historical & Financial Intelligence Routing
    entities = extract_financial_entities(query, recent_history=recent_history)
    intent = classify_search_intent(query, entities=entities, has_document_context=has_document_context)

    if intent in (SearchIntent.HISTORICAL_DATA_QUERY, SearchIntent.REAL_TIME_QUERY):
        topics = build_authoritative_search_queries(query, entities, intent)
        return QueryClassification(
            category=QueryCategory.TIME_SENSITIVE,
            requires_web_search=True,
            requires_rag=False,
            required_freshness="historical" if intent == SearchIntent.HISTORICAL_DATA_QUERY else "current",
            search_topics=topics,
            verification_targets=["date", "currency", "unit", "official_source"],
            reason=f"Detected {intent.value} requiring real-time or historical web retrieval.",
            search_intent=intent.value,
            extracted_entities=entities,
        )

    # 4. Temporal & Time-Sensitive Triggers (Category C)
    temporal_triggers = [
        "current weather", "weather in", "temperature in",
        "stock price", "stock of", "market price",
        "today's news", "breaking news", "current events", "what happened today",
        "who is the current", "who won yesterday", "who won today"
    ]
    if any(t in cleaned for t in temporal_triggers):
        clean_target = clean_query_text(query)
        return QueryClassification(
            category=QueryCategory.TIME_SENSITIVE,
            requires_web_search=True,
            requires_rag=False,
            required_freshness="current",
            search_topics=[clean_target],
            verification_targets=["live_event", "current_value", "date"],
            reason="Query requests live temporal or real-time data."
        )

    # 5. Research & Comparison Triggers (Category D)
    comparison_triggers = [
        "compare", "versus", "vs", "differences between", "difference between",
        "pros and cons", "which is better", "evaluate", "benchmark"
    ]
    is_comparison = any(c in cleaned for c in comparison_triggers)

    # Post-2024 tech topics that need fresh research
    modern_tech_keywords = [
        "langgraph", "crewai", "autogen", "dspy", "deepseek", "claude 3", "claude 3.5",
        "claude 3.7", "gpt-4o", "gpt-4.5", "o1", "o3", "gemini 2", "gemini 1.5",
        "qwen 2.5", "qwen 3", "llama 3", "llama 3.1", "llama 3.2", "llama 3.3",
        "mcp", "model context protocol", "pgvector", "vllm", "ollama",
        "figma", "swiftui", "react native", "flutter",
        "latest version", "release notes", "newest", "recently released"
    ]
    mentions_modern_tech = any(k in cleaned for k in modern_tech_keywords)

    if is_comparison and mentions_modern_tech:
        # Split comparison into topics
        clean_q = clean_query_text(query)
        topics = [clean_q]
        if " and " in clean_q:
            parts = clean_q.split(" and ")
            if len(parts) == 2:
                topics = [f"{parts[0].strip()} features documentation", f"{parts[1].strip()} features documentation"]
        return QueryClassification(
            category=QueryCategory.RESEARCH_COMPARISON,
            requires_web_search=True,
            requires_rag=False,
            required_freshness="recent",
            search_topics=topics,
            verification_targets=["features", "specifications", "official_docs"],
            reason="Comparative research query across modern AI/software tools."
        )

    # 6. Mixed Questions (Category F)
    # Explaining a fundamental concept while asking about latest versions/state
    foundational_concepts = [
        "transformer", "attention mechanism", "neural network", "recursion",
        "embedding", "backpropagation", "gradient descent", "vector database"
    ]
    has_foundational = any(f in cleaned for f in foundational_concepts)
    has_latest_marker = any(m in cleaned for m in ["latest", "newest", "current", "modern", "state of the art", "sota", "2024", "2025", "2026"])

    if has_foundational and has_latest_marker:
        return QueryClassification(
            category=QueryCategory.MIXED,
            requires_web_search=True,
            requires_rag=False,
            required_freshness="recent",
            search_topics=[clean_query_text(query)],
            verification_targets=["modern_variants", "benchmarks", "current_state"],
            reason="Combines foundational concept explanation with latest developments."
        )

    # 7. Latest Information & Ambiguous Technical Acronyms / Confirmation-Bias Challenges (Category B)
    latest_indicators = [
        "latest", "recent", "newest", "what's new", "what changed",
        "version of", "current version", "release", "released in",
        "roadmap", "pricing", "updates"
    ]

    # Detect technical acronym queries (e.g. "What is MCP?", "What does RAG stand for?", "MCP means X, right?")
    acronym_matches = re.findall(r'\b([A-Z]{2,8})\b', query)
    is_acronym_question = bool(acronym_matches) and any(
        w in cleaned for w in ["what is", "what does", "stand for", "mean", "means", "acronym", "definition", "right?"]
    )

    # Detect user confirmation-bias challenges ("Are you sure?", "I think it means...", "isn't it...")
    challenge_triggers = [
        "are you sure", "i think it means", "doesn't it mean", "isn't it",
        "not ", "right?", "wrong,", "actually it means"
    ]
    is_challenge = any(ct in cleaned for ct in challenge_triggers) and any(
        w in cleaned for w in ["mean", "means", "stand for", "protocol", "framework", "sure"]
    )

    if explicit_search or mentions_modern_tech or is_acronym_question or is_challenge or any(li in cleaned for li in latest_indicators):
        clean_target = clean_query_text(query)
        # Build authoritative search topic for acronym / challenge queries
        if is_challenge and not acronym_matches and recent_history:
            # Recover the acronym/topic from recent conversation history
            history_text = " ".join(m.get("content", "") for m in recent_history[-4:])
            hist_acronyms = re.findall(r'\b([A-Z]{2,8})\b', history_text)
            if hist_acronyms:
                acronym_matches = hist_acronyms

        if "mcp" in cleaned or "MCP" in acronym_matches:
            if "another industry" in cleaned or "other industry" in cleaned or "different" in cleaned:
                clean_target = "MCP acronym meanings industries Model Context Protocol"
            else:
                clean_target = "Model Context Protocol MCP AI agents official documentation"
        elif is_acronym_question and acronym_matches:
            acr = acronym_matches[0]
            clean_target = f"{acr} technical acronym official documentation"
        elif is_challenge and acronym_matches:
            acr = acronym_matches[0]
            clean_target = f"{acr} official definition documentation"

        return QueryClassification(
            category=QueryCategory.LATEST_INFO,
            requires_web_search=True,
            requires_rag=False,
            required_freshness="recent",
            search_topics=[clean_target],
            verification_targets=["official_docs", "definition", "version"],
            reason="Query asks for recent, post-cutoff, or technical acronym/factual verification."
        )

    # 8. Foundational Programming / CS (Category A - General Knowledge)
    coding_concepts = [
        "python loop", "for loop", "while loop", "explain loop", "quicksort", "bubble sort",
        "binary search", "linked list", "fibonacci", "what is recursion", "hello world",
        "object oriented", "polymorphism", "inheritance", "regex", "sql query", "select from",
        "write a function", "write a python", "write javascript", "css style", "html tag",
        "how does a hashmap work", "time complexity", "big o", "rest api", "explain decorator",
        "what is python", "what is an api", "what is a neural network", "what is a transformer"
    ]
    if any(c in cleaned for c in coding_concepts) or not any(li in cleaned for li in latest_indicators):
        return QueryClassification(
            category=QueryCategory.GENERAL_KNOWLEDGE,
            requires_web_search=False,
            requires_rag=False,
            required_freshness="stable",
            search_topics=[],
            verification_targets=[],
            reason="Foundational concept covered sufficiently by local LLM knowledge."
        )

    # Default fallback: safe general knowledge
    return QueryClassification(
        category=QueryCategory.GENERAL_KNOWLEDGE,
        requires_web_search=False,
        requires_rag=False,
        required_freshness="stable",
        search_topics=[],
        verification_targets=[],
        reason="Defaulted to local model knowledge."
    )

