from __future__ import annotations

from collections.abc import Iterable

from .contracts import EventArchetype, ThemeMatchResult


_DEFAULT_ENERGY_MARKERS = (
    "gas",
    "lng",
    "natural gas",
    "power",
    "electricity",
    "diesel",
    "oil",
    "crude",
    "brent",
    "wti",
    "feedstock",
)
_DEFAULT_SUPPLY_SIDE_MARKERS = (
    "supply disruption",
    "disruption",
    "shutdown",
    "outage",
    "curtail",
    "restriction",
    "export ban",
    "tightening",
    "shortage",
)
_DEFAULT_DOWNSTREAM_MARKERS = (
    "cost",
    "input",
    "margin",
    "capacity",
    "agri",
    "fertilizer",
    "ammonia",
    "urea",
)


def _normalized_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _iter_str(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    for value in values:
        if isinstance(value, str):
            cleaned = _normalized_text(value)
            if cleaned:
                out.append(cleaned)
    return out


def _payload_text(payload: dict[str, object]) -> str:
    keywords = _iter_str(payload.get("keywords", []) if isinstance(payload.get("keywords"), list) else [])
    summary = _normalized_text(payload.get("summary_1_sentence") if isinstance(payload.get("summary_1_sentence"), str) else "")
    source = _normalized_text(payload.get("source_claimed") if isinstance(payload.get("source_claimed"), str) else "")
    stats = payload.get("market_stats", [])
    stat_labels: list[str] = []
    if isinstance(stats, list):
        for row in stats:
            if not isinstance(row, dict):
                continue
            label = row.get("label")
            context = row.get("context")
            if isinstance(label, str):
                stat_labels.append(_normalized_text(label))
            if isinstance(context, str):
                stat_labels.append(_normalized_text(context))
    return " ".join([summary, source, " ".join(keywords), " ".join(stat_labels)]).strip()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _marker_hits(text: str, markers: tuple[str, ...]) -> list[str]:
    return sorted({marker for marker in markers if marker in text})


def infer_event_archetypes(
    *,
    text: str,
    topic: str | None,
) -> tuple[tuple[EventArchetype, ...], tuple[str, ...], str]:
    archetypes: set[EventArchetype] = set()
    reasons: list[str] = []

    if any(token in text for token in ("disruption", "shutdown", "halt", "shortage", "tightening")):
        archetypes.add("supply_disruption")
    if any(token in text for token in ("outage", "restart", "resume", "reopen")):
        archetypes.add("outage_restart")
    if any(token in text for token in ("regulation", "policy", "regulatory", "mandate")):
        archetypes.add("regulatory_change")
    if any(token in text for token in ("sanction", "embargo", "asset freeze")):
        archetypes.add("sanctions_escalation")
    if any(token in text for token in ("shipping", "freight", "logistics", "port", "transit", "route")):
        archetypes.add("logistics_disruption")
    if any(token in text for token in ("price shock", "price spike", "surge", "jump", "record high", "cost jump")):
        archetypes.add("input_price_shock")
    if any(token in text for token in ("export ban", "export curb", "quota", "export restriction")):
        archetypes.add("export_restriction")
    if any(token in text for token in ("storm", "freeze", "drought", "heatwave", "weather")):
        archetypes.add("weather_shock")
    if any(token in text for token in ("capacity", "closure", "shutdown", "curtailment", "utilization")):
        archetypes.add("capacity_expansion_closure")
    if any(token in text for token in ("guidance", "outlook", "expects", "forecast", "policy signal")):
        archetypes.add("guidance_or_policy_signal")

    for value in sorted(archetypes):
        reasons.append(f"archetype:{value}")

    direction = "neutral"
    stress_hits = any(
        token in text
        for token in (
            "surge",
            "spike",
            "jump",
            "shortage",
            "tightening",
            "shutdown",
            "curtail",
            "disruption",
            "restriction",
        )
    )
    easing_hits = any(
        token in text
        for token in (
            "restart",
            "resume",
            "reopen",
            "normalization",
            "price falls",
            "price drop",
            "capacity returns",
        )
    )
    if stress_hits and not easing_hits:
        direction = "stress"
    elif easing_hits and not stress_hits:
        direction = "easing"

    if topic == "commodities" and "input_price_shock" not in archetypes and "price" in text:
        archetypes.add("input_price_shock")
        reasons.append("archetype:input_price_shock_topic_bias")

    return tuple(sorted(archetypes)), tuple(sorted(set(reasons))), direction


def match_energy_to_agri_inputs(context: dict[str, object]) -> ThemeMatchResult:
    payload = context.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    event = context.get("event")
    extraction = context.get("extraction")
    matching_rules = context.get("event_matching_rules")
    if not isinstance(matching_rules, dict):
        matching_rules = {}

    energy_markers = tuple(matching_rules.get("energy_markers", _DEFAULT_ENERGY_MARKERS))
    supply_markers = tuple(matching_rules.get("supply_side_markers", _DEFAULT_SUPPLY_SIDE_MARKERS))
    downstream_markers = tuple(matching_rules.get("downstream_markers", _DEFAULT_DOWNSTREAM_MARKERS))

    text = _payload_text(payload)
    topic = getattr(event, "topic", None) or payload.get("topic")
    archetypes, archetype_reasons, directionality = infer_event_archetypes(text=text, topic=topic if isinstance(topic, str) else None)

    energy_hits = _marker_hits(text, energy_markers)
    supply_hits = _marker_hits(text, supply_markers)
    downstream_hits = _marker_hits(text, downstream_markers)

    has_energy_signal = bool(energy_hits)
    has_supply_shape = bool(supply_hits) or any(
        archetype in archetypes
        for archetype in (
            "supply_disruption",
            "logistics_disruption",
            "capacity_expansion_closure",
            "export_restriction",
            "outage_restart",
        )
    )
    has_downstream_shape = bool(downstream_hits) or "input_price_shock" in archetypes

    matched = has_energy_signal and (has_supply_shape or has_downstream_shape)
    reason_codes: list[str] = []
    if has_energy_signal:
        reason_codes.append("theme_match:energy_signal")
    if has_supply_shape:
        reason_codes.append("theme_match:supply_shape")
    if has_downstream_shape:
        reason_codes.append("theme_match:downstream_shape")
    reason_codes.extend(archetype_reasons)

    entities = payload.get("entities", {})
    entity_refs: list[str] = []
    geography_refs: list[str] = []
    if isinstance(entities, dict):
        entity_refs.extend(_iter_str(entities.get("orgs", []) if isinstance(entities.get("orgs"), list) else []))
        entity_refs.extend(_iter_str(entities.get("tickers", []) if isinstance(entities.get("tickers"), list) else []))
        geography_refs.extend(
            _iter_str(entities.get("countries", []) if isinstance(entities.get("countries"), list) else [])
        )

    severity_snapshot = {
        "impact_score": float(getattr(event, "impact_score", 0.0) or 0.0),
        "is_breaking": bool(getattr(event, "is_breaking", False)),
        "breaking_window": getattr(event, "breaking_window", None),
        "calibrated_score": float(
            (
                (getattr(extraction, "metadata_json", {}) or {}).get("impact_scoring", {})
                if extraction is not None
                else {}
            ).get("calibrated_score", getattr(event, "impact_score", 0.0) or 0.0)
        ),
    }

    metadata = {
        "energy_hits": energy_hits,
        "supply_hits": supply_hits,
        "downstream_hits": downstream_hits,
    }

    return ThemeMatchResult(
        matched=matched,
        theme_key="energy_to_agri_inputs",
        matched_archetypes=archetypes,
        reason_codes=tuple(sorted(set(reason_codes))),
        directionality=directionality,  # type: ignore[arg-type]
        severity_snapshot=severity_snapshot,
        entity_refs=tuple(sorted(set(entity_refs))),
        geography_refs=tuple(sorted(set(geography_refs))),
        metadata=metadata,
    )
