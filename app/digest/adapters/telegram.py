from __future__ import annotations

import logging

import httpx

from ...config import Settings, get_settings
from ..types import CanonicalDigest
from .base import PublishResult


logger = logging.getLogger("civicquant.publisher.telegram")


def send_telegram_text(text: str, settings: Settings | None = None) -> str | None:
    cfg = settings or get_settings()
    if not cfg.tg_bot_token or not cfg.tg_vip_chat_id:
        raise RuntimeError("TG_BOT_TOKEN and TG_VIP_CHAT_ID must be configured to publish digests")

    url = f"https://api.telegram.org/bot{cfg.tg_bot_token}/sendMessage"
    payload = {"chat_id": cfg.tg_vip_chat_id, "text": text, "disable_web_page_preview": True}

    with httpx.Client(timeout=20.0) as client:
        r = client.post(url, json=payload)
        if r.status_code >= 400:
            logger.error("telegram_publish_failed status=%s body=%s", r.status_code, r.text[:500])
            r.raise_for_status()
        logger.info("telegram_publish_ok status=%s", r.status_code)
        try:
            body = r.json()
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
        return canonical_text

    def publish(self, payload: str) -> PublishResult:
        external_ref = send_telegram_text(payload, settings=self._settings)
        return PublishResult(status="published", external_ref=external_ref)
