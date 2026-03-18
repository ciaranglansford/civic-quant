## Contexts and Workflows

### Purpose

Define responsibilities in a wire-bulletin intelligence pipeline and distinguish implemented vs target/future roles.

Current ownership model:
- bounded contexts under `app/contexts/*`
- orchestration under `app/workflows/*`
- canonical digest/report semantics under `app/digest/*`

## Current Implementation Contexts

### Bulletin Ingest Service
- Responsibility: receive listener payloads and persist immutable raw observations idempotently.
- Inputs: source payloads mapped into a source-agnostic ingest envelope.
- Outputs: `raw_messages` row + processing state.
- Notes:
  - `POST /ingest/telegram` remains as a Telegram adapter endpoint.
  - `POST /ingest/source` accepts source-agnostic payloads for future adapters.

### Normalization Service
- Responsibility: deterministic preprocessing for extraction stability.
- Inputs: raw bulletin text.
- Outputs: normalized text.
- Note: normalization is preprocessing, not verification.

### Extraction Service (Phase2)
- Responsibility: convert normalized bulletin into structured reported-claim output.
- Inputs: normalized text, message time, source channel context.
- Outputs: validated extraction payload.
- Semantics:
  - captures reported claim,
  - preserves uncertainty/attribution,
  - does not assert truth.

### Routing / Triage Service
- Responsibility: deterministic ranking and actioning from structured extraction.
- Inputs: extraction payload.
- Outputs: routing decision (`store_to`, priority, flags, event action).
- Persistence ownership:
  - routing decision upsert is handled in a dedicated persistence module (`routing_decisions`).

### Event Manager Service
- Responsibility: cluster repetitive/incremental observations into evolving canonical events.
- Inputs: extraction + raw message id.
- Outputs: event create/update + link row.

### Reporting Service
- Responsibility: build scheduled digest outputs from event data using deterministic state logic plus optional LLM synthesis.
- Inputs: queried event dataset, digest synthesis settings.
- Outputs: canonical digest artifact + destination payload + publication audit record.
- Guardrails:
  - deterministic pre-dedupe runs before synthesis,
  - synthesis output is schema/semantic validated,
  - deterministic fallback is used when synthesis is disabled or invalid.

### Feed Query Context
- Responsibility: serve canonical event feed retrieval (`/api/feed/events`) with deterministic ordering and cursor semantics.
- Inputs: topic/filter/cursor query params.
- Outputs: `FeedEventsResponse`.

## Target-State Additions

### Deterministic Post-Processing Layer
- Canonicalize entities/sources/values before final triage.
- Reduce model variance and improve retrieval quality.

### Entity Indexing Layer
- Build query-optimized internal dataset for downstream retrieval APIs.

### Deferred Validation / Enrichment Layer
- Selective external corroboration for chosen events.
- Produces enriched event confidence/corroboration context.

## Future Optional Agents

### Evidence Enrichment Agent (Future)
- External source collection and corroboration scoring.

### Reporting Expansion Agent (Future)
- Additional report formats/channels beyond digest output.

