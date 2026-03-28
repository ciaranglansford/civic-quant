from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import Event, EventMessage, EventRelation, EventTag, Extraction, RawMessage
from ..schemas import QueryNewsResponse, QueryNewsResultItem, QueryWindow


WINDOW_HOURS: dict[str, int] = {"1h": 1, "4h": 4, "24h": 24}
WINDOW_LIMITS: dict[str, int] = {"1h": 5, "4h": 5, "24h": 8}
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


@dataclass(frozen=True)
class RankedQueryEvent:
    event_id: int
    timestamp: datetime
    source: str
    claim: str
    category: str | None
    importance: str
    score: float
    evidence_refs: tuple[str, ...]
    dedupe_key: str


@dataclass(frozen=True)
class _RawEvidence:
    raw_id: int
    source_channel_id: str
    source_channel_name: str | None
    message_timestamp_utc: datetime
    normalized_text: str


@dataclass(frozen=True)
class _EventMatchContext:
    event: Event
    event_level_match: bool
    summary_match: bool
    raw_text_match: bool
    tags: tuple[str, ...]
    relations: tuple[str, ...]
    payload_texts: tuple[str, ...]
    raw_evidence: tuple[_RawEvidence, ...]
    source_claimed: str | None


def normalize_topic(topic: str | None) -> str:
    if not isinstance(topic, str):
        return ""
    return _WS_RE.sub(" ", topic.strip().lower())


def validate_window(window: str | None) -> QueryWindow:
    if window not in WINDOW_HOURS:
        raise ValueError("window must be one of 1h, 4h, 24h")
    return window


def _window_limit(window: QueryWindow) -> int:
    return WINDOW_LIMITS[window]


def _window_hours(window: QueryWindow) -> int:
    return WINDOW_HOURS[window]


def _to_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_utc_naive(value: datetime) -> datetime:
    return _to_utc_aware(value).replace(tzinfo=None)


def _format_timestamp(value: datetime) -> str:
    return _to_utc_aware(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_claim_for_key(text: str) -> str:
    lowered = _WS_RE.sub(" ", (text or "").strip().casefold())
    return _WS_RE.sub(" ", _PUNCT_RE.sub("", lowered)).strip()


def _match_text(text: str | None, *, topic_tokens: tuple[str, ...]) -> bool:
    if not text:
        return False
    normalized = _WS_RE.sub(" ", text.strip().lower())
    if not normalized:
        return False
    return all(token in normalized for token in topic_tokens)


def _extract_payload_texts(payload: dict[str, object]) -> list[str]:
    out: list[str] = []
    summary = payload.get("summary_1_sentence")
    if isinstance(summary, str) and summary.strip():
        out.append(summary)

    source_claimed = payload.get("source_claimed")
    if isinstance(source_claimed, str) and source_claimed.strip():
        out.append(source_claimed)

    topic = payload.get("topic")
    if isinstance(topic, str) and topic.strip():
        out.append(topic)

    keywords = payload.get("keywords")
    if isinstance(keywords, list):
        for keyword in keywords:
            if isinstance(keyword, str) and keyword.strip():
                out.append(keyword)

    entities = payload.get("entities")
    if isinstance(entities, dict):
        for key in ("countries", "orgs", "people", "tickers"):
            values = entities.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, str) and value.strip():
                    out.append(value)
    return out


def _importance_label(impact_score: float | None) -> str:
    score = float(impact_score or 0.0)
    if score >= 75.0:
        return "high"
    if score >= 50.0:
        return "medium"
    return "low"


def _ranking_score(
    *,
    now_utc: datetime,
    anchor_time: datetime,
    window_hours: int,
    impact_score: float | None,
    evidence_count: int,
    event_level_match: bool,
    summary_match: bool,
) -> float:
    age_seconds = max(0.0, (_to_utc_naive(now_utc) - anchor_time).total_seconds())
    window_seconds = max(3600.0, float(window_hours) * 3600.0)
    recency_component = max(0.0, 1.0 - min(1.0, age_seconds / (window_seconds * 1.5)))
    impact_component = min(1.0, max(0.0, float(impact_score or 0.0) / 100.0))
    evidence_component = min(1.0, float(evidence_count) / 4.0)

    score = (0.45 * recency_component) + (0.35 * impact_component) + (0.20 * evidence_component)
    if event_level_match:
        score += 0.05
    if summary_match:
        score += 0.03
    if not event_level_match:
        score *= 0.7
    return round(min(1.0, max(0.0, score)), 4)


