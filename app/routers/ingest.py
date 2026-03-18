from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..logging_utils import new_request_id
from ..schemas import IngestResponse, SourceIngestPayload, TelegramIngestPayload
from ..contexts.ingest.normalization import normalize_message_text
from ..contexts.ingest.ingest_pipeline import process_ingest_payload, process_source_ingest_payload


logger = logging.getLogger("civicquant.ingest")
router = APIRouter(tags=["ingest"])


def _build_response(result: dict[str, object]) -> IngestResponse:
    return IngestResponse(
        status=result["status"],  # type: ignore[arg-type]
        raw_message_id=int(result["raw_message_id"]),
        event_id=(int(result["event_id"]) if result.get("event_id") is not None else None),
        event_action=result.get("event_action"),  # type: ignore[arg-type]
    )


def _process_ingest_with_logging(
    *,
    request_id: str,
    db: Session,
    source_stream_id: str,
    source_message_id: str,
    raw_text: str,
    process_fn,
) -> IngestResponse:
    normalized = normalize_message_text(raw_text)
    try:
        result = process_fn(db=db, normalized_text=normalized)
        db.commit()
        logger.info(
            "ingest_ok request_id=%s source_stream_id=%s source_message_id=%s raw_message_id=%s status=%s event_id=%s",
            request_id,
            source_stream_id,
            source_message_id,
            result["raw_message_id"],
            result["status"],
            result.get("event_id"),
        )
        return _build_response(result)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.exception(
            "ingest_failed request_id=%s source_stream_id=%s source_message_id=%s error=%s",
            request_id,
            source_stream_id,
            source_message_id,
            type(e).__name__,
        )
        raise HTTPException(status_code=500, detail="ingest failed")


@router.post("/ingest/telegram", response_model=IngestResponse)
def ingest_telegram(
    payload: TelegramIngestPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> IngestResponse:
    request_id = request.headers.get("x-request-id") or new_request_id()
    return _process_ingest_with_logging(
        request_id=request_id,
        db=db,
        source_stream_id=payload.source_channel_id,
        source_message_id=payload.telegram_message_id,
        raw_text=payload.raw_text,
        process_fn=lambda *, db, normalized_text: process_ingest_payload(
            db=db,
            payload=payload,
            normalized_text=normalized_text,
        ),
    )


@router.post("/ingest/source", response_model=IngestResponse)
def ingest_source(
    payload: SourceIngestPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> IngestResponse:
    request_id = request.headers.get("x-request-id") or new_request_id()
    return _process_ingest_with_logging(
        request_id=request_id,
        db=db,
        source_stream_id=payload.source_stream_id,
        source_message_id=payload.source_message_id,
        raw_text=payload.raw_text,
        process_fn=lambda *, db, normalized_text: process_source_ingest_payload(
            db=db,
            payload=payload,
            normalized_text=normalized_text,
        ),
    )


