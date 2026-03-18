## Schemas and Storage Model

### Purpose

Define the implemented storage contracts and semantics for the wire-bulletin pipeline.

## Semantic Contract (Extraction Fields)

- `confidence`: extraction/classification certainty, not factual truth.
- Raw `impact_score`: model-reported signal retained for traceability.
- Calibrated impact score: deterministic backend score used for triage/routing/event updates/enrichment selection.
- Extraction outputs represent reported claims, not confirmed facts.

## Extraction Schema (`ExtractionJson`)

- `topic`
- `entities` (`countries`, `orgs`, `people`, `tickers`)
- `affected_countries_first_order`
- `market_stats`
- `sentiment`
- `confidence` (`0..1`)
- `impact_score` (`0..100`)
- `is_breaking`
- `breaking_window` (`15m|1h|4h|none`)
- `event_time`
- `source_claimed`
- `summary_1_sentence`
- `keywords`
- `event_fingerprint`

## Persisted Extraction Contract (`extractions`)

Canonical fields:
- `extractor_name`, `schema_version`, `topic`, `event_time`
- `impact_score`, `confidence`, `sentiment`, `is_breaking`, `breaking_window`
- `event_fingerprint`, `event_identity_fingerprint_v2`
- `normalized_text_hash`, `replay_identity_key`
- `canonicalizer_version`, `canonical_payload_hash`, `claim_hash`

Traceability/ops fields:
- `model_name`, `prompt_version`, `processing_run_id`
- `llm_raw_response`, `validated_at`

JSON contracts:
- `payload_json`: strict validated extraction payload from provider output.
- `canonical_payload_json`: backend-canonicalized payload used downstream.
- `metadata_json`: provider telemetry, canonicalization rules, replay/content-reuse metadata, and `impact_scoring` breakdown.

## Identity Contracts

Replay identity (same raw message + same extraction contract):
- Inputs: `raw_message_id`, `normalized_text_hash`, `extractor_name`, `prompt_version`, `schema_version`, `canonicalizer_version`.
- Matching key allows reuse without re-calling the model unless force reprocess is set.

Event identity (cross-message clustering):
- Authoritative key: `event_identity_fingerprint_v2`.
- Comparison key: `claim_hash`.
- Conflict handling uses `action_class` and `event_time_bucket`.

## Routing / Triage Contract (`routing_decisions`)

- Core fields: `store_to`, `publish_priority`, `requires_evidence`, `event_action`, `flags`.
- Deterministic triage fields: `triage_action`, `triage_rules`.

## Enrichment Candidate Contract (`enrichment_candidates`)

- Purpose: persist deterministic enrichment candidate decisions without blocking phase2.
- Key fields: `event_id` (unique), `selected`, `triage_action`, `reason_codes`, `novelty_state`, `novelty_cluster_key`.
- Scoring fields: `calibrated_score`, `raw_llm_score`, `score_band`, `shock_flags`, `score_breakdown`.
- Timing fields: `scored_at`, `created_at`.

## Raw/Event/Entity/Reporting Contracts

Raw capture (`raw_messages`):
- immutable source-of-record
- idempotent unique key on `(source_channel_id, telegram_message_id)`

Events (`events`, `event_messages`):
- events are the downstream unit
- strict identity key: `events.event_identity_fingerprint_v2`
- conflict tracking: `claim_hash`, `action_class`, `event_time_bucket`, `review_required`, `review_reason`

Entity indexing (`entity_mentions`):
- normalized mentions keyed by `(raw_message_id, entity_type, entity_value)`
- supports topic/time/breaking query slices

Reporting (`digest_artifacts`, `published_posts`):
- canonical digest/report semantics live in `app/digest/*`
- artifact identity uses `input_hash` plus `canonical_hash`
- destination outcomes are tracked in `published_posts.status`

## Reprocessability

- Raw layer is preserved.
- Derived layers (`extractions`, `routing_decisions`, `events`, `event_messages`, `enrichment_candidates`, `entity_mentions`, publication/state tables) are recomputable.
- Existing data adoption tooling: `python -m app.jobs.adopt_stability_contracts`.

## Forward Extension Seams (Current)

- `app/contexts/enrichment/provider_contracts.py`: enrichment provider protocol contracts.
- `app/contexts/triage/opportunity_contracts.py`: opportunity scoring contracts.
- `app/digest/contracts.py`: thesis-card and periodic brief contracts colocated with canonical digest/report semantics.
