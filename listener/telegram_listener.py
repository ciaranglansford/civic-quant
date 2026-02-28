from __future__ import annotations

import asyncio
import logging
import os
from datetime import timezone

import httpx
from dotenv import load_dotenv
from telethon import TelegramClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.listener")

load_dotenv()


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def _normalize_channel_peer_id(entity, fallback: str) -> str:
    raw_id = getattr(entity, "id", None)
    if isinstance(raw_id, int) and raw_id > 0:
        return f"-100{raw_id}"
    return str(fallback)


def build_ingest_payload(message, source_channel_id: str, source_channel_name: str | None) -> dict:
    dt = message.date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)

    forwarded_from = None
    if getattr(message, "fwd_from", None) and getattr(message.fwd_from, "from_name", None):
        forwarded_from = message.fwd_from.from_name

    return {
        "source_channel_id": str(source_channel_id),
        "source_channel_name": source_channel_name,
        "telegram_message_id": str(message.id),
        "message_timestamp_utc": dt_utc.isoformat().replace("+00:00", "Z"),
        "raw_text": message.message or "",
        "raw_entities_if_available": None,
        "forwarded_from_if_available": forwarded_from,
    }


async def post_with_retries(url: str, payload: dict, max_attempts: int = 5) -> None:
    backoff_s = 1.0
    async with httpx.AsyncClient(timeout=20.0) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                r = await client.post(url, json=payload)
                if 200 <= r.status_code < 300:
                    logger.info(
                        "post_ok telegram_message_id=%s attempt=%s status=%s",
                        payload.get("telegram_message_id"),
                        attempt,
                        r.status_code,
                    )
                    return

                if r.status_code == 429 or r.status_code >= 500:
                    logger.warning(
                        "post_retryable telegram_message_id=%s attempt=%s status=%s body=%s",
                        payload.get("telegram_message_id"),
                        attempt,
                        r.status_code,
                        r.text[:300],
                    )
                else:
                    logger.error(
                        "post_nonretryable telegram_message_id=%s attempt=%s status=%s body=%s",
                        payload.get("telegram_message_id"),
                        attempt,
                        r.status_code,
                        r.text[:300],
                    )
                    return
            except Exception as e:
                logger.warning(
                    "post_error telegram_message_id=%s attempt=%s error=%s",
                    payload.get("telegram_message_id"),
                    attempt,
                    type(e).__name__,
                )

            if attempt < max_attempts:
                await asyncio.sleep(backoff_s)
                backoff_s = min(backoff_s * 2.0, 30.0)

    logger.error(
        "post_failed telegram_message_id=%s attempts=%s",
        payload.get("telegram_message_id"),
        max_attempts,
    )


async def main() -> None:
    api_id = int(_require_env("TG_API_ID"))
    api_hash = _require_env("TG_API_HASH")
    session_name = _require_env("TG_SESSION_NAME")
    source_channel = _require_env("TG_SOURCE_CHANNEL")
    ingest_base = _require_env("INGEST_API_BASE_URL").rstrip("/")
    poll_interval_s = float(os.getenv("TG_POLL_INTERVAL_S", "60"))

    ingest_url = f"{ingest_base}/ingest/telegram"

    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    entity = await client.get_entity(source_channel)

    source_channel_id = _normalize_channel_peer_id(entity, source_channel)
    source_channel_name = getattr(entity, "title", None) or getattr(entity, "username", None)

    logger.info(
        "listener_started mode=poll source_channel=%s source_channel_id=%s ingest_url=%s poll_interval_s=%s",
        source_channel,
        source_channel_id,
        ingest_url,
        poll_interval_s,
    )

    # Show a few recent messages so you can see it's the right feed
    recent = await client.get_messages(entity, limit=3)
    logger.info(
        "entity_resolved type=%s raw_id=%s title=%s username=%s",
        type(entity).__name__,
        getattr(entity, "id", None),
        getattr(entity, "title", None),
        getattr(entity, "username", None),
    )
    for m in reversed(recent):
        logger.info(
            "pull_msg id=%s date=%s text_preview=%s",
            m.id,
            m.date,
            (m.message or "")[:120].replace("\n", " "),
        )

    # Initialize last_seen to the newest message currently present
    last_seen_id = recent[0].id if recent else 0

    while True:
        try:
            # Grab up to 20 in case of bursts; process only unseen, oldest->newest
            msgs = await client.get_messages(entity, limit=20)
            if msgs:
                new_msgs = [m for m in msgs if m.id > last_seen_id]
                new_msgs.sort(key=lambda m: m.id)

                for m in new_msgs:
                    logger.info(
                        "tg_msg_received id=%s date=%s text_preview=%s",
                        m.id,
                        m.date,
                        (m.message or "")[:120].replace("\n", " "),
                    )
                    payload = build_ingest_payload(m, source_channel_id, source_channel_name)
                    await post_with_retries(ingest_url, payload)
                    last_seen_id = max(last_seen_id, m.id)

        except Exception as e:
            logger.exception("poll_error error=%s", type(e).__name__)

        await asyncio.sleep(poll_interval_s)


if __name__ == "__main__":
    asyncio.run(main())