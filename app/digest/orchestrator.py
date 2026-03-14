from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import PublishedPost
from .adapters.base import DigestAdapter
from .adapters.telegram import TelegramDigestAdapter
from .artifact_store import canonical_hash_for_text, get_or_create_artifact
from .builder import build_canonical_digest
from .dedupe import destination_already_published, get_destination_publication
from .query import get_events_for_window
from .renderer_text import render_canonical_text
from .types import DigestWindow


logger = logging.getLogger("civicquant.digest")


def _freeze_window(now_utc: datetime, window_hours: int) -> DigestWindow:
    end_utc = now_utc.replace(microsecond=0)
    start_utc = end_utc - timedelta(hours=window_hours)
    return DigestWindow(start_utc=start_utc, end_utc=end_utc, hours=window_hours)


def _payload_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _default_adapters(settings: Settings) -> list[DigestAdapter]:
    adapters: list[DigestAdapter] = []
    telegram = TelegramDigestAdapter(settings=settings)
    if telegram.is_enabled():
        adapters.append(telegram)
    else:
        logger.info("digest_destination_disabled destination=vip_telegram reason=missing_config")
    return adapters


def _upsert_destination_row(
    db: Session,
    *,
    artifact_id: int,
    destination: str,
    payload: str,
    payload_hash: str,
) -> PublishedPost:
    existing = get_destination_publication(db, artifact_id=artifact_id, destination=destination)
    if existing is not None:
        existing.content = payload
        existing.content_hash = payload_hash
        existing.last_attempted_at = datetime.utcnow()
        return existing

    row = PublishedPost(
        event_id=None,
        artifact_id=artifact_id,
        destination=destination,
        status="failed",
        last_attempted_at=datetime.utcnow(),
        published_at=None,
        content=payload,
        content_hash=payload_hash,
        last_error=None,
        external_ref=None,
    )
    db.add(row)
    db.flush()
    return row


def run_digest(
    db: Session,
    window_hours: int,
    *,
    now_utc: datetime | None = None,
    adapters: Sequence[DigestAdapter] | None = None,
) -> dict[str, object]:
    settings = get_settings()
    frozen_now = now_utc or datetime.utcnow()
    window = _freeze_window(frozen_now, window_hours)

    events = get_events_for_window(db, window.start_utc, window.end_utc)
    canonical_digest = build_canonical_digest(events, window=window)
    canonical_text = render_canonical_text(canonical_digest)
    artifact = get_or_create_artifact(db, window=window, canonical_text=canonical_text)

    # Invariant: persist and commit the canonical artifact before any publish attempt.
    db.commit()

    canonical_hash = canonical_hash_for_text(canonical_text)
    event_ids = list(canonical_digest.event_ids)
    selected_adapters = list(adapters) if adapters is not None else _default_adapters(settings)

    publication_results: list[dict[str, object]] = []
    for adapter in selected_adapters:
        destination = adapter.destination
        payload = adapter.render_payload(canonical_digest, canonical_text)
        payload_hash = _payload_hash(payload)

        if destination_already_published(db, artifact_id=artifact.id, destination=destination):
            logger.info(
                "digest_skip_published artifact_id=%s destination=%s", artifact.id, destination
            )
            publication_results.append({"destination": destination, "status": "skipped_published"})
            continue

        row = _upsert_destination_row(
            db,
            artifact_id=artifact.id,
            destination=destination,
            payload=payload,
            payload_hash=payload_hash,
        )

        try:
            result = adapter.publish(payload)
            row.status = result.status
            row.last_error = result.error
            row.external_ref = result.external_ref
            row.published_at = datetime.utcnow() if result.status == "published" else None
            db.commit()
            publication_results.append({"destination": destination, "status": result.status})
            logger.info(
                "digest_publish_result artifact_id=%s destination=%s status=%s",
                artifact.id,
                destination,
                result.status,
            )
        except Exception as exc:  # noqa: BLE001
            row.status = "failed"
            row.last_error = str(exc)[:1000]
            row.external_ref = None
            row.published_at = None
            db.commit()
            publication_results.append({"destination": destination, "status": "failed"})
            logger.error(
                "digest_publish_failed artifact_id=%s destination=%s error=%s",
                artifact.id,
                destination,
                row.last_error,
            )

    return {
        "status": "completed",
        "artifact_id": artifact.id,
        "canonical_hash": canonical_hash,
        "event_ids": event_ids,
        "window_start_utc": window.start_utc.isoformat(),
        "window_end_utc": window.end_utc.isoformat(),
        "publications": publication_results,
    }
