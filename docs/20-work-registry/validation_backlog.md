# Validation Backlog

## Status
Backlog for deeper validation beyond current unit/integration test coverage.

## Why it matters
Ensures deterministic thesis output quality is measured on realistic evidence distributions.

## Current implementation
- Automated tests cover registry/matching/bundle/scoring/gating/workflow/admin routes.
- Existing ingest/extraction/triage/digest/feed tests remain passing.

## What remains
- Multi-week replay validation against historical event sets.
- Threshold tuning against manual analyst scoring.
- Drift checks for emission/suppression rates by cadence.

## Files/modules involved
- `tests/test_theme_*`
- `tests/test_admin_theme_api.py`
- `app/contexts/opportunities/scoring.py`

## Next recommended move
- Add scenario fixtures for contradictory windows and low-signal windows to tune false positives.

## Last updated
2026-03-18
