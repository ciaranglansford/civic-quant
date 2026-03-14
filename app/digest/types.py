from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DigestWindow:
    start_utc: datetime
    end_utc: datetime
    hours: int


@dataclass(frozen=True)
class DigestItem:
    event_id: int
    topic_raw: str | None
    topic_label: str
    summary_1_sentence: str
    impact_score: float | None
    corroboration: str
    last_updated_at: datetime


@dataclass(frozen=True)
class TopicSection:
    topic_label: str
    items: tuple[DigestItem, ...]

    @property
    def item_count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class CanonicalDigest:
    window: DigestWindow
    sections: tuple[TopicSection, ...]
    event_ids: tuple[int, ...]

    @property
    def total_events(self) -> int:
        return len(self.event_ids)
