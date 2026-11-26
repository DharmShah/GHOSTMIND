import logging
from typing import Dict, Any, List, Optional, Callable, Generator
from services.query_classifier import QueryClassification, QueryCategory
from services.page_retrieval_service import retrieve_page_content, compute_authority_score, PageContent
from services.source_verification_service import evaluate_sources_and_verify, VerificationResult
from services.evidence_service import extract_evidence_claims, package_research_context
from services.web_search_service import web_search_service
from services.web_intelligence_service import SearchIntent, build_structured_evidence

logger = logging.getLogger("ghostmind.research_agent")

class InternetResearchAgent:
    """
    Autonomous multi-stage Internet Research Agent:
    - Stage 1: Query Planning
    - Stage 2: Web Search (DuckDuckGo with priority domain weighting)
    - Stage 3: Real Page Content Retrieval & Metadata/Date Extraction
    - Stage 4: Claim & Evidence Extraction
    - Stage 5: Source Cross-Verification & Conflict Detection
    - Stage 6: Evidence Packaging & Token Budgeting
    """

    def __init__(self, max_pages: int = 2, page_timeout: float = 3.0):
        self.max_pages = max_pages
        self.page_timeout = page_timeout

    def execute_research_stream(
        self,
        query: str,
        classification: QueryClassification
    ) -> Generator[tuple, None, None]:
        """
        Generator executing research stages, yielding ("status", stage_message)
        and finally ("result", research_dict).
        """
        entities = getattr(classification, "extracted_entities", {}) or {}
        search_intent_str = getattr(classification, "search_intent", SearchIntent.GENERAL_INFORMATION_QUERY.value)
        try:
            search_intent = SearchIntent(search_intent_str)
        except ValueError:
            search_intent = SearchIntent.GENERAL_INFORMATION_QUERY

        # Step 0a: Future Date Guard (never fabricate future market/historical data)
        if entities.get("is_future"):
            date_disp = entities.get("date_display") or entities.get("date") or "the requested future date"
            res = {
                "success": False,
                "offline": False,
                "future_date": True,
                "status_label": "Web Evidence Insufficient",
                "research_context": (
                    "\n--- RESEARCH STATUS ---\n"
                    f"The user asked for data on a FUTURE date ({date_disp}).\n"
                    "Historical or market prices for future dates are NOT yet available.\n"
                    "Explicitly explain that future historical/market data is unavailable and do NOT fabricate any prices.\n"
                    "-------------------------\n"
                ),
                "sources": [],
                "verification": VerificationResult(
                    overall_status="Web Evidence Insufficient",
                    corroborated_domains=[],
                    conflicts=[],
                    notes=f"Future date requested ({date_disp}); historical data unavailable."
                )
            }
            yield ("result", res)
            return

        # Step 0: Connectivity Verification
        yield ("status", "Checking internet connectivity...")

        if not web_search_service.is_internet_available():
            logger.warning("Internet research requested but system is offline.")
            res = {
                "success": False,
                "offline": True,
                "status_label": "Search Failed",
                "research_context": (
                    "\n--- RESEARCH STATUS ---\n"
                    "Internet research was requested, but the system is currently OFFLINE (Search Failed).\n"
                    "Do NOT fabricate information. Explicitly state that search failed because there is no active internet connection.\n"
                    "-------------------------\n"
                ),
                "sources": [],
                "verification": VerificationResult(
                    overall_status="Search Failed",
                    corroborated_domains=[],
                    conflicts=[],
                    notes="Search Failed: Internet connectivity unavailable."
                )
            }
            yield ("result", res)
            return

        # Stage 1: Query Planning
        yield ("status", "Planning research topics...")
        search_topics = classification.search_topics or [query]
        logger.info(f"Research agent planned queries: {search_topics}")

        # Stage 2: Search Sources (DuckDuckGo with TTL cache)
        yield ("status", "Searching the internet for authoritative sources...")
        discovered_results = []
        seen_urls = set()
        cache_ttl = 3600 if search_intent == SearchIntent.HISTORICAL_DATA_QUERY else 120

        for topic in search_topics[:2]:  # Limit to max 2 queries for CPU / RAM speed
            results = web_search_service.search_web(topic, max_results=4, cache_ttl_seconds=cache_ttl)
            for r in results:
                url = r.get("url", "").strip()
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    discovered_results.append(r)

        if not discovered_results:
            logger.info(f"No search results found for query: {query}")
            res = {
                "success": False,
                "offline": False,
                "status_label": "Web Evidence Insufficient",
                "research_context": (
                    "\n--- RESEARCH STATUS ---\n"
                    "Live internet search was executed, but no relevant external sources were found.\n"
                    "State clearly: 'I couldn't find enough reliable data to answer this accurately.'\n"
                    "-------------------------\n"
                ),
                "sources": [],
                "verification": VerificationResult(
                    overall_status="Web Evidence Insufficient",
                    corroborated_domains=[],
                    conflicts=[],
                    notes="Search returned no matching sources."
                )
            }
            yield ("result", res)
            return

        # Stage 3: Page Retrieval & Metadata/Date Extraction (prioritize official/authoritative domains)
        yield ("status", "Retrieving and reading verified webpage content...")
        import urllib.parse
        discovered_results.sort(
            key=lambda item: compute_authority_score(
                urllib.parse.urlparse(item.get("url", "")).netloc.lower(),
                item.get("url", "")
            ),
            reverse=True
        )
        retrieved_pages: List[PageContent] = []
        for item in discovered_results[:self.max_pages]:
            target_url = item.get("url")
            if not target_url:
                continue

            page = retrieve_page_content(target_url, timeout=self.page_timeout)

            # Fallback to search snippet if full page retrieval failed
            if page.status != "retrieved" or not page.clean_text:
                if item.get("snippet"):
                    page.clean_text = item["snippet"]
                    page.status = "retrieved"
                    page.title = item.get("title", page.domain)

            retrieved_pages.append(page)

        # Stage 4: Claim & Evidence Extraction
        yield ("status", "Extracting factual claims and evidence snippets...")
        claims = extract_evidence_claims(retrieved_pages, max_claims=4)

        # Stage 5: Cross-Verification & Conflict Detection
        yield ("status", "Cross-verifying claims across independent sources...")
        verification = evaluate_sources_and_verify(retrieved_pages)

        # Stage 6: Evidence Packaging & Structured Output
        packaged_context = package_research_context(query, claims, retrieved_pages, verification)
        structured_evidence = build_structured_evidence(
            query=query,
            intent=search_intent,
            entities=entities,
            pages=retrieved_pages,
            verification=verification,
        )

        # Determine authoritative backend status label
        if verification.conflicts:
            status_label = "Conflicting Sources"
        elif search_intent == SearchIntent.HISTORICAL_DATA_QUERY:
            status_label = "Historical Data Retrieved"
        elif search_intent == SearchIntent.REAL_TIME_QUERY:
            status_label = "Real-Time Data Retrieved"
        elif verification.overall_status == "Verified":
            status_label = "Web Verified"
        else:
            status_label = "Web Evidence Insufficient"

        # Prepare formatted sources for metadata payload
        formatted_sources = []
        for p in retrieved_pages:
            formatted_sources.append({
                "filename": f"Web: {p.url}",
                "title": p.title,
                "url": p.url,
                "domain": p.domain,
                "publication_date": p.publication_date,
                "authority_score": p.authority_score,
                "preview": p.clean_text[:140] + "..." if len(p.clean_text) > 140 else p.clean_text
            })

        logger.info(f"Research complete: {len(retrieved_pages)} pages read, status={status_label}")

        yield ("result", {
            "success": True,
            "offline": False,
            "status_label": status_label,
            "structured_evidence": structured_evidence,
            "research_context": packaged_context,
            "sources": formatted_sources,
            "verification": verification,
            "claims": claims
        })

    def execute_research(
        self,
        query: str,
        classification: QueryClassification,
        on_status: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Coordinates full research workflow and returns packaged context and sources.
        """
        final_result = None
        for item_type, data in self.execute_research_stream(query, classification):
            if item_type == "status" and on_status:
                on_status(data)
            elif item_type == "result":
                final_result = data

        return final_result or {}

research_agent = InternetResearchAgent()
