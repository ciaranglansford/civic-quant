"""
Transitional compatibility shim for legacy service imports.

Authoritative digest query implementation lives in `app.digest.query` and remains
deterministic (window bounds, impact threshold integration in orchestrator, and
destination publication-eligibility filtering).

Do not add business logic here; keep this module as a thin delegator only.

TODO(refactor-2026-03-18): Remove this shim after all internal imports and docs
have migrated to `app.digest.query` and no external callers depend on
`app.services.digest_query` for one full release cycle.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..digest.query import get_events_for_digest_hours


def get_events_for_digest(db: Session, hours: int):
    return get_events_for_digest_hours(db, hours=hours)


