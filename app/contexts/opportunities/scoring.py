from __future__ import annotations

from statistics import mean

from ..themes.contracts import EvidenceBundle, LensDefinition, ThemeDefinition


def _clamp(score: float) -> float:
    return float(max(0.0, min(100.0, score)))


def derive_bundle_signals(bundle: EvidenceBundle) -> set[str]:
    archetypes = set(bundle.archetype_mix.keys())
    signals: set[str] = set()
    if "input_price_shock" in archetypes or bundle.severity_distribution.get("high", 0) > 0:
        signals.add("energy_price_or_cost_stress")
    if {
        "supply_disruption",
        "logistics_disruption",
        "export_restriction",
        "outage_restart",
        "capacity_expansion_closure",
    } & archetypes:
        signals.add("supply_side_friction")
    if {"capacity_expansion_closure", "outage_restart"} & archetypes:
        signals.add("capacity_or_utilization_stress")
    if bundle.freshness_profile in {"persistent_buildup", "distributed_accumulation"} and (
        "supply_disruption" in archetypes or "capacity_expansion_closure" in archetypes
    ):
        signals.add("persistent_supply_tightening")
    return signals


def compute_evidence_strength_score(bundle: EvidenceBundle, enrichment_payload: dict[str, object]) -> float:
    if not bundle.evidence_items:
        return 0.0
    avg_score = mean(item.calibrated_score for item in bundle.evidence_items)
    supporting = len(bundle.top_supporting_evidence_ids)
    contradictory = len(bundle.top_contradictory_evidence_ids)
    freshness_boost = {
        "recent_spike": 8.0,
        "persistent_buildup": 10.0,
        "distributed_accumulation": 5.0,
        "sparse": 0.0,
    }.get(bundle.freshness_profile, 0.0)
    novelty_ratio = float(bundle.novelty_indicators.get("novelty_ratio", 0.0) or 0.0)
    directionality = str(enrichment_payload.get("directionality", "mixed"))
    directionality_boost = 4.0 if directionality in {"stress_accumulation", "stress_dominant"} else 0.0
    raw = (
        (len(bundle.evidence_items) * 7.0)
        + (avg_score * 0.45)
        + (supporting * 2.0)
        - (contradictory * 2.5)
        + freshness_boost
        + (novelty_ratio * 10.0)
        + directionality_boost
    )
    return _clamp(raw)


def compute_lens_fit_score(lens: LensDefinition, *, available_signals: set[str], bundle: EvidenceBundle) -> float:
    if not lens.required_evidence_signals:
        return 0.0
    required = set(lens.required_evidence_signals)
    hit = len(required & available_signals)
    signal_ratio = hit / float(len(required))

    archetype_overlap = len(set(lens.applicable_archetypes) & set(bundle.archetype_mix.keys()))
    archetype_ratio = archetype_overlap / float(max(1, len(lens.applicable_archetypes)))

    modifier = 0.0
    if bundle.freshness_profile == "recent_spike":
        modifier += lens.optional_score_modifiers.get("freshness_recent_spike", 0.0)
    if bundle.freshness_profile == "persistent_buildup":
        modifier += lens.optional_score_modifiers.get("persistent_buildup", 0.0)
    if bundle.top_contradictory_evidence_ids:
        modifier += lens.optional_score_modifiers.get("contradiction_penalty", 0.0)

    raw = (signal_ratio * 60.0) + (archetype_ratio * 35.0) + modifier
    return _clamp(raw)


def determine_active_lenses(
    theme_definition: ThemeDefinition,
    *,
    bundle: EvidenceBundle,
    available_signals: set[str],
) -> tuple[list[str], dict[str, float]]:
    lens_scores: dict[str, float] = {}
    active: list[str] = []
    for lens in theme_definition.lenses:
        score = compute_lens_fit_score(lens, available_signals=available_signals, bundle=bundle)
        lens_scores[lens.key] = score
        if score >= 45.0:
            active.append(lens.key)
    return active, lens_scores


def infer_active_transmission_patterns(
    theme_definition: ThemeDefinition,
    *,
    active_lens_keys: list[str],
    bundle: EvidenceBundle,
) -> list[str]:
    lens_by_key = {lens.key: lens for lens in theme_definition.lenses}
    patterns = {
        lens_by_key[key].applicable_transmission_pattern
        for key in active_lens_keys
        if key in lens_by_key
    }

    archetypes = set(bundle.archetype_mix.keys())
    if "logistics_disruption" in archetypes:
        patterns.add("trade_flow_rerouting")
    if "supply_disruption" in archetypes:
        patterns.add("supply_tightening")
    if "input_price_shock" in archetypes:
        patterns.add("margin_compression_expansion")

    allowed = set(theme_definition.allowed_transmission_patterns)
    return sorted(pattern for pattern in patterns if pattern in allowed)


def compute_opportunity_priority_score(
    *,
    evidence_strength_score: float,
    lens_fit_score: float,
    contradiction_ratio: float,
) -> float:
    raw = (evidence_strength_score * 0.45) + (lens_fit_score * 0.45) - (contradiction_ratio * 20.0)
    return _clamp(raw)


def compute_confidence_score(
    *,
    evidence_strength_score: float,
    lens_fit_score: float,
    freshness_profile: str,
    contradiction_ratio: float,
) -> float:
    freshness_bonus = {
        "recent_spike": 6.0,
        "persistent_buildup": 8.0,
        "distributed_accumulation": 4.0,
        "sparse": -4.0,
    }.get(freshness_profile, 0.0)
    raw = (evidence_strength_score * 0.5) + (lens_fit_score * 0.35) + freshness_bonus - (contradiction_ratio * 15.0)
    return _clamp(raw)


def infer_urgency(bundle: EvidenceBundle, confidence_score: float) -> str:
    if confidence_score >= 75 and bundle.freshness_profile in {"recent_spike", "persistent_buildup"}:
        return "high"
    if confidence_score >= 55:
        return "medium"
    return "low"


def infer_time_horizon(bundle: EvidenceBundle) -> str:
    if bundle.freshness_profile == "recent_spike":
        return "short_term"
    if bundle.freshness_profile == "persistent_buildup":
        return "medium_term"
    return "medium_to_long_term"


def default_scoring_strategy(bundle: EvidenceBundle, enrichment_payload: dict[str, object]) -> dict[str, object]:
    evidence_strength = compute_evidence_strength_score(bundle, enrichment_payload)
    contradiction_ratio = float(bundle.novelty_indicators.get("contradiction_ratio", 0.0) or 0.0)
    confidence = compute_confidence_score(
        evidence_strength_score=evidence_strength,
        lens_fit_score=50.0,
        freshness_profile=bundle.freshness_profile,
        contradiction_ratio=contradiction_ratio,
    )
    return {
        "evidence_strength_score": evidence_strength,
        "confidence_score": confidence,
        "urgency": infer_urgency(bundle, confidence),
        "time_horizon": infer_time_horizon(bundle),
    }
