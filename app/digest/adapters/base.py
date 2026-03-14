from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..types import CanonicalDigest


@dataclass(frozen=True)
class PublishResult:
    status: str  # published|failed|deferred
    external_ref: str | None = None
    error: str | None = None


class DigestAdapter(Protocol):
    destination: str

    def render_payload(self, digest: CanonicalDigest, canonical_text: str) -> str:
        ...

    def publish(self, payload: str) -> PublishResult:
        ...
