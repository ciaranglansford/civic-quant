"""
Transitional compatibility shim for legacy service imports.

Authoritative digest orchestration implementation lives in `app.digest.orchestrator`
and owns deterministic selection, synthesis/fallback routing, artifact persistence,
and publish-state transitions.

Do not add business logic here; keep this module as a thin delegator only.
"""

from __future__ import annotations

from ..digest.orchestrator import run_digest


__all__ = ["run_digest"]

