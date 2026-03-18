from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.opportunities.assessment import create_assessments_for_bundle
from app.contexts.opportunities.thesis_cards import create_cards_for_assessments
from app.contexts.themes.contracts import EvidenceBundle, EvidenceItem
from app.contexts.themes.registry import get_theme_definition
from app.db import Base
from app.models import ThemeOpportunityAssessment, ThemeRun


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True), engine


def _bundle(window_start: datetime, window_end: datetime) -> EvidenceBundle:
    items = (
        EvidenceItem(
            evidence_id=1,
            event_id=101,
            extraction_id=201,
            event_time=window_end - timedelta(hours=2),
            event_topic="commodities",
            impact_score=82.0,
            calibrated_score=82.0,
            matched_archetypes=("input_price_shock", "supply_disruption"),
            reason_codes=("theme_match:energy_signal",),
            directionality="stress",
            summary="Gas price spike and LNG disruption tighten supply.",
            entities=("lng supplier", "ttf"),
            geographies=("qatar",),
            dedupe_key="claim-a",
        ),
        EvidenceItem(
            evidence_id=2,
            event_id=102,
            extraction_id=202,
            event_time=window_end - timedelta(hours=1),
            event_topic="commodities",
            impact_score=75.0,
            calibrated_score=75.0,
            matched_archetypes=("capacity_expansion_closure", "supply_disruption"),
            reason_codes=("theme_match:supply_shape",),
            directionality="stress",
            summary="Producer signals potential curtailment under elevated energy costs.",
            entities=("producer",),
            geographies=("europe",),
            dedupe_key="claim-b",
        ),
    )
    return EvidenceBundle(
        theme_key="energy_to_agri_inputs",
        cadence="daily",
        window_start_utc=window_start,
        window_end_utc=window_end,
        evidence_items=items,
        top_supporting_evidence_ids=(1, 2),
        top_contradictory_evidence_ids=(),
        archetype_mix={
            "input_price_shock": 1,
            "supply_disruption": 2,
            "capacity_expansion_closure": 1,
        },
        entity_mix={"lng supplier": 1, "producer": 1},
        geography_mix={"qatar": 1, "europe": 1},
        severity_distribution={"high": 1, "medium": 1},
        novelty_indicators={"repeat_ratio": 0.0, "novelty_ratio": 1.0, "contradiction_ratio": 0.0},
        freshness_profile="recent_spike",
        metadata={"total_raw_evidence_count": 2, "deduped_evidence_count": 2},
    )


def _make_run(db, *, start: datetime, end: datetime, run_key: str) -> ThemeRun:
    row = ThemeRun(
        run_key=run_key,
        theme_key="energy_to_agri_inputs",
        cadence="daily",
        window_start_utc=start,
        window_end_utc=end,
        status="running",
        started_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def test_assessment_scoring_components_and_lens_activation():
    SessionLocal, engine = _session_factory()
    theme = get_theme_definition("energy_to_agri_inputs")
    try:
        with SessionLocal() as db:
            end = datetime.utcnow().replace(microsecond=0)
            start = end - timedelta(days=1)
            run = _make_run(db, start=start, end=end, run_key="run-a")
            assessments = create_assessments_for_bundle(
                db,
                theme_run=run,
                theme_definition=theme,
                bundle=_bundle(start, end),
                enrichment_payload={"directionality": "stress_dominant"},
            )
            db.commit()

            assert len(assessments) >= 1
            for assessment in assessments:
                assert assessment.evidence_strength_score > 0
                assert assessment.lens_fit_score > 0
                assert assessment.opportunity_priority_score > 0
                assert assessment.confidence_score > 0
                assert assessment.primary_lens in {"input_cost_pass_through", "capacity_curtailment"}

    finally:
        engine.dispose()


def test_duplicate_suppression_and_material_update_behavior():
    SessionLocal, engine = _session_factory()
    theme = get_theme_definition("energy_to_agri_inputs")
    try:
        with SessionLocal() as db:
            now = datetime.utcnow().replace(microsecond=0)
            run1 = _make_run(db, start=now - timedelta(days=1), end=now, run_key="run-1")
            assessments1 = create_assessments_for_bundle(
                db,
                theme_run=run1,
                theme_definition=theme,
                bundle=_bundle(run1.window_start_utc, run1.window_end_utc),
                enrichment_payload={"directionality": "stress_dominant"},
            )
            cards1 = create_cards_for_assessments(
                db,
                theme_run=run1,
                theme_definition=theme,
                assessments=assessments1,
                dry_run=False,
            )
            assert any(card.status == "emitted" for card in cards1)

            run2 = _make_run(
                db,
                start=now,
                end=now + timedelta(days=1),
                run_key="run-2",
            )
            assessments2 = create_assessments_for_bundle(
                db,
                theme_run=run2,
                theme_definition=theme,
                bundle=_bundle(run2.window_start_utc, run2.window_end_utc),
                enrichment_payload={"directionality": "stress_dominant"},
            )
            cards2 = create_cards_for_assessments(
                db,
                theme_run=run2,
                theme_definition=theme,
                assessments=assessments2,
                dry_run=False,
            )
            assert any(card.status == "repeat_suppressed" for card in cards2)

            run3 = _make_run(
                db,
                start=now + timedelta(days=1),
                end=now + timedelta(days=2),
                run_key="run-3",
            )
            row = ThemeOpportunityAssessment(
                theme_run_id=run3.id,
                stable_key="manual-material-change",
                theme_key="energy_to_agri_inputs",
                cadence="daily",
                window_start_utc=run3.window_start_utc,
                window_end_utc=run3.window_end_utc,
                active_lenses=["input_cost_pass_through"],
                active_transmission_patterns=["input_cost_pass_through"],
                primary_lens="input_cost_pass_through",
                primary_transmission_pattern="input_cost_pass_through",
                evidence_summary_json={"count": 2},
                top_supporting_evidence_ids=[1, 999],
                top_contradictory_evidence_ids=[],
                dominant_drivers={},
                transmission_narrative_json={},
                candidate_opportunities=["Look for downstream agri-input margin pressure where feedstock costs stay elevated."],
                candidate_risks=[],
                evidence_strength_score=80.0,
                lens_fit_score=82.0,
                opportunity_priority_score=90.0,
                confidence_score=90.0,
                urgency="high",
                time_horizon="short_term",
                invalidation_conditions=["condition"],
                status="active",
            )
            db.add(row)
            db.flush()

            cards3 = create_cards_for_assessments(
                db,
                theme_run=run3,
                theme_definition=theme,
                assessments=[row],
                dry_run=False,
            )
            assert len(cards3) == 1
            assert cards3[0].status in {"updated", "emitted"}
            db.commit()
    finally:
        engine.dispose()
