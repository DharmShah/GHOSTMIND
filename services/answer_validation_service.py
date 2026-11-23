import re
from typing import List, Dict, Any, Optional

def validate_citations_and_format(
    raw_response: str,
    retrieved_sources: List[Dict[str, Any]],
    query_category: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates model response against actual retrieved evidence:
    - Strips or flags hallucinated URLs not present in retrieved sources
    - Normalizes inline citations [1], [2], etc.
    - Determines the Knowledge Source Badge:
      - 'Local Knowledge'
      - 'Internet Research'
      - 'Local Knowledge + Internet Research'
    - Prepares clean structured citations metadata for frontend consumption.
    """
    # 1. Determine Knowledge Source Badge
    has_web_sources = any(
        (s.get("filename", "").startswith("Web:") or s.get("url"))
        for s in retrieved_sources
    )
    has_doc_sources = any(
        (not s.get("filename", "").startswith("Web:") and not s.get("url"))
        for s in retrieved_sources
    )

    if has_web_sources and has_doc_sources:
        badge = "Local Knowledge + Internet Research"
        badge_type = "hybrid"
    elif has_web_sources:
        badge = "Internet Research"
        badge_type = "web"
    else:
        badge = "Local Knowledge"
        badge_type = "local"

    # 2. Extract and validate URLs in response
    valid_urls = set()
    for s in retrieved_sources:
        url = s.get("url")
        if url:
            valid_urls.add(url.rstrip("/").lower())
        fn = s.get("filename", "")
        if fn.startswith("Web:"):
            clean_fn_url = fn.replace("Web:", "").strip()
            if clean_fn_url.startswith("http"):
                valid_urls.add(clean_fn_url.rstrip("/").lower())

    # Detect hallucinated markdown links [Title](http://fake.url)
    def clean_hallucinated_links(match):
        label = match.group(1)
        url = match.group(2).strip()
        clean_target = url.rstrip("/").lower()
        if not clean_target.startswith("http"):
            return label

        # Check if URL or its domain was in valid retrieved sources
        url_domain = clean_target.split("/")[2] if len(clean_target.split("/")) > 2 else ""
        is_known = any(
            clean_target in v or (url_domain and url_domain in v)
            for v in valid_urls
        )
        if is_known:
            return match.group(0)  # Keep valid link
        else:
            # Strip fake URL, keep readable label text
            return f"{label} (unverified source)"

    sanitized_response = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', clean_hallucinated_links, raw_response)

    # 3. Clean and enrich sources metadata for frontend display
    formatted_sources: List[Dict[str, Any]] = []
    seen_urls = set()

    for idx, s in enumerate(retrieved_sources, start=1):
        url = s.get("url") or (s.get("filename", "").replace("Web:", "").strip() if s.get("filename", "").startswith("Web:") else None)
        title = s.get("title") or s.get("filename") or f"Source {idx}"
        domain = s.get("domain") or (url.split("/")[2] if url and len(url.split("/")) > 2 else "local")
        date_str = s.get("publication_date") or None

        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        formatted_sources.append({
            "index": idx,
            "title": title,
            "url": url,
            "domain": domain,
            "publication_date": date_str,
            "authority_score": s.get("authority_score", 0.5),
            "preview": s.get("preview", "")
        })

    return {
        "sanitized_response": sanitized_response,
        "knowledge_source_badge": badge,
        "badge_type": badge_type,
        "formatted_sources": formatted_sources
    }

