from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from ..models import DigestArtifact
from .types import DigestWindow


def canonical_hash_for_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_or_create_artifact(db: Session, window: DigestWindow, canonical_text: str) -> DigestArtifact:
    canonical_hash = canonical_hash_for_text(canonical_text)
    existing = db.query(DigestArtifact).filter(DigestArtifact.canonical_hash == canonical_hash).one_or_none()
    if existing is not None:
        return existing

    artifact = DigestArtifact(
        window_start_utc=window.start_utc,
        window_end_utc=window.end_utc,
        canonical_text=canonical_text,
        canonical_hash=canonical_hash,
    )
    db.add(artifact)
    db.flush()
    return artifact
