from __future__ import annotations

import hmac
import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..schemas import QueryNewsResponse, QuerySummaryResponse
from ..services.query_service import build_news_response
from ..services.summary_service import build_summary_response


logger = logging.getLogger("civicquant.query_api")
router = APIRouter(prefix="/api/query", tags=["query"])


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="unauthorized")


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "bearer "
    if not authorization.lower().startswith(prefix):
        return None
    token = authorization[len(prefix) :].strip()
    return token or None


def require_bot_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.bot_api_token
    provided = _extract_bearer_token(authorization)
    if not expected or not provided:
        raise _unauthorized()
    if not hmac.compare_digest(provided, expected):
        raise _unauthorized()


@router.get(
    "/news",
    response_model=QueryNewsResponse,
    dependencies=[Depends(require_bot_token)],
)
def query_news(
    topic: str | None = Query(default=None),
    window: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> QueryNewsResponse:
    started_at = time.perf_counter()
    try:
        response = build_news_response(db, topic=topic or "", window=window or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "query_news_ok topic=%s window=%s count=%s latency_ms=%s",
        response.topic,
        response.window,
        response.count,
        latency_ms,
    )
    return response


@router.get(
    "/summary",
    response_model=QuerySummaryResponse,
    dependencies=[Depends(require_bot_token)],
)
def query_summary(
    topic: str | None = Query(default=None),
    window: str | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QuerySummaryResponse:
    started_at = time.perf_counter()
    try:
        news_response = build_news_response(db, topic=topic or "", window=window or "")
        response = build_summary_response(news_response=news_response, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "query_summary_ok topic=%s window=%s source_count=%s latency_ms=%s",
        response.topic,
        response.window,
        response.source_count,
        latency_ms,
    )
    return response
