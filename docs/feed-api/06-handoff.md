# Feed API Handoff

## Delivered Endpoint
- `GET /api/feed/events`

## Query Parameters
- `limit` (optional): default `30`, max `100`, min `1`
- `cursor` (optional): opaque continuation token
- `topic` (optional): validated against backend `Topic` literal values

## Response
```json
{
  "items": [
    {
      "id": 1287,
      "summary": "US CPI rose 0.4% m/m in February.",
      "topic": "macro_econ",
      "event_time": "2026-03-01T20:28:48.000Z"
    }
  ],
  "next_cursor": "opaque-token-or-null"
}
```

## Backend Guarantees
- Source of truth is canonical `events` table.
- Rows with null/blank summaries are excluded.
- Topic filtering is backend-validated and enforced.
- Ordering is deterministic: `event_time DESC`, tie-break `id DESC`.
- Cursor pagination is deterministic and stable for that ordering.
- Cursor is opaque (URL-safe base64 payload) and validated server-side.
- Invalid cursor returns `400` with `invalid cursor`.

## Time Semantics
- API emits `event_time` as ISO-8601 UTC with timezone (`Z`).
- Current DB stores naive datetimes; API assumes naive values are UTC and normalizes before serialization.

## Files Added/Updated
- `app/routers/feed.py`
- `app/services/feed_query.py`
- `app/schemas.py`
- `app/main.py`
- `tests/test_feed_api.py`
- `docs/feed-api/01-plan.md`
- `docs/feed-api/02-user-stories.md`
- `docs/feed-api/03-decisions.md`
- `docs/feed-api/04-execution-log.md`
- `docs/feed-api/05-test-plan.md`
- `docs/feed-api/06-handoff.md`

## Operational Notes
- No schema migration required.
- No frontend logic required for dedupe/order/filter; frontend should only pass filters and cursor.

## Follow-Up Recommendations
1. Add API docs example in `docs/03-interfaces/API.md` for public consumers.
2. Consider signed cursors (HMAC) if tamper-evidence is desired.
3. Consider migrating DB datetime columns to timezone-aware types in PostgreSQL for stronger temporal guarantees.
