import re
from enum import Enum
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List, Optional


class SearchIntent(str, Enum):
    REAL_TIME_QUERY = "REAL_TIME_QUERY"
    HISTORICAL_DATA_QUERY = "HISTORICAL_DATA_QUERY"
    CURRENT_TECHNICAL_QUERY = "CURRENT_TECHNICAL_QUERY"
    GENERAL_INFORMATION_QUERY = "GENERAL_INFORMATION_QUERY"
    LOCAL_KNOWLEDGE_QUERY = "LOCAL_KNOWLEDGE_QUERY"


MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

LOCATION_TO_CURRENCY = {
    "india": "INR", "mumbai": "INR", "delhi": "INR", "chennai": "INR",
    "bangalore": "INR", "bengaluru": "INR", "kolkata": "INR", "hyderabad": "INR",
    "ahmedabad": "INR", "pune": "INR", "jaipur": "INR", "kerala": "INR",
    "usa": "USD", "us": "USD", "united states": "USD", "america": "USD", "new york": "USD",
    "uk": "GBP", "united kingdom": "GBP", "london": "GBP", "britain": "GBP",
    "uae": "AED", "dubai": "AED", "abu dhabi": "AED",
    "europe": "EUR", "eu": "EUR", "germany": "EUR", "france": "EUR",
    "japan": "JPY", "tokyo": "JPY",
    "singapore": "SGD", "australia": "AUD", "canada": "CAD", "china": "CNY",
}

CURRENCY_CODES = {"INR", "USD", "EUR", "GBP", "AED", "JPY", "AUD", "CAD", "SGD", "CHF", "CNY"}

BULLION_ASSETS = {"gold", "silver", "platinum", "palladium"}
CRYPTO_ASSETS = {
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH",
    "solana": "SOL", "sol": "SOL",
    "ripple": "XRP", "xrp": "XRP",
    "dogecoin": "DOGE", "doge": "DOGE",
    "cardano": "ADA", "ada": "ADA",
    "bnb": "BNB",
}
STOCK_COMPANIES = {
    "apple": "AAPL", "aapl": "AAPL",
    "microsoft": "MSFT", "msft": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "googl": "GOOGL",
    "amazon": "AMZN", "amzn": "AMZN",
    "nvidia": "NVDA", "nvda": "NVDA",
    "tesla": "TSLA", "tsla": "TSLA",
    "meta": "META", "reliance": "RELIANCE.NS", "tcs": "TCS.NS", "infosys": "INFY.NS",
}


