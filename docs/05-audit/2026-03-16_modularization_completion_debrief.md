# 2026-03-16 Modularization Completion Debrief

## Current Status (2026-03-18)

This is a historical implementation log for an earlier modularization pass.
Path ownership references under `app/services/*` may now be stale after the
context-first refactor.

Current canonical ownership:
- `app/contexts/*` for bounded contexts
- `app/workflows/*` for orchestration
- `app/digest/*` for canonical digest/reporting semantics

See `docs/05-audit/refactor_audit_2026-03-18.md` for the latest refactor state.

## Purpose

Debrief the architectural implementation pass focused on reducing coupling, clarifying module ownership, and preparing the backend for additional ingestion adapters without changing core processing behavior.

## Summary of What Was Modularized

1. Source ingest mapping was isolated into a dedicated adapter module.
2. Routing decision persistence was moved into a dedicated routing persistence module.
3. Shared extraction payload parsing logic was centralized and reused across phase2 orchestration, event matching, and enrichment selection.
4. Ingest APIs now expose both a Telegram adapter endpoint and a source-agnostic endpoint.

## High-Level Changes Implemented

### 1) Source-Agnostic Ingest Envelope

- Added `SourceIngestPayload` in `app/schemas.py`.
- Added `app/services/source_ingest.py` with:
  - `SourceMessageEnvelope`
  - `envelope_from_telegram_payload`
  - `envelope_from_source_payload`
- Refactored ingest pipeline to process a generic envelope internally (`process_ingest_message`) while preserving existing Telegram API behavior through compatibility wrappers.
- Added source-safe identity behavior: non-Telegram stream IDs are namespaced as `<source_type>:<source_stream_id>` before persistence to prevent cross-source collisions.
- Added new endpoint:
  - `POST /ingest/source`

### 2) Routing Decision Persistence Ownership

- Added `app/services/routing_decisions.py` with `upsert_routing_decision`.
- Updated phase2 processing to use `upsert_routing_decision` directly.
- Kept `store_routing_decision` in `ingest_pipeline` as a compatibility shim to avoid breaking imports/tests.

### 3) Shared Extraction Payload Utilities

- Added `app/services/extraction_payload_utils.py` with reusable helpers:
  - payload selection (`payload_for_extraction_row`)
  - payload entity signatures
  - payload keyword extraction
  - payload source extraction
  - payload summary/source classification helpers
- Updated:
  - `app/services/phase2_processing.py`
  - `app/services/event_manager.py`
  - `app/services/enrichment_selection.py`
  to consume shared utilities instead of local duplicate helper implementations.
- Exposed `summary_tags` in `triage_engine` for reuse.

## Behavioral Intent

- Preserve ingest idempotency semantics.
- Preserve phase2 extraction/triage/event/enrichment outcomes.
- Preserve backward compatibility for existing Telegram ingest clients.
- Improve extension seams without introducing new architecture framework overhead.

## Documentation Updates Included

- `docs/02-flows/agents_and_services.md`
- `docs/03-interfaces/API.md`
- `docs/04-operations/operations_and_scheduling.md`
- `docs/05-audit/spec_vs_impl_audit.md`

## Validation Performed

Executed targeted regression tests:

- `pytest -q tests/test_e2e_backend.py tests/test_event_manager_refinement.py tests/test_enrichment_selection.py tests/test_triage_engine.py`

Result:

- 24 passed
- 0 failed

Executed full regression suite:

- `pytest -q`

Result:

- 65 passed
- 0 failed

## What This Unlocks Next

1. Additional source adapters can map into the generic ingest envelope without rewriting core ingest persistence logic.
2. Further phase2 decomposition can proceed with lower risk because shared payload parsing behavior is centralized.
3. Routing persistence can evolve independently (for example audit/versioning) without coupling to ingest service concerns.

## Deferred Work (Intentionally Not Done In This Pass)

1. Full storage schema rename from Telegram-specific identifiers to fully source-agnostic column names.
2. Full phase2 orchestration split into separate batch coordinator and single-message use-case modules.
3. Provider abstraction refactor for extraction clients beyond current OpenAI-backed flow.
