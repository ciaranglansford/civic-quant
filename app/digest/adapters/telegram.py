"""Telegram adapter for digest payload rendering and transport.

Digest semantics (top developments, section membership, source coverage) are
provided by `CanonicalDigest` and must not be recomputed here.
"""

from __future__ import annotations

import html
import logging
import re

import httpx

from ...config import Settings, get_settings
from ..types import CanonicalDigest
from .base import PublishResult


logger = logging.getLogger("civicquant.publisher.telegram")


_WS_RE = re.compile(r"\s+")


def _clean_summary_for_display(summary: str) -> str:
    return _WS_RE.sub(" ", (summary or "").strip())


def _format_window_line(digest: CanonicalDigest) -> str:
    start = digest.window.start_utc
    end = digest.window.end_utc
    same_day = start.date() == end.date()
    if same_day:
        return f"Window: {start.strftime('%H:%M')}-{end.strftime('%H:%M')} UTC"
    return f"Window: {start.strftime('%Y-%m-%d %H:%M')} UTC to {end.strftime('%Y-%m-%d %H:%M')} UTC"


def _topics_line(digest: CanonicalDigest) -> str:
    if not digest.sections:
        return "Topics: none"
    parts = [f"{section.topic_label} {section.source_event_count}" for section in digest.sections]
    return f"Topics: {' | '.join(parts)}"


def render_telegram_payload(digest: CanonicalDigest) -> str:
    lines: list[str] = []
    lines.append("<b>News Digest</b>")
    lines.append("")
    lines.append(f"<i>{html.escape(_format_window_line(digest))}</i>")
    lines.append(f"<i>{html.escape(f'Covered events: {digest.total_events}')}</i>")
    lines.append(f"<i>{html.escape(_topics_line(digest))}</i>")

    if digest.top_developments:
        lines.append("")
        lines.append("<b>Top developments</b>")
        for bullet in digest.top_developments:
            lines.append(f"- {html.escape(_clean_summary_for_display(bullet.text))}")

    for section in digest.sections:
        lines.append("")
        lines.append(f"<b>{html.escape(section.topic_label)}</b>")
        for bullet in section.bullets:
            lines.append(f"- {html.escape(_clean_summary_for_display(bullet.text))}")

    lines.append("")
    lines.append("<i>- Not investment advice.</i>")
    return "\n".join(lines).strip()


def send_telegram_text(text: str, settings: Settings | None = None) -> str | None:
    cfg = settings or get_settings()
    if not cfg.tg_bot_token or not cfg.tg_vip_chat_id:
        raise RuntimeError("TG_BOT_TOKEN and TG_VIP_CHAT_ID must be configured to publish digests")

    url = f"https://api.telegram.org/bot{cfg.tg_bot_token}/sendMessage"
    payload = {
        "chat_id": cfg.tg_vip_chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.post(url, json=payload)
        if response.status_code >= 400:
            logger.error(
                "telegram_publish_failed status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            response.raise_for_status()
        logger.info("telegram_publish_ok status=%s", response.status_code)
        try:
            body = response.json()
        except ValueError:
            return None
        result = body.get("result") if isinstance(body, dict) else None
        if isinstance(result, dict):
            message_id = result.get("message_id")
            if message_id is not None:
                return str(message_id)
        return None


class TelegramDigestAdapter:
    destination = "vip_telegram"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def is_enabled(self) -> bool:
        return bool(self._settings.tg_bot_token and self._settings.tg_vip_chat_id)

    def render_payload(self, digest: CanonicalDigest, canonical_text: str) -> str:  # noqa: ARG002
        return render_telegram_payload(digest)

    def publish(self, payload: str) -> PublishResult:
        external_ref = send_telegram_text(payload, settings=self._settings)
        return PublishResult(status="published", external_ref=external_ref)
