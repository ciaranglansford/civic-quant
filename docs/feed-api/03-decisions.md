# Feed API Key Decisions

## D1: Canonical Source Of Truth
- Decision: feed reads from `events` only.
- Why: `events` is the backend's canonical, deduplicated event layer; ingest/raw tables are pipeline internals.

## D2: Authoritative Ordering
- Decision: order by `event_time DESC, id DESC`.
- Why: deterministic, stable, and cursor-safe.
- Tie-break: `id DESC` guarantees stable ordering when multiple rows share `event_time`.

## D3: Cursor Strategy
- Decision: use opaque URL-safe base64 JSON cursor carrying `{v, event_time, id}`.
- Why: deterministic continuation boundary while hiding internal query details from clients.
- Cursor predicate: `(event_time < cursor_event_time) OR (event_time = cursor_event_time AND id < cursor_id)`.

## D4: Summary Quality Filter
- Decision: exclude rows with `summary_1_sentence` null or blank/whitespace.
- Why: frontend should not receive empty feed cards; quality and filtering stay backend-owned.

## D5: Topic Validation
- Decision: validate `topic` query param against backend `Topic` literal values in `app/schemas.py`.
- Why: single authoritative set avoids enum drift across layers.

## D6: Event Time Serialization
- Decision: emit `event_time` as ISO-8601 UTC string with timezone (`Z`).
- Why: explicit timezone removes ambiguity for public clients.
- Known risk: DB currently stores naive datetimes. API assumes naive values are UTC and normalizes to UTC-aware output.

## D7: Error Handling
- Decision: invalid cursor returns HTTP 400 with a clear `invalid cursor` detail.
- Why: malformed client continuation tokens are request errors, not server faults.
