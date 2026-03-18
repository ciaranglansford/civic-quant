from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class EnrichmentRequest:
    event_id: int
    requested_at: datetime
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class EnrichmentResult:
    provider_name: str
    status: str
    evidence_summary: str | None = None
    payload: dict[str, object] | None = None


class EnrichmentProvider(Protocol):
    name: str

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        ...
