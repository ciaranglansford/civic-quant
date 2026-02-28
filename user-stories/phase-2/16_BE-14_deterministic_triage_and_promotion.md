### Story BE-14 - Implement deterministic triage and promotion actions

* **Story ID**: BE-14
* **Title**: Compute deterministic triage actions from validated canonicalized extraction output
* **As a**: Backend engineer
* **I want**: A deterministic service that classifies messages/events into `archive`, `monitor`, `update`, or `promote`.
* **So that**: Stage 4 stabilization is owned by code, not model variability.

#### Preconditions

* Validated and canonicalized extraction payloads are available.
* Existing routing logic exists in `app/services/routing_engine.py`.

#### Acceptance Criteria

* A deterministic triage function exists in `app/services` (for example `triage_engine.py`) that:
  * Consumes canonicalized extraction and context.
  * Produces action classification and reason codes.
* Triage outputs are reproducible for identical inputs/configuration.
* Routing decision persistence includes triage action mapping and rule identifiers.
* Promotion decisions are explicitly rule-based and documented in `plans/` and `docs/02-flows/`.
* Tests cover:
  * low-signal archive case,
  * monitor case,
  * update case tied to existing event context,
  * promote case tied to high-significance/breaking conditions.

#### Out-of-scope

* ML-learned ranking models.
