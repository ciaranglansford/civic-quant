from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from ...models import ThemeOpportunityAssessment, ThemeRun
from ..themes.contracts import EvidenceBundle, ThemeDefinition
from .scoring import (
    compute_confidence_score,
    compute_evidence_strength_score,
    compute_opportunity_priority_score,
    derive_bundle_signals,
    determine_active_lenses,
    infer_active_transmission_patterns,
    infer_time_horizon,
    infer_urgency,
)


def _hash_stable_key(parts: list[str]) -> str:
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _lens_by_key(theme_definition: ThemeDefinition) -> dict[str, object]:
    return {lens.key: lens for lens in theme_definition.lenses}


def _dominant_driver_summary(
    *,
    enrichment_payload: dict[str, object],
    active_lens: str,
    active_patterns: list[str],
) -> dict[str, object]:
    return {
        "primary_lens": active_lens,
        "active_transmission_patterns": active_patterns,
        "dominant_archetypes": enrichment_payload.get("dominant_archetypes", []),
        "dominant_entities": enrichment_payload.get("dominant_entities", []),
        "dominant_geographies": enrichment_payload.get("dominant_geographies", []),
        "directionality": enrichment_payload.get("directionality", "mixed"),
    }


def _candidate_opportunities(
    *,
    active_lens: str,
    active_patterns: list[str],
) -> list[str]:
    if active_lens == "input_cost_pass_through":
        return [
            "Look for downstream agri-input margin pressure where feedstock costs stay elevated.",
            "Monitor relative winners with stronger pass-through pricing power.",
        ]
    if active_lens == "capacity_curtailment":
        return [
            "Watch for producers exposed to energy-cost-driven utilization cuts.",
            "Prioritize setups where tightening supply can support pricing downstream.",
        ]
    return [f"Monitor transmission via {', '.join(active_patterns)}."]


def _candidate_risks(active_lens: str) -> list[str]:
    if active_lens == "input_cost_pass_through":
        return [
            "Energy retracement can soften pass-through pressure quickly.",
            "Policy intervention on input subsidies can reduce pricing transmission.",
        ]
    if active_lens == "capacity_curtailment":
        return [
            "Rapid restart/outage resolution can invalidate curtailment risk.",
            "Demand softness can offset supply tightening effects.",
        ]
    return ["Conflicting evidence can reduce opportunity conviction."]


def _invalidation_conditions(active_lens: str) -> list[str]:
    if active_lens == "input_cost_pass_through":
        return [
            "Energy input benchmarks normalize materially for multiple consecutive runs.",
            "Contradictory evidence dominates supporting evidence in the next run window.",
        ]
    return [
        "Capacity normalization/restart evidence outpaces disruption signals.",
        "Supply-side stress markers fade below activation thresholds.",
    ]


def create_assessments_for_bundle(
    db: Session,
    *,
    theme_run: ThemeRun,
    theme_definition: ThemeDefinition,
    bundle: EvidenceBundle,
    enrichment_payload: dict[str, object],
) -> list[ThemeOpportunityAssessment]:
    available_signals = derive_bundle_signals(bundle)
    active_lens_keys, lens_scores = determine_active_lenses(
        theme_definition,
        bundle=bundle,
        available_signals=available_signals,
    )
    if not active_lens_keys:
        return []

    active_patterns = infer_active_transmission_patterns(
        theme_definition,
        active_lens_keys=active_lens_keys,
        bundle=bundle,
    )
    evidence_strength = compute_evidence_strength_score(bundle, enrichment_payload)
    contradiction_ratio = float(bundle.novelty_indicators.get("contradiction_ratio", 0.0) or 0.0)
    lenses = _lens_by_key(theme_definition)

    saved: list[ThemeOpportunityAssessment] = []
    for lens_key in active_lens_keys:
        lens = lenses.get(lens_key)
        if lens is None:
            continue
        lens_fit = float(lens_scores.get(lens_key, 0.0))
        priority = compute_opportunity_priority_score(
            evidence_strength_score=evidence_strength,
            lens_fit_score=lens_fit,
            contradiction_ratio=contradiction_ratio,
        )
        confidence = compute_confidence_score(
            evidence_strength_score=evidence_strength,
            lens_fit_score=lens_fit,
            freshness_profile=bundle.freshness_profile,
            contradiction_ratio=contradiction_ratio,
        )
        urgency = infer_urgency(bundle, confidence)
        time_horizon = infer_time_horizon(bundle)

        stable_key = _hash_stable_key(
            [
                theme_definition.key,
                theme_run.cadence,
                theme_run.window_start_utc.isoformat(),
                theme_run.window_end_utc.isoformat(),
                lens_key,
                ",".join(str(eid) for eid in bundle.top_supporting_evidence_ids[:3]),
            ]
        )

        existing = db.query(ThemeOpportunityAssessment).filter_by(stable_key=stable_key).one_or_none()
        row = existing or ThemeOpportunityAssessment(
            theme_run_id=theme_run.id,
            stable_key=stable_key,
            theme_key=theme_definition.key,
            cadence=theme_run.cadence,
            window_start_utc=theme_run.window_start_utc,
            window_end_utc=theme_run.window_end_utc,
        )
        if existing is None:
            db.add(row)

        row.active_lenses = list(active_lens_keys)
        row.active_transmission_patterns = list(active_patterns)
        row.primary_lens = lens_key
        row.primary_transmission_pattern = getattr(lens, "applicable_transmission_pattern", None)
        row.evidence_summary_json = {
            "count": len(bundle.evidence_items),
            "archetype_mix": bundle.archetype_mix,
            "severity_distribution": bundle.severity_distribution,
            "freshness_profile": bundle.freshness_profile,
            "novelty_indicators": bundle.novelty_indicators,
        }
        row.top_supporting_evidence_ids = list(bundle.top_supporting_evidence_ids)
        row.top_contradictory_evidence_ids = list(bundle.top_contradictory_evidence_ids)
        row.dominant_drivers = _dominant_driver_summary(
            enrichment_payload=enrichment_payload,
            active_lens=lens_key,
            active_patterns=active_patterns,
        )
        row.transmission_narrative_json = {
            "start": "Energy and supply-side evidence accumulates.",
            "transmission": getattr(lens, "applicable_transmission_pattern", "input_cost_pass_through"),
            "end": "Potential downstream agri-input pressure or capacity stress.",
        }
        row.candidate_opportunities = _candidate_opportunities(
            active_lens=lens_key,
            active_patterns=active_patterns,
        )
        row.candidate_risks = _candidate_risks(lens_key)
        row.evidence_strength_score = evidence_strength
        row.lens_fit_score = lens_fit
        row.opportunity_priority_score = priority
        row.confidence_score = confidence
        row.urgency = urgency
        row.time_horizon = time_horizon
        row.invalidation_conditions = _invalidation_conditions(lens_key)
        row.status = "active" if confidence >= 50.0 else "watch"
        row.created_at = row.created_at or datetime.utcnow()
        db.flush()
        saved.append(row)

    return saved
