from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..schemas import SourceIngestPayload, TelegramIngestPayload


@dataclass(frozen=True)
class SourceMessageEnvelope:
    source_type: str
    source_stream_id: str
    source_stream_name: str | None
    source_message_id: str
    message_timestamp_utc: datetime
    raw_text: str
    raw_entities_if_available: Any | None
    forwarded_from_if_available: str | None


def envelope_from_source_payload(payload: SourceIngestPayload) -> SourceMessageEnvelope:
    normalized_type = payload.source_type.strip().lower()
    normalized_stream_id = payload.source_stream_id
    if normalized_type and normalized_type != "telegram":
        # Preserve existing telegram identity behavior while avoiding cross-source collisions.
        normalized_stream_id = f"{normalized_type}:{payload.source_stream_id}"

    return SourceMessageEnvelope(
        source_type=normalized_type or payload.source_type,
        source_stream_id=normalized_stream_id,
        source_stream_name=payload.source_stream_name,
        source_message_id=payload.source_message_id,
        message_timestamp_utc=payload.message_timestamp_utc,
        raw_text=payload.raw_text,
        raw_entities_if_available=payload.raw_entities_if_available,
        forwarded_from_if_available=payload.forwarded_from_if_available,
    )


def envelope_from_telegram_payload(payload: TelegramIngestPayload) -> SourceMessageEnvelope:
    source_payload = SourceIngestPayload(
        source_type="telegram",
        source_stream_id=payload.source_channel_id,
        source_stream_name=payload.source_channel_name,
        source_message_id=payload.telegram_message_id,
        message_timestamp_utc=payload.message_timestamp_utc,
        raw_text=payload.raw_text,
        raw_entities_if_available=payload.raw_entities_if_available,
        forwarded_from_if_available=payload.forwarded_from_if_available,
    )
    return envelope_from_source_payload(source_payload)
