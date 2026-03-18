from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import create_app
from app.models import Event, Extraction, RawMessage


def _seed_event(db, *, event_time: datetime):
    raw = RawMessage(
        source_channel_id="seed",
        source_channel_name="seed",
        telegram_message_id=f"admin-{int(event_time.timestamp())}",
        message_timestamp_utc=event_time,
        raw_text="LNG disruption lifts gas and input costs",
        normalized_text="lng disruption lifts gas and input costs",
    )
    db.add(raw)
    db.flush()

    payload = {
        "topic": "commodities",
        "entities": {
            "countries": ["Algeria"],
            "orgs": ["Gas Exporter"],
            "people": [],
            "tickers": ["TTF"],
        },
        "affected_countries_first_order": ["Algeria"],
        "market_stats": [],
        "sentiment": "negative",
        "confidence": 0.88,
        "impact_score": 84.0,
        "is_breaking": True,
        "breaking_window": "1h",
        "event_time": event_time.isoformat(),
        "source_claimed": "Wire",
        "summary_1_sentence": "LNG disruption lifts gas and input costs.",
        "keywords": ["lng", "gas", "input costs", "disruption"],
        "event_core": None,
        "event_fingerprint": "admin-fp",
    }
    extraction = Extraction(
        raw_message_id=raw.id,
        extractor_name="extract-and-score-openai-v1",
        schema_version=1,
        event_time=event_time,
        topic="commodities",
        impact_score=84.0,
        confidence=0.88,
        sentiment="negative",
        is_breaking=True,
        breaking_window="1h",
        event_fingerprint="admin-fp",
        event_identity_fingerprint_v2="admin-fp",
        payload_json=payload,
        canonical_payload_json=payload,
        metadata_json={"impact_scoring": {"calibrated_score": 84.0}},
        claim_hash="admin-claim",
    )
    db.add(extraction)
    db.flush()

    event = Event(
        event_fingerprint="admin-event",
        event_identity_fingerprint_v2="admin-event",
        topic="commodities",
        summary_1_sentence="LNG disruption lifts gas and input costs.",
        impact_score=84.0,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        last_updated_at=event_time,
        latest_extraction_id=extraction.id,
        claim_hash="admin-claim",
    )
    db.add(event)
    db.flush()


def test_admin_theme_endpoints():
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
    try:
        now = datetime.utcnow().replace(microsecond=0)
        with SessionLocal() as db:
            _seed_event(db, event_time=now - timedelta(hours=1))
            db.commit()

        themes = client.get("/admin/themes")
        assert themes.status_code == 200
        assert any(row["key"] == "energy_to_agri_inputs" for row in themes.json())

        trigger = client.post(
            "/admin/theme/run",
            json={
                "theme_key": "energy_to_agri_inputs",
                "cadence": "daily",
                "window_start_utc": (now - timedelta(days=1)).isoformat() + "Z",
                "window_end_utc": now.isoformat() + "Z",
                "dry_run": False,
                "emit_brief": True,
            },
        )
        assert trigger.status_code == 200
        run = trigger.json()
        assert run["status"] == "completed"
        run_id = run["run_id"]

        runs = client.get("/admin/theme-runs")
        assert runs.status_code == 200
        assert len(runs.json()) >= 1

        single = client.get(f"/admin/theme-runs/{run_id}")
        assert single.status_code == 200
        assert single.json()["id"] == run_id

        assessments = client.get(f"/admin/theme-runs/{run_id}/assessments")
        assert assessments.status_code == 200
        assert isinstance(assessments.json(), list)

        cards = client.get(f"/admin/theme-runs/{run_id}/thesis-cards")
        assert cards.status_code == 200
        assert isinstance(cards.json(), list)

        brief = client.get(f"/admin/theme-runs/{run_id}/brief")
        assert brief.status_code == 200
        assert brief.json()["theme_run_id"] == run_id
    finally:
        app.dependency_overrides.clear()
        client.close()
        engine.dispose()
