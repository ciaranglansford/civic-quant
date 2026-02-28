## Civicquant Execution Checklist (Transition-Focused)

Status legend:
- `implemented`: present and working in current repo
- `stabilize`: implemented but needs hardening/clarity
- `next`: near-term implementation target
- `later`: deferred/future work

### Semantic Safety Checks (Always-On)

- [stabilize] SEM-01 - Raw messages remain immutable source-of-record data.
- [stabilize] SEM-02 - Normalization is deterministic preprocessing, not verification.
- [stabilize] SEM-03 - Extraction captures literal reported claims, not truth adjudication.
- [stabilize] SEM-04 - `confidence` interpreted as extraction certainty only.
- [stabilize] SEM-05 - `impact_score` interpreted as face-value claim significance.
- [stabilize] SEM-06 - Reporting derives from event-level structured data, not raw text.

### Stage 1: Raw Ingest

- [implemented] ING-01 - Poll-based listener captures source bulletins and posts ingest payloads.
- [implemented] ING-02 - Ingest endpoint validates payload and writes idempotent raw records.
- [stabilize] ING-03 - Verify ingest observability fields for replay/debug workflows.

Run/verify:
- Run listener: `python -m listener.telegram_listener`
- Verify new rows in `raw_messages`
- Verify duplicate source/message IDs return `duplicate` behavior

### Stage 2: Structural Normalization

- [implemented] NOR-01 - Deterministic normalization step exists before extraction.
- [next] NOR-02 - Deepen wire-style normalization coverage (markers/datelines/attribution variants).
- [stabilize] NOR-03 - Keep normalization deterministic and auditable.

Run/verify:
- Trigger ingest with representative wire bulletins
- Inspect `raw_messages.normalized_text`

### Stage 3: AI Claim Extraction

- [implemented] EXT-01 - Phase2 extraction job runs OpenAI-backed extraction with strict schema validation.
- [stabilize] EXT-02 - Enforce claim-capture semantics and attribution/uncertainty preservation.
- [next] EXT-03 - Improve extraction quality checks on repetitive/contradictory bulletin patterns.

Run/verify:
- Run extraction batch: `python -m app.jobs.run_phase2_extraction`
- Probe extractor: `python -m app.jobs.test_openai_extract`
- Validate extraction rows (`extractor_name`, typed fields, payload/metadata JSON)

### Stage 4: Deterministic Post-Processing / Triage

- [implemented] TRI-01 - Deterministic routing logic persists triage outputs.
- [next] TRI-02 - Expand deterministic canonicalization and triage action categories.
- [later] TRI-03 - Add richer promotion logic for downstream reporting queues.

Run/verify:
- Inspect `routing_decisions` for deterministic outcomes
- Confirm repeated extraction inputs produce stable routing decisions

### Stage 5: Event Clustering

- [implemented] EVT-01 - Event upsert clusters observations by fingerprint + window logic.
- [stabilize] EVT-02 - Validate clustering behavior on repetitive/incremental/contradictory bulletins.
- [next] EVT-03 - Refine update heuristics for evolving event quality.

Run/verify:
- Inspect `events` and `event_messages`
- Confirm one evolving event can aggregate multiple bulletin observations

### Stage 6: Indexed Dataset Construction

- [implemented] IDX-01 - Typed extraction fields and indexes exist for core retrieval filters.
- [next] IDX-02 - Validate query patterns for topic/time/impact filters.
- [later] IDX-03 - Publish retrieval interface docs once retrieval endpoints exist.

Run/verify:
- Query extraction/event tables with topic + time range + score filters

### Stage 7: Deferred Enrichment Hooks

- [later] ENR-01 - Add selective enrichment trigger points for high-value events.
- [later] ENR-02 - Define corroboration/reliability persistence model.

Run/verify:
- N/A (deferred by design)

### Stage 8: Scheduled Reporting

- [implemented] REP-01 - Digest job generates event-level reports.
- [stabilize] REP-02 - Validate report quality against clustered event data freshness.
- [next] REP-03 - Add richer scheduled reporting variants once triage/promote tracks mature.

Run/verify:
- Run digest: `python -m app.jobs.run_digest`
- Verify output and `published_posts` row creation/dedup behavior

### Reprocessing Tasks

- [implemented] REPROC-01 - Preserve raw and clear derived artifacts:
  - `CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages`
- [implemented] REPROC-02 - Full dev reset path:
  - `CONFIRM_RESET_DEV_SCHEMA=true python -m app.jobs.reset_dev_schema`
- [stabilize] REPROC-03 - Document when to use partial clear vs full reset in runbooks.

### Test Execution Tasks

- [implemented] TEST-01 - Full suite: `pytest -q`
- [implemented] TEST-02 - Targeted extraction client tests: `pytest -q tests/test_extraction_llm_client.py`
- [implemented] TEST-03 - Targeted phase2/e2e tests: `pytest -q tests/test_e2e_backend.py`
- [next] TEST-04 - Add more deterministic normalization/triage test coverage

### Story Mapping (Phase 2 Backlog IDs)

- Stage 2 normalization: `BE-11`
- Stage 3 extraction semantics: `BE-12`
- Stage 4 canonicalization/triage: `BE-13`, `BE-14`
- Stage 5 event-cluster refinement: `BE-15`
- Stage 6 entity indexing: `DB-03`
- Stage 7 deferred enrichment hooks: `BE-16`
- Stage 8 reporting readiness: `BE-17`
- Stage 9 runbook support: `OPS-04`
