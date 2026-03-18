from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import EntityMention, Event, RawMessage
from app.schemas import ExtractionEntities, ExtractionJson


def _extraction(event_time: datetime) -> ExtractionJson:
    return ExtractionJson(
        topic="geopolitics",
        entities=ExtractionEntities(
            countries=["United States"],
            orgs=["AP"],
            people=["John Doe"],
            tickers=["EUR"],
        ),
        affected_countries_first_order=["United States"],
        market_stats=[],
        sentiment="neutral",
        confidence=0.7,
        impact_score=60.0,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        source_claimed="AP",
        summary_1_sentence="Reported claim.",
        keywords=["reported"],
        event_core=None,
        event_fingerprint="f",
    )


def test_entity_indexing_insert_dedup_and_time_window_query():
    from app.contexts.entities.entity_indexing import index_entities_for_extraction, query_entity_mentions

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)

    now = datetime.utcnow()
    extraction = _extraction(now)

    try:
        with SessionLocal() as db:
            raw = RawMessage(
                source_channel_id="c1",
                source_channel_name="feed",
                telegram_message_id="entity-test-1",
                message_timestamp_utc=now,
                raw_text="entity test",
                raw_entities=None,
                forwarded_from=None,
                normalized_text="entity test",
            )
            db.add(raw)
            db.flush()

            event = Event(
                event_fingerprint="entity-event-1",
                topic="geopolitics",
                summary_1_sentence="Entity event",
                impact_score=55.0,
                is_breaking=True,
                breaking_window="1h",
                event_time=now,
                last_updated_at=now,
            )
            db.add(event)
            db.flush()

            index_entities_for_extraction(db, raw_message_id=raw.id, event_id=event.id, extraction=extraction)
            index_entities_for_extraction(db, raw_message_id=raw.id, event_id=event.id, extraction=extraction)
            db.commit()

            all_rows = db.query(EntityMention).filter_by(raw_message_id=raw.id).all()
            assert len(all_rows) == 4

            in_window = query_entity_mentions(
                db,
                entity_type="country",
                entity_value="United States",
                start_time=now - timedelta(minutes=5),
                end_time=now + timedelta(minutes=5),
            )
            assert len(in_window) == 1
    finally:
        engine.dispose()

