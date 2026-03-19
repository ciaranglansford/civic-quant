from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from ...schemas import (
    ExtractionImpactInputs,
    ExtractionJson,
    ExtractionRelation,
    ExtractionTag,
)
from ...structured_contracts import (
    inference_level_for_source,
    normalize_directionality,
    normalize_event_type,
    normalize_relation_entity_type,
    normalize_relation_source,
    normalize_relation_type,
    normalize_relation_value,
    normalize_tag_family,
    normalize_tag_source,
    normalize_tag_value,
)


_WS_RE = re.compile(r"\s+")
_TICKER_CLEAN_RE = re.compile(r"[^A-Z0-9.\-]")
_PRONOUN_RE = re.compile(r"\b(it|they|he|she)\b", re.IGNORECASE)
_HIGH_RISK_TERMS = (
    "killing",
    "killed",
    "assassination",
    "death of",
    "strike",
    "attack",
    "attacked",
    "targeting",
    "casualties",
    "injured",
    "wounded",
    "dead",
    "invasion",
    "military escalation",
    "direct strike",
    "major incident",
    "launched",
    "missile",
    "missiles",
)
_ATTRIBUTION_MARKERS = (
    "according to",
    "said",
    "says",
    "stated",
    "warned",
    "warns",
    "reported",
    "reportedly",
    "claims",
    "claimed",
    "responded to reports",
)
_GENERIC_SOURCE_LABELS = {
    "market news feed",
    "news feed",
    "wire",
    "wire feed",
    "market wire",
    "telegram feed",
}

_COUNTRY_ALIASES: dict[str, str] = {
    "us": "United States",
    "u.s.": "United States",
    "u.s": "United States",
    "usa": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "u.k": "United Kingdom",
    "uae": "United Arab Emirates",
    "eu": "European Union",
}

_PLACEHOLDER_ENTITY_VALUES: frozenset[str] = frozenset(
    {
        "multiple countries",
        "multiple country",
        "various countries",
        "several countries",
        "multiple entities",
        "various entities",
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
        "not specified",
        "tbd",
    }
)
_ACRONYM_TOKENS: frozenset[str] = frozenset(
    {
        "AP",
        "BOE",
        "ECB",
        "EU",
        "FED",
        "FOMC",
        "IAEA",
        "IMF",
        "NATO",
        "NIOC",
        "OPEC",
        "RBNZ",
        "UN",
        "UK",
        "US",
    }
)
_LOWERCASE_TITLE_TOKENS: frozenset[str] = frozenset({"a", "an", "and", "for", "in", "of", "on", "the", "to"})
_ORG_INSTITUTION_MARKERS: tuple[str, ...] = (
    "agency",
    "authority",
    "bank of",
    "central bank",
    "council",
    "department",
    "federal reserve",
    "government",
    "iaea",
    "ministry",
    "nato",
    "office",
    "pentagon",
    "reserve bank",
    "treasury",
    "united nations",
)
_KNOWN_COMPANY_NAMES: frozenset[str] = frozenset(
    {
        "amazon",
        "coinbase",
        "fedex",
        "google",
        "kalshi",
    }
)
_ORG_COMPANY_MARKERS: tuple[str, ...] = (
    " inc",
    " llc",
    " ltd",
    " plc",
    " corp",
    " corporation",
    " holdings",
    " technologies",
)
_STRESS_RELATION_TYPES: frozenset[str] = frozenset(
    {
        "conflict_with",
        "curtails",
        "disrupts_logistics_of",
        "increases_spending_on",
        "restricts_export_of",
        "sanctions",
    }
)
_EASING_RELATION_TYPES: frozenset[str] = frozenset({"contradicts", "expands_production_of", "supports"})
_DIRECTIONALITY_SUPPORT_TAG_TYPES: frozenset[str] = frozenset(
    {"conflict", "event_mechanisms", "logistics", "policy", "production", "sanctions", "spending", "strategic", "weather"}
)
_STRESS_SUMMARY_MARKERS: tuple[str, ...] = (
    "attack",
    "conflict",
    "curtail",
    "disrupt",
    "escalat",
    "halt",
    "restrict",
    "sanction",
    "shortage",
    "strike",
)
_EASING_SUMMARY_MARKERS: tuple[str, ...] = (
    "ceasefire",
    "de-escalat",
    "expand",
    "lift",
    "resume",
    "supports",
)
_MAX_CANONICAL_RELATIONS = 3

