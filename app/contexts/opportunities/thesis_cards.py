from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ...models import ThemeOpportunityAssessment, ThemeRun, ThesisCard
from ..themes.contracts import ThemeDefinition


_WS_RE = re.compile(r"\s+")


def _norm(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip().lower())


def _signature(theme_key: str, primary_lens: str, transmission_pattern: str, opportunity_angles: list[str]) -> str:
    head = _norm(opportunity_angles[0]) if opportunity_angles else "none"
    raw = f"{theme_key}|{primary_lens}|{transmission_pattern}|{head}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _jaccard(a: set[int], b: set[int]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return float(len(a & b)) / float(len(a | b))


def _passes_gates(theme_definition: ThemeDefinition, assessment: ThemeOpportunityAssessment) -> tuple[bool, str | None]:
    rules = theme_definition.output_rules
    if assessment.evidence_strength_score < float(rules.get("min_evidence_strength_score", 45.0)):
        return False, "gate:evidence_strength_below_threshold"
    if assessment.confidence_score < float(rules.get("min_confidence_score", 50.0)):
        return False, "gate:confidence_below_threshold"
    if assessment.opportunity_priority_score < float(rules.get("min_opportunity_priority_score", 55.0)):
        return False, "gate:priority_below_threshold"
    return True, None


def _lookback_start(theme_definition: ThemeDefinition, cadence: str, now_utc: datetime) -> datetime:
    rules = theme_definition.output_rules
    if cadence == "weekly":
        days = int(rules.get("duplicate_weekly_lookback_days", 28))
    else:
        days = int(rules.get("duplicate_daily_lookback_days", 7))
    return now_utc - timedelta(days=days)


def _find_recent_similar_card(
    db: Session,
    *,
    theme_key: str,
    narrative_signature: str,
    lookback_start: datetime,
) -> ThesisCard | None:
    return (
        db.query(ThesisCard)
        .filter(
            ThesisCard.theme_key == theme_key,
            ThesisCard.status.in_(["emitted", "updated"]),
            ThesisCard.created_at >= lookback_start,
            ThesisCard.narrative_signature == narrative_signature,
        )
        .order_by(ThesisCard.created_at.desc(), ThesisCard.id.desc())
        .first()
    )


def _material_update_reason(
    theme_definition: ThemeDefinition,
    *,
    assessment: ThemeOpportunityAssessment,
    prior_assessment: ThemeOpportunityAssessment | None,
) -> str | None:
    if prior_assessment is None:
        return None
    rules = theme_definition.output_rules
    confidence_delta = abs(assessment.confidence_score - prior_assessment.confidence_score)
    priority_delta = abs(assessment.opportunity_priority_score - prior_assessment.opportunity_priority_score)
    if confidence_delta >= float(rules.get("material_change_confidence_delta", 8.0)):
        return "material_change:confidence_delta"
    if priority_delta >= float(rules.get("material_change_priority_delta", 8.0)):
        return "material_change:priority_delta"

    current_support = set(int(v) for v in (assessment.top_supporting_evidence_ids or []))
    prior_support = set(int(v) for v in (prior_assessment.top_supporting_evidence_ids or []))
    overlap = _jaccard(current_support, prior_support)
    if overlap <= float(rules.get("material_change_evidence_overlap_max", 0.75)):
        return "material_change:supporting_evidence_shift"

    if assessment.primary_transmission_pattern != prior_assessment.primary_transmission_pattern:
        return "material_change:transmission_pattern_shift"
    if assessment.status != prior_assessment.status:
        return "material_change:assessment_status_shift"
    return None


