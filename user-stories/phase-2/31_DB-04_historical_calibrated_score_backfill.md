### Story DB-04 - Add historical calibrated-score backfill workflow

* **Story ID**: DB-04
* **Status**: future
* **Title**: Provide controlled historical re-calibration workflow for previously processed rows
* **As a**: Backend engineer
* **I want**: A deterministic backfill job that recalculates calibrated impact metadata for historical extractions.
* **So that**: Historical analytics can be made consistent after scoring-rule upgrades.

#### Preconditions

* Deterministic calibration service is versioned.
* Backfill run boundaries and safety controls are documented.

#### Acceptance Criteria

* A backfill job supports bounded windows (for example by date range/topic) with dry-run mode.
* Existing raw payloads remain immutable.
* Backfill writes calibrated metadata with calibration-version provenance.
* Operations docs include rollback/replay guidance for backfill runs.

#### Out-of-scope

* Full historical replay of ingest/listener pipelines.
