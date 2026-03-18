from __future__ import annotations

from types import SimpleNamespace

from app.contexts.themes.matching import infer_event_archetypes, match_energy_to_agri_inputs


def _context(summary: str, keywords: list[str]) -> dict[str, object]:
    event = SimpleNamespace(
        topic="commodities",
        impact_score=78.0,
        is_breaking=True,
        breaking_window="1h",
    )
    payload = {
        "topic": "commodities",
        "summary_1_sentence": summary,
        "keywords": keywords,
        "source_claimed": "Market wire",
        "entities": {
            "countries": ["Qatar"],
            "orgs": ["LNG Exporter"],
            "tickers": ["TTF"],
        },
    }
    return {
        "event": event,
        "payload": payload,
        "event_matching_rules": {
            "energy_markers": ("gas", "lng", "energy"),
            "supply_side_markers": ("disruption", "outage", "curtailment"),
            "downstream_markers": ("cost", "input", "capacity"),
        },
    }


def test_matching_is_deterministic_and_explainable():
    context = _context(
        "LNG supply disruption lifts gas prices and raises input costs for downstream users.",
        ["lng", "supply disruption", "input costs"],
    )

    result_a = match_energy_to_agri_inputs(context)
    result_b = match_energy_to_agri_inputs(context)
    assert result_a == result_b
    assert result_a.matched is True
    assert "theme_match:energy_signal" in result_a.reason_codes
    assert any(code.startswith("archetype:") for code in result_a.reason_codes)
    assert result_a.directionality == "stress"


def test_matching_rejects_unrelated_signal():
    context = _context(
        "Election commentary focused on domestic politics without commodity implications.",
        ["politics", "campaign"],
    )
    result = match_energy_to_agri_inputs(context)
    assert result.matched is False


def test_archetype_inference_detects_supply_and_capacity_shape():
    archetypes, _, directionality = infer_event_archetypes(
        text="Plant shutdown and logistics disruption point to capacity curtailment risk.",
        topic="commodities",
    )
    assert "supply_disruption" in archetypes
    assert "capacity_expansion_closure" in archetypes
    assert directionality == "stress"
