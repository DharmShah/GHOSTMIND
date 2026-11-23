import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional

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
    has_memories: bool = False
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

    # 7. Latest Information (Category B)
    latest_indicators = [
        "latest", "recent", "newest", "what's new", "what changed",
        "version of", "current version", "release", "released in",
        "roadmap", "pricing", "updates"
    ]
    if explicit_search or mentions_modern_tech or any(li in cleaned for li in latest_indicators):
        clean_target = clean_query_text(query)
        return QueryClassification(
            category=QueryCategory.LATEST_INFO,
            requires_web_search=True,
            requires_rag=False,
            required_freshness="recent",
            search_topics=[clean_target],
            verification_targets=["version", "release_date", "features"],
            reason="Query asks for recent or post-cutoff information requiring web research."
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

