### Story BE-15 - Refine event clustering for repetitive and contradictory bulletins

* **Story ID**: BE-15
* **Title**: Handle paraphrase/repeat/contradictory observations with deterministic event update rules
* **As a**: Backend engineer
* **I want**: Event update logic that links repetitive bulletin observations to evolving event clusters safely.
* **So that**: Stage 5 clustering produces coherent event records for downstream reporting.

#### Preconditions

* Event upsert service exists (`app/services/event_manager.py`).
* Message-event links exist via `event_messages`.

#### Acceptance Criteria

* Event update policy is documented and implemented with deterministic field precedence rules.
* Repetitive/paraphrased bulletins with matching fingerprint/window attach to existing event clusters.
* Contradictory bulletins can update event summaries/flags while preserving linked observation history.
* Message-event linkage remains one link per `(event_id, raw_message_id)`.
* Tests cover:
  * paraphrase duplicate attach behavior,
  * incremental update behavior,
  * contradictory observation update behavior without raw history loss.

#### Out-of-scope

* Human editorial conflict resolution UI.
