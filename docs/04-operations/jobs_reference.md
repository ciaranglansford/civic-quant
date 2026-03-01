# Jobs Reference

## Purpose

Quick reference for the scripts in `app/jobs/`: what each one does, how to run it, and what changes before/after execution.

## How to Run Jobs

From repository root:

```bash
.\.venv\Scripts\Activate.ps1
python -m app.jobs.<job_module>
```

Example:

```bash
python -m app.jobs.run_phase2_extraction
```

## Job Matrix

| Job module | What it does | Run command |
|---|---|---|
| `run_phase2_extraction` | Processes eligible raw messages through extraction, triage, routing, event updates, and entity indexing. | `python -m app.jobs.run_phase2_extraction` |
| `run_digest` | Builds and publishes digest output from recent events and records publication. | `python -m app.jobs.run_digest` |
| `test_openai_extract` | Runs a single extraction smoke test against OpenAI + schema validation (no DB writes). | `python -m app.jobs.test_openai_extract` |
| `clear_all_but_raw_messages` | Deletes derived pipeline tables while preserving `raw_messages`. | `CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages` |
| `reset_dev_schema` | Drops and recreates all tables from SQLAlchemy models (destructive). | `CONFIRM_RESET_DEV_SCHEMA=true python -m app.jobs.reset_dev_schema` |

## Before/After by Job

### `run_phase2_extraction`

- Before:
  - `raw_messages` contains ingested rows.
  - `message_processing_states` has `pending`/`failed`/expired lease rows.
  - Env requires `PHASE2_EXTRACTION_ENABLED=true` and `OPENAI_API_KEY`.
- After:
  - `extractions` inserted/updated for processed messages.
  - `routing_decisions` persisted.
  - `events` and `event_messages` created/updated.
  - `entity_mentions` inserted idempotently.
  - `message_processing_states` moved to `completed` or `failed`.

### `run_digest`

- Before:
  - `events` has recent rows inside `VIP_DIGEST_HOURS` window.
  - Telegram bot publish env vars are configured.
- After:
  - Digest is sent (unless duplicate by content hash/window).
  - `published_posts` gets a new row on publish.
  - If duplicate content is detected, job exits with skip behavior and no new publish row.

### `test_openai_extract`

- Before:
  - `PHASE2_EXTRACTION_ENABLED=true`.
  - `OPENAI_API_KEY` and model config are set.
- After:
  - Prints extractor/model/latency and validated JSON to console.
  - Does not write pipeline rows (`raw_messages`, `extractions`, `events`, etc.).

### `clear_all_but_raw_messages`

- Before:
  - You want to reprocess from existing raw history.
  - `CONFIRM_CLEAR_NON_RAW=true` is set.
- After:
  - Cleared tables: `event_messages`, `published_posts`, `events`, `routing_decisions`, `extractions`, `message_processing_states`, `processing_locks`.
  - `raw_messages` remains unchanged.
  - On SQLite, ID sequences are reset where possible.

### `reset_dev_schema`

- Before:
  - You need a full schema reset in dev/test.
  - `CONFIRM_RESET_DEV_SCHEMA=true` is set.
- After:
  - All tables are dropped and recreated from current models.
  - All data is removed, including `raw_messages`.

## Suggested Order

1. Start API and ingest messages.
2. Run `run_phase2_extraction`.
3. Run `run_digest`.
4. Use `clear_all_but_raw_messages` when iterating derived logic.
5. Use `reset_dev_schema` only for full destructive resets.
