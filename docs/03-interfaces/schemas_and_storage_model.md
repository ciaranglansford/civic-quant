## Schemas and Storage Model

### Purpose

Define structured claim schema and storage contracts for a Telegram wire-bulletin intelligence pipeline.

## Semantic Contract (Extraction Fields)

- `confidence`: confidence in extraction/classification quality.
- Raw `impact_score`: model-reported claim significance signal for traceability.
- Calibrated impact score: deterministic backend operational severity used for triage/routing/event impact/enrichment.
- Non-confirmation guarantee: extraction outputs represent reported claims, not verified truth.
- Stage 1 routing interpretation:
  - confidence/impact are bounded model signals for deterministic routing, not precise urgency truth.
  - deterministic score bands are used for triage/routing decisions while raw values are preserved.

### Extraction Schema (`ExtractionJson`)

- `topic`: enum
- `entities`: countries/orgs/people/tickers arrays
- `affected_countries_first_order`: string[]
- `market_stats`: list of labeled numeric facts
- `sentiment`: enum
- `confidence`: number [0..1]
- `impact_score`: number [0..100]
- `is_breaking`: boolean
- `breaking_window`: enum (`15m|1h|4h|none`)
- `event_time`: datetime|null
- `source_claimed`: string|null
- `summary_1_sentence`: string
- `keywords`: string[]
- `event_fingerprint`: deterministic string

### Persisted Extraction Contract (`extractions`)

#### Purpose
- Store structured reported-claim output with retrieval-optimized typed fields plus full payload.

#### Canonical fields
- `extractor_name` (canonical identity)
- `schema_version`
- `topic`
- `event_time`
- `impact_score`
- `confidence`
- `sentiment`
- `is_breaking`
- `breaking_window`
- `event_fingerprint`
- `event_identity_fingerprint_v2`
- `normalized_text_hash`
- `replay_identity_key`
- `canonical_payload_hash`
- `claim_hash`
- `canonicalizer_version`

#### Compatibility / traceability fields
- `model_name` (legacy compatibility)
- `prompt_version`
- `processing_run_id`
- `llm_raw_response`
- `validated_at`

#### JSON payloads
- `payload_json`: raw validated extraction object produced from strict schema validation.
- `canonical_payload_json`: deterministic canonicalized extraction payload used for triage, clustering, and indexing.
  - may include Stage 1 safety rewrite adjustments to `summary_1_sentence` for high-risk unattributed phrasing.
  - does not overwrite or mutate `payload_json`.
- `metadata_json`: provider telemetry and processing context (`used_openai`, model, response id, latency, retries, fallback reason, canonicalization rules).
  - Includes `impact_scoring` metadata: `raw_llm_score`, `calibrated_score`, `score_band`, `shock_flags`, `rules_fired`, `score_breakdown`.
  - `score_breakdown` is deterministic and reproducible from backend rule logic + structured extraction fields (no ad hoc model inference).
  - Includes replay/identity metadata: `normalized_text_hash`, `replay_identity_key`, `canonical_payload_hash`, `claim_hash`, `action_class`, `event_time_bucket`, `canonicalizer_version`.
  - Includes reuse telemetry: `replay_reused`, `content_reused`, `content_reuse_source_extraction_id`, `canonical_payload_unchanged`.

### Replay Identity Contract (Level A)

- Purpose: detect when the same raw message is being reprocessed under the same extraction contract.
- Replay identity key inputs:
  - `raw_message_id`
  - `normalized_text_hash`
  - `extractor_name`
  - `prompt_version`
  - `schema_version`
  - `canonicalizer_version`
- Default behavior:
  - If replay identity key matches and force-reprocess is not requested, reuse existing canonical extraction row and skip model call.
  - If replay identity does not match but normalized text hash + extractor contract match a prior extraction, reuse that canonical extraction (content reuse) and skip model call.
  - If extractor/prompt/schema/canonicalizer versions change (or force-reprocess is set), model call is allowed.

### Event Identity Contract (Level B)

- Purpose: cluster extractions from different raw messages into canonical events.
- Authoritative key: `event_identity_fingerprint_v2`.
- Additional comparison key: `claim_hash`.
- Update policy:
  - same `event_identity_fingerprint_v2` + same `claim_hash` -> no-op event update
  - same `event_identity_fingerprint_v2` + different `claim_hash` -> controlled update or review-required conflict path depending on action/time conflict

