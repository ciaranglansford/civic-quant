### Story BE-13 - Canonicalize extracted entities and sources deterministically

* **Story ID**: BE-13
* **Title**: Normalize country, organization, person, ticker, and source representations
* **As a**: Backend engineer
* **I want**: Deterministic canonicalization after schema validation.
* **So that**: Stage 4 triage and Stage 5 event clustering operate on stable structured values.

#### Preconditions

* Validated extraction payloads are available from Stage 3.
* Routing/event services consume structured extraction fields.

#### Acceptance Criteria

* A canonicalization service module exists in `app/services` (for example `canonicalization.py`) that:
  * Consumes validated extraction payload.
  * Produces canonicalized fields for entities and source labels.
* Canonicalization covers at minimum:
  * country alias normalization (for example `U.S.` -> `US`),
  * ticker normalization (uppercase, dedup, formatting cleanup),
  * organization/person spacing/case cleanup,
  * source label normalization where deterministic rules exist.
* Canonicalization is deterministic and side-effect free for same input.
* Phase2 processing integrates canonicalized payload before deterministic triage and event clustering.
* Unit tests cover:
  * alias handling,
  * dedup behavior,
  * deterministic output guarantee.

#### Out-of-scope

* LLM-based entity disambiguation.
