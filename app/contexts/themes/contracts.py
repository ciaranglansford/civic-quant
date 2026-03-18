from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal


Cadence = Literal["daily", "weekly"]
FreshnessProfile = Literal["recent_spike", "persistent_buildup", "distributed_accumulation", "sparse"]
Directionality = Literal["stress", "easing", "neutral"]

EventArchetype = Literal[
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
]

TransmissionPattern = Literal[
    "input_cost_pass_through",
    "supply_tightening",
    "capacity_curtailment",
    "trade_flow_rerouting",
    "substitution_effect",
    "margin_compression_expansion",
    "geographic_bottleneck",
]


@dataclass(frozen=True)
class LensDefinition:
    key: str
    description: str
    applicable_archetypes: tuple[EventArchetype, ...]
    applicable_transmission_pattern: TransmissionPattern
    required_evidence_signals: tuple[str, ...]
    optional_score_modifiers: dict[str, float] = field(default_factory=dict)
    output_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThemeMatchResult:
    matched: bool
    theme_key: str
    matched_archetypes: tuple[EventArchetype, ...] = ()
    reason_codes: tuple[str, ...] = ()
    directionality: Directionality = "neutral"
    severity_snapshot: dict[str, object] = field(default_factory=dict)
    entity_refs: tuple[str, ...] = ()
    geography_refs: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: int
    event_id: int
    extraction_id: int | None
    event_time: datetime | None
    event_topic: str | None
    impact_score: float
    calibrated_score: float
    matched_archetypes: tuple[EventArchetype, ...]
    reason_codes: tuple[str, ...]
    directionality: Directionality
    summary: str
    entities: tuple[str, ...]
    geographies: tuple[str, ...]
    dedupe_key: str


@dataclass(frozen=True)
class EvidenceBundle:
    theme_key: str
    cadence: Cadence
    window_start_utc: datetime
    window_end_utc: datetime
    evidence_items: tuple[EvidenceItem, ...]
    top_supporting_evidence_ids: tuple[int, ...]
    top_contradictory_evidence_ids: tuple[int, ...]
    archetype_mix: dict[str, int]
    entity_mix: dict[str, int]
    geography_mix: dict[str, int]
    severity_distribution: dict[str, int]
    novelty_indicators: dict[str, float]
    freshness_profile: FreshnessProfile
    metadata: dict[str, object] = field(default_factory=dict)


ThemeMatcher = Callable[[dict[str, object]], ThemeMatchResult]
EnrichmentPlanBuilder = Callable[[EvidenceBundle], dict[str, object]]
ScoringStrategy = Callable[[EvidenceBundle, dict[str, object]], dict[str, object]]


@dataclass(frozen=True)
class ThemeDefinition:
    key: str
    title: str
    supported_cadences: tuple[Cadence, ...]
    relevant_event_archetypes: tuple[EventArchetype, ...]
    allowed_transmission_patterns: tuple[TransmissionPattern, ...]
    event_matching_rules: dict[str, object]
    evidence_window_rules: dict[str, object]
    enrichment_plan_builder: EnrichmentPlanBuilder
    scoring_strategy: ScoringStrategy
    output_rules: dict[str, object]
    lenses: tuple[LensDefinition, ...]
    event_matcher: ThemeMatcher
