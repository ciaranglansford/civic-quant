# Tech Debt

## Status
Theme batch POC introduced manageable, explicit debt items.

## Why it matters
Makes future hardening work visible without blocking delivery.

## Current implementation
- No migration framework; additive table adoption is job-driven.
- Locking reused from `processing_locks`; no dedicated theme-run lock table.
- Deterministic similarity signature is intentionally simple.

## What remains
- Evaluate Alembic adoption before broader schema evolution.
- Add stronger run idempotency controls for repeated identical windows.
- Add richer metadata versioning for assessment/card schemas.

## Files/modules involved
- `app/models.py`
- `app/jobs/adopt_theme_batch_schema.py`
- `app/workflows/theme_batch_pipeline.py`

## Next recommended move
- Introduce lightweight migration discipline before adding more theme-related tables/fields.

## Last updated
2026-03-18
