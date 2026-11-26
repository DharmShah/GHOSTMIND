import re
import time
import html as html_lib
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional

_last_connectivity_check = 0.0
_cached_internet_status = False
_SEARCH_CACHE: Dict[str, Dict[str, Any]] = {}

def is_internet_available(timeout: float = 1.5, force_refresh: bool = False) -> bool:
    """
    Checks whether the system currently has an active internet connection.
    Caches the result for 10 seconds to avoid unnecessary network latency.
    """
    global _last_connectivity_check, _cached_internet_status
    now = time.time()
    if not force_refresh and (now - _last_connectivity_check < 10.0):
        return _cached_internet_status

    test_endpoints = [
        "http://www.google.com",
        "http://1.1.1.1",
        "http://httpbin.org/get"
    ]

    for endpoint in test_endpoints:
        try:
            req = urllib.request.Request(
                endpoint,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status in (200, 301, 302):
                    _cached_internet_status = True
                    _last_connectivity_check = now
                    return True
        except Exception:
            continue

    _cached_internet_status = False
    _last_connectivity_check = now
    return False


def clean_search_query(query: str) -> str:
    """Extracts core search intent by stripping conversational fluff."""
    q = query.strip()
    patterns = [
        r'^(?:can you|could you|please|kindly)\s+(?:tell me|search for|find out|explain)\s+',
        r'^(?:what is|what are|who is|who are|explain|define|tell me about)\s+',
        r'^(?:search for|google|look up|find online)\s+'
    ]
    for p in patterns:
        q = re.sub(p, '', q, flags=re.IGNORECASE).strip()
    return q if q else query.strip()


def should_search_web(query: str, has_document_context: bool = False) -> bool:
    """
    Intelligent prompt classification routing delegating to QueryClassifier.
    - Avoids searching for standard programming concepts (e.g., loops, algorithms, functions)
    - Avoids searching when document RAG context is explicitly requested
    - Searches for real-time/temporal queries, latest versions, current news, unknown acronyms,
      modern post-2024 AI tools, or explicit search commands.
    """
    try:
        from services.query_classifier import classify_query
        classification = classify_query(query, has_document_context=has_document_context)
        return classification.requires_web_search
    except Exception:
        # Fallback to local heuristic if import fails
        if has_document_context:
            return False
        cleaned = query.strip().lower()
        if len(cleaned) < 3:
            return False
        return any(t in cleaned for t in ["search", "latest", "recent", "today", "news", "version", "mcp"])


def search_web(
    query: str,
    max_results: int = 3,
    timeout: float = 4.0,
    cache_ttl_seconds: int = 0
) -> List[Dict[str, str]]:
    """
    Executes a web search via DuckDuckGo HTML without external dependencies or API keys.
    Cleans, filters, and deduplicates results by URL.
    Supports optional TTL caching (never serves expired entries).
    Returns: [{"title": ..., "snippet": ..., "url": ...}]
    """
    search_query = clean_search_query(query)
    if cache_ttl_seconds > 0:
        cached = _SEARCH_CACHE.get(search_query.lower())
        if cached and (time.time() - cached["ts"] < cache_ttl_seconds):
            return cached["results"][:max_results]

    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(search_query)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        snippets = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        urls = re.findall(r'<a[^>]+class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        hrefs = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html, re.DOTALL)

        results = []
        seen_domains = set()

        for i in range(min(len(snippets), len(titles), 10)):
            raw_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            raw_url = re.sub(r'<[^>]+>', '', urls[i]).strip() if i < len(urls) else ""
            raw_title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else ""

            # Check if href has real destination URL via uddg parameter
            real_url = ""
            if i < len(hrefs):
                h = hrefs[i]
                if "uddg=" in h:
                    try:
                        parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(h).query)
                        real_url = parsed_qs.get("uddg", [""])[0]
                    except Exception:
                        real_url = ""

            clean_snippet = html_lib.unescape(raw_snippet)
            clean_url = html_lib.unescape(real_url if real_url else raw_url)
            clean_title = html_lib.unescape(raw_title)

            # Clean leading/trailing junk
            clean_snippet = re.sub(r'^\W+|\W+$', '', clean_snippet).strip()

            if not clean_snippet or len(clean_snippet) < 30:
                continue

            # Extract domain for deduplication
            domain_part = clean_url.replace("https://", "").replace("http://", "").split('/')[0].lower() if clean_url else str(i)
            if domain_part in seen_domains:
                continue
            seen_domains.add(domain_part)

            results.append({
                "title": clean_title,
                "url": clean_url,
                "snippet": clean_snippet
            })

            if len(results) >= max_results:
                break

        if cache_ttl_seconds > 0 and results:
            _SEARCH_CACHE[search_query.lower()] = {"ts": time.time(), "results": results}

        return results
    except Exception:
        return []


def format_web_search_prompt(results: List[Dict[str, str]]) -> str:
    """Formats live web search results into a clean, structured context block."""
    if not results:
        return ""

    parts = []
    for idx, r in enumerate(results, start=1):
        source = r.get("url") or r.get("title") or f"Web Source {idx}"
        parts.append(f"[Web Source {idx}: {source}]\n{r['snippet']}")

    return (
        "\n--- REAL-TIME LIVE WEB SEARCH EVIDENCE ---\n"
        + "\n\n".join(parts)
        + "\n---------------------------------------------\n"
    )


class WebSearchService:
    is_internet_available = staticmethod(is_internet_available)
    clean_search_query = staticmethod(clean_search_query)
    should_search_web = staticmethod(should_search_web)
    search_web = staticmethod(search_web)
    format_web_search_prompt = staticmethod(format_web_search_prompt)


web_search_service = WebSearchService()

