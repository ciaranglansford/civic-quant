from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...schemas import ExtractionJson


@dataclass(frozen=True)
class OpportunityScoreInput:
    extraction: ExtractionJson
    triage_action: str
    triage_rules: tuple[str, ...]


@dataclass(frozen=True)
class OpportunityScoreResult:
    score: float
    confidence: float
    rationale_codes: tuple[str, ...]


class OpportunityScorer(Protocol):
    name: str

    def score(self, value: OpportunityScoreInput) -> OpportunityScoreResult:
        ...
