from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...models import EventMessage, MessageProcessingState, RawMessage
from ...schemas import SourceIngestPayload, TelegramIngestPayload
from .source_ingest import (
    SourceMessageEnvelope,
    envelope_from_source_payload,
    envelope_from_telegram_payload,
)


logger = logging.getLogger("civicquant.pipeline")


def _get_existing_raw(db: Session, source_stream_id: str, source_message_id: str) -> RawMessage | None:
    return (
        db.query(RawMessage)
        .filter(
            RawMessage.source_channel_id == source_stream_id,
            RawMessage.telegram_message_id == source_message_id,
        )
        .one_or_none()
    )


def _get_event_id_for_raw(db: Session, raw_message_id: int) -> int | None:
    link = db.query(EventMessage).filter(EventMessage.raw_message_id == raw_message_id).first()
    return link.event_id if link else None


def process_ingest_message(
    db: Session,
    payload: SourceMessageEnvelope,
    normalized_text: str,
) -> dict[str, object]:
    existing = _get_existing_raw(db, payload.source_stream_id, payload.source_message_id)
    if existing is not None:
        event_id = _get_event_id_for_raw(db, existing.id)
        return {
            "status": "duplicate",
            "raw_message_id": existing.id,
            "event_id": event_id,
            "event_action": None,
        }

    raw = RawMessage(
        source_channel_id=payload.source_stream_id,
        source_channel_name=payload.source_stream_name,
        telegram_message_id=payload.source_message_id,
        message_timestamp_utc=payload.message_timestamp_utc.replace(tzinfo=None),
        raw_text=payload.raw_text,
        raw_entities=payload.raw_entities_if_available,
        forwarded_from=payload.forwarded_from_if_available,
        normalized_text=normalized_text,
    )

    try:
        db.add(raw)
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = _get_existing_raw(db, payload.source_stream_id, payload.source_message_id)
        if existing is None:
            raise
        event_id = _get_event_id_for_raw(db, existing.id)
        return {
            "status": "duplicate",
            "raw_message_id": existing.id,
            "event_id": event_id,
            "event_action": None,
        }

    db.add(MessageProcessingState(raw_message_id=raw.id, status="pending", attempt_count=0))
    db.flush()

    logger.info("ingest_stored raw_message_id=%s phase2_state=pending", raw.id)

    return {
        "status": "created",
        "raw_message_id": raw.id,
        "event_id": None,
        "event_action": None,
    }


def process_ingest_payload(
    db: Session,
    payload: TelegramIngestPayload,
    normalized_text: str,
) -> dict[str, object]:
    envelope = envelope_from_telegram_payload(payload)
    return process_ingest_message(db=db, payload=envelope, normalized_text=normalized_text)


def process_source_ingest_payload(
    db: Session,
    payload: SourceIngestPayload,
    normalized_text: str,
) -> dict[str, object]:
    envelope = envelope_from_source_payload(payload)
    return process_ingest_message(db=db, payload=envelope, normalized_text=normalized_text)

