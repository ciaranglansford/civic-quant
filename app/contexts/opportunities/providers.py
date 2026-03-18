from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..themes.contracts import EvidenceBundle


@dataclass(frozen=True)
class EnrichmentRequest:
    theme_key: str
    cadence: str
    window_start_iso: str
    window_end_iso: str
    bundle: EvidenceBundle


@dataclass(frozen=True)
class EnrichmentResult:
    provider_name: str
    payload: dict[str, object]


class BatchEnrichmentProvider(Protocol):
    name: str

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        ...


def _top_keys(mapping: dict[str, int], *, limit: int = 5) -> list[dict[str, object]]:
    ranked = sorted(mapping.items(), key=lambda item: (-item[1], item[0]))
    return [{"key": key, "count": count} for key, count in ranked[:limit]]


class InternalEvidenceAggregationProvider:
    name = "internal_evidence_aggregation"

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        bundle = request.bundle
        supporting_count = len(bundle.top_supporting_evidence_ids)
        contradictory_count = len(bundle.top_contradictory_evidence_ids)
        directionality = "mixed"
        if supporting_count > 0 and contradictory_count == 0:
            directionality = "stress_accumulation"
        elif supporting_count > contradictory_count:
            directionality = "stress_dominant"
        elif contradictory_count > supporting_count:
            directionality = "easing_dominant"

        payload = {
            "evidence_count": len(bundle.evidence_items),
            "directionality": directionality,
            "freshness_profile": bundle.freshness_profile,
            "dominant_archetypes": _top_keys(bundle.archetype_mix, limit=4),
            "dominant_entities": _top_keys(bundle.entity_mix, limit=5),
            "dominant_geographies": _top_keys(bundle.geography_mix, limit=5),
            "severity_distribution": bundle.severity_distribution,
            "novelty_indicators": bundle.novelty_indicators,
            "strongest_supporting_evidence_ids": list(bundle.top_supporting_evidence_ids),
            "strongest_contradictory_evidence_ids": list(bundle.top_contradictory_evidence_ids),
        }
        return EnrichmentResult(provider_name=self.name, payload=payload)


class NoOpExternalProvider:
    name = "noop_external_context"

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:  # noqa: ARG002
        return EnrichmentResult(
            provider_name=self.name,
            payload={"status": "noop", "note": "external provider seam only"},
        )
