### Story BE-11 - Implement wire-bulletin structural normalization

* **Story ID**: BE-11
* **Title**: Normalize wire markers, datelines, and source suffixes deterministically
* **As a**: Backend engineer
* **I want**: A deterministic normalization layer for headline/ticker-style bulletins.
* **So that**: Stage 3 extraction receives stable `normalized_text` while preserving literal reported claim content.

#### Preconditions

* `raw_messages` ingest is already idempotent and immutable.
* A normalization function exists in `app/services/normalization.py`.

#### Acceptance Criteria

* A normalization service function in `app/services`:
  * Consumes `raw_text`.
  * Produces `normalized_text` with deterministic output for identical input.
* Normalization handles common wire-bulletin noise without changing claim meaning:
  * leading markers (`BREAKING`, `ALERT`, emoji siren markers, leading `*`),
  * dateline wrappers and separators,
  * duplicated punctuation and spacing artifacts,
  * source suffix boilerplate when pattern-safe.
* Normalization preserves attribution and uncertainty phrases (for example `SAYS`, `REPORTS`, `UNCONFIRMED`, `NEITHER ... CONFIRMED`).
* The ingest path persists normalized output in `raw_messages.normalized_text`.
* Unit tests cover:
  * repetitive marker cleanup,
  * dateline/source suffix normalization,
  * deterministic same-input same-output behavior,
  * preservation of claim text semantics.

#### Out-of-scope

* Truth validation or corroboration.
