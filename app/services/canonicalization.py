from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

from ..schemas import ExtractionJson


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
    "reported",
    "reportedly",
    "claims",
    "claimed",
    "responded to reports",
)

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

FINGERPRINT_VERSION = "v1"
_MISSING_TOKEN = "~"


@dataclass(frozen=True)
class FingerprintComputation:
    version: str
    canonical_input: str
    fingerprint: str | None
    hard_identity_sufficient: bool


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


def _best_actor(canonical_payload: dict) -> str | None:
    source = canonical_payload.get("source_claimed")
    if isinstance(source, str) and source.strip():
        return _normalize_spaces(source)
    entities = canonical_payload.get("entities") or {}
    for key in ("orgs", "people", "countries"):
        values = entities.get(key, [])
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    return _normalize_spaces(value)
    return None


def _rewrite_summary_safely(canonical_payload: dict) -> tuple[str, list[str]]:
    summary_raw = str(canonical_payload.get("summary_1_sentence") or "")
    summary = _normalize_spaces(summary_raw)
    rules: list[str] = []
    if not summary:
        return summary_raw, rules

    actor = _best_actor(canonical_payload)
    if _PRONOUN_RE.search(summary):
        if actor:
            summary = _PRONOUN_RE.sub(actor, summary, count=1)
            rules.append("summary_pronoun_disambiguated")

    if _summary_has_high_risk_language(summary) and not _summary_has_attribution(summary):
        claim = summary.rstrip(".")
        if actor:
            summary = f"{actor} said {claim.lower()}."
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

    keyword_tokens = _tokenize(extraction.keywords, limit=3)
    action = keyword_tokens[0] if keyword_tokens else _MISSING_TOKEN
    subject = _join_or_missing(keyword_tokens)

    location_values = extraction.affected_countries_first_order or extraction.entities.countries
    location = _join_or_missing(_tokenize(location_values))
    country = _join_or_missing(_tokenize(extraction.entities.countries))

    date = _MISSING_TOKEN
    precision = "unknown"
    if extraction.event_time is not None:
        date = extraction.event_time.date().isoformat()
        precision = "day"

    orgs = _join_or_missing(_tokenize(extraction.entities.orgs))
    people = _join_or_missing(_tokenize(extraction.entities.people))
    tickers = _join_or_missing(_tokenize(extraction.entities.tickers, upper=True))

    canonical_input = (
        f"{FINGERPRINT_VERSION}"
        f"|event_type={_safe_token(extraction.topic)}"
        f"|actor={actor}"
        f"|target={target}"
        f"|action={action}"
        f"|subject={subject}"
        f"|location={location}"
        f"|country={country}"
        f"|date={date}"
        f"|precision={precision}"
        f"|orgs={orgs}"
        f"|people={people}"
        f"|tickers={tickers}"
    )
    has_entity_anchor = any(
        value != _MISSING_TOKEN
        for value in (actor, target, location, country, orgs, people, tickers)
    )
    has_semantic_anchor = action != _MISSING_TOKEN or subject != _MISSING_TOKEN
    has_time_anchor = date != _MISSING_TOKEN
    hard_identity_sufficient = has_entity_anchor and (has_semantic_anchor or has_time_anchor)

    fingerprint: str | None = None
    if hard_identity_sufficient:
        fingerprint_hash = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()
        fingerprint = f"{FINGERPRINT_VERSION}:{fingerprint_hash}"
    return FingerprintComputation(
        version=FINGERPRINT_VERSION,
        canonical_input=canonical_input,
        fingerprint=fingerprint,
        hard_identity_sufficient=hard_identity_sufficient,
    )


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

    orgs = _canonical_text_list(entities.get("orgs", []))
    if orgs != entities.get("orgs", []):
        rules.append("org_text_normalization")
    entities["orgs"] = orgs

    people = _canonical_text_list(entities.get("people", []))
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

