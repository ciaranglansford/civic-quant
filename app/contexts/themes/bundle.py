from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ...models import Event, EventThemeEvidence
from .contracts import EvidenceBundle, EvidenceItem


def _severity_bucket(score: float) -> str:
    if score >= 80.0:
        return "high"
    if score >= 60.0:
        return "medium"
    if score >= 40.0:
        return "low"
    return "very_low"


def _sort_key(item: EvidenceItem) -> tuple[float, float, int]:
    timestamp = item.event_time.timestamp() if item.event_time is not None else 0.0
    return (float(item.calibrated_score or item.impact_score), timestamp, item.evidence_id)


def _dedupe_items(items: list[EvidenceItem]) -> tuple[list[EvidenceItem], int]:
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in items:
        grouped[item.dedupe_key].append(item)

    kept: list[EvidenceItem] = []
    repeats = 0
    for group in grouped.values():
        group_sorted = sorted(group, key=_sort_key, reverse=True)
        kept.append(group_sorted[0])
        repeats += max(0, len(group_sorted) - 1)

    kept.sort(key=_sort_key, reverse=True)
    return kept, repeats


def _freshness_profile(
    *,
    items: list[EvidenceItem],
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> str:
    if len(items) < 3:
        return "sparse"

    window_span = max(window_end_utc - window_start_utc, timedelta(hours=1))
    midpoint = window_start_utc + (window_span / 2)
    recent_cutoff = window_end_utc - timedelta(hours=6)

    recent = sum(1 for item in items if item.event_time is not None and item.event_time >= recent_cutoff)
    first_half = sum(1 for item in items if item.event_time is not None and item.event_time < midpoint)
    second_half = sum(1 for item in items if item.event_time is not None and item.event_time >= midpoint)
    total = float(len(items))

    if recent / total >= 0.6:
        return "recent_spike"
    if first_half / total >= 0.3 and second_half / total >= 0.3:
        return "persistent_buildup"
    return "distributed_accumulation"


def build_evidence_bundle(
    db: Session,
    *,
    theme_key: str,
    cadence: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> EvidenceBundle:
    rows = (
        db.query(EventThemeEvidence, Event)
        .join(Event, Event.id == EventThemeEvidence.event_id)
        .filter(
            EventThemeEvidence.theme_key == theme_key,
            or_(
                and_(
                    EventThemeEvidence.event_time.is_not(None),
                    EventThemeEvidence.event_time >= window_start_utc,
                    EventThemeEvidence.event_time < window_end_utc,
                ),
                and_(
                    EventThemeEvidence.event_time.is_(None),
                    EventThemeEvidence.created_at >= window_start_utc,
                    EventThemeEvidence.created_at < window_end_utc,
                ),
            ),
        )
        .order_by(
            EventThemeEvidence.event_time.desc().nullslast(),
            EventThemeEvidence.calibrated_score.desc(),
            EventThemeEvidence.id.desc(),
        )
        .all()
    )

    items: list[EvidenceItem] = []
    for evidence, event in rows:
        metadata = evidence.metadata_json if isinstance(evidence.metadata_json, dict) else {}
        dedupe_key = str(metadata.get("claim_hash") or f"event:{evidence.event_id}")
        directionality = str(metadata.get("directionality") or "neutral")
        items.append(
            EvidenceItem(
                evidence_id=evidence.id,
                event_id=evidence.event_id,
                extraction_id=evidence.extraction_id,
                event_time=evidence.event_time,
                event_topic=evidence.event_topic,
                impact_score=float(evidence.impact_score or 0.0),
                calibrated_score=float(evidence.calibrated_score or evidence.impact_score or 0.0),
                matched_archetypes=tuple(sorted(evidence.matched_archetypes or [])),
                reason_codes=tuple(sorted(evidence.match_reason_codes or [])),
                directionality=directionality if directionality in {"stress", "easing", "neutral"} else "neutral",
                summary=(event.summary_1_sentence or "").strip(),
                entities=tuple(sorted(evidence.entity_refs or [])),
                geographies=tuple(sorted(evidence.geography_refs or [])),
                dedupe_key=dedupe_key,
            )
        )

    deduped_items, repeat_count = _dedupe_items(items)
    supporting = [item for item in deduped_items if item.directionality != "easing"]
    contradictory = [item for item in deduped_items if item.directionality == "easing"]

    archetype_mix = Counter()
    entity_mix = Counter()
    geography_mix = Counter()
    severity_distribution = Counter()
    for item in deduped_items:
        archetype_mix.update(item.matched_archetypes)
        entity_mix.update(item.entities)
        geography_mix.update(item.geographies)
        severity_distribution.update([_severity_bucket(item.calibrated_score)])

    top_supporting = tuple(item.evidence_id for item in supporting[:5])
    top_contradictory = tuple(item.evidence_id for item in contradictory[:3])

    total_raw = len(items)
    unique = len(deduped_items)
    repeat_ratio = float(repeat_count) / float(total_raw) if total_raw > 0 else 0.0
    novelty_ratio = float(unique) / float(total_raw) if total_raw > 0 else 0.0
    contradiction_ratio = float(len(contradictory)) / float(unique) if unique > 0 else 0.0
    freshness = _freshness_profile(
        items=deduped_items,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
    )

    return EvidenceBundle(
        theme_key=theme_key,
        cadence=cadence,  # type: ignore[arg-type]
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        evidence_items=tuple(deduped_items),
        top_supporting_evidence_ids=top_supporting,
        top_contradictory_evidence_ids=top_contradictory,
        archetype_mix=dict(archetype_mix),
        entity_mix=dict(entity_mix),
        geography_mix=dict(geography_mix),
        severity_distribution=dict(severity_distribution),
        novelty_indicators={
            "repeat_ratio": round(repeat_ratio, 4),
            "novelty_ratio": round(novelty_ratio, 4),
            "contradiction_ratio": round(contradiction_ratio, 4),
            "repeat_count": float(repeat_count),
        },
        freshness_profile=freshness,  # type: ignore[arg-type]
        metadata={
            "total_raw_evidence_count": total_raw,
            "deduped_evidence_count": unique,
            "supporting_count": len(supporting),
            "contradictory_count": len(contradictory),
        },
    )
