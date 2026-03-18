from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ...contexts.extraction.extraction_payload_utils import payload_for_extraction_row
from ...models import Event, EventThemeEvidence, Extraction
from .contracts import ThemeDefinition, ThemeMatchResult
from .registry import list_theme_definitions


def _match_context(
    *,
    theme_definition: ThemeDefinition,
    event: Event,
    extraction: Extraction | None,
) -> dict[str, object]:
    payload = payload_for_extraction_row(extraction) if extraction is not None else {}
    return {
        "theme_key": theme_definition.key,
        "payload": payload,
        "event": event,
        "extraction": extraction,
        "event_matching_rules": theme_definition.event_matching_rules,
    }


def _upsert_event_theme_evidence(
    db: Session,
    *,
    theme_key: str,
    event: Event,
    extraction: Extraction | None,
    match: ThemeMatchResult,
) -> EventThemeEvidence:
    extraction_id = extraction.id if extraction is not None else None
    existing = (
        db.query(EventThemeEvidence)
        .filter(
            EventThemeEvidence.theme_key == theme_key,
            EventThemeEvidence.event_id == event.id,
            EventThemeEvidence.extraction_id == extraction_id,
        )
        .one_or_none()
    )
    row = existing or EventThemeEvidence(
        theme_key=theme_key,
        event_id=event.id,
        extraction_id=extraction_id,
    )
    if existing is None:
        db.add(row)

    calibrated = 0.0
    if extraction is not None and isinstance(extraction.metadata_json, dict):
        impact_scoring = extraction.metadata_json.get("impact_scoring", {})
        if isinstance(impact_scoring, dict):
            calibrated = float(impact_scoring.get("calibrated_score", 0.0) or 0.0)

    row.event_time = event.event_time
    row.event_topic = event.topic
    row.impact_score = float(event.impact_score or 0.0)
    row.calibrated_score = calibrated or float(event.impact_score or 0.0)
    row.matched_archetypes = list(match.matched_archetypes)
    row.match_reason_codes = list(match.reason_codes)
    row.severity_snapshot_json = dict(match.severity_snapshot)
    row.entity_refs = list(match.entity_refs)
    row.geography_refs = list(match.geography_refs)
    row.metadata_json = {
        **dict(match.metadata),
        "directionality": match.directionality,
        "claim_hash": getattr(extraction, "claim_hash", None) or event.claim_hash,
        "event_identity_fingerprint_v2": event.event_identity_fingerprint_v2,
    }
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def persist_theme_matches_for_event(
    db: Session,
    *,
    event: Event,
    extraction: Extraction | None,
) -> list[EventThemeEvidence]:
    saved_rows: list[EventThemeEvidence] = []
    for definition in list_theme_definitions():
        context = _match_context(theme_definition=definition, event=event, extraction=extraction)
        match = definition.event_matcher(context)
        if not match.matched:
            continue
        saved_rows.append(
            _upsert_event_theme_evidence(
                db,
                theme_key=definition.key,
                event=event,
                extraction=extraction,
                match=match,
            )
        )
    return saved_rows


def ensure_theme_evidence_for_window(
    db: Session,
    *,
    theme_definition: ThemeDefinition,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> dict[str, int]:
    scanned = 0
    matched = 0
    inserted_or_updated = 0

    events = (
        db.query(Event)
        .filter(
            or_(
                and_(Event.event_time.is_not(None), Event.event_time >= window_start_utc, Event.event_time < window_end_utc),
                and_(
                    Event.event_time.is_(None),
                    Event.last_updated_at >= window_start_utc,
                    Event.last_updated_at < window_end_utc,
                ),
            )
        )
        .order_by(Event.event_time.desc().nullslast(), Event.last_updated_at.desc(), Event.id.desc())
        .all()
    )

    for event in events:
        scanned += 1
        extraction = None
        if event.latest_extraction_id is not None:
            extraction = db.query(Extraction).filter_by(id=event.latest_extraction_id).one_or_none()
        extraction_id = extraction.id if extraction is not None else None

        existing = (
            db.query(EventThemeEvidence)
            .filter(
                EventThemeEvidence.theme_key == theme_definition.key,
                EventThemeEvidence.event_id == event.id,
                EventThemeEvidence.extraction_id == extraction_id,
            )
            .one_or_none()
        )
        if existing is not None:
            continue

        context = _match_context(theme_definition=theme_definition, event=event, extraction=extraction)
        match = theme_definition.event_matcher(context)
        if not match.matched:
            continue

        matched += 1
        _upsert_event_theme_evidence(
            db,
            theme_key=theme_definition.key,
            event=event,
            extraction=extraction,
            match=match,
        )
        inserted_or_updated += 1

    return {
        "scanned": scanned,
        "matched": matched,
        "inserted_or_updated": inserted_or_updated,
    }
