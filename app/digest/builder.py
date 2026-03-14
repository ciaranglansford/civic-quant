from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..models import Event
from .types import CanonicalDigest, DigestItem, DigestWindow, TopicSection


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


def normalize_topic_label(topic: str | None) -> str:
    if not topic:
        return "Other"
    return _TOPIC_LABELS.get(topic, topic)


def build_canonical_digest(events: list[Event], window: DigestWindow) -> CanonicalDigest:
    by_topic: dict[str, list[DigestItem]] = defaultdict(list)
    event_ids = tuple(e.id for e in events if e.id is not None)

    for e in events:
        if e.id is None:
            continue
        topic_label = normalize_topic_label(e.topic)
        summary = (e.summary_1_sentence or "").strip() or "(no summary)"
        by_topic[topic_label].append(
            DigestItem(
                event_id=e.id,
                topic_raw=e.topic,
                topic_label=topic_label,
                summary_1_sentence=summary,
                impact_score=e.impact_score,
                corroboration="unknown",
                last_updated_at=e.last_updated_at,
            )
        )

    sections: list[TopicSection] = []
    for topic_label in sorted(by_topic.keys(), key=lambda s: (s.lower(), s)):
        items = tuple(
            sorted(
                by_topic[topic_label],
                key=lambda item: (-item.last_updated_at.timestamp(), item.event_id),
            )
        )
        sections.append(TopicSection(topic_label=topic_label, items=items))

    return CanonicalDigest(window=window, sections=tuple(sections), event_ids=event_ids)


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
