from __future__ import annotations

import datetime as dt
import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _payload(channel_id: str, msg_id: str, text: str) -> dict:
    return {
        "source_channel_id": channel_id,
        "source_channel_name": "feed",
        "telegram_message_id": msg_id,
        "message_timestamp_utc": (dt.datetime.utcnow().isoformat() + "Z"),
        "raw_text": text,
        "raw_entities_if_available": None,
        "forwarded_from_if_available": None,
    }


def test_phase2_reuses_extraction_across_distinct_raw_messages(monkeypatch):
    os.environ["PHASE2_EXTRACTION_ENABLED"] = "true"
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["PHASE2_ADMIN_TOKEN"] = "secret-admin"
    os.environ["PHASE2_CONTENT_REUSE_ENABLED"] = "true"
    os.environ["PHASE2_CONTENT_REUSE_WINDOW_HOURS"] = "6"

    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import Base, get_db
    from app.main import create_app
    from app.models import Extraction, RawMessage
    from app.contexts.extraction import extraction_llm_client
    import app.db as db_module

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)

    original_session_local = db_module.SessionLocal
    db_module.SessionLocal = testing_session_local

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    calls = {"count": 0}

    def fake_extract(self, prompt_text: str):
        calls["count"] += 1
        return extraction_llm_client.LlmResponse(
            extractor_name="extract-and-score-openai-v1",
            used_openai=True,
            model_name="gpt-4o-mini",
            openai_response_id=f"resp_content_reuse_{calls['count']}",
            latency_ms=9,
            retries=0,
            raw_text='{"topic":"geopolitics","entities":{"countries":["Iran","United States"],"orgs":[],"people":[],"tickers":[]},"affected_countries_first_order":["Iran","United States"],"market_stats":[],"sentiment":"neutral","confidence":0.9,"impact_score":40,"is_breaking":true,"breaking_window":"15m","event_time":"2026-03-14T17:05:57","source_claimed":"Market News Feed","summary_1_sentence":"Iran says U.S. bases in the region do not protect anyone.","keywords":["Iran","U.S. bases","war"],"event_fingerprint":"candidate"}',
        )

    monkeypatch.setattr(extraction_llm_client.OpenAiExtractionClient, "extract", fake_extract)

    try:
        text = "IRAN PARLIAMENT SPEAKER: THIS WAR PROVED AMERICAN BASES IN OUR REGION DOES NOT PROTECT ANYONE."
        r1 = client.post("/ingest/telegram", json=_payload("c1", "dup-a", text))
        r2 = client.post("/ingest/telegram", json=_payload("c1", "dup-b", text))
        assert r1.status_code == 200
        assert r2.status_code == 200

        run = client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})
        assert run.status_code == 200
        assert calls["count"] == 1

        with testing_session_local() as db:
            raws = (
                db.query(RawMessage)
                .filter(RawMessage.telegram_message_id.in_(["dup-a", "dup-b"]))
                .order_by(RawMessage.id.asc())
                .all()
            )
            assert len(raws) == 2
            exts = (
                db.query(Extraction)
                .filter(Extraction.raw_message_id.in_([raws[0].id, raws[1].id]))
                .order_by(Extraction.raw_message_id.asc())
                .all()
            )
            assert len(exts) == 2
            first, second = exts[0], exts[1]
            assert first.canonical_payload_hash == second.canonical_payload_hash
            assert first.claim_hash == second.claim_hash
            assert second.metadata_json["content_reused"] is True
            assert second.metadata_json["content_reuse_source_extraction_id"] == first.id
    finally:
        app.dependency_overrides.clear()
        db_module.SessionLocal = original_session_local
        client.close()
        engine.dispose()
        for key in (
            "PHASE2_EXTRACTION_ENABLED",
            "OPENAI_API_KEY",
            "PHASE2_ADMIN_TOKEN",
            "PHASE2_CONTENT_REUSE_ENABLED",
            "PHASE2_CONTENT_REUSE_WINDOW_HOURS",
        ):
            os.environ.pop(key, None)
        get_settings.cache_clear()

