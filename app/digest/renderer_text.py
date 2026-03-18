"""Canonical text renderer for `CanonicalDigest`.

This renderer consumes canonical digest semantics only. It does not implement
selection, dedupe, or publication rules.
"""

from __future__ import annotations

from .types import CanonicalDigest


def _format_utc(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def render_canonical_text(digest: CanonicalDigest) -> str:
    lines: list[str] = []
    lines.append(f"Window {_format_utc(digest.window.start_utc)} to {_format_utc(digest.window.end_utc)}")
    lines.append(f"Covered events: {digest.total_events}")
    lines.append(f"Source events: {len(digest.source_events)}")
    lines.append(f"Top developments: {len(digest.top_developments)}")
    counts = ", ".join(
        f"{section.topic_label}: {section.source_event_count}" for section in digest.sections
    )
    lines.append(f"Counts: {counts}" if counts else "Counts: 0")
    lines.append("")

    if digest.top_developments:
        lines.append("== Top developments ==")
        for bullet in digest.top_developments:
            lines.append(f"- {bullet.text}")
        lines.append("")

    for section in digest.sections:
        lines.append(f"== {section.topic_label} ==")
        for bullet in section.bullets:
            lines.append(f"- {bullet.text}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
