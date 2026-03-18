from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.themes.bundle import build_evidence_bundle
from app.contexts.themes.evidence import ensure_theme_evidence_for_window, persist_theme_matches_for_event
from app.contexts.themes.registry import get_theme_definition
from app.db import Base
from app.models import Event, EventThemeEvidence, Extraction, RawMessage


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True), engine


def _seed_event_with_extraction(db, *, summary: str, event_time: datetime, impact_score: float, claim_hash: str):
    raw = RawMessage(
        source_channel_id="seed",
        source_channel_name="seed",
        telegram_message_id=f"msg-{claim_hash}-{int(event_time.timestamp())}",
        message_timestamp_utc=event_time,
        raw_text=summary,
        normalized_text=summary.lower(),
    )
    db.add(raw)
    db.flush()

    payload = {
        "topic": "commodities",
        "entities": {
            "countries": ["Qatar"],
            "orgs": ["LNG Supplier"],
            "people": [],
            "tickers": ["TTF"],
        },
        "affected_countries_first_order": ["Qatar"],
        "market_stats": [],
        "sentiment": "negative",
        "confidence": 0.8,
        "impact_score": impact_score,
        "is_breaking": True,
        "breaking_window": "1h",
        "event_time": event_time.isoformat(),
        "source_claimed": "Wire",
        "summary_1_sentence": summary,
        "keywords": ["lng", "gas", "supply disruption", "input costs"],
        "event_core": None,
        "event_fingerprint": "f",
    }
    extraction = Extraction(
        raw_message_id=raw.id,
        extractor_name="extract-and-score-openai-v1",
        schema_version=1,
        event_time=event_time,
        topic="commodities",
        impact_score=impact_score,
        confidence=0.8,
        sentiment="negative",
        is_breaking=True,
        breaking_window="1h",
        event_fingerprint=f"fp-{claim_hash}",
        event_identity_fingerprint_v2=f"fp-{claim_hash}",
        payload_json=payload,
        canonical_payload_json=payload,
        claim_hash=claim_hash,
        metadata_json={"impact_scoring": {"calibrated_score": impact_score}},
    )
    db.add(extraction)
    db.flush()

    event = Event(
        event_fingerprint=f"event-{claim_hash}-{raw.id}",
        event_identity_fingerprint_v2=f"event-{claim_hash}-{raw.id}",
        topic="commodities",
        summary_1_sentence=summary,
        impact_score=impact_score,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        claim_hash=claim_hash,
        latest_extraction_id=extraction.id,
        last_updated_at=event_time,
    )
    db.add(event)
    db.flush()
    return event, extraction


def test_theme_evidence_persistence_is_idempotent_and_catchup_safe():
    SessionLocal, engine = _session_factory()
    try:
        with SessionLocal() as db:
            now = datetime.utcnow()
            event, extraction = _seed_event_with_extraction(
                db,
                summary="LNG supply disruption raises gas costs for downstream input users.",
                event_time=now - timedelta(hours=2),
                impact_score=81.0,
                claim_hash="claim-1",
            )
            db.commit()

            with SessionLocal() as db2:
                event_row = db2.query(Event).filter_by(id=event.id).one()
                extraction_row = db2.query(Extraction).filter_by(id=extraction.id).one()
                persist_theme_matches_for_event(db2, event=event_row, extraction=extraction_row)
                persist_theme_matches_for_event(db2, event=event_row, extraction=extraction_row)
                db2.commit()

            with SessionLocal() as db3:
                rows = db3.query(EventThemeEvidence).filter_by(theme_key="energy_to_agri_inputs").all()
                assert len(rows) == 1
                summary = ensure_theme_evidence_for_window(
                    db3,
                    theme_definition=get_theme_definition("energy_to_agri_inputs"),
                    window_start_utc=now - timedelta(days=1),
                    window_end_utc=now + timedelta(minutes=1),
                )
                assert summary["inserted_or_updated"] == 0
    finally:
        engine.dispose()


