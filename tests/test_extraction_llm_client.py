from __future__ import annotations

import httpx
import pytest

from app.services.extraction_llm_client import OpenAiExtractionClient, ProviderError


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClientSuccess:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, endpoint: str, headers: dict, json: dict) -> _FakeHttpResponse:  # noqa: A002
        return _FakeHttpResponse(
            {
                "id": "resp_test_ok",
                "model": "gpt-4o-mini",
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": '{"topic":"other","entities":{"countries":[],"orgs":[],"people":[],"tickers":[]},"affected_countries_first_order":[],"market_stats":[],"sentiment":"unknown","confidence":0.1,"impact_score":1,"is_breaking":false,"breaking_window":"none","event_time":null,"source_claimed":null,"summary_1_sentence":"x","keywords":[],"event_fingerprint":"f"}'}
                        ]
                    }
                ],
            }
        )


class _FakeClientFail:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, endpoint: str, headers: dict, json: dict) -> _FakeHttpResponse:  # noqa: A002
        raise httpx.ConnectError("boom")


def test_openai_responses_extract_parses_output(monkeypatch):
    monkeypatch.setattr(httpx, "Client", _FakeClientSuccess)
    client = OpenAiExtractionClient(
        api_key="test",
        model="gpt-4o-mini",
        timeout_seconds=5,
        max_retries=2,
    )
    out = client.extract("hello")
    assert out.extractor_name == "extract-and-score-openai-v1"
    assert out.used_openai is True
    assert out.model_name == "gpt-4o-mini"
    assert out.openai_response_id == "resp_test_ok"
    assert out.retries == 0
    assert out.raw_text.startswith('{"topic":"other"')


def test_openai_responses_extract_retries_and_raises(monkeypatch):
    monkeypatch.setattr(httpx, "Client", _FakeClientFail)
    client = OpenAiExtractionClient(
        api_key="test",
        model="gpt-4o-mini",
        timeout_seconds=5,
        max_retries=1,
    )
    with pytest.raises(ProviderError, match="openai request failed after retries"):
        client.extract("hello")
