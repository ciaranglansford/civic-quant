# Feed API Test Plan

## Current Status (2026-03-18)

This document is a historical feed-api planning/execution artifact.
Some module paths and ownership references may be stale after the context-first
refactor (`app/contexts/*`, `app/workflows/*`, `app/digest/*`).

For implementation-truth references, use:
- `docs/01-overview/ARCHITECTURE.md`
- `docs/02-flows/DATA_FLOW.md`
- `docs/05-audit/refactor_audit_2026-03-18.md`

## Objective
Validate that `GET /api/feed/events` is deterministic, cursor-safe, schema-correct, and backend-authoritative for ordering/filtering.

## Test Scope
- Endpoint contract and response shape
- Limit and cursor pagination behavior
- Stable ordering guarantees
- Topic filter behavior and validation
- Summary quality filtering (null/blank exclusion)
- Cursor validation and error behavior

## Test Cases
1. Response shape and required fields
- Assert top-level response contains `items` and `next_cursor`.
- Assert each item has `id`, `summary`, `topic`, `event_time`.

2. Summary filtering
- Insert events with valid summary, blank summary, and null summary.
- Assert only valid summary rows are returned.

3. Pagination correctness
- Insert a deterministic event sequence.
- Request `limit=2` and assert:
  - first page contents are correct,
  - `next_cursor` is returned,
  - second page returns remaining rows,
  - no overlaps/gaps across pages.

4. Cursor determinism
- Repeat first-page request with same params.
- Assert item order and `next_cursor` are stable.

5. Ordering stability
- Insert two rows with same `event_time` and different IDs plus an older row.
- Assert ordering is `event_time DESC, id DESC`.

6. Topic filter and validation
- Assert valid topic filter returns only matching rows.
- Assert invalid topic yields FastAPI validation error (`422`).

7. Invalid cursor handling
- Pass malformed cursor.
- Assert HTTP `400` with `invalid cursor` detail.

## Commands
- Targeted feed tests:
  - `pytest -q tests/test_feed_api.py`
- Full regression suite:
  - `pytest -q`

## Results (2026-03-11)
- `pytest -q tests/test_feed_api.py`
  - `5 passed, 1 warning in 1.02s`
- `pytest -q`
  - `32 passed, 1 warning in 1.48s`

## Known Warning
- `PendingDeprecationWarning` from `starlette.formparsers` about `python_multipart` import path; unrelated to feed API logic.
