# Feed API Plan (`GET /api/feed/events`)

## Objective
Ship a production-ready public feed endpoint backed by canonical `events` records, with deterministic cursor pagination, topic filtering, and stable backend-owned ordering/filtering behavior.

## Scope
- Add a new endpoint: `GET /api/feed/events`
- Query params:
  - `limit` (optional, default `30`, max `100`)
  - `cursor` (optional, opaque string)
  - `topic` (optional, validated against backend `Topic` values)
- Response shape:
  - `items`: array of feed event DTOs (`id`, `summary`, `topic`, `event_time`)
  - `next_cursor`: opaque cursor or `null`

## Non-Goals
- Frontend-side sorting, filtering, deduplication, or pagination logic.
- Changes to ingestion/extraction/event-creation pipelines.
- Schema migrations unless strictly necessary (none expected).

## Delivery Plan
1. Repository inspection
1. Confirm router wiring (`app/main.py`) and conventions in existing routers.
2. Confirm canonical data model and topic type source (`app/models.py`, `app/schemas.py`).

2. API design + implementation
1. Add feed response DTOs to `app/schemas.py`.
2. Add feed query service (`app/services/feed_query.py`) for:
   - deterministic ordering
   - summary filtering
   - topic filtering
   - opaque cursor encode/decode
3. Add feed router (`app/routers/feed.py`) and wire in `app/main.py`.

3. Testing
1. Add endpoint-level tests in `tests/test_feed_api.py` for:
   - response shape
   - ordering stability
   - cursor pagination correctness
   - topic validation/filtering
   - null/empty summary filtering

4. Validation + handoff
1. Run tests and capture exact outcomes.
2. Document execution log, test plan, and handoff details.

## Risks And Mitigations
- Naive DB timestamps:
  - Mitigation: emit API timestamps as explicit UTC ISO-8601 (`...Z`) by normalizing to UTC in API layer.
- Cursor tampering:
  - Mitigation: strict decode validation and HTTP 400 on malformed/unsupported cursors.
- Ordering drift:
  - Mitigation: explicit deterministic order (`event_time DESC`, tie-break `id DESC`) and cursor predicate that matches this sort order.
