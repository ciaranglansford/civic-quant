"""Deterministic digest preparation primitives.

This module does not perform transport formatting or publish decisions.
Its responsibilities are:
- map selected `Event` rows into canonical `SourceDigestEvent` objects,
- run deterministic pre-dedupe grouping before synthesis,
- build deterministic fallback digest composition when LLM synthesis is disabled/invalid.

The output from this module is designed to be consumed by `synthesizer.py`
and `orchestrator.py`, where publication state and artifact persistence are handled.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import re
from typing import Sequence

from ..models import Event
from .types import (
    CanonicalDigest,
    DigestBullet,
    DigestWindow,
    SourceDigestEvent,
    SourceEventGroup,
    TopicSection,
)


_TOPIC_LABELS: dict[str, str] = {
    "macro_econ": "Macro Econ",
    "central_banks": "Central Banks",
    "equities": "Equities",
    "credit": "Credit",
    "rates": "Rates",
    "fx": "FX",
    "commodities": "Commodities",
    "crypto": "Crypto",
    "war_security": "War / Security",
    "geopolitics": "Geopolitics",
    "company_specific": "Company Specific",
    "other": "Other",
}

_SUMMARY_WS_RE = re.compile(r"\s+")
_SUMMARY_PUNCT_RE = re.compile(r"[^\w\s]")


def normalize_topic_label(topic: str | None) -> str:
    if not topic:
        return "Other"
    cleaned = topic.strip()
    if not cleaned:
        return "Other"
    return _TOPIC_LABELS.get(cleaned, cleaned)


def known_topic_labels() -> tuple[str, ...]:
    labels = set(_TOPIC_LABELS.values())
    labels.add("Other")
    return tuple(sorted(labels, key=lambda s: (s.lower(), s)))


def topic_label_supported(value: str | None) -> bool:
    normalized = normalize_topic_label(value)
    return normalized in known_topic_labels()


def normalize_summary_for_compare(text: str) -> str:
    collapsed = _SUMMARY_WS_RE.sub(" ", (text or "").strip()).casefold()
    stripped = _SUMMARY_PUNCT_RE.sub("", collapsed)
    return _SUMMARY_WS_RE.sub(" ", stripped).strip()


def _clean_summary_for_output(summary: str | None) -> str:
    cleaned = _SUMMARY_WS_RE.sub(" ", (summary or "").strip())
    return cleaned or "(no summary)"


def _event_order_key(event: SourceDigestEvent) -> tuple[float, float, int]:
    impact = event.impact_score if event.impact_score is not None else -1.0
    return (-impact, -event.last_updated_at.timestamp(), event.event_id)


def _group_order_key(group: SourceEventGroup) -> tuple[float, float, int]:
    impact = group.impact_score if group.impact_score is not None else -1.0
    return (-impact, -group.last_updated_at.timestamp(), group.representative_event_id)


def _group_to_bullet(group: SourceEventGroup) -> DigestBullet:
    return DigestBullet(
        text=group.summary_1_sentence,
        topic_label=group.topic_label,
        source_event_ids=group.source_event_ids,
    )


def build_source_digest_events(events: Sequence[Event]) -> tuple[SourceDigestEvent, ...]:
    """Convert selected `Event` rows into canonical source digest events."""

    rows: list[SourceDigestEvent] = []
    for event in events:
        if event.id is None:
            continue
        rows.append(
            SourceDigestEvent(
                event_id=event.id,
                topic_raw=event.topic,
                topic_label=normalize_topic_label(event.topic),
                summary_1_sentence=_clean_summary_for_output(event.summary_1_sentence),
                impact_score=event.impact_score,
                last_updated_at=event.last_updated_at,
                event_fingerprint=(event.event_fingerprint or "").strip() or None,
                claim_hash=(event.claim_hash or "").strip() or None,
            )
        )

    rows.sort(key=lambda row: (-row.last_updated_at.timestamp(), row.event_id))
    return tuple(rows)


def _norm_token(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().casefold()
    return cleaned or None


def _cluster_topic_events(topic_events: Sequence[SourceDigestEvent]) -> list[list[SourceDigestEvent]]:
    if not topic_events:
        return []

    parent = list(range(len(topic_events)))

    def find(index: int) -> int:
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != index:
            nxt = parent[index]
            parent[index] = root
            index = nxt
        return root

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    key_to_index: dict[str, int] = {}
    for idx, event in enumerate(topic_events):
        keys: list[str] = []
        claim_hash = _norm_token(event.claim_hash)
        if claim_hash:
            keys.append(f"claim:{claim_hash}")
        fingerprint = _norm_token(event.event_fingerprint)
        if fingerprint:
            keys.append(f"fingerprint:{fingerprint}")
        normalized_summary = normalize_summary_for_compare(event.summary_1_sentence)
        if normalized_summary:
            keys.append(f"summary:{normalized_summary}")
        if not keys:
            keys.append(f"event:{event.event_id}")

        for key in keys:
            existing = key_to_index.get(key)
            if existing is None:
                key_to_index[key] = idx
                continue
            union(idx, existing)

    clustered: dict[int, list[SourceDigestEvent]] = defaultdict(list)
    for idx, event in enumerate(topic_events):
        clustered[find(idx)].append(event)

    clusters = list(clustered.values())
    for cluster in clusters:
        cluster.sort(key=lambda row: row.event_id)
    clusters.sort(
        key=lambda cluster: _event_order_key(sorted(cluster, key=_event_order_key)[0])
    )
    return clusters


def _merge_cluster(cluster: Sequence[SourceDigestEvent]) -> SourceEventGroup:
    representative = sorted(cluster, key=_event_order_key)[0]
    source_event_ids = tuple(sorted(row.event_id for row in cluster))

    non_null_impacts = [row.impact_score for row in cluster if row.impact_score is not None]
    merged_impact = max(non_null_impacts) if non_null_impacts else None
    merged_updated = max(row.last_updated_at for row in cluster)

    fingerprint = representative.event_fingerprint
    if not fingerprint:
        fingerprint = next((row.event_fingerprint for row in cluster if row.event_fingerprint), None)

    claim_hash = representative.claim_hash
    if not claim_hash:
        claim_hash = next((row.claim_hash for row in cluster if row.claim_hash), None)

    return SourceEventGroup(
        representative_event_id=representative.event_id,
        topic_label=representative.topic_label,
        summary_1_sentence=representative.summary_1_sentence,
        impact_score=merged_impact,
        last_updated_at=merged_updated,
        event_fingerprint=fingerprint,
        claim_hash=claim_hash,
        source_event_ids=source_event_ids,
    )


def pre_dedupe_source_events(
    source_events: Sequence[SourceDigestEvent],
) -> tuple[SourceEventGroup, ...]:
    """Deterministically group obvious duplicates before synthesis.

    Grouping is performed within topic using claim hash, fingerprint, and
    normalized summary identity keys.
    """

    grouped: dict[str, list[SourceDigestEvent]] = defaultdict(list)
    for event in source_events:
        grouped[event.topic_label].append(event)

    merged_groups: list[SourceEventGroup] = []
    for topic_label in sorted(grouped.keys(), key=lambda s: (s.lower(), s)):
        clusters = _cluster_topic_events(grouped[topic_label])
        for cluster in clusters:
            merged_groups.append(_merge_cluster(cluster))

    merged_groups.sort(key=_group_order_key)
    return tuple(merged_groups)


def build_deterministic_digest(
    *,
    window: DigestWindow,
    source_events: Sequence[SourceDigestEvent],
    source_groups: Sequence[SourceEventGroup],
    top_developments_limit: int,
    section_bullet_limit: int,
) -> CanonicalDigest:
    """Compose canonical digest without LLM synthesis.

    Used as the primary fallback path and as a deterministic baseline.
    """

    if not source_groups:
        return CanonicalDigest(
            window=window,
            source_events=tuple(source_events),
            top_developments=tuple(),
            sections=tuple(),
            covered_event_ids=tuple(),
        )

    ordered_groups = sorted(source_groups, key=_group_order_key)

    top_limit = max(0, top_developments_limit)
    section_limit = max(0, section_bullet_limit)

    top_groups = ordered_groups[:top_limit] if top_limit > 0 else []
    top_ids = {group.representative_event_id for group in top_groups}
    top_developments = tuple(_group_to_bullet(group) for group in top_groups)

    by_topic: dict[str, list[SourceEventGroup]] = defaultdict(list)
    for group in ordered_groups:
        if group.representative_event_id in top_ids:
            continue
        by_topic[group.topic_label].append(group)

    sections: list[TopicSection] = []
    for topic_label in sorted(by_topic.keys(), key=lambda s: (s.lower(), s)):
        topic_groups = sorted(by_topic[topic_label], key=_group_order_key)
        if section_limit > 0:
            topic_groups = topic_groups[:section_limit]
        bullets = tuple(_group_to_bullet(group) for group in topic_groups)
        covered_event_ids = tuple(
            sorted({event_id for bullet in bullets for event_id in bullet.source_event_ids})
        )
        if bullets:
            sections.append(
                TopicSection(
                    topic_label=topic_label,
                    bullets=bullets,
                    covered_event_ids=covered_event_ids,
                )
            )

    covered_ids = tuple(
        sorted(
            {
                event_id
                for bullet in top_developments
                for event_id in bullet.source_event_ids
            }
            | {
                event_id
                for section in sections
                for event_id in section.covered_event_ids
            }
        )
    )

    return CanonicalDigest(
        window=window,
        source_events=tuple(sorted(source_events, key=lambda row: row.event_id)),
        top_developments=top_developments,
        sections=tuple(sections),
        covered_event_ids=covered_ids,
    )


def build_canonical_digest(events: list[Event], window: DigestWindow) -> CanonicalDigest:
    source_events = build_source_digest_events(events)
    source_groups = pre_dedupe_source_events(source_events)
    return build_deterministic_digest(
        window=window,
        source_events=source_events,
        source_groups=source_groups,
        top_developments_limit=3,
        section_bullet_limit=6,
    )


def build_canonical_digest_for_hours(
    events: list[Event], window_hours: int, *, now_utc: datetime | None = None
) -> CanonicalDigest:
    end_utc = (now_utc or datetime.utcnow()).replace(microsecond=0)
    window = DigestWindow(
        start_utc=end_utc - timedelta(hours=window_hours),
        end_utc=end_utc,
        hours=window_hours,
    )
    return build_canonical_digest(events, window=window)
