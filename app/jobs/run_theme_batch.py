from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

from ..db import SessionLocal, init_db
from ..workflows.theme_batch_pipeline import ThemeBatchRequest, run_theme_batch


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.theme_batch")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _parse_emit_brief(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError("--emit-brief must be true or false")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one deterministic batch thematic thesis cycle.")
    parser.add_argument("--theme", required=True, help="Theme key, e.g. energy_to_agri_inputs")
    parser.add_argument("--cadence", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--window-start", dest="window_start", default=None)
    parser.add_argument("--window-end", dest="window_end", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-brief", default="true", help="true|false (default true)")
    args = parser.parse_args()

    load_dotenv()
    init_db()

    emit_brief = _parse_emit_brief(args.emit_brief)
    request = ThemeBatchRequest(
        theme_key=args.theme,
        cadence=args.cadence,
        window_start_utc=_parse_iso_datetime(args.window_start),
        window_end_utc=_parse_iso_datetime(args.window_end),
        dry_run=bool(args.dry_run),
        emit_brief=emit_brief,
    )

    with SessionLocal() as db:
        summary = run_theme_batch(db, request=request)
        db.commit()
        logger.info(
            "theme_batch_summary run_id=%s status=%s theme=%s cadence=%s evidence=%s assessments=%s cards=%s emitted=%s suppressed=%s brief_status=%s error=%s",
            summary.run_id,
            summary.status,
            summary.theme_key,
            summary.cadence,
            summary.evidence_count,
            summary.assessments_created,
            summary.cards_created,
            summary.emitted_cards,
            summary.suppressed_cards,
            summary.brief_status,
            summary.error_message,
        )


if __name__ == "__main__":
    main()
