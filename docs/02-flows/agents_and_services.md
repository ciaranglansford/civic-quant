## Agents and Services

### Purpose

Define responsibilities in a wire-bulletin intelligence pipeline and distinguish implemented vs target/future roles.

## Current Implementation Services

### Bulletin Ingest Service
- Responsibility: receive listener payloads and persist immutable raw observations idempotently.
- Inputs: Telegram bulletin payload.
- Outputs: `raw_messages` row + processing state.

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

### Event Manager Service
- Responsibility: cluster repetitive/incremental observations into evolving canonical events.
- Inputs: extraction + raw message id.
- Outputs: event create/update + link row.

### Reporting Service
- Responsibility: build scheduled event-level digest/report outputs.
- Inputs: queried event dataset.
- Outputs: published report text + publication audit record.

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
