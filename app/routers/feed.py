from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import FeedEventsResponse, Topic
from ..services.feed_query import list_feed_events


router = APIRouter(prefix="/api/feed", tags=["feed"])


@router.get("/events", response_model=FeedEventsResponse)
def get_feed_events(
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None),
    topic: Topic | None = Query(default=None),
    db: Session = Depends(get_db),
) -> FeedEventsResponse:
    try:
        return list_feed_events(db=db, limit=limit, cursor=cursor, topic=topic)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid cursor")
