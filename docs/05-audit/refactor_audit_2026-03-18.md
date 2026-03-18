# Refactor Audit - 2026-03-18

## What Changed

- Refactored backend ownership to a context-first modular monolith layout.
- Added canonical context packages under `app/contexts/`:
  - `ingest`, `extraction`, `triage`, `events`, `entities`, `enrichment`, `feed`
- Added workflow orchestration module:
  - `app/workflows/phase2_pipeline.py`
- Moved non-digest service logic from `app/services/*` into context/workflow modules and updated imports across routers, jobs, and tests.
- Kept `app/digest/` as the single canonical reporting/digest implementation.
- Retained only digest/report transitional shims in `app/services/`:
  - `digest_builder.py`, `digest_query.py`, `digest_runner.py`, `telegram_publisher.py`
- Added minimal forward extension seams (contracts only):
  - `app/contexts/enrichment/provider_contracts.py`
  - `app/contexts/triage/opportunity_contracts.py`
  - `app/digest/contracts.py`
- Added seam tests:
  - `tests/test_extension_seams.py`
- Updated living documentation to reflect new module ownership and runbook truth.
- Added "Current status" annotations to historical docs in `docs/05-audit/*` and `docs/feed-api/*`.

## What Was Intentionally Not Changed

- No microservice split, no second backend repo.
- No public HTTP contract changes:
  - `/health`, `/ingest/telegram`, `/ingest/source`, `/admin/process/phase2-extractions`, `/api/feed/events`.
- No schema redesign/cleanup and no destructive database migration work.
- No rewrite of canonical digest semantics outside `app/digest/*`.

## Schema Changes

- None in this refactor pass.
- Existing schema remains compatible.

## Manual Adoption Steps Required

- None required for this refactor because no schema changes were introduced.
- Standard local reset/reprocess commands remain available if needed for dev data resets:
  - `CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages`
  - `python -m app.jobs.reset_dev_schema` (destructive; no runtime confirmation guard)

## Known Follow-Up Work

- Remove remaining digest/report transitional shims from `app/services/*` after one full release cycle and external dependency verification.
- Consider adding migration tooling (Alembic) before future schema evolution.
- Continue splitting `app/workflows/phase2_pipeline.py` if future features increase orchestration complexity.
- Implement concrete enrichment providers, opportunity scoring behavior, thesis-card generation, and periodic brief assembly behind the new contract seams.

## Remaining Technical Debt

- `app/workflows/phase2_pipeline.py` remains a large coordinator module, though business helper logic was further extracted.
- `reset_dev_schema` still executes without a runtime confirmation guard.
- Some historical docs remain intentionally archival and may reference prior module names/paths despite top-level annotations.

## Documentation Still Needing Future Revision

- Historical planning/audit timelines under `docs/feed-api/*` and older `docs/05-audit/*` if/when those records are consolidated.
- `docs/04-operations/IMPROVEMENTS.md` backlog priorities as architecture matures.
