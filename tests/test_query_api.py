from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client_and_session():
    os.environ["BOT_API_TOKEN"] = "bot-secret"
    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import Base, get_db
    from app.main import create_app
    from app.models import Event, EventMessage, EventRelation, EventTag, Extraction, RawMessage

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    with SessionLocal() as db:
        now = dt.datetime(2026, 3, 28, 18, 0, 0)
        raw = RawMessage(
            source_channel_id="-100channel",
            source_channel_name="intel_feed",
            telegram_message_id="m-1",
            message_timestamp_utc=now,
            raw_text="Iran reportedly launched new missile activity.",
            raw_entities=None,
            forwarded_from=None,
            normalized_text="iran reportedly launched new missile activity",
        )
        db.add(raw)
        db.flush()

        extraction = Extraction(
            raw_message_id=raw.id,
            extractor_name="extract-and-score-openai-v1",
            schema_version=1,
            event_time=now,
            topic="geopolitics",
            impact_score=82.0,
            confidence=0.8,
            sentiment="negative",
            is_breaking=True,
            breaking_window="1h",
            event_fingerprint="v2:query-test-event",
            payload_json={
                "topic": "geopolitics",
                "summary_1_sentence": "Iran reportedly launched new missile activity.",
                "keywords": ["iran", "missile"],
                "entities": {"countries": ["Iran"], "orgs": [], "people": [], "tickers": []},
            },
            canonical_payload_json={
                "topic": "geopolitics",
                "summary_1_sentence": "Iran reportedly launched new missile activity.",
                "source_claimed": "Reuters",
                "keywords": ["iran", "missile"],
                "entities": {"countries": ["Iran"], "orgs": [], "people": [], "tickers": []},
            },
            metadata_json={},
        )
        db.add(extraction)
        db.flush()

        event = Event(
            event_fingerprint="v2:query-test-event",
            event_identity_fingerprint_v2="v2:query-test-event",
            topic="geopolitics",
            summary_1_sentence="Iran reportedly launched new missile activity.",
            impact_score=82.0,
            is_breaking=True,
            breaking_window="1h",
            event_time=now,
            last_updated_at=now,
            latest_extraction_id=extraction.id,
            claim_hash="claim-query-test",
        )
        db.add(event)
        db.flush()

        db.add(EventMessage(event_id=event.id, raw_message_id=raw.id))
        db.add(EventTag(event_id=event.id, tag_type="countries", tag_value="Iran", tag_source="observed"))
        db.add(
            EventRelation(
                event_id=event.id,
                subject_type="country",
                subject_value="Iran",
                relation_type="conflict_with",
                object_type="country",
                object_value="Israel",
                relation_source="observed",
                inference_level=0,
            )
        )
        db.commit()

    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        client.close()
        engine.dispose()
        get_settings.cache_clear()


def _auth_headers(token: str = "bot-secret") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_query_news_valid_response(client_and_session):
    client = client_and_session
    response = client.get(
        "/api/query/news",
        params={"topic": "iran", "window": "4h"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"] == "iran"
    assert payload["window"] == "4h"
    assert payload["count"] == 1
    result = payload["results"][0]
    assert result["event_id"] > 0
    assert result["source"] == "telegram:intel_feed"
    assert result["claim"].lower().startswith("iran reportedly")
    assert result["evidence_refs"] == ["src_1"]


def test_query_summary_valid_response(client_and_session):
    client = client_and_session
    response = client.get(
        "/api/query/summary",
        params={"topic": "iran", "window": "4h"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"] == "iran"
    assert payload["window"] == "4h"
    assert payload["source_count"] == 1
    assert "key_developments" in payload["summary"]
    assert "uncertainties" in payload["summary"]
    assert "why_it_matters" in payload["summary"]


def test_query_invalid_window_returns_400(client_and_session):
    client = client_and_session
    response = client.get(
        "/api/query/news",
        params={"topic": "iran", "window": "3d"},
        headers=_auth_headers(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "window must be one of 1h, 4h, 24h"


def test_query_empty_topic_returns_400(client_and_session):
    client = client_and_session
    response = client.get(
        "/api/query/news",
        params={"topic": "   ", "window": "4h"},
        headers=_auth_headers(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "topic must be non-empty"


def test_query_missing_token_returns_401(client_and_session):
    client = client_and_session
    response = client.get(
        "/api/query/news",
        params={"topic": "iran", "window": "4h"},
    )
    assert response.status_code == 401


def test_query_invalid_token_returns_401(client_and_session):
    client = client_and_session
    response = client.get(
        "/api/query/news",
        params={"topic": "iran", "window": "4h"},
        headers=_auth_headers(token="wrong"),
    )
    assert response.status_code == 401
