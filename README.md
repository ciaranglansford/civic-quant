# Civicquant Telegram Group Intelligence

Civicquant is a Telegram-group intelligence system with a narrow product scope:

- `/news <topic> <1h|4h|24h>` returns ranked, deduplicated, evidence-aware updates.
- `/summary <topic> <1h|4h|24h>` returns a grounded summary of those same updates.

It is not a general chatbot or generic adapter platform.  
Events and summaries represent reported claims, not confirmed facts.

## Product Boundary

Primary user workflow:
- user asks in a Telegram group: `/news iran 4h` or `/summary iran 4h`
- bot calls backend query API
- backend returns structured, traceable output
- bot formats and posts response in the same group

Only supported windows:
- `1h`
- `4h`
- `24h`

## System Roles

1. Ingestion listener (`listener/telegram_listener.py`)
- polls a source Telegram channel
- forwards source messages into backend ingest endpoints
- does not serve user commands

2. Backend intelligence API (`app/main.py` + query services)
- stores and processes source messages through extraction/event pipelines
- serves `/api/query/news` and `/api/query/summary` for bot consumption
- owns ranking, dedupe, and summarization behavior

3. Telegram command bot (`bot/telegram_bot.py`)
- runs in Telegram groups
- parses `/news` and `/summary`
- validates syntax and window values
- calls backend with bearer auth
- formats compact group-readable responses

## API Surface

New query endpoints:
- `GET /api/query/news?topic=<topic>&window=<1h|4h|24h>`
- `GET /api/query/summary?topic=<topic>&window=<1h|4h|24h>`

Authentication:
- backend expects `Authorization: Bearer <BOT_API_TOKEN>` on `/api/query/*`
- bot sends `BACKEND_BOT_API_TOKEN` as bearer token

## Environment Variables

Backend:
- `DATABASE_URL`
- `BOT_API_TOKEN`
- `OPENAI_API_KEY` (optional; enables LLM summary path)
- `QUERY_SUMMARY_OPENAI_MODEL` (optional; falls back to `OPENAI_MODEL`)

Ingest listener (unchanged):
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION_NAME`
- `TG_SOURCE_CHANNEL`
- `INGEST_API_BASE_URL`

Telegram command bot:
- `TELEGRAM_BOT_TOKEN`
- `BACKEND_API_BASE_URL`
- `BACKEND_BOT_API_TOKEN`
- `ALLOWED_TELEGRAM_CHAT_IDS` (optional, comma-separated)
- `REQUEST_TIMEOUT_SECONDS` (optional)

## Local Run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start backend API:

```bash
uvicorn app.main:app --reload
```

3. Run ingest listener (source channel -> backend ingest):

```bash
python -m listener.telegram_listener
```

4. Run Telegram command bot (group commands -> backend query API):

```bash
python -m bot.telegram_bot
```

5. Run extraction job so ingest data becomes queryable events:

```bash
python -m app.jobs.run_phase2_extraction
```

## Example Commands

Telegram group:
- `/news iran 4h`
- `/summary iran 4h`
- `/news oil 24h`

## Documentation

- [Telegram Bot Guide](docs/telegram_bot.md)
- [API](docs/api.md)
- [Architecture](docs/architecture.md)
- [System Flow](docs/system-flow.md)
- [Configuration](docs/configuration.md)
- [Local Development](docs/local-development.md)
