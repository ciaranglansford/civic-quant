"""
Transitional compatibility shim for legacy service imports.

Authoritative digest build/render implementation lives in `app.digest.*`.
Do not add business logic here; keep this module as a thin delegator only.
"""

from __future__ import annotations

from ..digest.builder import build_canonical_digest_for_hours
from ..digest.renderer_text import render_canonical_text


def build_digest(events, window_hours: int) -> str:
    digest = build_canonical_digest_for_hours(events, window_hours=window_hours)
    return render_canonical_text(digest)
