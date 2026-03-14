from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Event


def get_events_for_window(db: Session, window_start_utc: datetime, window_end_utc: datetime) -> list[Event]:
    return (
        db.query(Event)
        .filter(
            Event.last_updated_at >= window_start_utc,
            Event.last_updated_at < window_end_utc,
        )
        .order_by(Event.last_updated_at.desc(), Event.id.asc())
        .all()
    )


def get_events_for_digest_hours(
    db: Session, hours: int, *, now_utc: datetime | None = None
) -> list[Event]:
    end_utc = (now_utc or datetime.utcnow()).replace(microsecond=0)
    start_utc = end_utc - timedelta(hours=hours)
    return get_events_for_window(db, window_start_utc=start_utc, window_end_utc=end_utc)
