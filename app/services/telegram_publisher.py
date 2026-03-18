"""
Transitional compatibility shim for legacy service imports.

Authoritative Telegram digest transport lives in `app.digest.adapters.telegram`.
Do not add business logic here; keep this module as a thin delegator only.

TODO(refactor-2026-03-18): Remove this shim after all internal imports/docs
use `app.digest.adapters.telegram.send_telegram_text` directly for one full
release cycle.
"""

from __future__ import annotations


def send_digest_to_vip(text: str) -> None:
    from ..digest.adapters.telegram import send_telegram_text

    send_telegram_text(text)


