import uuid
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from core.database import SessionLocal
from models import User
from services import chat_service
from services.query_classifier import classify_query
from services.page_retrieval_service import PageContent
from services.research_agent import research_agent
from services.source_verification_service import evaluate_sources_and_verify
from services.web_intelligence_service import (
    SearchIntent,
    extract_date_info,
    extract_financial_entities,
    classify_search_intent,
)


def _make_user(db):
    unique = uuid.uuid4().hex[:8]
    u = User(
        id=uuid.uuid4(),
        google_sub=f"sub_wi_{unique}",
        email=f"wi_{unique}@ghostmind.local",
        display_name="Web Intelligence Test User",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_1_gold_price_today_real_web_retrieval():
    """Test 1: 'What is the gold price today?' triggers REAL_TIME_QUERY and real web retrieval."""
    db = SessionLocal()
    try:
        user = _make_user(db)
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Gold today is ₹77,500 per 10g (24K) [1].")

        ibja_page = PageContent(
            url="https://ibjarates.com/today",
            domain="ibjarates.com",
            title="IBJA Gold Rates Today",
            publication_date="2026-11-27",
            clean_text="IBJA 24K (999) Gold Rate Today: ₹77,500 per 10 grams.",
            status="retrieved",
            authority_score=1.0,
        )

        with patch("services.web_search_service.web_search_service.is_internet_available", return_value=True), \
             patch("services.web_search_service.web_search_service.search_web", return_value=[{"title": "IBJA", "url": "https://ibjarates.com/today", "snippet": "Gold rate ₹77,500"}]) as mock_search, \
             patch("services.research_agent.retrieve_page_content", return_value=ibja_page), \
             patch("ollama_service.check_system_readiness", return_value={"ready": True}), \
             patch("services.chat_service.get_chat_model", return_value=mock_llm):
            res = chat_service.execute_chat_turn(
                db=db,
                user=user,
                message="What is the gold price today?",
                enable_web_search=True,
                enable_rag=False,
            )

        assert mock_search.called
        assert res["verification_status"] == "Real-Time Data Retrieved"
        assert res["knowledge_source_badge"] == "Internet Research"
        assert len(res["sources"]) == 1
    finally:
        db.close()


def test_2_historical_gold_price_date_extraction_and_search():
    """Test 2: 'What was the gold price on 26/11/2026?' extracts 2026-11-26 and retrieves historical data."""
    ref_today = date(2026, 11, 27)
    entities = extract_financial_entities("What was the gold price on 26/11/2026?", reference_date=ref_today)
    assert entities["asset"] == "gold"
    assert entities["date"] == "2026-11-26"
    assert entities["is_historical"] is True

    intent = classify_search_intent("What was the gold price on 26/11/2026?", entities=entities)
    assert intent == SearchIntent.HISTORICAL_DATA_QUERY

    cls = classify_query("What was the gold price on 26/11/2026?")
    assert cls.requires_web_search is True
    assert cls.search_intent == SearchIntent.HISTORICAL_DATA_QUERY.value

    hist_page = PageContent(
        url="https://ibjarates.com/2026-11-26",
        domain="ibjarates.com",
        title="IBJA Gold Rate 26 November 2026",
        publication_date="2026-11-26",
        clean_text="IBJA 24K Gold on 26 Nov 2026: ₹76,800 per 10 grams.",
        status="retrieved",
        authority_score=1.0,
    )
    with patch("services.web_search_service.web_search_service.is_internet_available", return_value=True), \
         patch("services.web_search_service.web_search_service.search_web", return_value=[{"title": "IBJA", "url": "https://ibjarates.com/2026-11-26", "snippet": "₹76,800"}]), \
         patch("services.research_agent.retrieve_page_content", return_value=hist_page):
        res = research_agent.execute_research("What was the gold price on 26/11/2026?", cls)

    assert res["success"] is True
    assert res["status_label"] == "Historical Data Retrieved"
    assert res["structured_evidence"]["data"]["date"] == "2026-11-26"


def test_3_usd_to_inr_exchange_rate_retrieval():
    """Test 3: 'What is the current USD to INR exchange rate?' extracts forex pair and retrieves live rate."""
    entities = extract_financial_entities("What is the current USD to INR exchange rate?")
    assert entities["asset_type"] == "forex"
    assert entities["base_currency"] == "USD"
    assert entities["target_currency"] == "INR"

    cls = classify_query("What is the current USD to INR exchange rate?")
    assert cls.requires_web_search is True
    assert cls.search_intent == SearchIntent.REAL_TIME_QUERY.value


def test_4_latest_qwen_model_technical_search():
    """Test 4: 'What is the latest Qwen model?' routes to current technical web search."""
    cls = classify_query("What is the latest Qwen model?")
    assert cls.requires_web_search is True


def test_5_python_list_local_knowledge_no_web_search():
    """Test 5: 'What is a Python list?' is answered locally without unnecessary web search."""
    cls = classify_query("What is a Python list?")
    assert cls.requires_web_search is False


def test_6_web_search_off_gold_price_today():
    """Test 6: Web Search OFF + gold price today makes zero network calls and states inability to retrieve."""
    db = SessionLocal()
    try:
        user = _make_user(db)
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="I cannot retrieve current gold prices because Web Search is turned off. Please enable Web Search."
        )

        with patch("services.web_search_service.web_search_service.is_internet_available") as mock_inet, \
             patch("services.web_search_service.web_search_service.search_web") as mock_search, \
             patch("ollama_service.check_system_readiness", return_value={"ready": True}), \
             patch("services.chat_service.get_chat_model", return_value=mock_llm):
            res = chat_service.execute_chat_turn(
                db=db,
                user=user,
                message="What is the gold price today?",
                enable_web_search=False,
                enable_rag=False,
            )

        mock_inet.assert_not_called()
        mock_search.assert_not_called()
        assert res["verification_status"] == "Local Knowledge"
        assert res["knowledge_source_badge"] == "Local Knowledge"
        sys_prompt = mock_llm.invoke.call_args[0][0][0]["content"]
        assert "Web Search is currently OFF" in sys_prompt
        assert "cannot be retrieved" in sys_prompt
    finally:
        db.close()