def _render_card_fields(assessment: ThemeOpportunityAssessment) -> dict[str, object]:
    opportunities = [str(value) for value in (assessment.candidate_opportunities or [])]
    risks = [str(value) for value in (assessment.candidate_risks or [])]
    lens = assessment.primary_lens or "theme_signal"
    transmission = assessment.primary_transmission_pattern or "input_cost_pass_through"
    title = f"{assessment.theme_key}: {lens.replace('_', ' ').title()} signal"
    what_happened = (
        f"Window evidence shows {len(assessment.top_supporting_evidence_ids or [])} supporting signals with "
        f"{assessment.urgency} urgency and {assessment.time_horizon} horizon."
    )
    why_it_matters = (
        f"Transmission via {transmission.replace('_', ' ')} can affect downstream agri-input pricing or capacity dynamics."
    )
    transmission_path = (
        f"Energy/supply stress -> {transmission.replace('_', ' ')} -> agri-input pressure/capacity response"
    )
    watch_next = "Track incremental supportive vs contradictory evidence in the next batch window."
    invalidation = "; ".join(str(x) for x in (assessment.invalidation_conditions or []))
    if risks:
        watch_next = f"{watch_next} Key risk watch: {risks[0]}"
    return {
        "title": title,
        "what_happened": what_happened,
        "why_it_matters": why_it_matters,
        "transmission_path": transmission_path,
        "opportunity_angles": opportunities,
        "confidence": float(assessment.confidence_score),
        "what_to_watch_next": watch_next,
        "invalidation_criteria": invalidation,
        "supporting_evidence_refs": [int(v) for v in (assessment.top_supporting_evidence_ids or [])],
    }


def create_cards_for_assessments(
    db: Session,
    *,
    theme_run: ThemeRun,
    theme_definition: ThemeDefinition,
    assessments: list[ThemeOpportunityAssessment],
    dry_run: bool,
) -> list[ThesisCard]:
    now_utc = datetime.utcnow()
    results: list[ThesisCard] = []

    for assessment in assessments:
        rendered = _render_card_fields(assessment)
        narrative_signature = _signature(
            theme_definition.key,
            assessment.primary_lens or "theme_signal",
            assessment.primary_transmission_pattern or "input_cost_pass_through",
            [str(value) for value in rendered["opportunity_angles"]],
        )

        pass_gate, gate_reason = _passes_gates(theme_definition, assessment)
        status = "draft_only"
        suppression_reason = gate_reason
        material_update_reason = None

        if pass_gate:
            similar = _find_recent_similar_card(
                db,
                theme_key=theme_definition.key,
                narrative_signature=narrative_signature,
                lookback_start=_lookback_start(theme_definition, theme_run.cadence, now_utc),
            )
            prior_assessment = None
            if similar is not None:
                prior_assessment = (
                    db.query(ThemeOpportunityAssessment)
                    .filter(ThemeOpportunityAssessment.id == similar.assessment_id)
                    .one_or_none()
                )
            material_update_reason = _material_update_reason(
                theme_definition,
                assessment=assessment,
                prior_assessment=prior_assessment,
            )
            if similar is None:
                status = "emitted"
                suppression_reason = None
            elif material_update_reason is not None:
                status = "updated"
                suppression_reason = None
            else:
                status = "repeat_suppressed"
                suppression_reason = "duplicate:materially_similar_recent_card"

            if dry_run and status in {"emitted", "updated"}:
                status = "draft_only"
                suppression_reason = "dry_run:no_emit"

        card = ThesisCard(
            theme_run_id=theme_run.id,
            assessment_id=assessment.id,
            theme_key=theme_definition.key,
            cadence=theme_run.cadence,
            window_start_utc=theme_run.window_start_utc,
            window_end_utc=theme_run.window_end_utc,
            title=str(rendered["title"]),
            what_happened=str(rendered["what_happened"]),
            why_it_matters=str(rendered["why_it_matters"]),
            transmission_path=str(rendered["transmission_path"]),
            opportunity_angles=list(rendered["opportunity_angles"]),
            confidence=float(rendered["confidence"]),
            what_to_watch_next=str(rendered["what_to_watch_next"]),
            invalidation_criteria=str(rendered["invalidation_criteria"]),
            supporting_evidence_refs=list(rendered["supporting_evidence_refs"]),
            narrative_signature=narrative_signature,
            status=status,
            suppression_reason=suppression_reason,
            material_update_reason=material_update_reason,
            updated_at=now_utc,
        )
        db.add(card)
        db.flush()
        results.append(card)

    return results
