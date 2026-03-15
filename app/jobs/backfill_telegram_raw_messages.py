from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import timezone

from dotenv import load_dotenv
from telethon import TelegramClient

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..schemas import TelegramIngestPayload
from ..services.ingest_pipeline import process_ingest_payload
from ..services.normalization import normalize_message_text


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.backfill")


def _normalize_channel_peer_id(entity, fallback: str) -> str:
    raw_id = getattr(entity, "id", None)
    if isinstance(raw_id, int) and raw_id > 0:
        return f"-100{raw_id}"
    return str(fallback)


def _required_setting(value: str | int | None, name: str) -> str | int:
    if value in (None, ""):
        raise RuntimeError(f"Missing required setting: {name}")
    return value


async def _run_backfill(limit: int, source_channel: str, api_id: int, api_hash: str, session_name: str) -> None:
    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    try:
        entity = await client.get_entity(source_channel)
        source_channel_id = _normalize_channel_peer_id(entity, source_channel)
        source_channel_name = getattr(entity, "title", None) or getattr(entity, "username", None)
        recent = await client.get_messages(entity, limit=limit)
        recent_ordered = sorted((m for m in recent if getattr(m, "id", None) is not None), key=lambda m: m.id)

        logger.info(
            "backfill_start source_channel=%s source_channel_id=%s source_channel_name=%s requested_limit=%s fetched=%s",
            source_channel,
            source_channel_id,
            source_channel_name,
            limit,
            len(recent_ordered),
        )

        created = 0
        duplicate = 0
        failed = 0

        with SessionLocal() as db:
            for message in recent_ordered:
                dt = message.date
                if dt is None:
                    failed += 1
                    logger.warning("backfill_skip_missing_date telegram_message_id=%s", message.id)
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_utc = dt.astimezone(timezone.utc)

                forwarded_from = None
                if getattr(message, "fwd_from", None) and getattr(message.fwd_from, "from_name", None):
                    forwarded_from = message.fwd_from.from_name

                payload = TelegramIngestPayload(
                    source_channel_id=str(source_channel_id),
                    source_channel_name=source_channel_name,
                    telegram_message_id=str(message.id),
                    message_timestamp_utc=dt_utc,
                    raw_text=message.message or "",
                    raw_entities_if_available=None,
                    forwarded_from_if_available=forwarded_from,
                )
                normalized = normalize_message_text(payload.raw_text)

                try:
                    result = process_ingest_payload(db=db, payload=payload, normalized_text=normalized)
                    db.commit()
                except Exception:
                    db.rollback()
                    failed += 1
                    logger.exception("backfill_failed telegram_message_id=%s", message.id)
                    continue

                status = str(result.get("status"))
                if status == "created":
                    created += 1
                else:
                    duplicate += 1

                logger.info(
                    "backfill_row status=%s telegram_message_id=%s raw_message_id=%s",
                    status,
                    message.id,
                    result.get("raw_message_id"),
                )

        logger.info(
            "backfill_done requested_limit=%s fetched=%s created=%s duplicate=%s failed=%s",
            limit,
            len(recent_ordered),
            created,
            duplicate,
            failed,
        )
    finally:
        await client.disconnect()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill the most recent Telegram messages into raw_messages via the ingest pipeline."
    )
    parser.add_argument(
        "--limit",
        type=int,
        required=True,
        help="How many recent messages to backfill from the Telegram source channel.",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Telegram channel username/ID to backfill from. Defaults to TG_SOURCE_CHANNEL.",
    )
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")
    return args


def main() -> None:
    args = _parse_args()
    load_dotenv()
    settings = get_settings()
    init_db()

    source_channel = args.channel or _required_setting(settings.tg_source_channel, "TG_SOURCE_CHANNEL")
    api_id = int(_required_setting(settings.tg_api_id, "TG_API_ID"))
    api_hash = str(_required_setting(settings.tg_api_hash, "TG_API_HASH"))
    session_name = str(_required_setting(settings.tg_session_name, "TG_SESSION_NAME"))

    asyncio.run(
        _run_backfill(
            limit=args.limit,
            source_channel=str(source_channel),
            api_id=api_id,
            api_hash=api_hash,
            session_name=session_name,
        )
    )


if __name__ == "__main__":
    main()
