from __future__ import annotations

import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Event, EventMessage, EventTag, Extraction, RawMessage
from app.services.query_service import build_news_response, rank_query_events


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal, engine


def _seed_event_with_raw(
    db,
    *,
    fingerprint: str,
    claim_hash: str | None,
    summary: str,
    impact: float,
    event_time: dt.datetime,
    topic: str = "geopolitics",
    raw_text: str,
    raw_channel: str = "intel_feed",
) -> tuple[int, int]:
    raw = RawMessage(
        source_channel_id="-100source",
        source_channel_name=raw_channel,
        telegram_message_id=f"msg-{fingerprint}",
        message_timestamp_utc=event_time,
        raw_text=raw_text,
        raw_entities=None,
        forwarded_from=None,
        normalized_text=raw_text.lower(),
    )
    db.add(raw)
    db.flush()

    extraction = Extraction(
        raw_message_id=raw.id,
        extractor_name="extract-and-score-openai-v1",
        schema_version=1,
        event_time=event_time,
        topic=topic,
        impact_score=impact,
        confidence=0.8,
        sentiment="neutral",
        is_breaking=False,
        breaking_window="4h",
        event_fingerprint=fingerprint,
        payload_json={"summary_1_sentence": summary, "keywords": ["iran"], "entities": {"countries": ["Iran"]}},
        canonical_payload_json={
            "summary_1_sentence": summary,
            "source_claimed": "Reuters",
            "keywords": ["iran"],
            "entities": {"countries": ["Iran"], "orgs": [], "people": [], "tickers": []},
        },
        metadata_json={},
    )
    db.add(extraction)
    db.flush()

    event = Event(
        event_fingerprint=fingerprint,
        event_identity_fingerprint_v2=fingerprint,
        topic=topic,
        summary_1_sentence=summary,
        impact_score=impact,
        is_breaking=False,
        breaking_window="4h",
        event_time=event_time,
        last_updated_at=event_time,
        latest_extraction_id=extraction.id,
        claim_hash=claim_hash,
    )
    db.add(event)
    db.flush()
    db.add(EventMessage(event_id=event.id, raw_message_id=raw.id))
    db.flush()
    return event.id, raw.id


def test_query_service_ranking_dedupe_and_evidence_refs():
    SessionLocal, engine = _session_factory()
    try:
        with SessionLocal() as db:
            base_time = dt.datetime(2026, 3, 28, 12, 0, 0)
            evt_1, _ = _seed_event_with_raw(
                db,
                fingerprint="v2:iran-1",
                claim_hash="claim-dup",
                summary="Iran reportedly launched missile activity near the border.",
                impact=84.0,
                event_time=base_time - dt.timedelta(minutes=10),
                raw_text="Iran reportedly launched missile activity near the border.",
            )
            _seed_event_with_raw(
                db,
                fingerprint="v2:iran-2",
                claim_hash="claim-dup",
                summary="Iran reportedly launched missile activity near the border",
                impact=70.0,
                event_time=base_time - dt.timedelta(minutes=20),
                raw_text="Iran reportedly launched missile activity near the border",
            )
            evt_3, _ = _seed_event_with_raw(
                db,
                fingerprint="v2:iran-3",
                claim_hash="claim-distinct",
                summary="Officials said naval patrols expanded in nearby waters.",
                impact=63.0,
                event_time=base_time - dt.timedelta(minutes=30),
                raw_text="Iran naval patrols reportedly expanded in nearby waters.",
            )
            db.add(EventTag(event_id=evt_3, tag_type="countries", tag_value="Iran", tag_source="observed"))

            evt_4, raw_4 = _seed_event_with_raw(
                db,
                fingerprint="v2:fallback-4",
                claim_hash="claim-fallback",
                summary="Regional shipping advisories were updated overnight.",
                impact=48.0,
                event_time=base_time - dt.timedelta(minutes=15),
                raw_text="Iran shipping advisories were updated overnight.",
            )
            # Strip event-level match cues so this row can only match raw fallback.
            event_4 = db.query(Event).filter_by(id=evt_4).one()
            event_4.summary_1_sentence = "Regional shipping advisories were updated overnight."
            event_4.topic = "other"
            extraction_4 = db.query(Extraction).filter_by(raw_message_id=raw_4).one()
            extraction_4.canonical_payload_json = {"summary_1_sentence": "Regional shipping advisories were updated overnight."}
            extraction_4.payload_json = {"summary_1_sentence": "Regional shipping advisories were updated overnight."}
            db.commit()

            ranked = rank_query_events(
                db,
                topic="iran",
                window="4h",
                now_utc=base_time,
            )
            assert len(ranked) == 3
            assert ranked[0].event_id == evt_1
            assert ranked[0].score >= ranked[1].score

            event_ids = [row.event_id for row in ranked]
            assert evt_3 in event_ids
            assert evt_4 in event_ids
            assert sum(1 for row in ranked if row.dedupe_key == "claim:claim-dup") == 1

            news = build_news_response(db, topic="iran", window="4h", now_utc=base_time)
            assert news.count == 3
            first = news.results[0]
            assert first.evidence_refs
            assert all(ref.startswith("src_") for ref in first.evidence_refs)
            assert first.importance in {"high", "medium", "low"}
    finally:
        engine.dispose()
