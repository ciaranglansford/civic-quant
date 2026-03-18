from __future__ import annotations

import argparse
import hashlib
import logging

from dotenv import load_dotenv
from sqlalchemy import func, inspect, text

from ..models import (
    EnrichmentCandidate,
    Event,
    EventMessage,
    Extraction,
    PublishedPost,
    RawMessage,
    RoutingDecision,
)
from ..db import SessionLocal, engine
from ..contexts.extraction.canonicalization import (
    CANONICALIZER_VERSION,
    canonicalize_extraction,
    compute_canonical_payload_hash,
    compute_claim_hash,
    derive_action_class,
    event_time_bucket,
)
from ..contexts.extraction.prompt_templates import PROMPT_VERSION


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.stability_adopt")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_replay_identity_key(
    *,
    raw_message_id: int,
    normalized_text_hash: str,
    extractor_name: str,
    prompt_version: str,
    schema_version: int,
    canonicalizer_version: str,
) -> str:
    source = (
        f"raw_message_id={raw_message_id}"
        f"|normalized_text_hash={normalized_text_hash}"
        f"|extractor_name={extractor_name}"
        f"|prompt_version={prompt_version}"
        f"|schema_version={schema_version}"
        f"|canonicalizer_version={canonicalizer_version}"
    )
    return _sha256_text(source)


def _ensure_columns(*, apply_changes: bool = True) -> bool:
    insp = inspect(engine)
    dialect = engine.dialect.name
    missing: list[str] = []

    def add_column_if_missing(table: str, column: str, spec: str) -> None:
        nonlocal missing
        cols = {c["name"] for c in insp.get_columns(table)}
        if column in cols:
            return
        missing.append(f"{table}.{column}")
        if not apply_changes:
            return
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {spec}"))
        logger.info("added column %s.%s", table, column)

    extraction_cols = {
        "event_identity_fingerprint_v2": "VARCHAR(512)",
        "normalized_text_hash": "VARCHAR(64)",
        "replay_identity_key": "VARCHAR(64)",
        "canonicalizer_version": "VARCHAR(32)",
        "canonical_payload_hash": "VARCHAR(64)",
        "claim_hash": "VARCHAR(64)",
    }
    event_cols = {
        "event_identity_fingerprint_v2": "VARCHAR(512)",
        "event_time_bucket": "VARCHAR(16)",
        "action_class": "VARCHAR(64)",
        "canonical_payload_hash": "VARCHAR(64)",
        "claim_hash": "VARCHAR(64)",
        "review_required": "BOOLEAN DEFAULT FALSE",
        "review_reason": "VARCHAR(128)",
    }

    for name, spec in extraction_cols.items():
        add_column_if_missing("extractions", name, spec)
    for name, spec in event_cols.items():
        add_column_if_missing("events", name, spec)

    # Index creation is non-destructive and idempotent.
    index_sql = [
        "CREATE INDEX IF NOT EXISTS idx_extractions_replay_identity_key ON extractions(replay_identity_key)",
        "CREATE INDEX IF NOT EXISTS idx_extractions_canonical_payload_hash ON extractions(canonical_payload_hash)",
        "CREATE INDEX IF NOT EXISTS idx_extractions_claim_hash ON extractions(claim_hash)",
        "CREATE INDEX IF NOT EXISTS idx_extractions_event_identity_fp_v2 ON extractions(event_identity_fingerprint_v2)",
        (
            "CREATE INDEX IF NOT EXISTS idx_extractions_content_reuse_lookup "
            "ON extractions(normalized_text_hash, extractor_name, prompt_version, schema_version, canonicalizer_version, created_at)"
        ),
        "CREATE INDEX IF NOT EXISTS idx_events_event_identity_fp_v2 ON events(event_identity_fingerprint_v2)",
        "CREATE INDEX IF NOT EXISTS idx_events_claim_hash ON events(claim_hash)",
    ]
    if apply_changes:
        with engine.begin() as conn:
            for stmt in index_sql:
                conn.execute(text(stmt))
        logger.info("column/index ensure complete dialect=%s", dialect)
    else:
        if missing:
            logger.warning(
                "dry-run schema check found missing columns; run without --dry-run first missing=%s",
                ",".join(sorted(missing)),
            )
            return False
        logger.info("dry-run schema check complete; no missing columns detected")
    return True


def _canonical_model_from_row(row: Extraction):
    if isinstance(row.canonical_payload_json, dict):
        return canonicalize_extraction(row.canonical_payload_json)[0]
    if isinstance(row.payload_json, dict):
        return canonicalize_extraction(row.payload_json)[0]
    return None


