from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ...models import Extraction
from ...schemas import ExtractionJson
from ..extraction.extraction_payload_utils import (
    entity_signature_from_payload,
    keywords_from_payload,
    payload_for_extraction_row,
    source_class_from_payload,
    source_from_payload,
    summary_tags_from_payload,
)
from ..events.event_manager import find_candidate_event
from .triage_engine import CandidateEventContext, entity_signature, impact_band


def build_candidate_event_context(
    db: Session,
    *,
    extraction_model: ExtractionJson,
) -> tuple[object | None, CandidateEventContext | None]:
    existing_event = find_candidate_event(db, extraction=extraction_model)
    if existing_event is None or existing_event.latest_extraction_id is None:
        return existing_event, None

    latest = db.query(Extraction).filter_by(id=existing_event.latest_extraction_id).one_or_none()
    if latest is None:
        return existing_event, None

    payload = payload_for_extraction_row(latest)
    impact_val = latest.impact_score if latest.impact_score is not None else float(payload.get("impact_score") or 0.0)
    return (
        existing_event,
        CandidateEventContext(
            impact_band=impact_band(float(impact_val)),
            entities=entity_signature_from_payload(payload),
            summary_tags=summary_tags_from_payload(payload),
            source_class=source_class_from_payload(payload),
        ),
    )


def recent_related_rows(
    db: Session,
    *,
    extraction_model: ExtractionJson,
    raw_message_id: int,
    now_time: datetime,
) -> list[Extraction]:
    start = now_time - timedelta(minutes=15)
    end = now_time
    return (
        db.query(Extraction)
        .filter(
            Extraction.raw_message_id != raw_message_id,
            Extraction.topic == extraction_model.topic,
            Extraction.created_at >= start,
            Extraction.created_at <= end,
        )
        .order_by(Extraction.created_at.asc())
        .all()
    )


def burst_low_delta_prior_count(
    extraction_model: ExtractionJson,
    recent_rows: list[Extraction],
) -> tuple[bool, int]:
    current_entities = entity_signature(extraction_model)
    current_keywords = {k.strip().lower() for k in extraction_model.keywords if k and k.strip()}
    current_source = (extraction_model.source_claimed or "").strip().lower()
    current_band_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}[impact_band(extraction_model.impact_score)]
    prior_entity_union: set[str] = set()
    qualifying = 0
    soft_related_match = False

    for row in recent_rows:
        payload = payload_for_extraction_row(row)
        row_fp = str(payload.get("event_fingerprint") or row.event_fingerprint or "")
        row_entities = entity_signature_from_payload(payload)
        row_keywords = keywords_from_payload(payload)
        row_source = source_from_payload(payload)
        overlap = len(current_entities & row_entities)
        keyword_overlap = len(current_keywords & row_keywords)
        same_source_keyword_overlap = bool(
            current_source and row_source and current_source == row_source and keyword_overlap >= 2
        )
        related = (row_fp and row_fp == extraction_model.event_fingerprint) or overlap >= 2 or same_source_keyword_overlap
        if not related:
            continue

        soft_related_match = True
        prior_entity_union |= row_entities
        row_impact = row.impact_score if row.impact_score is not None else float(payload.get("impact_score") or 0.0)
        row_band_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}[impact_band(float(row_impact))]
        impact_not_increasing = current_band_rank <= row_band_rank
        no_new_entities = len(current_entities - prior_entity_union) == 0
        if impact_not_increasing and (no_new_entities or same_source_keyword_overlap):
            qualifying += 1

    return soft_related_match, qualifying