CANONICALIZER_VERSION = "canon_v3"
FINGERPRINT_VERSION = "v2"
_MISSING_TOKEN = "~"


@dataclass(frozen=True)
class FingerprintComputation:
    version: str
    canonical_input: str
    fingerprint: str | None
    hard_identity_sufficient: bool
    action_class: str
    event_time_bucket: str


@dataclass(frozen=True)
class StructuredListDiagnostics:
    emitted_count: int
    valid_count: int
    dropped_count: int
    dropped_reasons: list[str]


@dataclass(frozen=True)
class StructuredContractDiagnostics:
    tags: StructuredListDiagnostics
    relations: StructuredListDiagnostics


def _normalize_spaces(value: str) -> str:
    return _WS_RE.sub(" ", value.strip())


def _safe_token(value: str) -> str:
    cleaned = _normalize_spaces(value).lower()
    if not cleaned:
        return _MISSING_TOKEN
    return cleaned.replace("|", "/").replace("=", "-")


def _canonical_country(value: str) -> str:
    cleaned = _normalize_spaces(value)
    if not cleaned:
        return ""
    alias_key = cleaned.lower()
    canonical = _COUNTRY_ALIASES.get(alias_key, cleaned)
    return canonical.title() if canonical.islower() else canonical


def _canonical_entity_value(value: str) -> str:
    cleaned = _normalize_spaces(value)
    if not cleaned:
        return ""
    if cleaned.lower() in _PLACEHOLDER_ENTITY_VALUES:
        return ""
    if not cleaned.isupper():
        return cleaned

    tokens = cleaned.split(" ")
    rendered: list[str] = []
    for token in tokens:
        upper = token.upper()
        if upper in _ACRONYM_TOKENS:
            rendered.append(upper)
            continue
        if upper in _LOWERCASE_TITLE_TOKENS:
            rendered.append(upper.lower())
            continue
        if len(tokens) == 1 and len(upper) <= 4:
            rendered.append(upper)
            continue
        rendered.append(upper.capitalize())
    return " ".join(rendered)


