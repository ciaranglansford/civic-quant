### Story DB-03 - Build entity indexing dataset layer for retrieval-ready queries

* **Story ID**: DB-03
* **Title**: Create queryable entity indexing links for countries, organizations, people, and tickers
* **As a**: Backend engineer
* **I want**: A dataset layer linking entities to messages and events with time/topic/breaking context.
* **So that**: Stage 6 supports retrieval by country/ticker/topic/breaking relevance/time window.

#### Preconditions

* Validated extraction rows persist canonicalized entities.
* Event clusters and message-event link tables exist.

#### Acceptance Criteria

* A persistence model/table set exists for entity indexing (for example `entity_mentions` and/or link tables) with:
  * normalized entity type/value,
  * references to `raw_message_id` and/or `event_id`,
  * timestamps for query windows.
* Indexes support retrieval filters by:
  * entity value/type,
  * topic,
  * breaking relevance,
  * time range.
* Entity indexing population happens deterministically in phase2 processing flow.
* Query helpers exist in `app/services` for retrieval-ready filters.
* Tests cover:
  * country/ticker/org/person indexing inserts,
  * dedup/idempotent reprocessing behavior,
  * basic time-window query correctness.

#### Out-of-scope

* Public retrieval API endpoint implementation.
