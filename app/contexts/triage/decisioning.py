from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ...schemas import ExtractionJson, RoutingDecisionData
from ..events.event_manager import EventUpsertResult
from .relatedness import (
    build_candidate_event_context,
    burst_low_delta_prior_count,
    recent_related_rows,
)
from .routing_engine import route_extraction
from .triage_engine import TriageContext, compute_triage_action


@dataclass(frozen=True)
class TriageRoutingResult:
    decision: RoutingDecisionData
    existing_event_id: int | None
    evaluated_at: datetime


def compute_routing_decision(
    db: Session,
    *,
    raw_message_id: int,
    extraction_model: ExtractionJson,
) -> TriageRoutingResult:
    existing_event, candidate_context = build_candidate_event_context(
        db,
        extraction_model=extraction_model,
    )
    now_time = datetime.utcnow()
    recent = recent_related_rows(
        db,
        extraction_model=extraction_model,
        raw_message_id=raw_message_id,
        now_time=now_time,
    )
    soft_related, burst_prior_count = burst_low_delta_prior_count(extraction_model, recent)
    triage = compute_triage_action(
        extraction_model,
        context=TriageContext(
            existing_event_id=(existing_event.id if existing_event is not None else None),
            candidate_event=candidate_context,
            soft_related_match=soft_related,
            burst_low_delta_prior_count=burst_prior_count,
        ),
    )
    decision = route_extraction(
        extraction_model,
        triage_action=triage.triage_action,
        triage_rules=triage.reason_codes,
    )
    if triage.triage_action == "archive":
        decision.event_action = "ignore"
    elif triage.triage_action == "update" and existing_event is not None:
        decision.event_action = "update"

    return TriageRoutingResult(
        decision=decision,
        existing_event_id=(existing_event.id if existing_event is not None else None),
        evaluated_at=now_time,
    )


def apply_identity_conflict_override(
    decision: RoutingDecisionData,
    upsert_result: EventUpsertResult | None,
) -> None:
    if upsert_result is None or not upsert_result.review_required:
        return

    triage_rules = list(decision.triage_rules or [])
    triage_rules.append(f"identity:review_required:{upsert_result.review_reason}")
    decision.triage_action = "monitor"
    decision.publish_priority = "none"
    flags = list(decision.flags or [])
    flags.append("identity_conflict_review")
    decision.flags = sorted(set(flags))
    decision.triage_rules = triage_rules

