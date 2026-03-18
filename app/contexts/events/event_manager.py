from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from ...models import Event, EventMessage, Extraction
from ...schemas import ExtractionJson
from ..extraction.canonicalization import derive_action_class, event_time_bucket
from .event_windows import get_event_time_window
from ..extraction.extraction_payload_utils import (
    entity_signature_from_payload,
    keywords_from_payload,
    source_from_payload,
)


logger = logging.getLogger("civicquant.events")


@dataclass(frozen=True)
class EventUpsertResult:
    event_id: int
    action: str
    review_required: bool = False
    review_reason: str | None = None
    material_update: bool = False


def _normalized_values(values: list[str]) -> set[str]:
    out: set[str] = set()
    for value in values:
        cleaned = value.strip().lower()
        if cleaned:
            out.add(cleaned)
    return out


def _entity_signature_from_extraction(extraction: ExtractionJson) -> set[str]:
    entities = extraction.entities
    out: set[str] = set()
    out |= {f"country:{v}" for v in _normalized_values(entities.countries)}
    out |= {f"org:{v}" for v in _normalized_values(entities.orgs)}
    out |= {f"person:{v}" for v in _normalized_values(entities.people)}
    return out


def _keywords_from_extraction(extraction: ExtractionJson) -> set[str]:
    return _normalized_values(extraction.keywords)


def _source_from_extraction(extraction: ExtractionJson) -> str:
    return (extraction.source_claimed or "").strip().lower()


def _is_contextual_match(
    extraction: ExtractionJson,
    payload: dict,
) -> bool:
    current_entities = _entity_signature_from_extraction(extraction)
    current_keywords = _keywords_from_extraction(extraction)
    current_source = _source_from_extraction(extraction)

    candidate_entities = entity_signature_from_payload(payload)
    candidate_keywords = keywords_from_payload(payload)
    candidate_source = source_from_payload(payload)

    entity_overlap = len(current_entities & candidate_entities)
    keyword_overlap = len(current_keywords & candidate_keywords)
    same_source = bool(current_source and candidate_source and current_source == candidate_source)

    if entity_overlap >= 2:
        return True
    if same_source and keyword_overlap >= 2:
        return True
    if entity_overlap >= 1 and keyword_overlap >= 2:
        return True
    return False


def _find_contextual_candidate_event(
    db: Session,
    *,
    extraction: ExtractionJson,
    start: datetime,
    end: datetime,
    require_same_topic: bool = True,
) -> Event | None:
    query = db.query(Event).filter(
        Event.event_time.isnot(None),
        Event.event_time >= start,
        Event.event_time <= end,
    )
    if require_same_topic:
        query = query.filter(Event.topic == extraction.topic)
    candidates = query.order_by(Event.last_updated_at.desc()).all()

    latest_ids = [candidate.latest_extraction_id for candidate in candidates if candidate.latest_extraction_id is not None]
    if not latest_ids:
        return None

    extraction_rows = db.query(Extraction).filter(Extraction.id.in_(latest_ids)).all()
    by_id = {row.id: row for row in extraction_rows}

    for candidate in candidates:
        if candidate.latest_extraction_id is None:
            continue
        latest = by_id.get(candidate.latest_extraction_id)
        if latest is None:
            continue
        payload = latest.canonical_payload_json or latest.payload_json or {}
        if not isinstance(payload, dict):
            continue
        if _is_contextual_match(extraction, payload):
            logger.info(
                "event_soft_match event_id=%s extraction_topic=%s extraction_fingerprint=%s",
                candidate.id,
                extraction.topic,
                extraction.event_fingerprint,
            )
            return candidate

    return None


