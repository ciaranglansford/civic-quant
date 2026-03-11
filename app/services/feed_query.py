from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import get_args

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..models import Event
from ..schemas import FeedEventItem, FeedEventsResponse, Topic

TOPIC_VALUES = tuple(get_args(Topic))
_CURSOR_VERSION = 1


def _to_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_utc_naive(value: datetime) -> datetime:
    return _to_utc_aware(value).replace(tzinfo=None)


def _format_event_time(value: datetime) -> str:
    utc_value = _to_utc_aware(value)
    return utc_value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _encode_cursor(*, event_time: datetime, event_id: int) -> str:
    payload = {
        "v": _CURSOR_VERSION,
        "event_time": _format_event_time(event_time),
        "id": event_id,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid cursor") from exc

    if not isinstance(payload, dict):
        raise ValueError("invalid cursor")

    version = payload.get("v")
    event_time_raw = payload.get("event_time")
    event_id = payload.get("id")

    if version != _CURSOR_VERSION or not isinstance(event_time_raw, str) or not isinstance(event_id, int) or event_id <= 0:
        raise ValueError("invalid cursor")

    try:
        parsed = datetime.fromisoformat(event_time_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid cursor") from exc

    return _to_utc_naive(parsed), event_id


def list_feed_events(
    db: Session,
    *,
    limit: int,
    cursor: str | None,
    topic: Topic | None,
) -> FeedEventsResponse:
    query = db.query(Event).filter(
        Event.event_time.isnot(None),
        Event.topic.in_(TOPIC_VALUES),
        Event.summary_1_sentence.isnot(None),
        func.length(func.trim(Event.summary_1_sentence)) > 0,
    )

    if topic is not None:
        query = query.filter(Event.topic == topic)

    if cursor is not None:
        cursor_event_time, cursor_event_id = _decode_cursor(cursor)
        query = query.filter(
            or_(
                Event.event_time < cursor_event_time,
                and_(Event.event_time == cursor_event_time, Event.id < cursor_event_id),
            )
        )

    rows = (
        query.order_by(Event.event_time.desc(), Event.id.desc())
        .limit(limit + 1)
        .all()
    )

    page_rows = rows[:limit]
    has_more = len(rows) > limit

    items = [
        FeedEventItem(
            id=row.id,
            summary=(row.summary_1_sentence or "").strip(),
            topic=row.topic,
            event_time=_format_event_time(row.event_time),
        )
        for row in page_rows
    ]

    next_cursor = None
    if has_more and page_rows:
        last_row = page_rows[-1]
        next_cursor = _encode_cursor(event_time=last_row.event_time, event_id=last_row.id)

    return FeedEventsResponse(items=items, next_cursor=next_cursor)