def _backfill_extractions(*, commit: bool = True) -> int:
    updated = 0
    with SessionLocal() as db:
        rows = (
            db.query(Extraction, RawMessage)
            .join(RawMessage, RawMessage.id == Extraction.raw_message_id)
            .all()
        )
        for extraction, raw in rows:
            extraction_model = _canonical_model_from_row(extraction)
            if extraction_model is None:
                continue
            normalized_text_hash = _sha256_text(raw.normalized_text or "")
            prompt_version = extraction.prompt_version or PROMPT_VERSION
            replay_identity_key = _build_replay_identity_key(
                raw_message_id=raw.id,
                normalized_text_hash=normalized_text_hash,
                extractor_name=extraction.extractor_name or "extract-and-score-openai-v1",
                prompt_version=prompt_version,
                schema_version=int(extraction.schema_version or 1),
                canonicalizer_version=CANONICALIZER_VERSION,
            )
            canonical_payload_hash = compute_canonical_payload_hash(extraction_model)
            claim_hash = compute_claim_hash(extraction_model)
            action_class = derive_action_class(extraction_model)
            time_bucket = event_time_bucket(extraction_model)
            canonical_payload = extraction_model.model_dump(mode="json")
            identity_fp = extraction_model.event_fingerprint or extraction.event_fingerprint or f"soft:{raw.id}"

            extraction.event_fingerprint = identity_fp
            extraction.event_identity_fingerprint_v2 = identity_fp
            extraction.normalized_text_hash = normalized_text_hash
            extraction.replay_identity_key = replay_identity_key
            extraction.canonicalizer_version = CANONICALIZER_VERSION
            extraction.canonical_payload_hash = canonical_payload_hash
            extraction.claim_hash = claim_hash
            extraction.canonical_payload_json = canonical_payload

            metadata = extraction.metadata_json if isinstance(extraction.metadata_json, dict) else {}
            metadata.update(
                {
                    "canonicalizer_version": CANONICALIZER_VERSION,
                    "normalized_text_hash": normalized_text_hash,
                    "replay_identity_key": replay_identity_key,
                    "canonical_payload_hash": canonical_payload_hash,
                    "claim_hash": claim_hash,
                    "action_class": action_class,
                    "event_time_bucket": time_bucket,
                    "backend_event_fingerprint": identity_fp,
                    "backend_event_fingerprint_version": "v2",
                }
            )
            extraction.metadata_json = metadata
            updated += 1
        if commit:
            db.commit()
        else:
            db.rollback()
    return updated


def _backfill_events(*, commit: bool = True) -> int:
    updated = 0
    with SessionLocal() as db:
        rows = db.query(Event).all()
        for event in rows:
            latest = None
            if event.latest_extraction_id is not None:
                latest = db.query(Extraction).filter_by(id=event.latest_extraction_id).one_or_none()

            identity_fp = (
                event.event_identity_fingerprint_v2
                or event.event_fingerprint
                or (latest.event_identity_fingerprint_v2 if latest is not None else None)
                or f"soft:event:{event.id}"
            )
            event.event_identity_fingerprint_v2 = identity_fp
            event.event_fingerprint = event.event_fingerprint or identity_fp

            if latest is not None:
                event.claim_hash = event.claim_hash or latest.claim_hash
                event.canonical_payload_hash = event.canonical_payload_hash or latest.canonical_payload_hash
                metadata = latest.metadata_json if isinstance(latest.metadata_json, dict) else {}
                if not event.action_class:
                    event.action_class = str(metadata.get("action_class") or "")
                if not event.event_time_bucket:
                    event.event_time_bucket = str(metadata.get("event_time_bucket") or "")
            updated += 1
        if commit:
            db.commit()
        else:
            db.rollback()
    return updated


def _duplicate_groups() -> tuple[list[list[Event]], list[list[Event]]]:
    with SessionLocal() as db:
        grouped = (
            db.query(Event.event_identity_fingerprint_v2, func.count(Event.id))
            .filter(Event.event_identity_fingerprint_v2.isnot(None))
            .group_by(Event.event_identity_fingerprint_v2)
            .having(func.count(Event.id) > 1)
            .all()
        )
        exact: list[list[Event]] = []
        conflicts: list[list[Event]] = []
        for fp, _ in grouped:
            events = (
                db.query(Event)
                .filter(Event.event_identity_fingerprint_v2 == fp)
                .order_by(Event.id.asc())
                .all()
            )
            claim_set = {e.claim_hash for e in events if e.claim_hash}
            if claim_set and len(claim_set) == 1:
                exact.append(events)
            else:
                conflicts.append(events)
        return exact, conflicts


