# System Overview

## Status
Current implementation includes:
- continuous ingest/extraction/triage/event/entity pipeline
- canonical digest pipeline in `app/digest/*`
- additive batch thematic thesis POC for `energy_to_agri_inputs`

## Why it matters
- Keeps existing event and digest contracts stable while adding a new batch-only thematic intelligence layer.
- Preserves deterministic state/orchestration and uses AI only as optional drafting polish.

## Current implementation
- Continuous stage:
  - ingest and normalize raw messages
  - run extraction and deterministic triage/event clustering
  - persist event-theme evidence matches (no per-event thesis generation)
- Batch stage:
  - run theme window (`daily`/`weekly`) with UTC half-open windows `[start, end)`
  - build deterministic evidence bundle
  - evaluate active lenses/transmission patterns
  - persist `ThemeOpportunityAssessment`
  - apply deterministic thesis-card gates/suppression
  - persist brief artifact

## Admin inspection endpoints
Internal-only by convention (no auth in this pass; future auth candidate):
- `POST /admin/theme/run`
- `GET /admin/themes`
- `GET /admin/theme-runs`
- `GET /admin/theme-runs/{run_id}`
- `GET /admin/theme-runs/{run_id}/assessments`
- `GET /admin/theme-runs/{run_id}/thesis-cards`
- `GET /admin/theme-runs/{run_id}/brief`

## What remains
- Expand themes/lenses beyond one implemented theme.
- Add optional external enrichment providers.
- Add explicit auth controls for admin theme endpoints.

## Last updated
2026-03-18
