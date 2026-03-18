"""Minimal forward contracts for thesis cards and periodic briefs.

These contracts are intentionally lightweight seams for upcoming reporting work.
Canonical digest semantics remain owned by `app.digest`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThesisCard:
    event_id: int
    title: str
    thesis: str
    confidence: float
    risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class InvestmentBrief:
    period_label: str
    cards: tuple[ThesisCard, ...]
    summary: str
