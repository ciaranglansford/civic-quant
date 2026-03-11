from __future__ import annotations

import os
from datetime import datetime, timedelta

from app.schemas import ExtractionEntities, ExtractionJson


def _extraction(
    *,
    summary: str,
    impact: float,
    event_time: datetime,
    countries: list[str] | None = None,
    orgs: list[str] | None = None,
    source_claimed: str = "AP",
    keywords: list[str] | None = None,
    fingerprint: str | None = None,
) -> ExtractionJson:
    return ExtractionJson(
        topic="war_security",
        entities=ExtractionEntities(
            countries=countries or ["United States"],
            orgs=orgs or ["AP"],
            people=[],
            tickers=[],
        ),
        affected_countries_first_order=["United States"],
        market_stats=[],
        sentiment="negative",
        confidence=0.8,
        impact_score=impact,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        source_claimed=source_claimed,
        summary_1_sentence=summary,
        keywords=keywords or ["conflict", "strike"],
        event_fingerprint=(
            fingerprint
            if fingerprint is not None
            else "war_security|2025-01-01|United States|ap|||" + summary.lower().replace(" ", "_")
        ),
    )


def _raw_message(msg_id: str, ts: datetime):
    from app.models import RawMessage

    return RawMessage(
        source_channel_id="test",
        source_channel_name="test",
        telegram_message_id=msg_id,
        message_timestamp_utc=ts,
        raw_text=f"raw-{msg_id}",
        normalized_text=f"norm-{msg_id}",
    )


