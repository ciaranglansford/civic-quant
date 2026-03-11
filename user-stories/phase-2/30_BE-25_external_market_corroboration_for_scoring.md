### Story BE-25 - Add external market corroboration signals for impact-confidence refinement

* **Story ID**: BE-25
* **Status**: future
* **Title**: Add selective external corroboration signals to enrich impact-confidence evaluation
* **As a**: Backend engineer
* **I want**: A deferred enrichment workflow that can fetch corroboration from trusted market/news sources for selected events.
* **So that**: High-impact decisions can be reviewed with external signal context without polluting the extraction hot path.

#### Preconditions

* BE-16 enrichment candidates are persisted deterministically.
* Operational guardrails for source allow-list and rate limits are defined.

#### Acceptance Criteria

* A corroboration service consumes `enrichment_candidates` and adds source evidence records for selected events.
* Corroboration execution remains asynchronous/deferred and never blocks ingest/phase2.
* Source trust tiering and fetch failures are persisted as explicit metadata.
* Runbook documents source allow-list, retries, and failure handling.

#### Out-of-scope

* Fully automated trading actioning from corroboration output.