def test_7_internet_unavailable_web_search_on_reports_search_failed():
    """Test 7: Internet unavailable + Web Search ON reports 'Search Failed', not 'Local Knowledge Sufficient'."""
    db = SessionLocal()
    try:
        user = _make_user(db)
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="Search failed because no internet connection is available."
        )

        with patch("services.web_search_service.web_search_service.is_internet_available", return_value=False), \
             patch("ollama_service.check_system_readiness", return_value={"ready": True}), \
             patch("services.chat_service.get_chat_model", return_value=mock_llm):
            res = chat_service.execute_chat_turn(
                db=db,
                user=user,
                message="What is the gold price today?",
                enable_web_search=True,
                enable_rag=False,
            )

        assert res["verification_status"] == "Search Failed"
    finally:
        db.close()


def test_8_conflicting_gold_prices_detected():
    """Test 8: Conflicting gold prices across sources are detected and flagged."""
    pages = [
        PageContent(
            url="https://ibjarates.com/today",
            domain="ibjarates.com",
            title="IBJA Gold Rate",
            publication_date="2026-11-27",
            clean_text="IBJA 24K Gold benchmark rate is ₹76,500 per 10 grams (excluding GST).",
            status="retrieved",
            authority_score=1.0,
        ),
        PageContent(
            url="https://goodreturns.in/gold-rates",
            domain="goodreturns.in",
            title="Retail Gold Rate",
            publication_date="2026-11-27",
            clean_text="Retail 24K Gold price in Mumbai is ₹80,200 per 10 grams.",
            status="retrieved",
            authority_score=0.85,
        ),
    ]
    verif = evaluate_sources_and_verify(pages)
    assert len(verif.conflicts) >= 1
    assert "Conflicting prices" in verif.conflicts[0]
    assert verif.overall_status == "Partially Verified"


def test_9_future_gold_price_date_rejected_without_fabrication():
    """Test 9: Future gold price date explains historical data is unavailable without searching or fabricating."""
    future_d = (date.today() + timedelta(days=30)).strftime("%d/%m/%Y")
    prompt = f"What will be the gold price on {future_d}?"
    cls = classify_query(prompt)
    assert cls.extracted_entities["is_future"] is True

    with patch("services.web_search_service.web_search_service.search_web") as mock_search:
        res = research_agent.execute_research(prompt, cls)

    mock_search.assert_not_called()
    assert res["success"] is False
    assert res.get("future_date") is True
    assert "future" in res["research_context"].lower()
    assert "not yet available" in res["research_context"].lower()


def test_10_missing_currency_or_location_flagged_for_clarification():
    """Test 10: Missing currency or location on bullion query flags clarification requirement."""
    entities = extract_financial_entities("What was the gold price on 26/11/2026?")
    assert entities["missing_location_or_currency"] is True

    entities_with_loc = extract_financial_entities("What was the gold price in India on 26/11/2026?")
    assert entities_with_loc["missing_location_or_currency"] is False
    assert entities_with_loc["location"] == "India"
    assert entities_with_loc["currency"] == "INR"