def _event_anchor_time(event: Event, raw_evidence: tuple[_RawEvidence, ...], now_utc: datetime) -> datetime:
    if event.event_time is not None:
        return _to_utc_naive(event.event_time)
    if raw_evidence:
        return _to_utc_naive(raw_evidence[0].message_timestamp_utc)
    return _to_utc_naive(event.last_updated_at or now_utc)


def _source_label(raw_evidence: tuple[_RawEvidence, ...], source_claimed: str | None) -> str:
    if raw_evidence:
        latest = raw_evidence[0]
        source_name = (latest.source_channel_name or latest.source_channel_id or "").strip()
        if source_name:
            return f"telegram:{source_name}"
    if source_claimed:
        cleaned = source_claimed.strip()
        if cleaned:
            return f"reported:{cleaned}"
    return "unknown"


def _dedupe_key(event: Event, claim: str) -> str:
    if event.claim_hash:
        return f"claim:{event.claim_hash}"
    if event.event_identity_fingerprint_v2:
        return f"identity:{event.event_identity_fingerprint_v2}"
    return f"claim_text:{_normalize_claim_for_key(claim)}"


def _load_candidate_events(db: Session, *, cutoff_utc_naive: datetime, now_utc: datetime) -> list[Event]:
    return (
        db.query(Event)
        .filter(
            or_(
                and_(Event.event_time.is_not(None), Event.event_time >= cutoff_utc_naive),
                and_(Event.event_time.is_(None), Event.last_updated_at >= cutoff_utc_naive),
            )
        )
        .order_by(
            Event.event_time.desc().nullslast(),
            Event.last_updated_at.desc().nullslast(),
            Event.id.desc(),
        )
        .limit(500)
        .all()
    )


def _build_match_contexts(
    db: Session,
    *,
    events: list[Event],
    topic_tokens: tuple[str, ...],
) -> list[_EventMatchContext]:
    if not events:
        return []

    event_ids = [event.id for event in events]
    extraction_ids = [event.latest_extraction_id for event in events if event.latest_extraction_id is not None]

    tags_by_event: dict[int, list[str]] = {event_id: [] for event_id in event_ids}
    for row in db.query(EventTag).filter(EventTag.event_id.in_(event_ids)).all():
        if row.tag_value:
            tags_by_event.setdefault(row.event_id, []).append(row.tag_value)

    relations_by_event: dict[int, list[str]] = {event_id: [] for event_id in event_ids}
    for row in db.query(EventRelation).filter(EventRelation.event_id.in_(event_ids)).all():
        parts = [row.subject_value, row.relation_type, row.object_value]
        for part in parts:
            if part:
                relations_by_event.setdefault(row.event_id, []).append(part)

    payload_by_extraction: dict[int, dict[str, object]] = {}
    if extraction_ids:
        extraction_rows = db.query(Extraction).filter(Extraction.id.in_(extraction_ids)).all()
        for row in extraction_rows:
            payload = row.canonical_payload_json or row.payload_json or {}
            if isinstance(payload, dict):
                payload_by_extraction[row.id] = payload

    raw_by_event: dict[int, list[_RawEvidence]] = {event_id: [] for event_id in event_ids}
    raw_rows = (
        db.query(
            EventMessage.event_id,
            RawMessage.id,
            RawMessage.source_channel_id,
            RawMessage.source_channel_name,
            RawMessage.message_timestamp_utc,
            RawMessage.normalized_text,
        )
        .join(RawMessage, RawMessage.id == EventMessage.raw_message_id)
        .filter(EventMessage.event_id.in_(event_ids))
        .all()
    )
    for event_id, raw_id, source_id, source_name, message_time, normalized_text in raw_rows:
        if message_time is None:
            continue
        raw_by_event.setdefault(event_id, []).append(
            _RawEvidence(
                raw_id=int(raw_id),
                source_channel_id=str(source_id or ""),
                source_channel_name=(str(source_name) if source_name is not None else None),
                message_timestamp_utc=message_time,
                normalized_text=str(normalized_text or ""),
            )
        )

    contexts: list[_EventMatchContext] = []
    for event in events:
        raw_evidence = tuple(
            sorted(
                raw_by_event.get(event.id, []),
                key=lambda row: (_to_utc_naive(row.message_timestamp_utc), row.raw_id),
                reverse=True,
            )
        )

        payload = payload_by_extraction.get(event.latest_extraction_id or -1, {})
        payload_texts = tuple(_extract_payload_texts(payload))
        source_claimed = payload.get("source_claimed") if isinstance(payload.get("source_claimed"), str) else None
        tags = tuple(tags_by_event.get(event.id, []))
        relations = tuple(relations_by_event.get(event.id, []))

        summary_match = _match_text(event.summary_1_sentence or "", topic_tokens=topic_tokens)
        event_topic_match = _match_text(event.topic or "", topic_tokens=topic_tokens)
        tags_match = any(_match_text(value, topic_tokens=topic_tokens) for value in tags)
        relations_match = any(_match_text(value, topic_tokens=topic_tokens) for value in relations)
        payload_match = any(_match_text(value, topic_tokens=topic_tokens) for value in payload_texts)
        raw_match = any(_match_text(row.normalized_text, topic_tokens=topic_tokens) for row in raw_evidence)

        event_level_match = summary_match or event_topic_match or tags_match or relations_match or payload_match
        contexts.append(
            _EventMatchContext(
                event=event,
                event_level_match=event_level_match,
                summary_match=summary_match,
                raw_text_match=raw_match,
                tags=tags,
                relations=relations,
                payload_texts=payload_texts,
                raw_evidence=raw_evidence,
                source_claimed=source_claimed,
            )
        )

    return contexts


