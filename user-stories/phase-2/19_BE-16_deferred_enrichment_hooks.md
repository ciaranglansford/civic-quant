### Story BE-16 - Add deferred enrichment hooks for selective downstream validation

* **Story ID**: BE-16
* **Title**: Define deferred enrichment trigger hooks without coupling ingest/extraction hot path
* **As a**: Backend engineer
* **I want**: Deterministic selection hooks that mark which event clusters are candidates for later enrichment.
* **So that**: Stage 7 validation is selective and downstream, not mixed into Stage 1-5 processing.

#### Preconditions

* Deterministic triage and event clustering outputs are available.
* Event records carry fields needed for enrichment candidacy decisions.

#### Acceptance Criteria

* A hook interface exists in `app/services` (for example `enrichment_selection.py`) that:
  * Consumes event-level structured signals.
  * Produces enrichment-candidate decisions and reason codes.
* Enrichment hook execution does not block or alter ingest immutability guarantees.
* Hook decisions are persisted or logged in a way that can drive future enrichment jobs.
* Documentation in `docs/02-flows/` and `docs/04-operations/` marks enrichment as deferred and selective.
* Tests cover deterministic candidate selection for:
  * high-impact/breaking event cluster,
  * low-impact non-candidate event cluster.

#### Out-of-scope

* External source crawling or corroboration execution.
