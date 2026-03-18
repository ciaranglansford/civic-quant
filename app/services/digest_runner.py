"""
Transitional compatibility shim for legacy service imports.

Authoritative digest orchestration implementation lives in `app.digest.orchestrator`
and owns deterministic selection, synthesis/fallback routing, artifact persistence,
and publish-state transitions.

Do not add business logic here; keep this module as a thin delegator only.

TODO(refactor-2026-03-18): Remove this shim after all internal imports and docs
have migrated to `app.digest.orchestrator`/`app.digest.run_digest` and no
external callers depend on `app.services.digest_runner` for one full release cycle.
"""

from __future__ import annotations

from ..digest.orchestrator import run_digest


__all__ = ["run_digest"]


