# System Flow

## 1) Ingestion Flow (Source Listener)

1. `listener/telegram_listener.py` polls configured source channel.
2. Listener posts payloads to backend `/ingest/telegram`.
3. Backend stores `raw_messages` and `message_processing_states`.
4. Phase2 extraction job materializes extractions, routing decisions, and events.

Result:
- structured events/evidence become queryable by `/api/query/*`.

## 2) Query Flow (`/news`)

1. User sends `/news <topic> <window>` in Telegram group.
2. Bot parses and validates:
- topic non-empty
- window in `1h|4h|24h`
3. Bot calls backend `GET /api/query/news`.
4. Backend auth-checks bearer token.
5. Backend query service:
- normalizes topic
- applies time cutoff
- retrieves relevant event-layer data
- ranks and deduplicates
- returns structured results with evidence refs
6. Bot formats compact numbered output and posts to same group.

## 3) Summary Flow (`/summary`)

1. User sends `/summary <topic> <window>`.
2. Bot parses/validates and calls backend `GET /api/query/summary`.
3. Backend builds ranked evidence set via query service.
4. Summary service:
- uses LLM when configured and available
- otherwise deterministic fallback
- preserves evidence refs and uncertainty language
5. Bot formats key developments, uncertainties, and why-it-matters sections.

## Responsibility Boundaries

- Source listener: ingestion only.
- Backend: retrieval/ranking/dedupe/summarization authority.
- Telegram bot: command parsing, backend calls, response formatting only.
