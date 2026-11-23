import logging
from typing import Dict, Any, List, Optional, Callable, Generator
from services.query_classifier import QueryClassification, QueryCategory
from services.page_retrieval_service import retrieve_page_content, PageContent
from services.source_verification_service import evaluate_sources_and_verify, VerificationResult
from services.evidence_service import extract_evidence_claims, package_research_context
from services.web_search_service import web_search_service

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
        # Step 0: Connectivity Verification
        yield ("status", "Checking internet connectivity...")

        if not web_search_service.is_internet_available():
            logger.warning("Internet research requested but system is offline.")
            res = {
                "success": False,
                "offline": True,
                "research_context": (
                    "\n--- RESEARCH STATUS ---\n"
                    "Internet research was requested, but the system is currently OFFLINE.\n"
                    "Do NOT fabricate information. Explicitly state that you do not have knowledge "
                    "of this and cannot search the web without an active internet connection.\n"
                    "-------------------------\n"
                ),
                "sources": [],
                "verification": VerificationResult(
                    overall_status="Unverified",
                    corroborated_domains=[],
                    conflicts=[],
                    notes="Offline: Internet connectivity unavailable."
                )
            }
            yield ("result", res)
            return

        # Stage 1: Query Planning
        yield ("status", "Planning research topics...")
        search_topics = classification.search_topics or [query]
        logger.info(f"Research agent planned queries: {search_topics}")

        # Stage 2: Search Sources (DuckDuckGo)
        yield ("status", "Searching the internet for authoritative sources...")
        discovered_results = []
        seen_urls = set()

        for topic in search_topics[:2]:  # Limit to max 2 queries for CPU / RAM speed
            results = web_search_service.search_web(topic, max_results=3)
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
                "research_context": (
                    "\n--- RESEARCH STATUS ---\n"
                    "Live internet search was executed, but no relevant external sources were found.\n"
                    "State clearly: 'I couldn't find reliable evidence on this topic.'\n"
                    "-------------------------\n"
                ),
                "sources": [],
                "verification": VerificationResult(
                    overall_status="Unverified",
                    corroborated_domains=[],
                    conflicts=[],
                    notes="Search returned no matching sources."
                )
            }
            yield ("result", res)
            return

        # Stage 3: Page Retrieval & Metadata/Date Extraction
        yield ("status", "Retrieving and reading verified webpage content...")
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

        # Stage 6: Evidence Packaging
        packaged_context = package_research_context(query, claims, retrieved_pages, verification)

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

        logger.info(f"Research complete: {len(retrieved_pages)} pages read, status={verification.overall_status}")

        yield ("result", {
            "success": True,
            "offline": False,
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
