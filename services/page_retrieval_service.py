import re
import html as html_lib
import urllib.parse
from html.parser import HTMLParser
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import httpx

@dataclass
class PageContent:
    url: str
    domain: str
    title: str
    publication_date: Optional[str]  # e.g. "2026-02-15" or None if unavailable
    clean_text: str                 # sanitized, injection-free, relevant text
    status: str                     # "retrieved", "failed", "timeout", "skipped"
    error: Optional[str] = None
    authority_score: float = 0.5    # 0.0 - 1.0 based on domain credibility

class LightweightHTMLStripper(HTMLParser):
    """
    Fast, streaming HTML text stripper using Python standard library.
    Omits scripts, styles, navigation, headers, footers, and structural boilerplate.
    """
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text_parts: List[str] = []
        self.ignored_tags = {
            "script", "style", "noscript", "nav", "footer", "header",
            "aside", "svg", "form", "button", "iframe"
        }
        self.current_ignore_depth = 0
        self.extracted_title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.ignored_tags:
            self.current_ignore_depth += 1
        elif t == "title":
            self.in_title = True
        elif t in ("p", "div", "h1", "h2", "h3", "h4", "li", "br"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.ignored_tags and self.current_ignore_depth > 0:
            self.current_ignore_depth -= 1
        elif t == "title":
            self.in_title = False
        elif t in ("p", "div", "h1", "h2", "h3", "h4", "li"):
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.extracted_title += data
        elif self.current_ignore_depth == 0:
            clean = data.strip()
            if clean:
                self.text_parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self.text_parts)
        # Collapse multiple newlines/spaces
        collapsed = re.sub(r'[ \t]+', ' ', raw)
        collapsed = re.sub(r'\n\s*\n+', '\n\n', collapsed)
        return collapsed.strip()

def sanitize_untrusted_web_content(text: str) -> str:
    """
    Neutralizes prompt injection attempts and dangerous directive markers
    contained within external web pages.
    """
    if not text:
        return ""

    # Neutralize instruction override directives
    injection_patterns = [
        (r'(?i)\bignore\s+(?:all\s+)?previous\s+instructions\b', '[REDACTED_INSTRUCTION]'),
        (r'(?i)\byou\s+are\s+now\s+(?:an?\s+)?(?:unfiltered|jailbroken|assistant|admin)\b', '[REDACTED_ROLE_CHANGE]'),
        (r'(?i)\bsystem\s+prompt(?:\s+override)?\s*:', '[REDACTED_SYSTEM_DIRECTIVE]:'),
        (r'<<<TOOL_INVOCATION:[\s\S]*?>>>', '[REDACTED_TOOL_CALL]'),
        (r'\[CONFIRM_ACTION:[a-zA-Z0-9_-]+\]', '[REDACTED_ACTION_TRIGGER]'),
        (r'(?i)\b(?:exec|eval|os\.system|subprocess\.Popen)\s*\(', '[REDACTED_CODE_EXEC](')
    ]

    sanitized = text
    for pattern, replacement in injection_patterns:
        sanitized = re.sub(pattern, replacement, sanitized)

    return sanitized

def extract_publication_date(html: str, url: str) -> Optional[str]:
    """
    Extracts published or updated date from standard HTML metadata tags or URL patterns.
    Returns ISO date (YYYY-MM-DD) or None if unavailable. Never invents a date.
    """
    if not html:
        return None

    # 1. OpenGraph / Schema.org meta tags
    meta_patterns = [
        r'<meta[^>]+property=[\'"]article:published_time[\'"][^>]+content=[\'"]([0-9]{4}-[0-9]{2}-[0-9]{2})',
        r'<meta[^>]+content=[\'"]([0-9]{4}-[0-9]{2}-[0-9]{2})[^>]+property=[\'"]article:published_time[\'"]',
        r'<meta[^>]+name=[\'"](?:pubdate|publishdate|date|dc\.date)[\'"][^>]+content=[\'"]([0-9]{4}-[0-9]{2}-[0-9]{2})',
        r'<meta[^>]+property=[\'"]og:updated_time[\'"][^>]+content=[\'"]([0-9]{4}-[0-9]{2}-[0-9]{2})',
        r'<time[^>]+datetime=[\'"]([0-9]{4}-[0-9]{2}-[0-9]{2})'
    ]

    for p in meta_patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1)

    # 2. Check URL for explicit date structure (e.g., /2026/02/15/ or /2025-11-20/)
    url_date_match = re.search(r'/([2][0-9]{3}[-/][0-1][0-9][-/][0-3][0-9])(?:/|$)', url)
    if url_date_match:
        return url_date_match.group(1).replace('/', '-')

    return None

