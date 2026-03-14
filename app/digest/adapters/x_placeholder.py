from __future__ import annotations

from ..types import CanonicalDigest
from .base import PublishResult


class XPlaceholderDigestAdapter:
    destination = "x"

    def render_payload(self, digest: CanonicalDigest, canonical_text: str) -> str:  # noqa: ARG002
        return canonical_text

    def publish(self, payload: str) -> PublishResult:  # noqa: ARG002
        return PublishResult(
            status="deferred",
            error="X adapter is a placeholder only; publishing is deferred.",
        )
