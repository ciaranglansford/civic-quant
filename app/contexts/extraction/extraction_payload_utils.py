from __future__ import annotations

from ...models import Extraction
from ..triage.triage_engine import classify_source, summary_tags


def payload_for_extraction_row(row: Extraction) -> dict:
    payload = row.canonical_payload_json or row.payload_json or {}
    return payload if isinstance(payload, dict) else {}


def entity_signature_from_payload(payload: dict) -> set[str]:
    entities = payload.get("entities") if isinstance(payload, dict) else {}
    if not isinstance(entities, dict):
        return set()

    out: set[str] = set()
    for key, prefix in (("countries", "country"), ("orgs", "org"), ("people", "person")):
        values = entities.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str):
                cleaned = value.strip().lower()
                if cleaned:
                    out.add(f"{prefix}:{cleaned}")
    return out


def keywords_from_payload(payload: dict) -> set[str]:
    values = payload.get("keywords", []) if isinstance(payload, dict) else []
    if not isinstance(values, list):
        return set()
    out: set[str] = set()
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned:
                out.add(cleaned)
    return out


def source_from_payload(payload: dict) -> str:
    value = payload.get("source_claimed") if isinstance(payload, dict) else None
    if isinstance(value, str):
        return value.strip().lower()
    return ""


def summary_tags_from_payload(payload: dict) -> set[str]:
    summary = payload.get("summary_1_sentence") if isinstance(payload, dict) else None
    if not isinstance(summary, str):
        return set()
    return summary_tags(summary)


def source_class_from_payload(payload: dict) -> str:
    source = payload.get("source_claimed") if isinstance(payload, dict) else None
    summary = payload.get("summary_1_sentence") if isinstance(payload, dict) else None
    return classify_source(source if isinstance(source, str) else None, summary if isinstance(summary, str) else "")

