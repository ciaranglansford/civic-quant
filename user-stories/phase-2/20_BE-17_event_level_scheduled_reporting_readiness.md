### Story BE-17 - Ensure scheduled reporting readiness from event-level structured data

* **Story ID**: BE-17
* **Title**: Gate reporting generation on event-level structured readiness checks
* **As a**: Backend engineer
* **I want**: Reporting jobs to consume event-level structured data with freshness/completeness checks.
* **So that**: Stage 8 reporting stays aligned with structured event clusters, not raw bulletin text.

#### Preconditions

* Digest/report job exists (`app/jobs/run_digest.py`, `app/services/digest_runner.py`).
* Event clusters and extraction outputs are persisted.

#### Acceptance Criteria

* Reporting path consumes event-level records and does not directly render from `raw_messages.raw_text`.
* A readiness check exists in reporting query/build flow that validates:
  * recent event freshness window,
  * minimum required event fields for report rendering.
* Reporting skips or degrades gracefully when readiness criteria are not met, with explicit logs.
* Ops/docs describe reporting readiness expectations and troubleshooting.
* Tests cover:
  * ready dataset report generation,
  * stale/incomplete dataset skip or reduced-output behavior.

#### Out-of-scope

* Additional public publishing channels beyond current digest flow.