def _merge_exact_duplicate_groups(exact_groups: list[list[Event]], *, commit: bool = True) -> int:
    merged_groups = 0
    with SessionLocal() as db:
        for group in exact_groups:
            ids = [row.id for row in group]
            rows = db.query(Event).filter(Event.id.in_(ids)).order_by(Event.id.asc()).all()
            if len(rows) < 2:
                continue
            survivor = rows[0]
            duplicates = rows[1:]

            for duplicate in duplicates:
                # Move event-message links, preventing duplicate pair collisions.
                links = db.query(EventMessage).filter_by(event_id=duplicate.id).all()
                for link in links:
                    existing = (
                        db.query(EventMessage)
                        .filter_by(event_id=survivor.id, raw_message_id=link.raw_message_id)
                        .one_or_none()
                    )
                    if existing is None:
                        link.event_id = survivor.id
                    else:
                        db.delete(link)

                db.query(PublishedPost).filter_by(event_id=duplicate.id).update({"event_id": survivor.id})
                db.query(EnrichmentCandidate).filter_by(event_id=duplicate.id).delete()
                db.delete(duplicate)

            merged_groups += 1
        if commit:
            db.commit()
        else:
            db.rollback()
    return merged_groups


def _apply_unique_indexes() -> None:
    with SessionLocal() as db:
        routing_dupes = (
            db.query(RoutingDecision.raw_message_id, func.count(RoutingDecision.id))
            .group_by(RoutingDecision.raw_message_id)
            .having(func.count(RoutingDecision.id) > 1)
            .all()
        )
        event_dupes = (
            db.query(Event.event_identity_fingerprint_v2, func.count(Event.id))
            .filter(Event.event_identity_fingerprint_v2.isnot(None))
            .group_by(Event.event_identity_fingerprint_v2)
            .having(func.count(Event.id) > 1)
            .all()
        )
        if routing_dupes:
            raise RuntimeError(f"cannot apply routing unique index; duplicates found: {len(routing_dupes)} groups")
        if event_dupes:
            raise RuntimeError(f"cannot apply event identity unique index; duplicates found: {len(event_dupes)} groups")

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_routing_decisions_raw_message_id "
                "ON routing_decisions(raw_message_id)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_events_identity_fp_v2 "
                "ON events(event_identity_fingerprint_v2)"
            )
        )
    logger.info("unique indexes applied")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Adopt replay/event identity stability contracts on existing data."
    )
    parser.add_argument(
        "--merge-exact",
        action="store_true",
        help="Merge duplicate events where identity fingerprint and claim_hash are identical.",
    )
    parser.add_argument(
        "--apply-unique-indexes",
        action="store_true",
        help="Apply unique indexes for routing_decisions(raw_message_id) and events(event_identity_fingerprint_v2).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run audits/backfills and report results, then rollback.",
    )
    args = parser.parse_args()

    load_dotenv()
    schema_ready = _ensure_columns(apply_changes=not args.dry_run)
    if not schema_ready:
        logger.warning("stability_adoption stopped before backfill because schema is not ready")
        return
    should_commit = not args.dry_run
    extraction_updates = _backfill_extractions(commit=should_commit)
    event_updates = _backfill_events(commit=should_commit)
    exact_groups, conflict_groups = _duplicate_groups()

    logger.info(
        "stability_adoption_audit extractions_backfilled=%s events_backfilled=%s exact_duplicate_groups=%s conflict_groups=%s",
        extraction_updates,
        event_updates,
        len(exact_groups),
        len(conflict_groups),
    )

    if args.merge_exact and exact_groups:
        merged = _merge_exact_duplicate_groups(exact_groups, commit=should_commit)
        logger.info("stability_adoption_merge merged_exact_groups=%s", merged)
        exact_groups, conflict_groups = _duplicate_groups()
        logger.info(
            "stability_adoption_post_merge exact_duplicate_groups=%s conflict_groups=%s",
            len(exact_groups),
            len(conflict_groups),
        )

    if args.apply_unique_indexes and not args.dry_run:
        _apply_unique_indexes()

    if args.dry_run:
        logger.info("dry-run requested: backfill and merge operations were rolled back")


if __name__ == "__main__":
    main()