def _canonical_named_entities(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = _canonical_entity_value(raw)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return sorted(out, key=str.lower)


def _organization_tag_family(value: str) -> str:
    cleaned = _canonical_entity_value(value)
    lowered = cleaned.lower()
    if lowered in _KNOWN_COMPANY_NAMES:
        return "companies"
    if any(marker in lowered for marker in _ORG_INSTITUTION_MARKERS):
        return "organizations"
    if any(marker in lowered for marker in _ORG_COMPANY_MARKERS):
        return "companies"
    return "companies"


def _canonical_relation_endpoint_value(entity_type: str, value: str) -> str:
    if entity_type in {"country", "state"}:
        return _canonical_country(value)
    return _canonical_entity_value(value)


def _canonical_countries(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        canonical = _canonical_country(raw)
        if not canonical:
            continue
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)
    return sorted(out, key=str.lower)


def _canonical_tickers(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = _normalize_spaces(raw).upper()
        cleaned = _TICKER_CLEAN_RE.sub("", cleaned)
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return sorted(out)


def _canonical_text_list(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = _normalize_spaces(raw)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return sorted(out, key=str.lower)


def _canonical_source(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _normalize_spaces(value)
    return cleaned or None


def _summary_has_high_risk_language(summary: str) -> bool:
    normalized = _normalize_spaces(summary).lower()
    return any(token in normalized for token in _HIGH_RISK_TERMS)


def _summary_has_attribution(summary: str) -> bool:
    normalized = _normalize_spaces(summary).lower()
    return any(token in normalized for token in _ATTRIBUTION_MARKERS)


def _is_generic_source_label(value: str | None) -> bool:
    if not value:
        return False
    normalized = _normalize_spaces(value).lower()
    if not normalized:
        return False
    if normalized in _GENERIC_SOURCE_LABELS:
        return True
    return normalized.endswith("news feed") or normalized.endswith("wire feed")


def _best_actor(canonical_payload: dict) -> str | None:
    source = canonical_payload.get("source_claimed")
    if isinstance(source, str) and source.strip() and not _is_generic_source_label(source):
        return _normalize_spaces(source)
    entities = canonical_payload.get("entities") or {}
    for key in ("orgs", "people", "countries"):
        values = entities.get(key, [])
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    return _normalize_spaces(value)
    return None


def _best_attribution_source(canonical_payload: dict) -> str | None:
    source = canonical_payload.get("source_claimed")
    if isinstance(source, str) and source.strip() and not _is_generic_source_label(source):
        return _normalize_spaces(source)
    return None


def _rewrite_summary_safely(canonical_payload: dict) -> tuple[str, list[str]]:
    summary_raw = str(canonical_payload.get("summary_1_sentence") or "")
    summary = _normalize_spaces(summary_raw)
    rules: list[str] = []
    if not summary:
        return summary_raw, rules

    actor = _best_actor(canonical_payload)
    attribution_source = _best_attribution_source(canonical_payload)
    if _PRONOUN_RE.search(summary):
        if actor:
            summary = _PRONOUN_RE.sub(actor, summary, count=1)
            rules.append("summary_pronoun_disambiguated")

    if _summary_has_high_risk_language(summary) and not _summary_has_attribution(summary):
        claim = summary.rstrip(".")
        if attribution_source:
            summary = f"{attribution_source} said {claim.lower()}."
        else:
            summary = f"Reportedly, {claim.lower()}."
        rules.append("summary_high_risk_attribution_rewrite")

    return summary, rules


def _tokenize(values: Iterable[str], *, upper: bool = False, limit: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = _normalize_spaces(raw)
        if not cleaned:
            continue
        token = cleaned.upper() if upper else cleaned.lower()
        token = token.replace("|", "/").replace("=", "-")
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    out = sorted(out)
    if limit is not None:
        return out[:limit]
    return out


def _join_or_missing(values: list[str]) -> str:
    if not values:
        return _MISSING_TOKEN
    return ",".join(values)


def _normalized_summary(extraction: ExtractionJson) -> str:
    return _safe_token(extraction.summary_1_sentence or "")


def derive_action_class(extraction: ExtractionJson) -> str:
    text = _normalize_spaces(
        " ".join(
            [
                extraction.summary_1_sentence or "",
                extraction.event_core or "",
                " ".join(extraction.keywords),
            ]
        )
    ).lower()

    if any(token in text for token in ("ceasefire", "talk", "negotiat", "diplom", "meeting", "summit", "agreement")):
        return "diplomatic"
    if any(token in text for token in ("strike", "attack", "missile", "drone", "shelling", "airstrike", "troops")):
        return "operational"
    if any(token in text for token in ("warn", "threat", "retaliat", "respond", "response")):
        return "threat_response"
    if any(token in text for token in ("sanction", "tariff", "export control", "embargo")):
        return "policy_restriction"
    if any(token in text for token in ("supply", "shipment", "pipeline", "loading", "halt", "disruption")):
        return "supply_disruption"
    if any(token in text for token in ("rate", "yield", "spread", "fx", "inflation", "gdp", "cpi")):
        return "market_macro"
    if any(token in text for token in ("probe", "investigation", "lawsuit", "charged", "regulator")):
        return "legal_regulatory"
    return "other"


def event_time_bucket(extraction: ExtractionJson) -> str:
    if extraction.event_time is None:
        return "unknown"
    return extraction.event_time.date().isoformat()


def compute_claim_hash(extraction: ExtractionJson) -> str:
    action_class = derive_action_class(extraction)
    source = _safe_token(extraction.source_claimed or "")
    summary = _normalized_summary(extraction)
    keywords = _join_or_missing(_tokenize(extraction.keywords, limit=8))
    actors = _join_or_missing(_tokenize(extraction.entities.orgs + extraction.entities.people, limit=6))
    countries = _join_or_missing(_tokenize(extraction.entities.countries, limit=6))
    bucket = event_time_bucket(extraction)

    claim_input = (
        f"claim_v1"
        f"|topic={_safe_token(extraction.topic)}"
        f"|action_class={action_class}"
        f"|source={source}"
        f"|summary={summary}"
        f"|keywords={keywords}"
        f"|actors={actors}"
        f"|countries={countries}"
        f"|time_bucket={bucket}"
    )
    return hashlib.sha256(claim_input.encode("utf-8")).hexdigest()


def compute_canonical_payload_hash(extraction: ExtractionJson) -> str:
    payload = extraction.model_dump(mode="json")
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _select_actor(extraction: ExtractionJson) -> str:
    if extraction.source_claimed and extraction.source_claimed.strip():
        return _safe_token(extraction.source_claimed)

    entities = extraction.entities
    orgs = _tokenize(entities.orgs)
    if orgs:
        return orgs[0]
    people = _tokenize(entities.people)
    if people:
        return people[0]
    countries = _tokenize(entities.countries)
    if countries:
        return countries[0]
    return _MISSING_TOKEN


def _select_target(extraction: ExtractionJson, actor: str) -> str:
    candidates = _tokenize(extraction.entities.orgs) + _tokenize(extraction.entities.people) + _tokenize(extraction.entities.countries)
    for candidate in candidates:
        if candidate != actor:
            return candidate
    return _MISSING_TOKEN


def compute_authoritative_fingerprint(extraction: ExtractionJson) -> FingerprintComputation:
    actor = _select_actor(extraction)
    target = _select_target(extraction, actor)
    action_class = derive_action_class(extraction)
    time_bucket = event_time_bucket(extraction)
    identity_topic = extraction.topic
    if extraction.topic in {"war_security", "geopolitics"}:
        identity_topic = "conflict_geo"
    location_values = extraction.affected_countries_first_order or extraction.entities.countries
    location_tokens = _tokenize(location_values)
    primary_location = location_tokens[0] if location_tokens else _MISSING_TOKEN

    canonical_input = (
        f"{FINGERPRINT_VERSION}"
        f"|event_type={_safe_token(identity_topic)}"
        f"|actor={actor}"
        f"|target={target}"
        f"|action_class={action_class}"
        f"|location_primary={primary_location}"
        f"|time_bucket={time_bucket}"
    )
    has_identity_anchor = any(value != _MISSING_TOKEN for value in (actor, target, primary_location))
    has_event_shape = action_class != "other" or time_bucket != "unknown"
    hard_identity_sufficient = has_identity_anchor and has_event_shape

    fingerprint: str | None = None
    if hard_identity_sufficient:
        fingerprint_hash = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()
        fingerprint = f"{FINGERPRINT_VERSION}:{fingerprint_hash}"
    return FingerprintComputation(
        version=FINGERPRINT_VERSION,
        canonical_input=canonical_input,
        fingerprint=fingerprint,
        hard_identity_sufficient=hard_identity_sufficient,
        action_class=action_class,
        event_time_bucket=time_bucket,
    )


_TOPIC_EVENT_TYPE_DEFAULT: dict[str, str] = {
    "macro_econ": "market",
    "central_banks": "policy",
    "equities": "market",
    "credit": "market",
    "rates": "market",
    "fx": "market",
    "commodities": "production",
    "crypto": "market",
    "war_security": "conflict",
    "geopolitics": "policy",
    "company_specific": "company",
    "other": "other",
}


def _safe_confidence(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (float, int)):
        return None
    numeric = float(value)
    if 0.0 <= numeric <= 1.0:
        return numeric
    return None


def _canonical_impact_inputs(raw_inputs: object) -> ExtractionImpactInputs:
    if not isinstance(raw_inputs, dict):
        return ExtractionImpactInputs()

    def _extract_list(name: str) -> list[str]:
        raw_values = raw_inputs.get(name)
        if not isinstance(raw_values, list):
            return []
        return _canonical_text_list([str(value) for value in raw_values if isinstance(value, str)])

    return ExtractionImpactInputs(
        severity_cues=_extract_list("severity_cues"),
        economic_relevance_cues=_extract_list("economic_relevance_cues"),
        propagation_potential_cues=_extract_list("propagation_potential_cues"),
        specificity_cues=_extract_list("specificity_cues"),
        novelty_cues=_extract_list("novelty_cues"),
        strategic_tag_hits=_extract_list("strategic_tag_hits"),
    )


def _has_directionality_support(
    directionality: str,
    *,
    raw_tags: object,
    raw_relations: object,
    summary: object,
) -> bool:
    if directionality == "neutral":
        return True

    summary_text = _normalize_spaces(summary) if isinstance(summary, str) else ""
    summary_lower = summary_text.lower()
    markers = _STRESS_SUMMARY_MARKERS if directionality == "stress" else _EASING_SUMMARY_MARKERS
    if any(marker in summary_lower for marker in markers):
        return True

    tag_items = raw_tags if isinstance(raw_tags, list) else []
    for item in tag_items:
        if not isinstance(item, dict):
            continue
        tag_type = normalize_tag_family(item.get("tag_type") if isinstance(item.get("tag_type"), str) else None)
        if tag_type and tag_type in _DIRECTIONALITY_SUPPORT_TAG_TYPES:
            return True

    relation_items = raw_relations if isinstance(raw_relations, list) else []
    target_relations = _STRESS_RELATION_TYPES if directionality == "stress" else _EASING_RELATION_TYPES
    for item in relation_items:
        if not isinstance(item, dict):
            continue
        relation_type = normalize_relation_type(
            item.get("relation_type") if isinstance(item.get("relation_type"), str) else None
        )
        if relation_type and relation_type in target_relations:
            return True
    return False


def _resolve_directionality(
    *,
    raw_directionality: object,
    raw_tags: object,
    raw_relations: object,
    summary: object,
) -> tuple[str, list[str]]:
    rules: list[str] = []

    directionality = normalize_directionality(raw_directionality if isinstance(raw_directionality, str) else None)
    if isinstance(raw_directionality, str) and directionality is None:
        rules.append("directionality_invalid_dropped")
    elif isinstance(raw_directionality, str) and raw_directionality != directionality:
        rules.append("directionality_normalization")

    if directionality in {"stress", "easing"} and not _has_directionality_support(
        directionality,
        raw_tags=raw_tags,
        raw_relations=raw_relations,
        summary=summary,
    ):
        directionality = "neutral"
        rules.append("directionality_demoted_without_support")

    if directionality is None:
        directionality = "neutral"
        rules.append("directionality_defaulted_neutral")

    return directionality, rules


def _diagnostics(
    *,
    emitted_count: int,
    valid_count: int,
    dropped_reasons: list[str],
) -> StructuredListDiagnostics:
    dropped_count = max(0, emitted_count - valid_count)
    return StructuredListDiagnostics(
        emitted_count=emitted_count,
        valid_count=valid_count,
        dropped_count=dropped_count,
        dropped_reasons=sorted(set(dropped_reasons)),
    )


def _canonical_tags(
    raw_tags: object,
    *,
    directionality: str,
) -> tuple[list[ExtractionTag], StructuredListDiagnostics]:
    canonical_tags: list[ExtractionTag] = []
    seen: set[tuple[str, str, str]] = set()
    dropped_reasons: list[str] = []
    valid_count = 0

    tag_items = raw_tags if isinstance(raw_tags, list) else []
    emitted_count = len(tag_items)
    for item in tag_items:
        if not isinstance(item, dict):
            dropped_reasons.append("invalid_shape")
            continue

        tag_type = normalize_tag_family(item.get("tag_type") if isinstance(item.get("tag_type"), str) else None)
        tag_value = normalize_tag_value(item.get("tag_value") if isinstance(item.get("tag_value"), str) else None)
        tag_source = normalize_tag_source(item.get("tag_source") if isinstance(item.get("tag_source"), str) else None)
        if not tag_type:
            dropped_reasons.append("invalid_tag_type")
            continue
        if not tag_value:
            dropped_reasons.append("invalid_tag_value")
            continue
        if not tag_source:
            dropped_reasons.append("invalid_tag_source")
            continue

        if tag_type == "directionality":
            normalized_dir = normalize_directionality(tag_value)
            if not normalized_dir:
                dropped_reasons.append("invalid_directionality_tag_value")
                continue
            tag_value = directionality or normalized_dir
            tag_source = "inferred"
        elif tag_type == "countries":
            tag_value = _canonical_country(tag_value)
        else:
            tag_value = _canonical_entity_value(tag_value)
        if not tag_value:
            dropped_reasons.append("invalid_tag_value")
            continue

        confidence = None if tag_type == "directionality" else _safe_confidence(item.get("confidence"))
        dedupe_key = (tag_type, tag_value.lower(), tag_source)
        if dedupe_key in seen:
            dropped_reasons.append("duplicate_tag")
            continue
        seen.add(dedupe_key)
        canonical_tags.append(
            ExtractionTag(
                tag_type=tag_type,
                tag_value=tag_value,
                tag_source=tag_source,
                confidence=confidence,
            )
        )
        valid_count += 1

    dedupe_key = ("directionality", directionality.lower(), "inferred")
    if dedupe_key not in seen:
        canonical_tags.append(
            ExtractionTag(
                tag_type="directionality",
                tag_value=directionality,
                tag_source="inferred",
                confidence=None,
            )
        )
        seen.add(dedupe_key)

    canonical_tags.sort(key=lambda tag: (tag.tag_type, tag.tag_value.lower(), tag.tag_source))
    return canonical_tags, _diagnostics(
        emitted_count=emitted_count,
        valid_count=valid_count,
        dropped_reasons=dropped_reasons,
    )


def _canonical_relations(raw_relations: object) -> tuple[list[ExtractionRelation], StructuredListDiagnostics]:
    canonical_relations: list[ExtractionRelation] = []
    seen: set[tuple[str, str, str, str, str, str, int]] = set()
    dropped_reasons: list[str] = []
    valid_count = 0

    relation_items = raw_relations if isinstance(raw_relations, list) else []
    emitted_count = len(relation_items)
    for item in relation_items:
        if not isinstance(item, dict):
            dropped_reasons.append("invalid_shape")
            continue

        subject_type = normalize_relation_entity_type(
            item.get("subject_type") if isinstance(item.get("subject_type"), str) else None
        )
        object_type = normalize_relation_entity_type(
            item.get("object_type") if isinstance(item.get("object_type"), str) else None
        )
        relation_type = normalize_relation_type(
            item.get("relation_type") if isinstance(item.get("relation_type"), str) else None
        )
        subject_value = normalize_relation_value(
            item.get("subject_value") if isinstance(item.get("subject_value"), str) else None
        )
        object_value = normalize_relation_value(
            item.get("object_value") if isinstance(item.get("object_value"), str) else None
        )
        relation_source = normalize_relation_source(
            item.get("relation_source") if isinstance(item.get("relation_source"), str) else None
        )

        if not subject_type:
            dropped_reasons.append("invalid_subject_type")
            continue
        if not object_type:
            dropped_reasons.append("invalid_object_type")
            continue
        if not relation_type:
            dropped_reasons.append("invalid_relation_type")
            continue
        if not subject_value:
            dropped_reasons.append("invalid_subject_value")
            continue
        if not object_value:
            dropped_reasons.append("invalid_object_value")
            continue
        if not relation_source:
            dropped_reasons.append("invalid_relation_source")
            continue

        subject_value = _canonical_relation_endpoint_value(subject_type, subject_value)
        object_value = _canonical_relation_endpoint_value(object_type, object_value)
        if not subject_value or not object_value:
            dropped_reasons.append("invalid_relation_value")
            continue

        inference_level = inference_level_for_source(relation_source)
        confidence = _safe_confidence(item.get("confidence"))
        dedupe_key = (
            subject_type,
            subject_value.lower(),
            relation_type,
            object_type,
            object_value.lower(),
            relation_source,
            inference_level,
        )
        if dedupe_key in seen:
            dropped_reasons.append("duplicate_relation")
            continue
        if len(canonical_relations) >= _MAX_CANONICAL_RELATIONS:
            dropped_reasons.append("relation_limit_exceeded")
            continue
        seen.add(dedupe_key)
        canonical_relations.append(
            ExtractionRelation(
                subject_type=subject_type,
                subject_value=_normalize_spaces(subject_value),
                relation_type=relation_type,
                object_type=object_type,
                object_value=_normalize_spaces(object_value),
                relation_source=relation_source,
                inference_level=inference_level,
                confidence=confidence,
            )
        )
        valid_count += 1

    canonical_relations.sort(
        key=lambda relation: (
            relation.subject_type,
            relation.subject_value.lower(),
            relation.relation_type,
            relation.object_type,
            relation.object_value.lower(),
            relation.relation_source,
            int(relation.inference_level or 0),
        )
    )
    return canonical_relations, _diagnostics(
        emitted_count=emitted_count,
        valid_count=valid_count,
        dropped_reasons=dropped_reasons,
    )


def summarize_structured_contract(payload: dict) -> StructuredContractDiagnostics:
    """Summarize emitted/valid/dropped structured items from raw extraction payload."""
    raw_tags = payload.get("tags")
    raw_relations = payload.get("relations")
    directionality, _ = _resolve_directionality(
        raw_directionality=payload.get("directionality"),
        raw_tags=raw_tags,
        raw_relations=raw_relations,
        summary=payload.get("summary_1_sentence"),
    )
    _, tag_diagnostics = _canonical_tags(raw_tags, directionality=directionality)
    _, relation_diagnostics = _canonical_relations(raw_relations)
    return StructuredContractDiagnostics(tags=tag_diagnostics, relations=relation_diagnostics)


def canonicalize_extraction(payload: dict) -> tuple[ExtractionJson, list[str], FingerprintComputation]:
    """
    Deterministically canonicalize validated extraction payload values for downstream logic.
    Returns a validated ExtractionJson, fired canonicalization rule identifiers, and authoritative fingerprint computation metadata.
    """
    canonical_payload = copy.deepcopy(payload)
    rules: list[str] = []

    llm_fingerprint_candidate = canonical_payload.get("event_fingerprint")

    entities = canonical_payload.setdefault("entities", {})

    canonical_countries = _canonical_countries(entities.get("countries", []))
    if canonical_countries != entities.get("countries", []):
        rules.append("country_alias_normalization")
    entities["countries"] = canonical_countries

    affected = _canonical_countries(canonical_payload.get("affected_countries_first_order", []))
    if affected != canonical_payload.get("affected_countries_first_order", []):
        rules.append("affected_country_alias_normalization")
    canonical_payload["affected_countries_first_order"] = affected

    tickers = _canonical_tickers(entities.get("tickers", []))
    if tickers != entities.get("tickers", []):
        rules.append("ticker_normalization")
    entities["tickers"] = tickers

    orgs = _canonical_named_entities(entities.get("orgs", []))
    if orgs != entities.get("orgs", []):
        rules.append("org_text_normalization")
    entities["orgs"] = orgs

    people = _canonical_named_entities(entities.get("people", []))
    if people != entities.get("people", []):
        rules.append("person_text_normalization")
    entities["people"] = people

    source_claimed = _canonical_source(canonical_payload.get("source_claimed"))
    if source_claimed != canonical_payload.get("source_claimed"):
        rules.append("source_text_normalization")
    canonical_payload["source_claimed"] = source_claimed

    keywords = _canonical_text_list(canonical_payload.get("keywords", []))
    if keywords != canonical_payload.get("keywords", []):
        rules.append("keyword_text_normalization")
    canonical_payload["keywords"] = keywords

    event_core_raw = canonical_payload.get("event_core")
    if isinstance(event_core_raw, str):
        event_core = _normalize_spaces(event_core_raw) or None
    else:
        event_core = None
    if event_core != event_core_raw:
        rules.append("event_core_text_normalization")
    canonical_payload["event_core"] = event_core

    topic_value = canonical_payload.get("topic")
    topic_key = str(topic_value) if isinstance(topic_value, str) else "other"

    event_type_raw = canonical_payload.get("event_type")
    event_type = normalize_event_type(event_type_raw if isinstance(event_type_raw, str) else None)
    if event_type is None:
        if isinstance(event_type_raw, str) and event_type_raw.strip():
            rules.append("event_type_invalid_dropped")
        event_type = _TOPIC_EVENT_TYPE_DEFAULT.get(topic_key, "other")
        rules.append("event_type_defaulted_from_topic")
    elif event_type_raw != event_type:
        rules.append("event_type_normalization")
    canonical_payload["event_type"] = event_type

    directionality, directionality_rules = _resolve_directionality(
        raw_directionality=canonical_payload.get("directionality"),
        raw_tags=canonical_payload.get("tags"),
        raw_relations=canonical_payload.get("relations"),
        summary=canonical_payload.get("summary_1_sentence"),
    )
    rules.extend(directionality_rules)
    canonical_payload["directionality"] = directionality

    impact_inputs_raw = canonical_payload.get("impact_inputs")
    impact_inputs = _canonical_impact_inputs(impact_inputs_raw)
    if impact_inputs.model_dump(mode="json") != impact_inputs_raw:
        rules.append("impact_inputs_normalization")

    tags_raw = canonical_payload.get("tags")
    canonical_tags, tag_diagnostics = _canonical_tags(tags_raw, directionality=directionality)
    if tag_diagnostics.dropped_count > 0:
        rules.append("structured_tags_invalid_dropped")

    tag_keys = {(tag.tag_type, tag.tag_value.lower(), tag.tag_source) for tag in canonical_tags}
    for country in sorted(set(canonical_countries + affected), key=str.lower):
        key = ("countries", country.lower(), "observed")
        if key in tag_keys:
            continue
        canonical_tags.append(
            ExtractionTag(
                tag_type="countries",
                tag_value=country,
                tag_source="observed",
                confidence=None,
            )
        )
        tag_keys.add(key)
    for org in orgs:
        tag_family = _organization_tag_family(org)
        key = (tag_family, org.lower(), "observed")
        if key in tag_keys:
            continue
        canonical_tags.append(
            ExtractionTag(
                tag_type=tag_family,
                tag_value=org,
                tag_source="observed",
                confidence=None,
            )
        )
        tag_keys.add(key)
    canonical_tags.sort(key=lambda tag: (tag.tag_type, tag.tag_value.lower(), tag.tag_source))

    strategic_from_tags = sorted(
        {
            tag.tag_value
            for tag in canonical_tags
            if tag.tag_type == "strategic" and tag.tag_value
        },
        key=str.lower,
    )
    if strategic_from_tags:
        merged_strategic = sorted(
            set(impact_inputs.strategic_tag_hits + strategic_from_tags),
            key=str.lower,
        )
        if merged_strategic != impact_inputs.strategic_tag_hits:
            impact_inputs = impact_inputs.model_copy(update={"strategic_tag_hits": merged_strategic})
            rules.append("impact_inputs_strategic_merge")

    canonical_payload["impact_inputs"] = impact_inputs.model_dump(mode="json")
    canonical_payload["tags"] = [tag.model_dump(mode="json") for tag in canonical_tags]

    relations_raw = canonical_payload.get("relations")
    canonical_relations, relation_diagnostics = _canonical_relations(relations_raw)
    if relation_diagnostics.dropped_count > 0:
        rules.append("structured_relations_invalid_dropped")
    canonical_payload["relations"] = [relation.model_dump(mode="json") for relation in canonical_relations]

    summary, summary_rules = _rewrite_summary_safely(canonical_payload)
    if summary != canonical_payload.get("summary_1_sentence"):
        rules.extend(summary_rules)
    canonical_payload["summary_1_sentence"] = summary

    canonical_model = ExtractionJson.model_validate(canonical_payload)
    fingerprint = compute_authoritative_fingerprint(canonical_model)
    canonical_payload["event_fingerprint"] = fingerprint.fingerprint or ""

    candidate_clean = llm_fingerprint_candidate.strip() if isinstance(llm_fingerprint_candidate, str) else ""
    if fingerprint.fingerprint:
        if candidate_clean:
            if candidate_clean != fingerprint.fingerprint:
                rules.append("event_fingerprint_backend_override")
        else:
            rules.append("event_fingerprint_backend_generated")
    else:
        rules.append("event_fingerprint_insufficient_identity")
        if candidate_clean:
            rules.append("event_fingerprint_llm_candidate_ignored")

    return ExtractionJson.model_validate(canonical_payload), rules, fingerprint






