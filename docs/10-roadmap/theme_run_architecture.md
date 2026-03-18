# Theme Run Architecture

## Status
Implemented for one theme (`energy_to_agri_inputs`) as deterministic batch orchestration.

## Why it matters
Separates event-time evidence capture from batch-time thesis interpretation and emission.

## Current implementation
Flow:
1. continuous events -> theme evidence matching -> `event_theme_evidence`
2. scheduled run resolves `(theme, cadence, window)`
3. catch-up matching for missing rows in window
4. deterministic evidence bundle build
5. internal enrichment provider aggregation
6. lens activation + transmission inference
7. `ThemeOpportunityAssessment` persistence
8. thesis-card gating/suppression/update status
9. brief artifact persistence
10. run status/counters/error state in `theme_runs`

Locking:
- workflow lock key: `theme_batch:{theme_key}:{cadence}` via `processing_locks`.

Window policy:
- UTC half-open `[start, end)`.

## What remains
- Add scheduler integration beyond manual CLI/admin triggers.
- Expand theme inventory.

## Files/modules involved
- `app/workflows/theme_batch_pipeline.py`
- `app/contexts/themes/*`
- `app/contexts/opportunities/*`

## Next recommended move
- Add window-level replay/idempotency guard to skip fully processed identical windows when desired.

## Last updated
2026-03-18
