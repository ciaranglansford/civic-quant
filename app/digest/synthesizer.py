"""Digest synthesis orchestration (LLM path + strict validation + fallback).

Input contract:
- `source_events`: all selected source events for the digest window.
- `source_groups`: deterministic pre-dedupe groups produced by `builder.py`.
- `settings`: synthesis/runtime limits and model configuration.

Expected LLM JSON schema:
- `top_developments`: list of `{text, source_event_ids}`
- `sections`: list of `{topic_label, bullets:[{text, source_event_ids}]}`
- `excluded_event_ids`: optional list of source IDs intentionally omitted

Validation rules enforced here:
- every referenced source ID must exist in the selected source set
- no source ID can appear in more than one bullet
- top and section coverage must be disjoint by source ID
- section topic labels must normalize to supported labels
- bullet text must be non-empty after cleanup
- duplicate bullet text is collapsed within location, cross-location conflicts are rejected
- all source IDs must be accounted for by bullets or `excluded_event_ids`

Fallback behavior:
- if synthesis is disabled, provider call fails, prompt/template is missing, or
  validation fails, composition falls back to deterministic builder output.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from pydantic import BaseModel, ConfigDict, ValidationError

from ..config import Settings
from .builder import (
    build_deterministic_digest,
    known_topic_labels,
    normalize_summary_for_compare,
    normalize_topic_label,
    topic_label_supported,
)
from .llm_client import DigestProviderError, OpenAiDigestSynthesisClient
from .prompt_templates import render_digest_synthesis_prompt
from .types import CanonicalDigest, DigestBullet, DigestWindow, SourceDigestEvent, SourceEventGroup, TopicSection


logger = logging.getLogger("civicquant.digest.synthesizer")

_WS_RE = re.compile(r"\s+")


class DigestSynthesisError(ValueError):
    pass


class DigestSynthesisClient(Protocol):
    def synthesize(self, prompt_text: str):  # noqa: ANN201
        ...


class _StrictDigestBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    source_event_ids: list[int]


class _StrictTopicSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_label: str
    bullets: list[_StrictDigestBullet]


class _StrictDigestSynthesisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_developments: list[_StrictDigestBullet]
    sections: list[_StrictTopicSection]
    excluded_event_ids: list[int] | None = None


@dataclass(frozen=True)
class _ValidatedDigestStructure:
    top_developments: tuple[DigestBullet, ...]
    sections: tuple[TopicSection, ...]
    covered_event_ids: tuple[int, ...]


def _clean_text(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip())


def _normalize_text_key(text: str) -> str:
    return normalize_summary_for_compare(text)


def _collapse_duplicate_bullets(bullets: Sequence[DigestBullet]) -> list[DigestBullet]:
    deduped: list[DigestBullet] = []
    by_text: dict[str, int] = {}
    for bullet in bullets:
        text_key = _normalize_text_key(bullet.text)
        if not text_key:
            continue
        existing_idx = by_text.get(text_key)
        if existing_idx is None:
            by_text[text_key] = len(deduped)
            deduped.append(
                DigestBullet(
                    text=bullet.text,
                    topic_label=bullet.topic_label,
                    source_event_ids=tuple(sorted(set(bullet.source_event_ids))),
                )
            )
            continue

        existing = deduped[existing_idx]
        merged_ids = tuple(sorted(set(existing.source_event_ids) | set(bullet.source_event_ids)))
        deduped[existing_idx] = DigestBullet(
            text=existing.text,
            topic_label=existing.topic_label,
            source_event_ids=merged_ids,
        )
    return deduped


def _to_digest_bullet(raw: _StrictDigestBullet, *, topic_label: str | None) -> DigestBullet:
    text = _clean_text(raw.text)
    if not text:
        raise DigestSynthesisError("empty bullet text")
    source_ids = tuple(sorted(set(raw.source_event_ids)))
    if not source_ids:
        raise DigestSynthesisError("bullet missing source_event_ids")
    return DigestBullet(text=text, topic_label=topic_label, source_event_ids=source_ids)


def _validate_topic_label(raw_label: str) -> str:
    cleaned = _clean_text(raw_label)
    normalized = normalize_topic_label(cleaned)
    if not topic_label_supported(normalized):
        raise DigestSynthesisError(f"unsupported topic label: {raw_label!r}")
    return normalized


def _validate_synthesis_payload(
    *,
    payload_text: str,
    source_event_ids: set[int],
    top_limit: int,
    section_limit: int,
) -> _ValidatedDigestStructure:
    try:
        payload_obj = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise DigestSynthesisError(f"invalid_json: {exc.msg}") from exc

    if not isinstance(payload_obj, dict):
        raise DigestSynthesisError("invalid_json: root must be object")

    try:
        parsed = _StrictDigestSynthesisPayload.model_validate(payload_obj)
    except ValidationError as exc:
        raise DigestSynthesisError(f"schema_error: {exc.errors()[0]['msg']}") from exc

    top_bullets = [
        _to_digest_bullet(raw, topic_label=None)
        for raw in parsed.top_developments[: max(0, top_limit)]
    ]
    top_bullets = _collapse_duplicate_bullets(top_bullets)

    section_order: list[str] = []
    section_bullets: dict[str, list[DigestBullet]] = {}
    for section in parsed.sections:
        topic_label = _validate_topic_label(section.topic_label)
        if topic_label not in section_bullets:
            section_order.append(topic_label)
            section_bullets[topic_label] = []

        bullets = [
            _to_digest_bullet(raw, topic_label=topic_label)
            for raw in section.bullets[: max(0, section_limit)]
        ]
        section_bullets[topic_label].extend(_collapse_duplicate_bullets(bullets))

    known_labels = set(known_topic_labels())
    for label in section_order:
        if label not in known_labels:
            raise DigestSynthesisError(f"unknown normalized topic label: {label}")

    sections: list[TopicSection] = []
    for label in section_order:
        collapsed = _collapse_duplicate_bullets(section_bullets[label])
        if not collapsed:
            continue
        covered_ids = tuple(sorted({event_id for bullet in collapsed for event_id in bullet.source_event_ids}))
        sections.append(
            TopicSection(
                topic_label=label,
                bullets=tuple(collapsed),
                covered_event_ids=covered_ids,
            )
        )

    text_locations: dict[str, str] = {}
    for bullet in top_bullets:
        key = _normalize_text_key(bullet.text)
        if not key:
            raise DigestSynthesisError("empty top_developments bullet after normalization")
        text_locations[key] = "top"

    for section in sections:
        for bullet in section.bullets:
            key = _normalize_text_key(bullet.text)
            if not key:
                raise DigestSynthesisError("empty section bullet after normalization")
            seen = text_locations.get(key)
            if seen is None:
                text_locations[key] = f"section:{section.topic_label}"
            elif seen != f"section:{section.topic_label}":
                raise DigestSynthesisError("duplicate bullet text across digest sections/top")

    referenced_ids: dict[int, str] = {}
    all_bullets = top_bullets + [bullet for section in sections for bullet in section.bullets]
    for idx, bullet in enumerate(all_bullets):
        location = f"bullet_{idx}"
        for source_id in bullet.source_event_ids:
            if source_id not in source_event_ids:
                raise DigestSynthesisError(f"referenced unknown source_event_id={source_id}")
            seen = referenced_ids.get(source_id)
            if seen is not None:
                raise DigestSynthesisError(f"source_event_id={source_id} appears multiple times")
            referenced_ids[source_id] = location

    excluded_ids = set(parsed.excluded_event_ids or [])
    if excluded_ids - source_event_ids:
        unknown = sorted(excluded_ids - source_event_ids)
        raise DigestSynthesisError(f"excluded unknown source_event_ids: {unknown}")
    if excluded_ids & set(referenced_ids.keys()):
        overlap = sorted(excluded_ids & set(referenced_ids.keys()))
        raise DigestSynthesisError(f"excluded ids also referenced in bullets: {overlap}")

    missing = source_event_ids - excluded_ids - set(referenced_ids.keys())
    if missing:
        raise DigestSynthesisError(f"model omitted source_event_ids without exclusion: {sorted(missing)}")

    covered_event_ids = tuple(sorted(referenced_ids.keys()))
    return _ValidatedDigestStructure(
        top_developments=tuple(top_bullets),
        sections=tuple(sections),
        covered_event_ids=covered_event_ids,
    )


def _can_use_llm(settings: Settings) -> bool:
    model_name = settings.digest_openai_model or settings.openai_model
    return bool(settings.digest_llm_enabled and settings.openai_api_key and model_name)


def _build_llm_client(
    settings: Settings, llm_client: DigestSynthesisClient | None
) -> DigestSynthesisClient | None:
    if llm_client is not None:
        return llm_client
    if not _can_use_llm(settings):
        return None
    model_name = settings.digest_openai_model or settings.openai_model
    if not model_name:
        return None
    return OpenAiDigestSynthesisClient(
        api_key=settings.openai_api_key or "",
        model=model_name,
        timeout_seconds=settings.digest_openai_timeout_seconds,
        max_retries=settings.digest_openai_max_retries,
    )


def synthesize_digest(
    *,
    window: DigestWindow,
    source_events: Sequence[SourceDigestEvent],
    source_groups: Sequence[SourceEventGroup],
    settings: Settings,
    llm_client: DigestSynthesisClient | None = None,
) -> CanonicalDigest:
    """Compose canonical digest via validated LLM synthesis or deterministic fallback.

    The function always returns a valid `CanonicalDigest`:
    - returns deterministic fallback when synthesis is disabled/unavailable
    - returns deterministic fallback on provider/template/validation errors
    - returns validated synthesized structure otherwise
    """

    fallback = build_deterministic_digest(
        window=window,
        source_events=source_events,
        source_groups=source_groups,
        top_developments_limit=settings.digest_top_developments_limit,
        section_bullet_limit=settings.digest_section_bullet_limit,
    )

    if not source_events or not source_groups:
        return fallback

    client = _build_llm_client(settings, llm_client)
    if client is None:
        return fallback

    source_candidates = [
        {
            "source_event_ids": list(group.source_event_ids),
            "topic_label": group.topic_label,
            "summary_1_sentence": group.summary_1_sentence,
            "impact_score": group.impact_score,
            "last_updated_at": group.last_updated_at.isoformat(),
            "event_fingerprint": group.event_fingerprint,
            "claim_hash": group.claim_hash,
        }
        for group in source_groups
    ]
    known_labels_csv = ", ".join(known_topic_labels())
    candidates_json = json.dumps(
        source_candidates,
        ensure_ascii=True,
        separators=(",", ":"),
    )

    try:
        prompt = render_digest_synthesis_prompt(
            source_candidates_json=candidates_json,
            top_developments_limit=settings.digest_top_developments_limit,
            section_bullet_limit=settings.digest_section_bullet_limit,
            known_topic_labels_csv=known_labels_csv,
        )
        llm_response = client.synthesize(prompt.prompt_text)
        validated = _validate_synthesis_payload(
            payload_text=llm_response.raw_text,
            source_event_ids={row.event_id for row in source_events},
            top_limit=settings.digest_top_developments_limit,
            section_limit=settings.digest_section_bullet_limit,
        )
    except (DigestProviderError, DigestSynthesisError, FileNotFoundError, ValueError) as exc:
        logger.warning("digest_synthesis_fallback reason=%s", str(exc))
        return fallback

    return CanonicalDigest(
        window=window,
        source_events=tuple(sorted(source_events, key=lambda row: row.event_id)),
        top_developments=validated.top_developments,
        sections=validated.sections,
        covered_event_ids=validated.covered_event_ids,
    )
