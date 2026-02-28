## Schemas and Storage Model

### Purpose

Define structured claim schema and storage contracts for a Telegram wire-bulletin intelligence pipeline.

## Semantic Contract (Extraction Fields)

- `confidence`: confidence in extraction/classification quality.
- `impact_score`: significance of the reported claim if taken at face value.
- Non-confirmation guarantee: extraction outputs represent reported claims, not verified truth.

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

#### Compatibility / traceability fields
- `model_name` (legacy compatibility)
- `prompt_version`
- `processing_run_id`
- `llm_raw_response`
- `validated_at`

#### JSON payloads
- `payload_json`: full validated extraction object for forward compatibility.
- `metadata_json`: provider telemetry and fallback context (`used_openai`, model, response id, latency, retries, fallback reason).

### Raw Capture Contract (`raw_messages`)

- Immutable source-of-record data.
- Idempotency via unique `(source_channel_id, telegram_message_id)`.
- No truth validation at ingest stage.

### Event Contract (`events`, `event_messages`)

- Messages are observations.
- Events are evolving clusters of related observations.
- Event-level records are the primary downstream indexing/reporting unit.

### Reporting Contract (`published_posts`)

- Reports are generated from structured event data.
- Publication records are persisted for auditability and dedup behavior.

### Reprocessability Contract

- Raw layer (`raw_messages`) should be preserved as immutable source history.
- Derived layers (`extractions`, `routing_decisions`, `events`, `event_messages`, `published_posts`, processing states) are recomputable from raw inputs.
- Operational scripts support both preserve-raw and full-reset workflows.

### Indexing Summary (Retrieval-Oriented)

- `extractions(topic, event_time)`
- `extractions(topic, event_time, impact_score)`
- `extractions(event_fingerprint)`
- `events(event_fingerprint)`
- `events(event_time)`
- `raw_messages(message_timestamp_utc)`

### Deferred Validation Status

External corroboration/validation is a later selective stage and is not part of the current ingest API contract.