def test_bundle_dedup_and_contradictory_selection_are_deterministic():
    SessionLocal, engine = _session_factory()
    try:
        with SessionLocal() as db:
            now = datetime.utcnow().replace(microsecond=0)
            event1, extraction1 = _seed_event_with_extraction(
                db,
                summary="LNG outage causes supply disruption and cost spikes.",
                event_time=now - timedelta(hours=1),
                impact_score=85.0,
                claim_hash="same-claim",
            )
            event2, extraction2 = _seed_event_with_extraction(
                db,
                summary="Follow-up note on same LNG outage and cost pressure.",
                event_time=now - timedelta(minutes=30),
                impact_score=70.0,
                claim_hash="same-claim",
            )
            event3, extraction3 = _seed_event_with_extraction(
                db,
                summary="Facility restart eases gas tightness and reduces cost pressure.",
                event_time=now - timedelta(minutes=20),
                impact_score=62.0,
                claim_hash="easing-claim",
            )
            db.flush()

            db.add_all(
                [
                    EventThemeEvidence(
                        theme_key="energy_to_agri_inputs",
                        event_id=event1.id,
                        extraction_id=extraction1.id,
                        event_time=event1.event_time,
                        event_topic=event1.topic,
                        impact_score=event1.impact_score,
                        calibrated_score=85.0,
                        matched_archetypes=["supply_disruption", "input_price_shock"],
                        match_reason_codes=["theme_match:energy_signal"],
                        severity_snapshot_json={"calibrated_score": 85.0},
                        entity_refs=["lng supplier", "ttf"],
                        geography_refs=["qatar"],
                        metadata_json={"directionality": "stress", "claim_hash": "same-claim"},
                    ),
                    EventThemeEvidence(
                        theme_key="energy_to_agri_inputs",
                        event_id=event2.id,
                        extraction_id=extraction2.id,
                        event_time=event2.event_time,
                        event_topic=event2.topic,
                        impact_score=event2.impact_score,
                        calibrated_score=70.0,
                        matched_archetypes=["supply_disruption"],
                        match_reason_codes=["theme_match:energy_signal"],
                        severity_snapshot_json={"calibrated_score": 70.0},
                        entity_refs=["lng supplier", "ttf"],
                        geography_refs=["qatar"],
                        metadata_json={"directionality": "stress", "claim_hash": "same-claim"},
                    ),
                    EventThemeEvidence(
                        theme_key="energy_to_agri_inputs",
                        event_id=event3.id,
                        extraction_id=extraction3.id,
                        event_time=event3.event_time,
                        event_topic=event3.topic,
                        impact_score=event3.impact_score,
                        calibrated_score=62.0,
                        matched_archetypes=["outage_restart"],
                        match_reason_codes=["theme_match:energy_signal"],
                        severity_snapshot_json={"calibrated_score": 62.0},
                        entity_refs=["lng supplier", "ttf"],
                        geography_refs=["qatar"],
                        metadata_json={"directionality": "easing", "claim_hash": "easing-claim"},
                    ),
                ]
            )
            db.commit()

            bundle = build_evidence_bundle(
                db,
                theme_key="energy_to_agri_inputs",
                cadence="daily",
                window_start_utc=now - timedelta(days=1),
                window_end_utc=now + timedelta(minutes=1),
            )

            assert bundle.metadata["total_raw_evidence_count"] == 3
            assert bundle.metadata["deduped_evidence_count"] == 2
            assert len(bundle.top_supporting_evidence_ids) == 1
            assert len(bundle.top_contradictory_evidence_ids) == 1
            assert bundle.archetype_mix["supply_disruption"] >= 1
            assert bundle.novelty_indicators["repeat_ratio"] > 0
            assert bundle.freshness_profile in {
                "recent_spike",
                "persistent_buildup",
                "distributed_accumulation",
                "sparse",
            }
    finally:
        engine.dispose()