### Routing / Triage Contract (`routing_decisions`)

- Core routing fields:
  - `store_to`
  - `publish_priority`
  - `requires_evidence`
  - `event_action`
  - `flags`
- Deterministic triage fields:
  - `triage_action` (`archive|monitor|update|promote`)
  - `triage_rules` (list of deterministic rule identifiers)
    - includes score-band rules, related-update/repeat downgrade rules, burst-cap rules, and local incident overrides when fired.


### Deferred Enrichment Candidate Contract (`enrichment_candidates`)

- Purpose:
  - Persist deterministic candidate decisions for downstream enrichment without blocking phase2.
- Key fields:
  - `event_id` (unique per event for idempotent candidate state)
  - `selected` (boolean)
  - `triage_action`
  - `reason_codes` (deterministic rule identifiers)
  - 
ovelty_state`
  - 
ovelty_cluster_key`
  - `calibrated_score`
  - `raw_llm_score`
  - `score_band`
  - `shock_flags`
  - `score_breakdown`
  - `scored_at`, `created_at`
- Novelty behavior:
  - Candidate selection prefers deterministic/low-variance duplicate suppression heuristics (event lineage, duplicate markers, cluster key, title/entity overlap) before future semantic similarity refinements.
### Raw Capture Contract (aw_messages)

- Immutable source-of-record data.
- Idempotency via unique `(source_channel_id, telegram_message_id)`.
- No truth validation at ingest stage.

### Event Contract (`events`, `event_messages`)

- Messages are observations.
- Events are evolving clusters of related observations.
- Event-level records are the primary downstream indexing/reporting unit.
- `events.event_identity_fingerprint_v2` is the strict event identity key for hard-match upsert behavior.
- `events.claim_hash`, `events.action_class`, and `events.event_time_bucket` support deterministic conflict handling.
- `events.review_required/review_reason` flag cases where same identity receives materially conflicting claim updates.

### Entity Indexing Contract (`entity_mentions`)

- Normalized entity links to message/event context:
  - `entity_type` (`country|org|person|ticker`)
  - `entity_value`
  - `raw_message_id`
  - `event_id` (nullable)
  - `topic`
  - `is_breaking`
  - `event_time`
- Canonical country values use full Title Case names (for example `United States`, `United Kingdom`).

### Reporting Contract (`published_posts`)

- Reports are generated from structured event data via canonical digest composition.
- Publication records are persisted for auditability and destination rerun behavior.
- Digest artifact identity now has two hashes:
  - `digest_artifacts.input_hash` (stable source-input identity)
  - `digest_artifacts.canonical_hash` (rendered canonical text hash)
- `published_posts` rows reference `artifact_id` and capture destination status transitions (`published`, `failed`, `deferred`).

### Reprocessability Contract

- Raw layer (`raw_messages`) should be preserved as immutable source history.
- Derived layers (`extractions`, `routing_decisions`, `events`, `event_messages`, `published_posts`, processing states) are recomputable from raw inputs.
- Operational scripts support both preserve-raw and full-reset workflows.
- Existing-data adoption workflow:
  - run `python -m app.jobs.adopt_stability_contracts` to backfill replay/identity hashes and audit duplicates
  - optionally merge exact duplicate identity groups with `--merge-exact`
  - optionally apply unique indexes with `--apply-unique-indexes` after duplicate cleanup

### Indexing Summary (Retrieval-Oriented)

- `extractions(topic, event_time)`
- `extractions(topic, event_time, impact_score)`
- `extractions(event_fingerprint)`
- `extractions(normalized_text_hash, extractor_name, prompt_version, schema_version, canonicalizer_version, created_at)`
- `entity_mentions(entity_type, entity_value, event_time)`
- `entity_mentions(topic, event_time)`
- `entity_mentions(is_breaking, event_time)`
- `events(event_fingerprint)`
- `events(event_time)`
- `raw_messages(message_timestamp_utc)`

### Deferred Validation Status

External corroboration/validation is a later selective stage and is not part of the current ingest API contract.


