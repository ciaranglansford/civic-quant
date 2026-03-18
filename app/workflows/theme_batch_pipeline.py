from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..contexts.opportunities import (
    EnrichmentRequest,
    InternalEvidenceAggregationProvider,
    build_and_persist_brief_artifact,
    create_assessments_for_bundle,
    create_cards_for_assessments,
)
from ..contexts.themes import (
    build_evidence_bundle,
    ensure_theme_evidence_for_window,
    get_theme_definition,
)
from ..models import ProcessingLock, ThemeRun


logger = logging.getLogger("civicquant.theme_batch")


@dataclass(frozen=True)
class ThemeBatchSummary:
    run_id: int
    run_key: str
    theme_key: str
    cadence: str
    window_start_utc: datetime
    window_end_utc: datetime
    status: str
    evidence_count: int
    assessments_created: int
    cards_created: int
    emitted_cards: int
    suppressed_cards: int
    brief_status: str
    error_message: str | None = None


@dataclass(frozen=True)
class ThemeBatchRequest:
    theme_key: str
    cadence: str = "daily"
    window_start_utc: datetime | None = None
    window_end_utc: datetime | None = None
    dry_run: bool = False
    emit_brief: bool = True


def _resolve_window(cadence: str, *, now_utc: datetime) -> tuple[datetime, datetime]:
    end_utc = now_utc.replace(microsecond=0)
    if cadence == "weekly":
        return end_utc - timedelta(days=7), end_utc
    return end_utc - timedelta(days=1), end_utc


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _acquire_lock(db: Session, *, lock_name: str, run_key: str, lock_seconds: int = 900) -> bool:
    now = datetime.utcnow()
    lock = db.query(ProcessingLock).filter_by(lock_name=lock_name).one_or_none()
    if lock is not None and lock.locked_until > now:
        return False
    until = now + timedelta(seconds=lock_seconds)
    if lock is None:
        db.add(ProcessingLock(lock_name=lock_name, locked_until=until, owner_run_id=run_key))
    else:
        lock.locked_until = until
        lock.owner_run_id = run_key
    db.flush()
    return True


def _release_lock(db: Session, *, lock_name: str, run_key: str) -> None:
    lock = db.query(ProcessingLock).filter_by(lock_name=lock_name).one_or_none()
    if lock is not None and lock.owner_run_id == run_key:
        lock.locked_until = datetime.utcnow()
        db.flush()


def run_theme_batch(
    db: Session,
    *,
    request: ThemeBatchRequest,
    now_utc: datetime | None = None,
) -> ThemeBatchSummary:
    if request.cadence not in {"daily", "weekly"}:
        raise ValueError("cadence must be daily or weekly")

    theme_definition = get_theme_definition(request.theme_key)
    if request.cadence not in theme_definition.supported_cadences:
        raise ValueError(
            f"cadence={request.cadence} is not supported by theme={request.theme_key}"
        )

    frozen_now = now_utc or datetime.utcnow()
    default_start, default_end = _resolve_window(request.cadence, now_utc=frozen_now)
    window_start_utc = _to_utc_naive(request.window_start_utc) if request.window_start_utc else default_start
    window_end_utc = _to_utc_naive(request.window_end_utc) if request.window_end_utc else default_end
    if window_start_utc >= window_end_utc:
        raise ValueError("window_start must be earlier than window_end")

    run_key = str(uuid.uuid4())
    run = ThemeRun(
        run_key=run_key,
        theme_key=request.theme_key,
        cadence=request.cadence,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        status="running",
        dry_run=bool(request.dry_run),
        emit_brief=bool(request.emit_brief),
        started_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()

    lock_name = f"theme_batch:{request.theme_key}:{request.cadence}"
    if not _acquire_lock(db, lock_name=lock_name, run_key=run_key):
        run.status = "skipped_lock_busy"
        run.error_message = "lock busy"
        run.completed_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.flush()
        return ThemeBatchSummary(
            run_id=run.id,
            run_key=run_key,
            theme_key=request.theme_key,
            cadence=request.cadence,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            status=run.status,
            evidence_count=0,
            assessments_created=0,
            cards_created=0,
            emitted_cards=0,
            suppressed_cards=0,
            brief_status="skipped",
            error_message=run.error_message,
        )

    try:
        catchup_summary = ensure_theme_evidence_for_window(
            db,
            theme_definition=theme_definition,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
        )
        bundle = build_evidence_bundle(
            db,
            theme_key=request.theme_key,
            cadence=request.cadence,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
        )

        provider = InternalEvidenceAggregationProvider()
        enrichment_result = provider.enrich(
            EnrichmentRequest(
                theme_key=request.theme_key,
                cadence=request.cadence,
                window_start_iso=window_start_utc.isoformat(),
                window_end_iso=window_end_utc.isoformat(),
                bundle=bundle,
            )
        )

        assessments = create_assessments_for_bundle(
            db,
            theme_run=run,
            theme_definition=theme_definition,
            bundle=bundle,
            enrichment_payload=enrichment_result.payload,
        )
        cards = create_cards_for_assessments(
            db,
            theme_run=run,
            theme_definition=theme_definition,
            assessments=assessments,
            dry_run=bool(request.dry_run),
        )
        brief = build_and_persist_brief_artifact(
            db,
            theme_run=run,
            assessments=assessments,
            cards=cards,
            emit_brief=bool(request.emit_brief),
        )

        emitted_cards = [card for card in cards if card.status in {"emitted", "updated"}]
        suppressed_cards = [card for card in cards if card.status == "repeat_suppressed"]

        run.selected_evidence_count = len(bundle.evidence_items)
        run.assessment_count = len(assessments)
        run.thesis_card_count = len(cards)
        run.suppressed_count = len(suppressed_cards)
        run.status = "completed"
        run.error_message = None
        run.completed_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.flush()

        logger.info(
            "theme_batch_completed run_id=%s theme=%s cadence=%s evidence=%s assessments=%s cards=%s emitted=%s suppressed=%s catchup_inserted=%s",
            run.id,
            request.theme_key,
            request.cadence,
            len(bundle.evidence_items),
            len(assessments),
            len(cards),
            len(emitted_cards),
            len(suppressed_cards),
            catchup_summary.get("inserted_or_updated", 0),
        )

        return ThemeBatchSummary(
            run_id=run.id,
            run_key=run_key,
            theme_key=request.theme_key,
            cadence=request.cadence,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            status=run.status,
            evidence_count=len(bundle.evidence_items),
            assessments_created=len(assessments),
            cards_created=len(cards),
            emitted_cards=len(emitted_cards),
            suppressed_cards=len(suppressed_cards),
            brief_status=brief.status,
        )
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.completed_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.flush()
        logger.exception(
            "theme_batch_failed run_id=%s theme=%s cadence=%s error=%s",
            run.id,
            request.theme_key,
            request.cadence,
            type(exc).__name__,
        )
        return ThemeBatchSummary(
            run_id=run.id,
            run_key=run_key,
            theme_key=request.theme_key,
            cadence=request.cadence,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            status=run.status,
            evidence_count=0,
            assessments_created=0,
            cards_created=0,
            emitted_cards=0,
            suppressed_cards=0,
            brief_status="failed",
            error_message=run.error_message,
        )
    finally:
        _release_lock(db, lock_name=lock_name, run_key=run_key)
