# Module Map

## Status
The repository remains a modular monolith with additive theme-batch modules.

## Why it matters
Clear ownership boundaries reduce accidental coupling between continuous pipeline, digest reporting, and new thesis-batch logic.

## Current implementation
- `app/contexts/ingest/*`: ingest envelope + normalization + raw persistence
- `app/contexts/extraction/*`: extraction client/validation/canonicalization/reuse
- `app/contexts/triage/*`: deterministic routing + impact calibration
- `app/contexts/events/*`: event matching/upsert
- `app/contexts/entities/*`: entity indexing
- `app/contexts/enrichment/*`: enrichment candidate selection seams
- `app/contexts/feed/*`: feed query contract
- `app/digest/*`: canonical digest/report implementation (unchanged ownership)
- `app/contexts/themes/*`: theme/lens definitions, registry, matching, evidence, bundle
- `app/contexts/opportunities/*`: enrichment providers, scoring, assessments, thesis cards, briefs
- `app/workflows/phase2_pipeline.py`: continuous extraction orchestration
- `app/workflows/theme_batch_pipeline.py`: batch thematic workflow coordinator
- `app/jobs/run_theme_batch.py`: CLI entrypoint for batch runs
- `app/routers/admin_theme.py`: internal admin trigger/inspection endpoints

## Files/modules involved
- Theme batch models are in `app/models.py` (`theme_runs`, `event_theme_evidence`, `theme_opportunity_assessments`, `thesis_cards`, `theme_brief_artifacts`).
- Schema adoption helper is `app/jobs/adopt_theme_batch_schema.py`.

## What remains
- Remove legacy digest shims when safe.
- Add auth boundary for `/admin/theme*`.

## Next recommended move
- Add a second theme using the same registries and confirm minimal code changes.

## Last updated
2026-03-18
