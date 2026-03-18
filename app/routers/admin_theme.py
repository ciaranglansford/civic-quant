from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..contexts.themes.registry import list_theme_definitions
from ..db import get_db
from ..models import ThemeBriefArtifact, ThemeOpportunityAssessment, ThemeRun, ThesisCard
from ..schemas import (
    ThemeAssessmentResponse,
    ThemeBatchRunResponse,
    ThemeBriefResponse,
    ThemeDefinitionResponse,
    ThemeRunItemResponse,
    ThemeRunTriggerRequest,
    ThesisCardResponse,
)
from ..workflows.theme_batch_pipeline import ThemeBatchRequest, run_theme_batch


router = APIRouter(prefix="/admin", tags=["admin-theme"])

# Internal-only inspection/control endpoints by convention.
# Auth is intentionally not introduced in this pass and can be added later.


@router.post("/theme/run", response_model=ThemeBatchRunResponse)
def trigger_theme_run(
    payload: ThemeRunTriggerRequest,
    db: Session = Depends(get_db),
) -> ThemeBatchRunResponse:
    summary = run_theme_batch(
        db,
        request=ThemeBatchRequest(
            theme_key=payload.theme_key,
            cadence=payload.cadence,
            window_start_utc=payload.window_start_utc,
            window_end_utc=payload.window_end_utc,
            dry_run=payload.dry_run,
            emit_brief=payload.emit_brief,
        ),
    )
    db.commit()
    return ThemeBatchRunResponse(**summary.__dict__)


@router.get("/themes", response_model=list[ThemeDefinitionResponse])
def get_themes() -> list[ThemeDefinitionResponse]:
    definitions = list_theme_definitions()
    return [
        ThemeDefinitionResponse(
            key=definition.key,
            title=definition.title,
            supported_cadences=list(definition.supported_cadences),
            lenses=[lens.key for lens in definition.lenses],
            allowed_transmission_patterns=list(definition.allowed_transmission_patterns),
            relevant_event_archetypes=list(definition.relevant_event_archetypes),
        )
        for definition in definitions
    ]


@router.get("/theme-runs", response_model=list[ThemeRunItemResponse])
def list_theme_runs(
    db: Session = Depends(get_db),
    theme_key: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[ThemeRunItemResponse]:
    query = db.query(ThemeRun)
    if theme_key:
        query = query.filter(ThemeRun.theme_key == theme_key)
    rows = query.order_by(ThemeRun.created_at.desc(), ThemeRun.id.desc()).limit(limit).all()
    return [ThemeRunItemResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/theme-runs/{run_id}", response_model=ThemeRunItemResponse)
def get_theme_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> ThemeRunItemResponse:
    row = db.query(ThemeRun).filter_by(id=run_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="theme run not found")
    return ThemeRunItemResponse.model_validate(row, from_attributes=True)


@router.get("/theme-runs/{run_id}/assessments", response_model=list[ThemeAssessmentResponse])
def get_theme_run_assessments(
    run_id: int,
    db: Session = Depends(get_db),
) -> list[ThemeAssessmentResponse]:
    rows = (
        db.query(ThemeOpportunityAssessment)
        .filter(ThemeOpportunityAssessment.theme_run_id == run_id)
        .order_by(ThemeOpportunityAssessment.created_at.desc(), ThemeOpportunityAssessment.id.desc())
        .all()
    )
    return [
        ThemeAssessmentResponse(
            id=row.id,
            stable_key=row.stable_key,
            theme_key=row.theme_key,
            cadence=row.cadence,
            window_start_utc=row.window_start_utc,
            window_end_utc=row.window_end_utc,
            active_lenses=list(row.active_lenses or []),
            active_transmission_patterns=list(row.active_transmission_patterns or []),
            primary_lens=row.primary_lens,
            primary_transmission_pattern=row.primary_transmission_pattern,
            evidence_summary=dict(row.evidence_summary_json or {}),
            top_supporting_evidence_ids=[int(v) for v in (row.top_supporting_evidence_ids or [])],
            top_contradictory_evidence_ids=[int(v) for v in (row.top_contradictory_evidence_ids or [])],
            dominant_drivers=dict(row.dominant_drivers or {}),
            transmission_narrative=dict(row.transmission_narrative_json or {}),
            candidate_opportunities=[str(v) for v in (row.candidate_opportunities or [])],
            candidate_risks=[str(v) for v in (row.candidate_risks or [])],
            evidence_strength_score=float(row.evidence_strength_score),
            lens_fit_score=float(row.lens_fit_score),
            opportunity_priority_score=float(row.opportunity_priority_score),
            confidence_score=float(row.confidence_score),
            urgency=row.urgency,
            time_horizon=row.time_horizon,
            invalidation_conditions=[str(v) for v in (row.invalidation_conditions or [])],
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/theme-runs/{run_id}/thesis-cards", response_model=list[ThesisCardResponse])
def get_theme_run_cards(
    run_id: int,
    db: Session = Depends(get_db),
) -> list[ThesisCardResponse]:
    rows = (
        db.query(ThesisCard)
        .filter(ThesisCard.theme_run_id == run_id)
        .order_by(ThesisCard.created_at.desc(), ThesisCard.id.desc())
        .all()
    )
    return [
        ThesisCardResponse(
            id=row.id,
            assessment_id=row.assessment_id,
            theme_key=row.theme_key,
            cadence=row.cadence,
            title=row.title,
            what_happened=row.what_happened,
            why_it_matters=row.why_it_matters,
            transmission_path=row.transmission_path,
            opportunity_angles=[str(v) for v in (row.opportunity_angles or [])],
            confidence=float(row.confidence),
            what_to_watch_next=row.what_to_watch_next,
            invalidation_criteria=row.invalidation_criteria,
            supporting_evidence_refs=[int(v) for v in (row.supporting_evidence_refs or [])],
            status=row.status,
            suppression_reason=row.suppression_reason,
            material_update_reason=row.material_update_reason,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/theme-runs/{run_id}/brief", response_model=ThemeBriefResponse)
def get_theme_run_brief(
    run_id: int,
    db: Session = Depends(get_db),
) -> ThemeBriefResponse:
    row = db.query(ThemeBriefArtifact).filter(ThemeBriefArtifact.theme_run_id == run_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="theme brief not found")
    return ThemeBriefResponse(
        id=row.id,
        theme_run_id=row.theme_run_id,
        theme_key=row.theme_key,
        cadence=row.cadence,
        window_start_utc=row.window_start_utc,
        window_end_utc=row.window_end_utc,
        summary_text=row.summary_text,
        highlights=[str(v) for v in (row.highlights_json or [])],
        assessment_ids=[int(v) for v in (row.assessment_ids_json or [])],
        thesis_card_ids=[int(v) for v in (row.thesis_card_ids_json or [])],
        status=row.status,
        created_at=row.created_at,
    )
