"""
Transitional compatibility shim for legacy service imports.

Authoritative Telegram digest transport lives in `app.digest.adapters.telegram`.
Do not add business logic here; keep this module as a thin delegator only.
"""

from __future__ import annotations


def send_digest_to_vip(text: str) -> None:
    from ..digest.adapters.telegram import send_telegram_text

    send_telegram_text(text)

