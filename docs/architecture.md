# Architecture

## Product-Centric Topology

This repository is implemented as a narrow Telegram group intelligence system with three distinct roles.

1. Ingestion listener
- code: `listener/telegram_listener.py`
- responsibility: source channel ingestion into backend `/ingest/*`
- non-responsibility: no user-command handling

2. Backend intelligence API
- code: `app/main.py`, `app/routers/query.py`, `app/services/query_service.py`, `app/services/summary_service.py`
- responsibility: retrieve/rank/dedupe events and produce grounded summaries
- non-responsibility: no Telegram chat UX formatting

3. Telegram command bot
- code: `bot/telegram_bot.py`
- responsibility: parse `/news` and `/summary`, call backend, format/send group replies
- non-responsibility: no business logic for ranking/summarization

## Runtime Components

| Component | Path | Command |
|---|---|---|
| API | `app/main.py` | `uvicorn app.main:app --reload` |
| Source listener | `listener/telegram_listener.py` | `python -m listener.telegram_listener` |
| Telegram command bot | `bot/telegram_bot.py` | `python -m bot.telegram_bot` |
| Phase2 extraction job | `app/jobs/run_phase2_extraction.py` | `python -m app.jobs.run_phase2_extraction` |

## Query Command Boundary

Supported user commands:
- `/news <topic> <1h|4h|24h>`
- `/summary <topic> <1h|4h|24h>`

No other command surfaces are part of this MVP boundary.

## Data and Logic Ownership

- Event extraction/scoring/triage/event upsert remains in backend contexts/workflows.
- Query matching, ranking, and dedupe are centralized in backend query services.
- Summary generation is centralized in backend summary service.
- Telegram message rendering is centralized in bot layer.

## Auth Boundary

- Backend `/api/query/*` routes require bearer token (`BOT_API_TOKEN`).
- Telegram bot uses `BACKEND_BOT_API_TOKEN` to call those routes.
- Shared token model is intentional for MVP simplicity.

## Domain Truth Model

- Events and summaries are representations of reported claims.
- They are not fact-verification outputs.
- Attribution and uncertainty language must be preserved.