def find_candidate_event(
    db: Session,
    *,
    extraction: ExtractionJson,
) -> Event | None:
    has_authoritative_fingerprint = bool(
        extraction.event_fingerprint and extraction.event_fingerprint.startswith("v2:")
    )
    if extraction.event_fingerprint:
        strict_candidate = (
            db.query(Event)
            .filter(
                Event.event_identity_fingerprint_v2 == extraction.event_fingerprint,
            )
            .order_by(Event.last_updated_at.desc())
            .first()
        )
        if strict_candidate is not None:
            return strict_candidate
        if not has_authoritative_fingerprint:
            return None

    if extraction.event_time is None:
        return None

    window = get_event_time_window(extraction.topic, extraction.is_breaking)
    start = extraction.event_time - window
    end = extraction.event_time + window

    same_topic_candidate = _find_contextual_candidate_event(
        db,
        extraction=extraction,
        start=start,
        end=end,
        require_same_topic=True,
    )
    if same_topic_candidate is not None:
        return same_topic_candidate

    if has_authoritative_fingerprint:
        cross_topic_candidate = _find_contextual_candidate_event(
            db,
            extraction=extraction,
            start=start,
            end=end,
            require_same_topic=False,
        )
        if cross_topic_candidate is not None:
            logger.info(
                "event_soft_match_cross_topic event_id=%s extraction_topic=%s extraction_fingerprint=%s",
                cross_topic_candidate.id,
                extraction.topic,
                extraction.event_fingerprint,
            )
            return cross_topic_candidate

    return None


def _parse_bucket(bucket: str | None) -> date | None:
    if not bucket or bucket == "unknown":
        return None
    try:
        return date.fromisoformat(bucket)
    except ValueError:
        return None


def _is_material_bucket_shift(current_bucket: str | None, incoming_bucket: str | None) -> bool:
    current_date = _parse_bucket(current_bucket)
    incoming_date = _parse_bucket(incoming_bucket)
    if current_date is None or incoming_date is None:
        return False
    return abs((incoming_date - current_date).days) > 1


def _ensure_event_message_link(db: Session, *, event_id: int, raw_message_id: int) -> None:
    existing = (
        db.query(EventMessage)
        .filter(
            EventMessage.event_id == event_id,
            EventMessage.raw_message_id == raw_message_id,
        )
        .one_or_none()
    )
    if existing is None:
        db.add(EventMessage(event_id=event_id, raw_message_id=raw_message_id))


def update_event_from_extraction(
    event: Event,
    extraction: ExtractionJson,
    latest_extraction_id: int | None,
    *,
    canonical_payload_hash: str,
    claim_hash: str,
    action_class: str,
    time_bucket: str,
) -> dict[str, tuple[object | None, object | None]]:
    changes: dict[str, tuple[object | None, object | None]] = {}

    def _set(name: str, new_value: object | None) -> None:
        old_value = getattr(event, name)
        if old_value != new_value:
            setattr(event, name, new_value)
            changes[name] = (old_value, new_value)

    if event.canonical_payload_hash == canonical_payload_hash:
        if latest_extraction_id is not None:
            _set("latest_extraction_id", latest_extraction_id)
        return changes

    if extraction.summary_1_sentence:
        _set("summary_1_sentence", extraction.summary_1_sentence)
    _set("impact_score", float(extraction.impact_score))
    _set("topic", extraction.topic)
    _set("is_breaking", bool(extraction.is_breaking))
    _set("breaking_window", extraction.breaking_window)
    _set("event_time", extraction.event_time)
    _set("event_time_bucket", time_bucket)
    _set("action_class", action_class)
    _set("canonical_payload_hash", canonical_payload_hash)
    _set("claim_hash", claim_hash)
    _set("review_required", False)
    _set("review_reason", None)

    if latest_extraction_id is not None:
        _set("latest_extraction_id", latest_extraction_id)

    _set("last_updated_at", datetime.utcnow())
    # Reset channel publish flags when event is updated so future digest windows
    # can republish materially updated events per destination.
    _set("is_published_telegram", False)
    _set("is_published_twitter", False)
    return changes


