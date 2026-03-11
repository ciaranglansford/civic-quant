# Feed API User Stories

## Story 1: Consume Latest Public Events
As a public frontend client,
I want to fetch a feed of canonical events,
So that users see backend-approved event summaries instead of raw ingest content.

### Acceptance Criteria
- `GET /api/feed/events` returns events sourced from `events` table.
- Each item includes `id`, `summary`, `topic`, `event_time`.
- Items with null/blank summaries are excluded.

## Story 2: Paginate Deterministically
As a frontend client,
I want cursor pagination,
So that I can load older events without duplicates or missing records.

### Acceptance Criteria
- `limit` defaults to `30` and supports values up to `100`.
- Response includes `next_cursor` when more rows exist, else `null`.
- Cursor is opaque and deterministic.
- Ordering is stable and cursor-safe across pages.

## Story 3: Filter By Topic
As a frontend client,
I want optional topic filtering,
So that I can show topic-specific event timelines.

### Acceptance Criteria
- Optional `topic` filter only accepts backend `Topic` values.
- Invalid topic values fail validation.
- Valid topic returns only matching feed items.

## Story 4: Reliable Time Semantics
As a frontend client,
I want timezone-explicit event timestamps,
So that date rendering is reliable across locales.

### Acceptance Criteria
- API outputs `event_time` in ISO-8601 UTC format with timezone (`Z`).
- Backend documents naive-datetime assumption and risks.

## Story 5: Keep Feed Logic In Backend
As a product team,
I want ordering/filtering/pagination rules centralized in backend,
So that frontend behavior is consistent and low-risk.

### Acceptance Criteria
- Backend owns summary filtering, ordering, and cursor predicates.
- Frontend only consumes response and cursor token.