def _persist_extraction(db, *, raw_message_id: int, extraction: ExtractionJson) -> int:
    from app.models import Extraction

    payload = extraction.model_dump(mode="json")
    row = Extraction(
        raw_message_id=raw_message_id,
        extractor_name="extract-and-score-openai-v1",
        schema_version=1,
        event_time=extraction.event_time,
        topic=extraction.topic,
        impact_score=float(extraction.impact_score),
        confidence=float(extraction.confidence),
        sentiment=extraction.sentiment,
        is_breaking=bool(extraction.is_breaking),
        breaking_window=extraction.breaking_window,
        event_fingerprint=extraction.event_fingerprint,
        payload_json=payload,
        canonical_payload_json=payload,
        validated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row.id


def _reset_pipeline_tables(db) -> None:
    from app.models import EntityMention, Event, EventMessage, Extraction, MessageProcessingState, RawMessage, RoutingDecision

    db.query(EntityMention).delete()
    db.query(EventMessage).delete()
    db.query(RoutingDecision).delete()
    db.query(MessageProcessingState).delete()
    db.query(Event).delete()
    db.query(Extraction).delete()
    db.query(RawMessage).delete()
    db.commit()


def test_event_upsert_links_repetitive_and_updates_summary():
    db_path = "./test_civicquant_events.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import SessionLocal, init_db
    from app.models import Event, EventMessage
    from app.services.event_manager import upsert_event

    init_db()
    now = datetime.utcnow()

    with SessionLocal() as db:
        _reset_pipeline_tables(db)
        raw1 = _raw_message("1001", now)
        raw2 = _raw_message("1002", now + timedelta(minutes=10))
        db.add_all([raw1, raw2])
        db.flush()

        base = _extraction(summary="Officials report strike.", impact=40.0, event_time=now)
        follow_up = _extraction(
            summary="Officials report strike; details disputed.",
            impact=65.0,
            event_time=now + timedelta(minutes=10),
            fingerprint=base.event_fingerprint,
        )

        extraction_id_1 = _persist_extraction(db, raw_message_id=raw1.id, extraction=base)
        extraction_id_2 = _persist_extraction(db, raw_message_id=raw2.id, extraction=follow_up)

        e1, a1 = upsert_event(db, base, raw_message_id=raw1.id, latest_extraction_id=extraction_id_1)
        e2, a2 = upsert_event(db, follow_up, raw_message_id=raw2.id, latest_extraction_id=extraction_id_2)
        db.commit()

        assert e1 == e2
        assert a1 == "create"
        assert a2 == "update"

        event = db.query(Event).filter_by(id=e1).one()
        assert event.summary_1_sentence == "Officials report strike; details disputed."
        assert float(event.impact_score or 0.0) == 65.0
        links = db.query(EventMessage).filter_by(event_id=e1).all()
        assert len(links) == 2


def test_event_upsert_soft_merges_related_context_within_window():
    db_path = "./test_civicquant_events_soft_related.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import SessionLocal, init_db
    from app.models import EventMessage
    from app.services.event_manager import upsert_event

    init_db()
    now = datetime.utcnow()

    with SessionLocal() as db:
        _reset_pipeline_tables(db)
        raw1 = _raw_message("3001", now)
        raw2 = _raw_message("3002", now + timedelta(minutes=5))
        db.add_all([raw1, raw2])
        db.flush()

        first = _extraction(
            summary="Russian Foreign Ministry warns Hormuz navigation stoppage may imbalance oil and gas markets.",
            impact=72.0,
            event_time=now,
            countries=["Russia"],
            orgs=["Russian Foreign Ministry"],
            source_claimed="Market News Feed",
            keywords=["hormuz", "oil", "gas", "navigation"],
            fingerprint="fingerprint-a",
        )
        second = _extraction(
            summary="Russian FM says Hormuz disruption may unbalance global oil and gas markets.",
            impact=74.0,
            event_time=now + timedelta(minutes=5),
            countries=["Russia"],
            orgs=["Russian Foreign Ministry"],
            source_claimed="Market News Feed",
            keywords=["hormuz", "oil", "gas", "shipping"],
            fingerprint="fingerprint-b",
        )

        extraction_id_1 = _persist_extraction(db, raw_message_id=raw1.id, extraction=first)
        extraction_id_2 = _persist_extraction(db, raw_message_id=raw2.id, extraction=second)

        e1, a1 = upsert_event(db, first, raw_message_id=raw1.id, latest_extraction_id=extraction_id_1)
        e2, a2 = upsert_event(db, second, raw_message_id=raw2.id, latest_extraction_id=extraction_id_2)
        db.commit()

        assert a1 == "create"
        assert a2 == "update"
        assert e1 == e2
        links = db.query(EventMessage).filter_by(event_id=e1).all()
        assert len(links) == 2


def test_event_upsert_does_not_soft_merge_different_contexts():
    db_path = "./test_civicquant_events_soft.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import SessionLocal, init_db
    from app.models import Event
    from app.services.event_manager import upsert_event

    init_db()
    now = datetime.utcnow()

    with SessionLocal() as db:
        _reset_pipeline_tables(db)
        raw1 = _raw_message("2001", now)
        raw2 = _raw_message("2002", now + timedelta(minutes=5))
        db.add_all([raw1, raw2])
        db.flush()

        first = _extraction(
            summary="Soft merge guard case one.",
            impact=60.0,
            event_time=now,
            countries=["United States"],
            orgs=["AP"],
            source_claimed="AP",
            keywords=["strike", "conflict"],
            fingerprint="fingerprint-first",
        )
        second = _extraction(
            summary="Separate maritime advisory case.",
            impact=62.0,
            event_time=now + timedelta(minutes=5),
            countries=["United Kingdom"],
            orgs=["UK Ministry of Defence"],
            source_claimed="UK MOD",
            keywords=["shipping", "maritime"],
            fingerprint="fingerprint-second",
        )

        extraction_id_1 = _persist_extraction(db, raw_message_id=raw1.id, extraction=first)
        extraction_id_2 = _persist_extraction(db, raw_message_id=raw2.id, extraction=second)

        e1, a1 = upsert_event(db, first, raw_message_id=raw1.id, latest_extraction_id=extraction_id_1)
        e2, a2 = upsert_event(db, second, raw_message_id=raw2.id, latest_extraction_id=extraction_id_2)
        db.commit()

        assert a1 == "create"
        assert a2 == "create"
        assert e1 != e2
        fingerprints = {
            row.event_fingerprint
            for row in db.query(Event).filter(Event.id.in_([e1, e2])).all()
        }
        assert fingerprints == {"fingerprint-first", "fingerprint-second"}

def test_event_upsert_without_hard_fingerprint_uses_soft_matching_only():
    db_path = "./test_civicquant_events_soft_only.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import SessionLocal, init_db
    from app.models import Event, EventMessage
    from app.services.event_manager import upsert_event

    init_db()
    now = datetime.utcnow()

    with SessionLocal() as db:
        _reset_pipeline_tables(db)
        raw1 = _raw_message("4001", now)
        raw2 = _raw_message("4002", now + timedelta(minutes=4))
        db.add_all([raw1, raw2])
        db.flush()

        first = _extraction(
            summary="Officials report coordinated patrol activity.",
            impact=52.0,
            event_time=now,
            countries=["United States"],
            orgs=["Coast Guard"],
            source_claimed="Coast Guard",
            keywords=["patrol", "maritime", "advisory"],
            fingerprint="",
        )
        second = _extraction(
            summary="Coast Guard says maritime patrol advisory remains active.",
            impact=58.0,
            event_time=now + timedelta(minutes=4),
            countries=["United States"],
            orgs=["Coast Guard"],
            source_claimed="Coast Guard",
            keywords=["patrol", "maritime", "advisory"],
            fingerprint="",
        )

        extraction_id_1 = _persist_extraction(db, raw_message_id=raw1.id, extraction=first)
        extraction_id_2 = _persist_extraction(db, raw_message_id=raw2.id, extraction=second)

        e1, a1 = upsert_event(db, first, raw_message_id=raw1.id, latest_extraction_id=extraction_id_1)
        e2, a2 = upsert_event(db, second, raw_message_id=raw2.id, latest_extraction_id=extraction_id_2)
        db.commit()

        assert a1 == "create"
        assert a2 == "update"
        assert e1 == e2

        event = db.query(Event).filter_by(id=e1).one()
        assert event.event_fingerprint == f"soft:{raw1.id}"
        links = db.query(EventMessage).filter_by(event_id=e1).all()
        assert len(links) == 2
