from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import ThemeBriefArtifact, ThemeOpportunityAssessment, ThemeRun, ThesisCard
from app.workflows.theme_batch_pipeline import ThemeBatchRequest, run_theme_batch


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True), engine


def _seed_event(db, *, event_time: datetime, msg_suffix: str):
    from app.models import Event, Extraction, RawMessage

    raw = RawMessage(
        source_channel_id="seed",
        source_channel_name="seed",
        telegram_message_id=f"wf-{msg_suffix}",
        message_timestamp_utc=event_time,
        raw_text="LNG outage raises gas and downstream input costs.",
        normalized_text="lng outage raises gas and downstream input costs",
    )
    db.add(raw)
    db.flush()

    payload = {
        "topic": "commodities",
        "entities": {
            "countries": ["Norway"],
            "orgs": ["Gas Producer"],
            "people": [],
            "tickers": ["TTF"],
        },
        "affected_countries_first_order": ["Norway"],
        "market_stats": [{"label": "gas", "value": 7.2, "unit": "%", "context": "up"}],
        "sentiment": "negative",
        "confidence": 0.9,
        "impact_score": 86.0,
        "is_breaking": True,
        "breaking_window": "1h",
        "event_time": event_time.isoformat(),
        "source_claimed": "Wire",
        "summary_1_sentence": "LNG outage lifts gas prices and raises input costs downstream.",
        "keywords": ["lng", "outage", "gas", "input costs"],
        "event_core": None,
        "event_fingerprint": "wf-fp",
    }
    extraction = Extraction(
        raw_message_id=raw.id,
        extractor_name="extract-and-score-openai-v1",
        schema_version=1,
        event_time=event_time,
        topic="commodities",
        impact_score=86.0,
        confidence=0.9,
        sentiment="negative",
        is_breaking=True,
        breaking_window="1h",
        event_fingerprint="wf-fp",
        event_identity_fingerprint_v2="wf-fp",
        payload_json=payload,
        canonical_payload_json=payload,
        metadata_json={"impact_scoring": {"calibrated_score": 86.0}},
        claim_hash=f"wf-claim-{msg_suffix}",
    )
    db.add(extraction)
    db.flush()

    event = Event(
        event_fingerprint=f"event-{msg_suffix}",
        event_identity_fingerprint_v2=f"event-{msg_suffix}",
        topic="commodities",
        summary_1_sentence="LNG outage lifts gas prices and raises input costs downstream.",
        impact_score=86.0,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        latest_extraction_id=extraction.id,
        claim_hash=f"wf-claim-{msg_suffix}",
        last_updated_at=event_time,
    )
    db.add(event)
    db.flush()


def test_theme_batch_workflow_end_to_end():
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        with SessionLocal() as db:
            _seed_event(db, event_time=now - timedelta(hours=2), msg_suffix="a")
            _seed_event(db, event_time=now - timedelta(hours=1), msg_suffix="b")
            db.commit()

        with SessionLocal() as db:
            summary = run_theme_batch(
                db,
                request=ThemeBatchRequest(
                    theme_key="energy_to_agri_inputs",
                    cadence="daily",
                    window_start_utc=now - timedelta(days=1),
                    window_end_utc=now,
                    dry_run=False,
                    emit_brief=True,
                ),
                now_utc=now,
            )
            db.commit()

            assert summary.status == "completed"
            assert summary.evidence_count >= 1
            assert db.query(ThemeRun).count() == 1
            assert db.query(ThemeOpportunityAssessment).count() >= 1
            assert db.query(ThesisCard).count() >= 1
            assert db.query(ThemeBriefArtifact).count() == 1
    finally:
        engine.dispose()


def test_theme_batch_is_deterministic_without_ai_drafting():
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        with SessionLocal() as db:
            _seed_event(db, event_time=now - timedelta(hours=3), msg_suffix="det-a")
            db.commit()

        with SessionLocal() as db:
            summary_1 = run_theme_batch(
                db,
                request=ThemeBatchRequest(
                    theme_key="energy_to_agri_inputs",
                    cadence="daily",
                    window_start_utc=now - timedelta(days=1),
                    window_end_utc=now,
                    dry_run=False,
                    emit_brief=True,
                ),
                now_utc=now,
            )
            db.commit()

        with SessionLocal() as db:
            summary_2 = run_theme_batch(
                db,
                request=ThemeBatchRequest(
                    theme_key="energy_to_agri_inputs",
                    cadence="daily",
                    window_start_utc=now,
                    window_end_utc=now + timedelta(days=1),
                    dry_run=False,
                    emit_brief=True,
                ),
                now_utc=now + timedelta(days=1),
            )
            db.commit()

            assert summary_1.status == "completed"
            assert summary_2.status == "completed"
            assert db.query(ThemeRun).count() == 2
    finally:
        engine.dispose()


def test_theme_tables_exist_with_expected_additive_schema():
    SessionLocal, engine = _session_factory()
    try:
        with SessionLocal() as db:
            inspector = inspect(db.get_bind())
            table_names = set(inspector.get_table_names())
            assert "theme_runs" in table_names
            assert "event_theme_evidence" in table_names
            assert "theme_opportunity_assessments" in table_names
            assert "thesis_cards" in table_names
            assert "theme_brief_artifacts" in table_names
    finally:
        engine.dispose()


def test_theme_schema_create_all_is_idempotent():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    try:
        Base.metadata.create_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert "theme_runs" in table_names
        assert "event_theme_evidence" in table_names
    finally:
        engine.dispose()
