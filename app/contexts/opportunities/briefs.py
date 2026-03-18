from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ...models import ThemeBriefArtifact, ThemeOpportunityAssessment, ThemeRun, ThesisCard


def _build_summary_text(
    *,
    theme_run: ThemeRun,
    assessments: list[ThemeOpportunityAssessment],
    cards: list[ThesisCard],
) -> str:
    emitted = [card for card in cards if card.status in {"emitted", "updated"}]
    lines = [
        f"Theme: {theme_run.theme_key}",
        f"Cadence: {theme_run.cadence}",
        f"Window: {theme_run.window_start_utc.isoformat()} -> {theme_run.window_end_utc.isoformat()} (UTC, half-open)",
        f"Assessments: {len(assessments)}",
        f"Cards emitted/updated: {len(emitted)}",
    ]
    for card in emitted[:3]:
        lines.append(f"- {card.title} (confidence={round(card.confidence, 1)})")
    if not emitted:
        lines.append("- No thesis card met emit thresholds for this run.")
    return "\n".join(lines)


def build_and_persist_brief_artifact(
    db: Session,
    *,
    theme_run: ThemeRun,
    assessments: list[ThemeOpportunityAssessment],
    cards: list[ThesisCard],
    emit_brief: bool,
) -> ThemeBriefArtifact:
    existing = db.query(ThemeBriefArtifact).filter_by(theme_run_id=theme_run.id).one_or_none()
    row = existing or ThemeBriefArtifact(
        theme_run_id=theme_run.id,
        theme_key=theme_run.theme_key,
        cadence=theme_run.cadence,
        window_start_utc=theme_run.window_start_utc,
        window_end_utc=theme_run.window_end_utc,
        summary_text="",
    )
    if existing is None:
        db.add(row)

    if emit_brief:
        row.summary_text = _build_summary_text(
            theme_run=theme_run,
            assessments=assessments,
            cards=cards,
        )
        row.status = "created"
    else:
        row.summary_text = "Brief emission disabled for this run."
        row.status = "skipped"

    row.highlights_json = [card.title for card in cards if card.status in {"emitted", "updated"}][:5]
    row.assessment_ids_json = [assessment.id for assessment in assessments]
    row.thesis_card_ids_json = [card.id for card in cards]
    row.created_at = row.created_at or datetime.utcnow()
    db.flush()
    return row
