from __future__ import annotations

from ..opportunities.scoring import default_scoring_strategy
from .contracts import (
    EventArchetype,
    LensDefinition,
    ThemeDefinition,
)
from .matching import match_energy_to_agri_inputs


EVENT_ARCHETYPE_LIBRARY: tuple[EventArchetype, ...] = (
    "supply_disruption",
    "outage_restart",
    "regulatory_change",
    "sanctions_escalation",
    "logistics_disruption",
    "input_price_shock",
    "export_restriction",
    "weather_shock",
    "capacity_expansion_closure",
    "guidance_or_policy_signal",
)


INPUT_COST_PASS_THROUGH_LENS = LensDefinition(
    key="input_cost_pass_through",
    description="Evidence that energy/input shocks can pass through to downstream agri input costs.",
    applicable_archetypes=(
        "input_price_shock",
        "supply_disruption",
        "sanctions_escalation",
        "logistics_disruption",
    ),
    applicable_transmission_pattern="input_cost_pass_through",
    required_evidence_signals=(
        "energy_price_or_cost_stress",
        "supply_side_friction",
    ),
    optional_score_modifiers={
        "freshness_recent_spike": 4.0,
        "multi_geography_reinforcement": 3.0,
    },
    output_hints=(
        "focus on cost-pressure channel",
        "highlight timeline from energy stress to agri-input margins",
    ),
)


CAPACITY_CURTAILMENT_LENS = LensDefinition(
    key="capacity_curtailment",
    description="Evidence that elevated energy/input strain can trigger capacity curtailment risk.",
    applicable_archetypes=(
        "capacity_expansion_closure",
        "supply_disruption",
        "outage_restart",
        "export_restriction",
    ),
    applicable_transmission_pattern="capacity_curtailment",
    required_evidence_signals=(
        "capacity_or_utilization_stress",
        "persistent_supply_tightening",
    ),
    optional_score_modifiers={
        "persistent_buildup": 5.0,
        "contradiction_penalty": -4.0,
    },
    output_hints=(
        "focus on utilization and production flexibility",
        "differentiate temporary outage from sustained curtailment risk",
    ),
)


def _default_enrichment_plan_builder(bundle) -> dict[str, object]:  # noqa: ANN001
    return {
        "providers": ("internal_evidence_aggregation",),
        "bundle_size": len(bundle.evidence_items),
        "freshness_profile": bundle.freshness_profile,
    }


THEME_DEFINITIONS: tuple[ThemeDefinition, ...] = (
    ThemeDefinition(
        key="energy_to_agri_inputs",
        title="Energy to Agri Inputs",
        supported_cadences=("daily", "weekly"),
        relevant_event_archetypes=EVENT_ARCHETYPE_LIBRARY,
        allowed_transmission_patterns=(
            "input_cost_pass_through",
            "supply_tightening",
            "capacity_curtailment",
            "trade_flow_rerouting",
            "substitution_effect",
            "margin_compression_expansion",
            "geographic_bottleneck",
        ),
        event_matching_rules={
            "energy_markers": (
                "gas",
                "lng",
                "natural gas",
                "power",
                "electricity",
                "diesel",
                "oil",
                "crude",
                "brent",
                "wti",
                "feedstock",
            ),
            "supply_side_markers": (
                "outage",
                "shutdown",
                "curtail",
                "restriction",
                "disruption",
                "tightening",
                "export ban",
            ),
            "downstream_markers": (
                "cost",
                "input",
                "margin",
                "capacity",
                "fertilizer",
                "ammonia",
                "urea",
                "agri",
            ),
        },
        evidence_window_rules={
            "daily_hours": 24,
            "weekly_hours": 168,
            "window_type": "half_open_utc",
        },
        enrichment_plan_builder=_default_enrichment_plan_builder,
        scoring_strategy=default_scoring_strategy,
        output_rules={
            "min_evidence_strength_score": 45.0,
            "min_confidence_score": 50.0,
            "min_opportunity_priority_score": 55.0,
            "duplicate_daily_lookback_days": 7,
            "duplicate_weekly_lookback_days": 28,
            "material_change_confidence_delta": 8.0,
            "material_change_priority_delta": 8.0,
            "material_change_evidence_overlap_max": 0.75,
        },
        lenses=(
            INPUT_COST_PASS_THROUGH_LENS,
            CAPACITY_CURTAILMENT_LENS,
        ),
        event_matcher=match_energy_to_agri_inputs,
    ),
)
