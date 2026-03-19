from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ...schemas import (
    ExtractionEntities,
    ExtractionImpactInputs,
    MarketStat,
)


class StrictExtractionJson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    event_type: str | None = None
    directionality: str | None = None
    entities: ExtractionEntities
    affected_countries_first_order: list[str]
    market_stats: list[MarketStat]
    tags: list[dict[str, object]] = Field(default_factory=list)
    relations: list[dict[str, object]] = Field(default_factory=list)
    impact_inputs: ExtractionImpactInputs = Field(default_factory=ExtractionImpactInputs)
    sentiment: str
    confidence: float
    impact_score: float
    is_breaking: bool
    breaking_window: str
    event_time: str | None
    source_claimed: str | None
    summary_1_sentence: str
    keywords: list[str]
    event_core: str | None = None
    event_fingerprint: str | None = None

    @field_validator("event_fingerprint", mode="before")
    @classmethod
    def _coerce_event_fingerprint(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return None


class ExtractionValidationError(ValueError):
    pass


def parse_and_validate_extraction(raw_text: str) -> dict:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ExtractionValidationError(f"invalid_json: {e.msg}") from e

    if not isinstance(payload, dict):
        raise ExtractionValidationError("invalid_json: root must be object")

    try:
        strict_obj = StrictExtractionJson.model_validate(payload)
    except ValidationError as e:
        raise ExtractionValidationError(f"schema_error: {e.errors()[0]['msg']}") from e

    extraction_payload = strict_obj.model_dump(mode="json")
    llm_fingerprint_candidate = extraction_payload.get("event_fingerprint")
    if isinstance(llm_fingerprint_candidate, str):
        extraction_payload["event_fingerprint"] = llm_fingerprint_candidate.strip()
    else:
        extraction_payload["event_fingerprint"] = ""

    raw_tags = extraction_payload.get("tags")
    if not isinstance(raw_tags, list):
        raw_tags = []
    raw_relations = extraction_payload.get("relations")
    if not isinstance(raw_relations, list):
        raw_relations = []

    from ...schemas import ExtractionJson

    # Validate core payload shape with strict ExtractionJson typing while allowing
    # malformed tag/relation entries to be dropped later during canonicalization.
    validation_payload = dict(extraction_payload)
    validation_payload["tags"] = []
    validation_payload["relations"] = []
    try:
        model = ExtractionJson.model_validate(validation_payload)
    except ValidationError as e:
        raise ExtractionValidationError(f"schema_error: {e.errors()[0]['msg']}") from e
    payload = model.model_dump(mode="json")
    payload["tags"] = raw_tags
    payload["relations"] = raw_relations
    return payload

