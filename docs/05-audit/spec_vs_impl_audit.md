# Spec vs Implementation Audit

## Purpose

Track documentation consistency against current runtime behavior and the refined target-state wire-bulletin architecture.

## Wire-Bulletin Semantics Compliance

### Required semantics
1. Raw messages are immutable source-of-record observations.
2. Normalization is deterministic preprocessing, not truth validation.
3. Extraction captures literal reported claims.
4. `confidence` is extraction certainty, not factual certainty.
5. `impact_score` is face-value significance of reported claim.
6. Deterministic post-processing/triage is required.
7. Event-level records are downstream indexing/reporting unit.
8. External validation is deferred and selective.
9. Reporting consumes structured event data, not raw bulletin text.

### Current documentation status
- README and architecture/flow/interface docs explicitly describe wire-bulletin claim semantics.
- Current implementation vs target state vs future optional distinctions are explicit in major architecture and flow docs.
- Listener mode is documented as poll-based.

## Current Implementation Verification Snapshot

- Ingest is idempotent and persists immutable raw rows.
- Phase2 extraction is OpenAI-backed with strict schema validation.
- Routing and event clustering run deterministically from structured extraction.
- Digest/reporting runs from event-level records.

## Execution Documentation Coverage Audit

### Coverage checks
- Runtime component execution guidance exists for:
  - backend API
  - listener
  - phase2 extraction job
  - digest/report job
  - dev reset/reprocess scripts
- Stage ownership is documented in flow + deployment + operations docs.
- Command coverage includes setup, run, targeted tests, and reprocessing.

### Validation summary
- New engineer can follow README + operations docs to run and verify the local pipeline.
- Stage-to-command mapping is explicit.
- Raw-vs-derived reprocessing boundaries are documented.

## Remaining Divergences / TODO (Docs-Level)

1. Deterministic post-processing/canonicalization depth is partially implemented and should be expanded in future revisions.
2. Entity-indexing dataset layer is represented in architecture intent; dedicated retrieval API docs should be added when endpoints are implemented.
3. Deferred external validation/enrichment remains future workflow and should be documented with operational runbooks once implemented.

## Out-of-Scope Notes

This audit pass is documentation-only and does not claim new code features beyond current implementation.
