"""Digest artifact persistence helpers.

`input_hash_for_digest_inputs` creates a stable identity from deterministic
source inputs so reruns can dedupe artifacts even when synthesized prose varies.
"""

from __future__ import annotations

import hashlib
import json
from typing import Sequence

from sqlalchemy import inspect
from sqlalchemy.orm import Session, load_only

from ..models import DigestArtifact
from .types import DigestWindow, SourceDigestEvent, SourceEventGroup


def canonical_hash_for_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _supports_input_hash(db: Session) -> bool:
    """Return whether the connected DB schema has `digest_artifacts.input_hash`.

    This keeps digest publishing compatible with pre-refactor databases that
    have not yet added the new column.
    """

    bind = db.get_bind()
    inspector = inspect(bind)
    columns = inspector.get_columns("digest_artifacts")
    names = {str(column.get("name")) for column in columns}
    return "input_hash" in names


def _artifact_query(db: Session, *, include_input_hash: bool):
    columns = [
        DigestArtifact.id,
        DigestArtifact.window_start_utc,
        DigestArtifact.window_end_utc,
        DigestArtifact.canonical_text,
        DigestArtifact.canonical_hash,
        DigestArtifact.created_at,
    ]
    if include_input_hash:
        columns.append(DigestArtifact.input_hash)
    return db.query(DigestArtifact).options(load_only(*columns))


def input_hash_for_digest_inputs(
    *,
    window: DigestWindow,
    source_events: Sequence[SourceDigestEvent],
    source_groups: Sequence[SourceEventGroup],
    top_developments_limit: int,
    section_bullet_limit: int,
    prompt_version: str,
) -> str:
    payload = {
        "window": {
            "start_utc": window.start_utc.isoformat(),
            "end_utc": window.end_utc.isoformat(),
            "hours": window.hours,
        },
        "limits": {
            "top_developments_limit": top_developments_limit,
            "section_bullet_limit": section_bullet_limit,
        },
        "prompt_version": prompt_version,
        "source_events": [
            {
                "event_id": row.event_id,
                "topic_raw": row.topic_raw,
                "topic_label": row.topic_label,
                "summary_1_sentence": row.summary_1_sentence,
                "impact_score": row.impact_score,
                "last_updated_at": row.last_updated_at.isoformat(),
                "event_fingerprint": row.event_fingerprint,
                "claim_hash": row.claim_hash,
            }
            for row in sorted(source_events, key=lambda row: row.event_id)
        ],
        "source_groups": [
            {
                "representative_event_id": row.representative_event_id,
                "topic_label": row.topic_label,
                "summary_1_sentence": row.summary_1_sentence,
                "impact_score": row.impact_score,
                "last_updated_at": row.last_updated_at.isoformat(),
                "event_fingerprint": row.event_fingerprint,
                "claim_hash": row.claim_hash,
                "source_event_ids": list(row.source_event_ids),
            }
            for row in sorted(source_groups, key=lambda row: row.representative_event_id)
        ],
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def get_or_create_artifact(
    db: Session,
    *,
    window: DigestWindow,
    canonical_text: str,
    input_hash: str | None = None,
) -> DigestArtifact:
    has_input_hash = _supports_input_hash(db)
    query = _artifact_query(db, include_input_hash=has_input_hash)

    if input_hash and has_input_hash:
        existing_by_input = query.filter(DigestArtifact.input_hash == input_hash).one_or_none()
        if existing_by_input is not None:
            return existing_by_input

    canonical_hash = canonical_hash_for_text(canonical_text)
    existing_by_canonical = query.filter(DigestArtifact.canonical_hash == canonical_hash).one_or_none()
    if existing_by_canonical is not None:
        if input_hash and has_input_hash and not existing_by_canonical.input_hash:
            existing_by_canonical.input_hash = input_hash
            db.flush()
        return existing_by_canonical

    artifact_kwargs: dict[str, object] = {
        "window_start_utc": window.start_utc,
        "window_end_utc": window.end_utc,
        "canonical_text": canonical_text,
        "canonical_hash": canonical_hash,
    }
    if has_input_hash and input_hash:
        artifact_kwargs["input_hash"] = input_hash

    artifact = DigestArtifact(**artifact_kwargs)
    db.add(artifact)
    db.flush()
    return artifact
