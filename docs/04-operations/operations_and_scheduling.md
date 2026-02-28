## Operations and Scheduling

### Purpose

Primary local runbook for executing the wire-bulletin pipeline end-to-end and validating stage outputs.

## Runtime Components

- Backend API: `uvicorn app.main:app`
- Listener (capture): `python -m listener.telegram_listener`
- Phase2 extraction: `python -m app.jobs.run_phase2_extraction`
- Reporting digest: `python -m app.jobs.run_digest`

## Developer Run Sequence (Local)

1. Environment + dependencies
- Ensure Python environment is active.
- Install dependencies:
  - `pip install -r requirements.txt`
- Configure `.env` for DB, listener, phase2 extraction, and digest publishing as needed.

2. Start backend (Stages 1-2 entrypoint)
- Command:
  - `uvicorn app.main:app --reload`
- Expected outputs:
  - API responds on `/health`
  - DB tables available

3. Start listener (optional; Stage 1 capture source)
- Command:
  - `python -m listener.telegram_listener`
- Expected outputs:
  - Poll loop logs
  - New ingest payload posts
  - New `raw_messages` rows

4. Run extraction batch (Stages 3-5)
- Command:
  - `python -m app.jobs.run_phase2_extraction`
- Expected outputs:
  - extractor selection log
  - processing summary log
  - updates in `extractions`, `routing_decisions`, `events`, `event_messages`

5. Run digest/report (Stage 8)
- Command:
  - `python -m app.jobs.run_digest`
- Expected outputs:
  - digest publish/skip logs
  - `published_posts` updates

6. Validation checks
- Verify stage outputs in DB:
  - Stage 1: `raw_messages`
  - Stage 3: `extractions`
  - Stage 4: `routing_decisions`
  - Stage 5: `events`, `event_messages`
  - Stage 8: `published_posts`

## When to Run What

- Run listener when validating capture behavior against live/burst bulletin feeds.
- Run phase2 extraction when validating claim extraction, deterministic triage, and event clustering.
- Run digest when validating event-level reporting outputs.

## Data Lifecycle + Reprocess Safety

- Raw data (`raw_messages`) is immutable source-of-record.
- Derived data (`extractions`, `routing_decisions`, `events`, `event_messages`, `published_posts`, processing state) is reprocessable.

### Reprocess Commands

- Preserve raw, clear derived:
  - `CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages`
- Full dev schema reset (destructive):
  - `CONFIRM_RESET_DEV_SCHEMA=true python -m app.jobs.reset_dev_schema`

Use preserve-raw reprocess for prompt/routing/event-logic iteration. Use full reset for schema-level resets.

## Scheduling

### Phase2 Extraction Cadence
- Recommended: every 10 minutes
- Example:
  - `*/10 * * * * python -m app.jobs.run_phase2_extraction`

### Digest Reporting Cadence
- Recommended: every 4 hours (or `VIP_DIGEST_HOURS`)
- Example:
  - `0 */4 * * * python -m app.jobs.run_digest`

## Targeted Test Commands

- Full suite:
  - `pytest -q`
- Extraction client tests:
  - `pytest -q tests/test_extraction_llm_client.py`
- Pipeline/e2e tests:
  - `pytest -q tests/test_e2e_backend.py`

## Expected Extraction Logs and Side Effects

### Key logs
- `phase2_config phase2_extraction_enabled=<bool> openai_api_key_present=<bool> openai_model=<value>`
- `Using extractor: extract-and-score-openai-v1`
- `phase2_run_done ... selected=<n> processed=<n> completed=<n> failed=<n> skipped=<n>`

### Key DB side effects
- `extractions`: typed extraction fields + `payload_json` + `metadata_json`
- `routing_decisions`: deterministic triage output
- `events`/`event_messages`: event cluster updates

## Troubleshooting: Repetitive or Contradictory Bulletins

- Repetition is expected in wire feeds; validate event clustering behavior, not one-message-one-event assumptions.
- Contradictory bulletins should appear as additional observations and may update existing event clusters.
- Inspect progression across `raw_messages` -> `extractions` -> `events/event_messages`.

## Troubleshooting: OpenAI Extraction Not Being Used

1. Confirm extraction job logs show `extract-and-score-openai-v1`.
2. Confirm phase2 env values (`PHASE2_EXTRACTION_ENABLED`, API key presence).
3. Inspect latest `extractions` rows for `extractor_name`, `payload_json`, and `metadata_json`.
