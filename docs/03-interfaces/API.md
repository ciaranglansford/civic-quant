# API and Interfaces

## HTTP API Overview

This API supports wire-bulletin ingestion and operational processing jobs.

## Current API Surface vs Internal Pipeline Stages

- Exposed HTTP endpoints are focused on ingest and operational triggering.
- Most stage execution (extraction, triage, clustering, reporting) currently runs via jobs/services, not broad public API endpoints.
- Retrieval API endpoints are not documented as implemented in the current codebase.

## Current Implemented Endpoints

### `GET /health`
- Purpose: service liveness.
- Response: `{ "status": "ok" }`.

### `POST /ingest/telegram`
- Purpose: ingest one Telegram bulletin observation.
- Request model: `TelegramIngestPayload`.
- Response model: `IngestResponse`.
- Behavior:
  - validates payload,
  - normalizes text,
  - stores immutable raw record idempotently.

### `POST /admin/process/phase2-extractions`
- Purpose: manual internal trigger for one phase2 extraction run.
- Guard: admin token header.
- Behavior: runs same extraction processing logic used by scheduled job.

## Request/Response Contract Notes

### Ingest Request Semantics

`raw_text` is treated as wire bulletin content that may represent an unverified reported claim.

### Ingest Response Semantics

- `status=created`: new raw bulletin captured.
- `status=duplicate`: same source/message identity already captured.

## Non-HTTP Interfaces

### CLI Jobs

- `python -m app.jobs.run_phase2_extraction`
- `python -m app.jobs.run_digest`
- `python -m app.jobs.test_openai_extract`
- `python -m app.jobs.reset_dev_schema`
- `python -m app.jobs.clear_all_but_raw_messages`

### Listener Runtime

- `python -m listener.telegram_listener`
- Poll-based loop that fetches unseen messages and posts to ingest endpoint.

## Out of Scope (Current API Surface)

- No public external-validation endpoint yet.
- No retrieval endpoint family documented in current implementation.
