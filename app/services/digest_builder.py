"""
Transitional compatibility shim for legacy service imports.

Authoritative digest composition now lives in `app.digest.*` and includes:
- deterministic source event preparation / pre-dedupe,
- optional LLM synthesis with strict validation,
- deterministic fallback composition.

This shim remains a thin delegator to canonical digest modules.
Do not add business logic here; keep this module as a thin delegator only.

TODO(refactor-2026-03-18): Remove this shim after all internal imports and docs
have migrated to `app.digest.builder` and no external callers depend on
`app.services.digest_builder` for one full release cycle.
"""

from __future__ import annotations

from ..digest.builder import build_canonical_digest_for_hours
from ..digest.renderer_text import render_canonical_text


def build_digest(events, window_hours: int) -> str:
    digest = build_canonical_digest_for_hours(events, window_hours=window_hours)
    return render_canonical_text(digest)