def extract_date_info(query: str, reference_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Extracts explicit or relative dates from a user query.
    Supports DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, natural language dates,
    and relative expressions (today, yesterday, last week, last month).
    """
    today = reference_date or datetime.now().date()
    q_low = query.lower()
    extracted: Optional[date] = None
    date_type = "none"  # "none", "today", "historical", "future"

    # 1. YYYY-MM-DD
    m_iso = re.search(r'\b(20\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b', query)
    if m_iso:
        try:
            extracted = date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except ValueError:
            pass

    # 2. DD/MM/YYYY or DD-MM-YYYY
    if not extracted:
        m_dmy = re.search(r'\b(0?[1-9]|[12]\d|3[01])[/-](0?[1-9]|1[0-2])[/-](20\d{2})\b', query)
        if m_dmy:
            try:
                extracted = date(int(m_dmy.group(3)), int(m_dmy.group(2)), int(m_dmy.group(1)))
            except ValueError:
                pass

    # 3. Natural language: "26 November 2026" or "26th Nov 2026"
    if not extracted:
        m_nat1 = re.search(
            r'\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+([a-zA-Z]+),?\s+(20\d{2})\b',
            q_low
        )
        if m_nat1 and m_nat1.group(2) in MONTH_MAP:
            try:
                extracted = date(int(m_nat1.group(3)), MONTH_MAP[m_nat1.group(2)], int(m_nat1.group(1)))
            except ValueError:
                pass

    # 4. Natural language: "November 26, 2026" or "Nov 26 2026"
    if not extracted:
        m_nat2 = re.search(
            r'\b([a-zA-Z]+)\s+(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,?\s+(20\d{2})\b',
            q_low
        )
        if m_nat2 and m_nat2.group(1) in MONTH_MAP:
            try:
                extracted = date(int(m_nat2.group(3)), MONTH_MAP[m_nat2.group(1)], int(m_nat2.group(2)))
            except ValueError:
                pass

    # 5. Relative dates
    if not extracted:
        if "yesterday" in q_low:
            extracted = today - timedelta(days=1)
        elif "last week" in q_low:
            extracted = today - timedelta(days=7)
        elif "last month" in q_low:
            extracted = today - timedelta(days=30)
        elif "tomorrow" in q_low:
            extracted = today + timedelta(days=1)
        elif any(w in q_low for w in ["today", "right now", "currently", "live", "current price", "current rate"]):
            extracted = today
            date_type = "today"

    if extracted:
        if extracted > today:
            date_type = "future"
        elif extracted < today:
            date_type = "historical"
        else:
            date_type = "today"

    return {
        "date": extracted.isoformat() if extracted else None,
        "date_display": extracted.strftime("%d %B %Y") if extracted else None,
        "date_type": date_type,
        "is_historical": date_type == "historical",
        "is_future": date_type == "future",
        "is_today": date_type == "today",
    }


def extract_financial_entities(
    query: str,
    recent_history: Optional[List[Dict[str, str]]] = None,
    reference_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Extracts structured financial, commodity, stock, crypto, forex, date,
    location, currency, purity, and unit entities from a user query.
    """
    q_low = query.lower()
    date_info = extract_date_info(query, reference_date=reference_date)

    asset: Optional[str] = None
    asset_type: Optional[str] = None
    ticker: Optional[str] = None
    base_currency: Optional[str] = None
    target_currency: Optional[str] = None
    amount: Optional[float] = None

    # 1. Forex / Currency Conversion detection (e.g. "USD to INR", "100 USD in EUR")
    curr_pattern = "|".join(CURRENCY_CODES)
    m_fx = re.search(
        rf'\b(?:(\d+(?:\.\d+)?)\s*)?({curr_pattern})\s+(?:to|in|into|vs|versus|/)\s+({curr_pattern})\b',
        query,
        re.IGNORECASE
    )
    if m_fx:
        asset_type = "forex"
        amount = float(m_fx.group(1)) if m_fx.group(1) else 1.0
        base_currency = m_fx.group(2).upper()
        target_currency = m_fx.group(3).upper()
        asset = f"{base_currency}/{target_currency}"

    # 2. Bullion / Commodity detection
    if not asset_type:
        for b in BULLION_ASSETS:
            if re.search(rf'\b{b}\b', q_low):
                asset = b
                asset_type = "bullion"
                break

    # 3. Crypto detection
    if not asset_type:
        for name, sym in CRYPTO_ASSETS.items():
            if re.search(rf'\b{name}\b', q_low):
                asset = name if len(name) > 4 else sym
                ticker = sym
                asset_type = "crypto"
                break

    # 4. Stock detection
    if not asset_type:
        for comp, sym in STOCK_COMPANIES.items():
            if re.search(rf'\b{comp}\b', q_low) and any(
                w in q_low for w in ["stock", "share", "price", "closing", "market", "nasdaq", "nyse", "nse", "bse", "ticker"]
            ):
                asset = comp.title() if len(comp) > 4 else sym
                ticker = sym
                asset_type = "stock"
                break
        if not asset_type and any(w in q_low for w in ["stock price", "share price", "closing price"]):
            asset_type = "stock"
            asset = "stock"

    # 5. Location & Currency extraction
    location: Optional[str] = None
    currency: Optional[str] = target_currency

    for loc, curr in LOCATION_TO_CURRENCY.items():
        if re.search(rf'\b{re.escape(loc)}\b', q_low):
            location = loc.title() if len(loc) > 3 else loc.upper()
            if not currency:
                currency = curr
            break

    if not currency:
        for code in CURRENCY_CODES:
            if re.search(rf'\b{code}\b', query, re.IGNORECASE):
                currency = code.upper()
                break
        if not currency and ("₹" in query or "rupee" in q_low or "rs." in q_low or "rs " in q_low):
            currency = "INR"
        elif not currency and "$" in query:
            currency = "USD"
        elif not currency and "€" in query:
            currency = "EUR"
        elif not currency and "£" in query:
            currency = "GBP"

    # Check recent conversation history for location/currency if missing
    if recent_history and (not location or not currency):
        hist_text = " ".join(m.get("content", "") for m in recent_history[-4:]).lower()
        if not location:
            for loc, curr in LOCATION_TO_CURRENCY.items():
                if re.search(rf'\b{re.escape(loc)}\b', hist_text):
                    location = loc.title() if len(loc) > 3 else loc.upper()
                    if not currency:
                        currency = curr
                    break

    # 6. Purity & Unit extraction (for bullion)
    purity: Optional[str] = None
    m_purity = re.search(r'\b(24k|22k|18k|14k|999|995|916)\b', q_low)
    if m_purity:
        purity = m_purity.group(1).upper()

    unit: Optional[str] = None
    if re.search(r'\b10\s*grams?\b|\b10g\b', q_low):
        unit = "10 grams"
    elif re.search(r'\b(?:per\s+)?(?:kg|kilogram|kilo)\b', q_low):
        unit = "1 kilogram"
    elif re.search(r'\b(?:per\s+)?gram\b|\b1g\b', q_low):
        unit = "1 gram"
    elif re.search(r'\b(?:per\s+)?ounce\b|\boz\b', q_low):
        unit = "1 troy ounce"

    # Determine if essential context (location or currency) is missing for local commodity prices
    # Note: Queries mentioning "today" / "live" / "current" or explicit historical date without location/currency
    # can still be searched globally or asked for clarification depending on query specificity.
    missing_location_or_currency = (
        asset_type == "bullion"
        and location is None
        and currency is None
    )

    return {
        "asset": asset,
        "asset_type": asset_type,
        "ticker": ticker,
        "base_currency": base_currency,
        "target_currency": target_currency,
        "amount": amount,
        "location": location,
        "currency": currency,
        "purity": purity,
        "unit": unit,
        **date_info,
        "missing_location_or_currency": missing_location_or_currency,
    }


def classify_search_intent(
    query: str,
    entities: Optional[Dict[str, Any]] = None,
    has_document_context: bool = False
) -> SearchIntent:
    """
    Deterministic 5-category search intent classifier:
    - REAL_TIME_QUERY
    - HISTORICAL_DATA_QUERY
    - CURRENT_TECHNICAL_QUERY
    - GENERAL_INFORMATION_QUERY
    - LOCAL_KNOWLEDGE_QUERY
    """
    if has_document_context:
        return SearchIntent.LOCAL_KNOWLEDGE_QUERY

    q_low = query.strip().lower()
    ent = entities or extract_financial_entities(query)

    # 1. Historical date query
    if ent.get("is_historical") or ent.get("is_future"):
        return SearchIntent.HISTORICAL_DATA_QUERY

    # 2. Real-time financial, weather, news, live prices
    real_time_triggers = [
        "today", "right now", "currently", "live", "current price", "current rate",
        "exchange rate", "stock price", "share price", "weather", "breaking news",
        "today's news", "commodity price"
    ]
    if ent.get("asset_type") in ("bullion", "stock", "crypto", "forex") or any(t in q_low for t in real_time_triggers):
        return SearchIntent.REAL_TIME_QUERY

    # 3. Current technical queries
    tech_triggers = [
        "latest", "newest", "current version", "latest version", "release notes",
        "qwen", "langchain", "mcp", "model context protocol", "python version",
        "fastapi", "pgvector", "ollama", "claude", "gpt-", "gemini", "llama"
    ]
    if any(t in q_low for t in tech_triggers):
        return SearchIntent.CURRENT_TECHNICAL_QUERY

    # 4. Local foundational CS/math concepts
    local_concepts = [
        "python list", "python dictionary", "recursion", "for loop", "while loop",
        "quicksort", "binary search", "linked list", "fibonacci", "hello world",
        "object oriented", "polymorphism", "inheritance", "big o", "time complexity",
        "backpropagation", "neural network", "explain loop"
    ]
    if any(c in q_low for c in local_concepts):
        return SearchIntent.LOCAL_KNOWLEDGE_QUERY

    return SearchIntent.GENERAL_INFORMATION_QUERY


def build_authoritative_search_queries(query: str, entities: Dict[str, Any], intent: SearchIntent) -> List[str]:
    """Generates clean, targeted search queries prioritizing official & financial sources."""
    asset = entities.get("asset")
    asset_type = entities.get("asset_type")
    loc = entities.get("location") or ""
    curr = entities.get("currency") or ""
    date_disp = entities.get("date_display") or ""
    purity = entities.get("purity") or ""

    if asset_type == "bullion":
        if intent == SearchIntent.HISTORICAL_DATA_QUERY and date_disp:
            if loc.lower() == "india" or curr == "INR":
                return [f"IBJA {asset} rate {date_disp} India 24K 22K INR", f"{asset} price {loc} {date_disp} {curr}".strip()]
            return [f"{asset} price {loc} {date_disp} {curr} {purity}".strip()]
        else:
            if loc.lower() == "india" or curr == "INR":
                return [f"{asset} rate today India IBJA 24K 22K INR"]
            return [f"{asset} price today {loc} {curr} {purity}".strip()]

    if asset_type == "forex":
        base = entities.get("base_currency") or "USD"
        target = entities.get("target_currency") or "INR"
        if intent == SearchIntent.HISTORICAL_DATA_QUERY and date_disp:
            return [f"{base} to {target} exchange rate {date_disp}"]
        return [f"{base} to {target} exchange rate today"]

    if asset_type == "crypto":
        sym = entities.get("ticker") or asset
        curr_str = curr or "USD"
        if intent == SearchIntent.HISTORICAL_DATA_QUERY and date_disp:
            return [f"{asset} {sym} historical price {date_disp} {curr_str}"]
        return [f"{asset} {sym} price today {curr_str}"]

    if asset_type == "stock":
        sym = entities.get("ticker") or asset
        if intent == SearchIntent.HISTORICAL_DATA_QUERY and date_disp:
            return [f"{asset} {sym} closing stock price {date_disp}"]
        return [f"{asset} {sym} stock price today"]

    return [query.strip()]


def build_structured_evidence(
    query: str,
    intent: SearchIntent,
    entities: Dict[str, Any],
    pages: List[Any],
    verification: Any
) -> Dict[str, Any]:
    """Builds the normalized structured evidence dictionary."""
    now_iso = datetime.now(timezone.utc).isoformat()
    sources = []
    for p in pages:
        if getattr(p, "status", "") == "retrieved":
            sources.append({
                "title": p.title,
                "url": p.url,
                "domain": p.domain,
                "retrieved_at": now_iso,
            })

    return {
        "query": query,
        "intent": intent.value,
        "data": {
            "asset": entities.get("asset"),
            "date": entities.get("date"),
            "purity": entities.get("purity"),
            "price": None,  # Never invented by backend; extracted/presented from verified sources
            "currency": entities.get("currency"),
            "unit": entities.get("unit"),
            "location": entities.get("location"),
        },
        "sources": sources,
        "verification": {
            "source_count": len(sources),
            "verified": getattr(verification, "overall_status", "Unverified") == "Verified",
            "conflicts_detected": bool(getattr(verification, "conflicts", [])),
        },
    }
