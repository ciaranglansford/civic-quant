# Configuration

## Backend (`app/config.py`)

Core:
- `API_HOST` (default `0.0.0.0`)
- `API_PORT` (default `8000`)
- `DATABASE_URL` (default `sqlite+pysqlite:///./civicquant_dev.db`)

Query API auth:
- `BOT_API_TOKEN` (required for `/api/query/*`)

Summary model path:
- `OPENAI_API_KEY` (optional, enables LLM summary path)
- `OPENAI_MODEL` (default `gpt-4o-mini`)
- `QUERY_SUMMARY_OPENAI_MODEL` (optional override for query summaries)
- `OPENAI_TIMEOUT_SECONDS` (default `30.0`)
- `OPENAI_MAX_RETRIES` (default `2`)

Existing listener env vars remain supported:
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION_NAME`
- `TG_SOURCE_CHANNEL`
- `INGEST_API_BASE_URL`

## Telegram Command Bot (`bot/telegram_bot.py`)

Required:
- `TG_BOT_TOKEN`
- `BACKEND_API_BASE_URL`
- `BACKEND_BOT_API_TOKEN`

Optional:
- `ALLOWED_TELEGRAM_CHAT_IDS` (comma-separated list)
- `REQUEST_TIMEOUT_SECONDS` (default `8`)
- `BOT_POLL_INTERVAL_SECONDS` (default `2.5`)

## Source Listener (`listener/telegram_listener.py`)

Required:
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION_NAME`
- `TG_SOURCE_CHANNEL`
- `INGEST_API_BASE_URL`

Optional:
- `TG_POLL_INTERVAL_S` (default `60`)

## Minimal Local Example

```dotenv
# Backend
DATABASE_URL=sqlite+pysqlite:///./civicquant_dev.db
BOT_API_TOKEN=change_me
OPENAI_API_KEY=your_openai_key
QUERY_SUMMARY_OPENAI_MODEL=gpt-4o-mini

# Source listener
TG_API_ID=123456
TG_API_HASH=your_hash
TG_SESSION_NAME=civicquant
TG_SOURCE_CHANNEL=@your_source_channel
INGEST_API_BASE_URL=http://127.0.0.1:8000

# Telegram command bot
TG_BOT_TOKEN=123456:abc
BACKEND_API_BASE_URL=http://127.0.0.1:8000
BACKEND_BOT_API_TOKEN=change_me
ALLOWED_TELEGRAM_CHAT_IDS=-1001234567890
```
