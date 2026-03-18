from __future__ import annotations

from datetime import datetime

from app.schemas import ExtractionEntities, ExtractionJson, MarketStat
from app.contexts.triage.impact_scoring import calibrate_impact, distribution_metrics


def _extraction(
    *,
    topic: str,
    summary: str,
    impact: float,
    breaking_window: str = "none",
    is_breaking: bool = False,
    keywords: list[str] | None = None,
    tickers: list[str] | None = None,
    market_stats: list[MarketStat] | None = None,
) -> ExtractionJson:
    return ExtractionJson(
        topic=topic,  # type: ignore[arg-type]
        entities=ExtractionEntities(
            countries=["United States"],
            orgs=["Federal Reserve"],
            people=[],
            tickers=tickers or [],
        ),
        affected_countries_first_order=["United States"],
        market_stats=market_stats or [],
        sentiment="neutral",
        confidence=0.85,
        impact_score=impact,
        is_breaking=is_breaking,
        breaking_window=breaking_window,  # type: ignore[arg-type]
        event_time=datetime.utcnow(),
        source_claimed="Reuters",
        summary_1_sentence=summary,
        keywords=keywords or [],
        event_core=None,
        event_fingerprint="f",
    )


def test_no_shock_blocks_top_band_even_with_high_raw_score():
    extraction = _extraction(
        topic="macro_econ",
        summary="Officials discuss inflation outlook and policy framework.",
        impact=98.0,
        keywords=["inflation", "policy"],
        tickers=["DXY"],
    )

    out = calibrate_impact(extraction)
    assert out.raw_llm_score == 98.0
    assert out.calibrated_score < 80.0
    assert "impact:no_shock_top_band_block" in out.rules_fired
    assert out.score_breakdown["score_band_computed_after_rules"] is True


def test_local_incident_cap_applies_regardless_of_raw_score():
    extraction = _extraction(
        topic="war_security",
        summary="Police report multiple people injured in Austin, TX incident.",
        impact=95.0,
        breaking_window="15m",
        is_breaking=True,
        keywords=["police", "incident", "injured"],
    )

    out = calibrate_impact(extraction)
    assert out.raw_llm_score == 95.0
    assert out.calibrated_score <= 40.0
    assert "impact:local_incident_cap_40" in out.rules_fired


def test_top_band_requires_shock_and_transmission():
    extraction = _extraction(
        topic="macro_econ",
        summary="US CPI surprise significantly above expectations; Treasury yields jump 35 bps and USD surges.",
        impact=42.0,
        breaking_window="15m",
        is_breaking=True,
        keywords=["cpi surprise", "yields", "usd"],
        tickers=["DXY"],
        market_stats=[MarketStat(label="US10Y", value=35.0, unit="bps", context="move")],
    )

    out = calibrate_impact(extraction)
    assert out.calibrated_score >= 80.0
    assert out.score_band == "top"
    assert "major_macroeconomic_surprise" in out.shock_flags
    assert out.score_breakdown["transmission_criteria_met"] is True


def test_distribution_metrics_include_percentiles_and_thresholds():
    metrics = distribution_metrics([10.0, 40.0, 61.0, 79.0, 80.0, 92.0])
    assert metrics["count"] == 6.0
    assert metrics["p95"] >= 80.0
    assert metrics["p99"] >= metrics["p95"]
    assert metrics["pct_gt_40"] > 0
    assert metrics["pct_gt_60"] > 0
    assert metrics["pct_gte_80"] > 0

