## Civicquant Transition Roadmap (Current -> Target State)

### Purpose

Define an execution-oriented roadmap that moves the current codebase toward the refined wire-bulletin target-state pipeline.

### System Context

Civicquant processes Telegram headline/ticker-style bulletins that are often short, urgent, repetitive, source-attributed, and occasionally contradictory. Inputs represent reported claims and should not be treated as confirmed truth at ingest or extraction stages.

## Current Implemented Baseline

- Poll-based listener ingests bulletins via `POST /ingest/telegram`.
- Raw bulletins are persisted idempotently in `raw_messages`.
- Deterministic normalization exists and currently focuses on whitespace stabilization.
- Phase2 extraction runs by job/admin trigger and uses strict schema validation.
- Routing and event upsert produce event clusters and links.
- Scheduled digest reporting consumes event-level data.

## Target-State Work Tracks

### Track 1: Ingestion Hardening
- Goal: make raw capture more resilient, auditable, and replay-safe.
- Why: ingest integrity underpins every downstream stage.
- Dependencies: listener reliability, idempotency constraints.
- Expected output: complete immutable raw bulletin archive with deterministic identities.
- Downstream impact: enables safe reprocessing and event reconstruction.

### Track 2: Structural Normalization Deepening
- Goal: normalize wire-style markers and formatting variance deterministically.
- Why: reduces extraction drift from formatting noise.
- Dependencies: stable raw ingest and deterministic normalization contract.
- Expected output: stable normalized representation preserving claim content.
- Downstream impact: higher extraction consistency and cleaner clustering inputs.

### Track 3: Extraction Semantics Upgrade (Claim Capture Integrity)
- Goal: ensure extraction captures literal reported claims with attribution/uncertainty.
- Why: avoid implicit truth-adjudication in early stages.
- Dependencies: prompt contract and strict validation.
- Expected output: schema-valid claim-structured records with semantic guardrails.
- Downstream impact: improves triage reliability and analyst trust.

### Track 4: Deterministic Post-Processing / Canonicalization
- Goal: stabilize model outputs via deterministic code.
- Why: AI output variance must be normalized before actioning.
- Dependencies: validated extraction payloads.
- Expected output: canonicalized entities/fields suitable for deterministic triage.
- Downstream impact: consistent routing and event clustering decisions.

### Track 5: Triage and Promotion Logic
- Goal: classify outputs into deterministic operational actions.
- Why: separate high-signal observations from low-signal noise.
- Dependencies: canonicalized extraction outputs and routing rules.
- Expected output: deterministic actioning (`archive`, `monitor`, `update`, `promote`).
- Downstream impact: controlled reporting workload and better event quality.

### Track 6: Event Clustering Refinement
- Goal: improve evolving-story clustering for repetitive/incremental/contradictory bulletins.
- Why: event-level records are the correct downstream reasoning/reporting unit.
- Dependencies: stable fingerprints + triage outputs.
- Expected output: cleaner event lifecycle updates and message-event linking.
- Downstream impact: improved reporting coherence and retrieval quality.

### Track 7: Entity Indexing Readiness
- Goal: support queryable datasets by topic/ticker/country/breaking/time.
- Why: retrieval APIs and analytics require typed/indexed structures.
- Dependencies: extraction typed fields and event clustering quality.
- Expected output: retrieval-ready indexed dataset layer.
- Downstream impact: powers internal query/report tooling.

### Track 8: Deferred Enrichment Hooks
- Goal: add integration points for selective external validation.
- Why: verification should be separate from raw capture and first-pass extraction.
- Dependencies: event triage outputs to decide which events are worth enrichment.
- Expected output: optional enrichment pipeline hooks with no ingest-path coupling.
- Downstream impact: improves confidence/corroboration for selected events.

### Track 9: Scheduled Reporting Readiness
- Goal: keep reporting grounded in structured event-level data.
- Why: reports should not be generated from raw noisy bulletin text.
- Dependencies: event clustering and retrieval-ready dataset freshness.
- Expected output: reliable scheduled digest/report generation with traceability.
- Downstream impact: safer external/internal communication outputs.

## Dependency Chain (Execution Order)

| Phase | Depends On | Enables |
|---|---|---|
| Ingestion Hardening | baseline runtime | normalization deepening, safe replay |
| Structural Normalization | raw ingest integrity | extraction semantics upgrade |
| Extraction Semantics Upgrade | normalization + schema contract | deterministic post-processing |
| Deterministic Post-Processing | validated extraction | triage/promotion logic |
| Triage and Promotion | canonicalized extraction | event clustering refinement |
| Event Clustering Refinement | triage outputs + fingerprints | indexed dataset quality |
| Entity Indexing Readiness | stable event/extraction outputs | retrieval/reporting quality |
| Deferred Enrichment Hooks | event triage | selective validation workflows |
| Scheduled Reporting Readiness | event clustering + indexed dataset | reliable event-level reporting |

## Deferred / Future Tracks

- External evidence aggregation and reliability scoring workflows.
- Additional distribution channels and report formats.
- Dedicated retrieval APIs on top of indexed dataset.

## Exit Criteria by Stage

1. Raw ingest stage: immutable idempotent capture is complete and replay-safe.
2. Normalization stage: deterministic transformations are documented and stable.
3. Extraction stage: claim semantics preserved; validation failures are explicit.
4. Post-processing/triage stage: deterministic actioning is reproducible.
5. Event stage: repetitive/contradictory observations converge to coherent event records.
6. Indexing stage: dataset supports topic/ticker/country/breaking/time filters.
7. Enrichment stage: optional hooks exist without coupling ingest path.
8. Reporting stage: scheduled outputs are event-level, traceable, and operationally stable.