def upsert_event(
    db: Session,
    extraction: ExtractionJson,
    raw_message_id: int,
    latest_extraction_id: int | None = None,
    *,
    canonical_payload_hash: str,
    claim_hash: str,
    action_class: str,
    time_bucket: str,
) -> EventUpsertResult:
    event_time = extraction.event_time
    candidate = find_candidate_event(db, extraction=extraction)
    identity_fingerprint = extraction.event_fingerprint or f"soft:{raw_message_id}"

    if candidate is None:
        stored_event_time = event_time or datetime.utcnow()
        event = Event(
            event_fingerprint=identity_fingerprint,
            event_identity_fingerprint_v2=identity_fingerprint,
            topic=extraction.topic,
            summary_1_sentence=extraction.summary_1_sentence,
            impact_score=float(extraction.impact_score),
            is_breaking=bool(extraction.is_breaking),
            breaking_window=extraction.breaking_window,
            event_time=stored_event_time,
            event_time_bucket=time_bucket,
            action_class=action_class,
            canonical_payload_hash=canonical_payload_hash,
            claim_hash=claim_hash,
            last_updated_at=datetime.utcnow(),
            latest_extraction_id=latest_extraction_id,
        )
        db.add(event)
        db.flush()
        _ensure_event_message_link(db, event_id=event.id, raw_message_id=raw_message_id)
        logger.info(
            "event_create raw_message_id=%s event_id=%s fingerprint=%s claim_hash=%s",
            raw_message_id,
            event.id,
            identity_fingerprint,
            claim_hash,
        )
        return EventUpsertResult(event_id=event.id, action="create", material_update=True)

    _ensure_event_message_link(db, event_id=candidate.id, raw_message_id=raw_message_id)
    has_hard_identity = bool(extraction.event_fingerprint)
    if has_hard_identity and candidate.event_identity_fingerprint_v2 == identity_fingerprint:
        if candidate.claim_hash == claim_hash:
            if latest_extraction_id is not None and candidate.latest_extraction_id != latest_extraction_id:
                candidate.latest_extraction_id = latest_extraction_id
            logger.info(
                "event_noop raw_message_id=%s event_id=%s fingerprint=%s claim_hash=%s",
                raw_message_id,
                candidate.id,
                identity_fingerprint,
                claim_hash,
            )
            return EventUpsertResult(event_id=candidate.id, action="noop", material_update=False)

        action_conflict = bool(candidate.action_class and action_class and candidate.action_class != action_class)
        bucket_conflict = _is_material_bucket_shift(candidate.event_time_bucket, time_bucket)
        if action_conflict or bucket_conflict:
            reason = "conflicting_action_class" if action_conflict else "material_time_bucket_shift"
            candidate.review_required = True
            candidate.review_reason = reason
            if latest_extraction_id is not None:
                candidate.latest_extraction_id = latest_extraction_id
            logger.warning(
                "event_identity_conflict raw_message_id=%s event_id=%s fingerprint=%s reason=%s old_claim_hash=%s new_claim_hash=%s",
                raw_message_id,
                candidate.id,
                identity_fingerprint,
                reason,
                candidate.claim_hash,
                claim_hash,
            )
            return EventUpsertResult(
                event_id=candidate.id,
                action="update_conflict",
                review_required=True,
                review_reason=reason,
                material_update=False,
            )

    changes = update_event_from_extraction(
        candidate,
        extraction,
        latest_extraction_id,
        canonical_payload_hash=canonical_payload_hash,
        claim_hash=claim_hash,
        action_class=action_class,
        time_bucket=time_bucket,
    )
    logger.info(
        "event_update raw_message_id=%s event_id=%s fingerprint=%s claim_hash=%s changes=%s",
        raw_message_id,
        candidate.id,
        identity_fingerprint,
        claim_hash,
        ",".join(sorted(changes.keys())) if changes else "none",
    )
    return EventUpsertResult(
        event_id=candidate.id,
        action="update",
        material_update=bool(changes),
    )