def rank_query_events(
    db: Session,
    *,
    topic: str,
    window: str,
    now_utc: datetime | None = None,
) -> list[RankedQueryEvent]:
    normalized_topic = normalize_topic(topic)
    if not normalized_topic:
        raise ValueError("topic must be non-empty")

    validated_window = validate_window(window)
    hours = _window_hours(validated_window)
    limit = _window_limit(validated_window)
    topic_tokens = tuple(token for token in normalized_topic.split(" ") if token)
    if not topic_tokens:
        raise ValueError("topic must be non-empty")

    now = (now_utc or datetime.utcnow()).replace(microsecond=0)
    cutoff = _to_utc_naive(now - timedelta(hours=hours))
    candidates = _load_candidate_events(db, cutoff_utc_naive=cutoff, now_utc=now)
    contexts = _build_match_contexts(db, events=candidates, topic_tokens=topic_tokens)

    event_level = [row for row in contexts if row.event_level_match]
    fallback = [row for row in contexts if (not row.event_level_match) and row.raw_text_match]

    selected: list[_EventMatchContext] = list(event_level)
    if len(selected) < limit:
        selected.extend(fallback)
    if not selected:
        return []

    deduped: dict[str, RankedQueryEvent] = {}
    for context in selected:
        event = context.event
        claim = _WS_RE.sub(" ", (event.summary_1_sentence or "").strip()) or "Reported development."
        anchor_time = _event_anchor_time(event, context.raw_evidence, now)
        evidence_refs = tuple(f"src_{row.raw_id}" for row in context.raw_evidence[:3])
        score = _ranking_score(
            now_utc=now,
            anchor_time=anchor_time,
            window_hours=hours,
            impact_score=event.impact_score,
            evidence_count=len(context.raw_evidence),
            event_level_match=context.event_level_match,
            summary_match=context.summary_match,
        )
        item = RankedQueryEvent(
            event_id=int(event.id),
            timestamp=anchor_time,
            source=_source_label(context.raw_evidence, context.source_claimed),
            claim=claim,
            category=event.topic,
            importance=_importance_label(event.impact_score),
            score=score,
            evidence_refs=evidence_refs,
            dedupe_key=_dedupe_key(event, claim),
        )
        existing = deduped.get(item.dedupe_key)
        if existing is None:
            deduped[item.dedupe_key] = item
            continue
        if (item.score, item.timestamp, item.event_id) > (existing.score, existing.timestamp, existing.event_id):
            deduped[item.dedupe_key] = item

    ranked = sorted(
        deduped.values(),
        key=lambda row: (row.score, _to_utc_naive(row.timestamp), row.event_id),
        reverse=True,
    )
    return ranked[:limit]


def build_news_response(
    db: Session,
    *,
    topic: str,
    window: str,
    now_utc: datetime | None = None,
) -> QueryNewsResponse:
    normalized_topic = normalize_topic(topic)
    if not normalized_topic:
        raise ValueError("topic must be non-empty")
    validated_window = validate_window(window)

    now = (now_utc or datetime.utcnow()).replace(microsecond=0)
    ranked = rank_query_events(db, topic=normalized_topic, window=validated_window, now_utc=now)
    results = [
        QueryNewsResultItem(
            event_id=item.event_id,
            timestamp=_format_timestamp(item.timestamp),
            source=item.source,
            claim=item.claim,
            category=item.category,
            importance=item.importance,  # type: ignore[arg-type]
            score=float(item.score),
            evidence_refs=list(item.evidence_refs),
        )
        for item in ranked
    ]
    return QueryNewsResponse(
        topic=normalized_topic,
        window=validated_window,
        generated_at=_format_timestamp(now),
        count=len(results),
        results=results,
    )
