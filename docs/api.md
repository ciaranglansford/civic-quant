# API and Interfaces

## Core HTTP Routes

### `GET /health`
- Response: `{"status":"ok"}`

### `POST /ingest/telegram`
- Source listener ingestion endpoint.
- Writes `raw_messages` idempotently and creates pending processing state.

### `POST /ingest/source`
- Generic source-ingest endpoint used by source listener workflows.

## Query API (Telegram Group Commands)

These routes are the backend interface for the Telegram command bot.

Auth for both:
- `Authorization: Bearer <BOT_API_TOKEN>`
- Missing/invalid token returns `401`.

### `GET /api/query/news`

Query params:
- `topic` (required, non-empty)
- `window` (required, one of `1h|4h|24h`)

Validation:
- invalid topic/window returns `400`

Response shape:
- `topic`
- `window`
- `generated_at`
- `count`
- `results[]`:
  - `event_id`
  - `timestamp`
  - `source`
  - `claim`
  - `category`
  - `importance`
  - `score`
  - `evidence_refs`

### `GET /api/query/summary`

Query params:
- `topic` (required, non-empty)
- `window` (required, one of `1h|4h|24h`)

Validation:
- invalid topic/window returns `400`

Response shape:
- `topic`
- `window`
- `generated_at`
- `summary`:
  - `key_developments[]` (`text`, `evidence_refs`)
  - `uncertainties[]` (`text`, `evidence_refs`)
  - `why_it_matters[]` (`text`, `evidence_refs`)
- `source_count`

## Existing Admin and Feed Routes

### `GET /api/feed/events`
- Existing feed endpoint with cursor pagination.

### `POST /admin/process/phase2-extractions`
- Requires `x-admin-token` matching `PHASE2_ADMIN_TOKEN`.

### `GET /admin/query/events/by-tag`
### `GET /admin/query/events/by-relation`
- Require `x-admin-token` matching `PHASE2_ADMIN_TOKEN`.

### Theme admin endpoints (`/admin/theme/*`)
- Internal admin surface (existing behavior retained).
