# Implementation Status

## Status
Batch thematic thesis POC is implemented and runnable for one theme:
- `energy_to_agri_inputs`

## Why it matters
Confirms a working vertical slice from continuous evidence capture to scheduled thesis-card/brief outputs without breaking existing pipeline contracts.

## Current implementation
- Theme/lens registries with reusable archetype and transmission libraries.
- Continuous deterministic event-to-theme evidence persistence.
- Batch window workflow:
  - catch-up evidence matching
  - deterministic bundle build (mixes, repeat dedupe, contradiction selection, freshness)
  - internal enrichment provider aggregation
  - structured opportunity assessments
  - gated card emission + duplicate suppression (7d daily / 28d weekly)
  - brief artifact persistence
- Internal admin inspection API under `/admin/*`.
- CLI run command: `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs`.

## What remains
- More themes/lenses.
- More external enrichment providers (optional seams exist).
- Authentication hardening for admin theme routes.

## Files/modules involved
- `app/contexts/themes/*`
- `app/contexts/opportunities/*`
- `app/workflows/theme_batch_pipeline.py`
- `app/jobs/run_theme_batch.py`
- `app/routers/admin_theme.py`

## Next recommended move
- Validate behavior on larger historical windows and calibrate gate thresholds from observed output quality.

## Last updated
2026-03-18
