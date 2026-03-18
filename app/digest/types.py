"""Canonical digest data types shared by builders, synthesizers, and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DigestWindow:
    start_utc: datetime
    end_utc: datetime
    hours: int


@dataclass(frozen=True)
class SourceDigestEvent:
    event_id: int
    topic_raw: str | None
    topic_label: str
    summary_1_sentence: str
    impact_score: float | None
    last_updated_at: datetime
    event_fingerprint: str | None
    claim_hash: str | None


@dataclass(frozen=True)
class SourceEventGroup:
    representative_event_id: int
    topic_label: str
    summary_1_sentence: str
    impact_score: float | None
    last_updated_at: datetime
    event_fingerprint: str | None
    claim_hash: str | None
    source_event_ids: tuple[int, ...]


@dataclass(frozen=True)
class DigestBullet:
    text: str
    topic_label: str | None
    source_event_ids: tuple[int, ...]


@dataclass(frozen=True)
class TopicSection:
    topic_label: str
    bullets: tuple[DigestBullet, ...]
    covered_event_ids: tuple[int, ...]

    @property
    def source_event_count(self) -> int:
        return len(self.covered_event_ids)


@dataclass(frozen=True)
class CanonicalDigest:
    window: DigestWindow
    source_events: tuple[SourceDigestEvent, ...]
    top_developments: tuple[DigestBullet, ...]
    sections: tuple[TopicSection, ...]
    covered_event_ids: tuple[int, ...]

    @property
    def total_events(self) -> int:
        return len(self.covered_event_ids)
