from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.schemas import QueryNewsResponse, QueryNewsResultItem
from app.services.summary_service import build_summary_response


def _news_response() -> QueryNewsResponse:
    return QueryNewsResponse(
        topic="iran",
        window="4h",
        generated_at="2026-03-28T12:00:00Z",
        count=2,
        results=[
            QueryNewsResultItem(
                event_id=101,
                timestamp="2026-03-28T11:40:00Z",
                source="telegram:intel_feed",
                claim="Iran reportedly launched missile activity near the border.",
                category="geopolitics",
                importance="high",
                score=0.92,
                evidence_refs=["src_11"],
            ),
            QueryNewsResultItem(
                event_id=102,
                timestamp="2026-03-28T11:20:00Z",
                source="telegram:intel_feed",
                claim="Officials said shipping advisories were updated overnight.",
                category="geopolitics",
                importance="medium",
                score=0.74,
                evidence_refs=["src_12"],
            ),
        ],
    )


@dataclass(frozen=True)
class _FakeLlmResponse:
    raw_text: str


class _FakeLlmClient:
    def __init__(self, raw_text: str) -> None:
        self._raw_text = raw_text

    def summarize(self, prompt_text: str) -> _FakeLlmResponse:  # noqa: ARG002
        return _FakeLlmResponse(raw_text=self._raw_text)


def test_summary_service_deterministic_fallback():
    settings = Settings()
    response = build_summary_response(news_response=_news_response(), settings=settings)

    assert response.topic == "iran"
    assert response.window == "4h"
    assert response.source_count == 2
    assert response.summary.key_developments
    assert response.summary.uncertainties
    assert response.summary.why_it_matters
    assert response.summary.key_developments[0].evidence_refs[0] == "evt_101"


def test_summary_service_uses_llm_when_valid():
    settings = Settings(openai_api_key="test-key", query_summary_openai_model="gpt-test")
    llm_payload = (
        '{"key_developments":[{"text":"Reported military activity increased.","evidence_refs":["evt_101"]}],'
        '"uncertainties":[{"text":"Casualty reports remain unconfirmed.","evidence_refs":["evt_101"]}],'
        '"why_it_matters":[{"text":"Escalation risk can affect regional energy pricing.","evidence_refs":["evt_102"]}]}'
    )
    response = build_summary_response(
        news_response=_news_response(),
        settings=settings,
        llm_client=_FakeLlmClient(llm_payload),
    )

    assert response.summary.key_developments[0].text == "Reported military activity increased."
    assert response.summary.uncertainties[0].text == "Casualty reports remain unconfirmed."


def test_summary_service_falls_back_when_llm_payload_invalid():
    settings = Settings(openai_api_key="test-key", query_summary_openai_model="gpt-test")
    invalid_payload = '{"key_developments":[],"uncertainties":[],"why_it_matters":[]}'
    response = build_summary_response(
        news_response=_news_response(),
        settings=settings,
        llm_client=_FakeLlmClient(invalid_payload),
    )

    assert response.summary.key_developments
    assert response.summary.key_developments[0].text.lower().startswith("iran reportedly")
