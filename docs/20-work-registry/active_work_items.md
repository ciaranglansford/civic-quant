# Active Work Items

## Status
Open follow-up items after initial batch theme POC.

## Why it matters
Keeps near-term execution visible for future prompt-driven sessions.

## Current implementation
- Core vertical slice is complete for one theme.
- Tests cover registry, matching, bundle, scoring, gating/suppression, workflow, and admin inspection endpoints.

## What remains
- Add second theme to validate reusable shape.
- Validate score/gate thresholds against production-like evidence volume.
- Add operational dashboards/alerts for failed theme runs.

## Files/modules involved
- `app/workflows/theme_batch_pipeline.py`
- `app/contexts/themes/*`
- `app/contexts/opportunities/*`

## Next recommended move
- Run weekly backfill windows and review emitted/suppressed outcomes for threshold tuning.

## Last updated
2026-03-18