def compute_authority_score(domain: str, url: str) -> float:
    """
    Scores source authority:
    - Official docs & releases (1.0)
    - Institutional & Academic (.edu, .gov, arxiv.org) (0.95)
    - Reputable tech journalism (0.80)
    - Community & Q&A / Blogs (0.60)
    - Generic / Unknown (0.45)
    """
    d = domain.lower()

    # Official documentation, exchanges, bullion associations, & core code repositories
    if any(h in d for h in [
        "docs.", "readthedocs.io", "github.com", "python.org",
        "fastapi.tiangolo.com", "langchain.com", "crewai.com",
        "huggingface.co", "anthropic.com", "openai.com", "ollama.com",
        "modelcontextprotocol.io", "developer.mozilla.org", "react.dev",
        "nextjs.org", "vuejs.org", "kubernetes.io", "docker.com",
        "mozilla.org", "w3.org", "iso.org",
        "ibja.co", "ibjarates.com", "rbi.org.in", "nseindia.com", "bseindia.com",
        "sec.gov", "ecb.europa.eu", "federalreserve.gov", "nasdaq.com", "nyse.com"
    ]):
        return 1.0

    # Institutional & Academic
    if d.endswith(".gov") or d.endswith(".edu") or "arxiv.org" in d or "nature.com" in d:
        return 0.95

    # Established financial & high-credibility tech publications
    if any(m in d for m in [
        "reuters.com", "bloomberg.com", "finance.yahoo.com", "economictimes.indiatimes.com",
        "moneycontrol.com", "livemint.com", "wsj.com", "ft.com",
        "goodreturns.in", "bankbazaar.com", "goldprice.org", "bullionvault.com",
        "xe.com", "coingecko.com", "coinmarketcap.com", "investing.com",
        "techcrunch.com", "theverge.com", "arstechnica.com", "wired.com",
        "zdnet.com", "venturebeat.com", "bleepingcomputer.com"
    ]):
        return 0.85

    # General technical community
    if any(c in d for c in ["stackoverflow.com", "dev.to", "medium.com", "substack.com"]):
        return 0.60

    return 0.45

def retrieve_page_content(
    url: str,
    timeout: float = 3.0,
    max_chars: int = 1200
) -> PageContent:
    """
    Fetches real webpage content over HTTP, sanitizes text, extracts metadata and dates.
    Capped at max_chars to stay within the 8GB RAM CPU token budget.
    """
    # Clean URL format
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = f"https://{clean_url}"

    parsed = urllib.parse.urlparse(clean_url)
    domain = parsed.netloc.lower() or "unknown"
    authority = compute_authority_score(domain, clean_url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(clean_url, headers=headers)
            if resp.status_code != 200:
                return PageContent(
                    url=clean_url,
                    domain=domain,
                    title=domain,
                    publication_date=None,
                    clean_text="",
                    status="failed",
                    error=f"HTTP {resp.status_code}",
                    authority_score=authority
                )

            # Limit reading to first 120KB of HTML to save RAM
            html_text = resp.text[:120000]

        stripper = LightweightHTMLStripper()
        stripper.feed(html_text)
        raw_text = stripper.get_text()
        extracted_title = stripper.extracted_title.strip() or domain

        # Sanitize against prompt injection
        safe_text = sanitize_untrusted_web_content(raw_text)

        # Truncate to relevant informative content
        truncated_text = safe_text[:max_chars].strip()

        # Extract date
        pub_date = extract_publication_date(html_text, clean_url)

        return PageContent(
            url=clean_url,
            domain=domain,
            title=extracted_title,
            publication_date=pub_date,
            clean_text=truncated_text,
            status="retrieved",
            authority_score=authority
        )

    except httpx.TimeoutException:
        return PageContent(
            url=clean_url,
            domain=domain,
            title=domain,
            publication_date=None,
            clean_text="",
            status="timeout",
            error="Connection timed out",
            authority_score=authority
        )
    except Exception as e:
        return PageContent(
            url=clean_url,
            domain=domain,
            title=domain,
            publication_date=None,
            clean_text="",
            status="failed",
            error=str(e),
            authority_score=authority
        )

class PageRetrievalService:
    retrieve_page_content = staticmethod(retrieve_page_content)

page_retrieval_service = PageRetrievalService()
