# Jobs README

This folder contains operational scripts you run as Python modules from the repo root.

## How to run

1. Open a shell in `C:\Users\ciara\civicquant-telegram`.
2. Ensure dependencies are installed: `pip install -r requirements.txt`.
3. Ensure your `.env` is configured.
4. Run jobs with `python -m app.jobs.<job_module>`.

## Jobs at a glance

| Job module | Command | What it does (1-liner) | Required env |
|---|---|---|---|
| `run_phase2_extraction` | `python -m app.jobs.run_phase2_extraction` | Runs one phase2 extraction batch and writes extraction, triage, and event updates to DB. | `PHASE2_EXTRACTION_ENABLED=true`, `OPENAI_API_KEY`, `DATABASE_URL` |
| `run_digest` | `python -m app.jobs.run_digest` | Builds/publishes the digest from current event data. | `DATABASE_URL` (and digest delivery vars if publishing) |
| `test_openai_extract` | `python -m app.jobs.test_openai_extract` | Smoke-tests the OpenAI extraction call and prints validated JSON output. | `PHASE2_EXTRACTION_ENABLED=true`, `OPENAI_API_KEY` |
| `inspect_pipeline` | `python -m app.jobs.inspect_pipeline` | Prints a recent end-to-end pipeline overview (raw -> extraction -> routing -> event). | `DATABASE_URL` |
| `clear_all_but_raw_messages` | `CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages` | Deletes all derived pipeline tables while preserving `raw_messages`. | `DATABASE_URL`, `CONFIRM_CLEAR_NON_RAW=true` |
| `reset_dev_schema` | `python -m app.jobs.reset_dev_schema` | Drops and recreates the full DB schema for a clean dev reset. | `DATABASE_URL` |
| `adopt_stability_contracts` | `python -m app.jobs.adopt_stability_contracts` | Backfills replay/identity hashes, audits duplicate event identities, and can optionally merge exact duplicates/apply unique indexes. | `DATABASE_URL` |

## Job-specific usage

### `inspect_pipeline`

Overview mode (latest rows):

```bash
python -m app.jobs.inspect_pipeline --limit 20
```

Detail mode (single raw message id):

```bash
python -m app.jobs.inspect_pipeline --detail 123
```

### `clear_all_but_raw_messages`

PowerShell:

```powershell
$env:CONFIRM_CLEAR_NON_RAW='true'; python -m app.jobs.clear_all_but_raw_messages
```

Bash:

```bash
CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages
```

### `reset_dev_schema`

```bash
python -m app.jobs.reset_dev_schema
```

Warning: this is destructive and currently executes without a runtime confirmation guard in code.

### `adopt_stability_contracts`

Audit/backfill only:

```bash
python -m app.jobs.adopt_stability_contracts
```

Dry-run (no writes committed):

```bash
python -m app.jobs.adopt_stability_contracts --dry-run
```

Merge exact duplicate identity groups and apply unique indexes after cleanup:

```bash
python -m app.jobs.adopt_stability_contracts --merge-exact --apply-unique-indexes
```

## Practical run order (local)

1. `python -m app.jobs.run_phase2_extraction`
2. `python -m app.jobs.inspect_pipeline --limit 20`
3. `python -m app.jobs.run_digest`

## Phase2 replay/content reuse knobs

- `PHASE2_FORCE_REPROCESS` (default `false`): force model call even when replay/content reuse candidates exist.
- `PHASE2_CONTENT_REUSE_ENABLED` (default `true`): allow cross-message canonical extraction reuse when normalized text + extractor contract match.
- `PHASE2_CONTENT_REUSE_WINDOW_HOURS` (default `6`): only reuse prior extractions created within this window (set `0` or negative to disable window bound).

## Troubleshooting

- If phase2 jobs fail immediately, confirm `PHASE2_EXTRACTION_ENABLED=true` and `OPENAI_API_KEY` are set.
- If DB-related jobs fail, confirm `DATABASE_URL` points to the expected database.
- If job imports fail, run from repo root (`C:\Users\ciara\civicquant-telegram`).
