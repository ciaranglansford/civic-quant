# Telegram Command Bot

## Purpose

`bot/telegram_bot.py` is the user-facing Telegram group interface for this MVP.

Supported commands:
- `/news <topic> <1h|4h|24h>`
- `/summary <topic> <1h|4h|24h>`

The bot is intentionally thin:
- command parsing and input validation
- backend HTTP calls
- Telegram-friendly formatting

The bot does not implement event retrieval, ranking, dedupe, or summarization rules.

## Architecture Split

1. Source listener (`listener/telegram_listener.py`)
- ingests source channel messages into backend
- does not process group commands

2. Backend intelligence API (`/api/query/*`)
- validates query input
- retrieves/ranks/deduplicates events
- produces structured news and summary payloads

3. Telegram command bot (`bot/telegram_bot.py`)
- receives group slash commands
- calls backend query endpoints with bearer token
- posts formatted responses back to the same chat

## Bot and Backend Auth

Backend expects:
- `Authorization: Bearer <BOT_API_TOKEN>`

Bot sends:
- `Authorization: Bearer <BACKEND_BOT_API_TOKEN>`

For MVP, set both values to the same shared secret.

## Environment Variables

Required for bot:
- `TG_BOT_TOKEN`
- `BACKEND_API_BASE_URL`
- `BACKEND_BOT_API_TOKEN`

Optional:
- `ALLOWED_TELEGRAM_CHAT_IDS` (comma-separated chat IDs)
- `REQUEST_TIMEOUT_SECONDS` (default `8`)
- `BOT_POLL_INTERVAL_SECONDS` (default `2.5`)

## Run

```bash
python -m bot.telegram_bot
```

## Command Validation Behavior

Invalid `/news` usage:
- `Usage: /news <topic> <1h|4h|24h>`

Invalid `/summary` usage:
- `Usage: /summary <topic> <1h|4h|24h>`

If allowlist is configured and chat is not listed:
- `This bot is not enabled for this chat.`

Backend/network failures:
- `Request failed. Please try again shortly.`

## Example Telegram Output

`/news iran 4h` (shape):

```text
News: iran (4h)
3 ranked updates
1. Iran reportedly launched missile activity...
   2026-03-28 11:35Z | telegram:intel_feed | high | geopolitics | score 0.88 | refs src_1, src_2
```

`/summary iran 4h` (shape):

```text
Summary: iran (4h)
Key Developments
- Reported military activity increased. (evt_11)
Uncertainties
- Casualty figures remain unconfirmed. (evt_11)
Why It Matters
- Escalation risk can affect regional oil pricing. (evt_11)
```

## Deployment Notes

- Run bot as a separate process from backend API and source listener.
- Keep `ALLOWED_TELEGRAM_CHAT_IDS` configured for private group usage when needed.
- Do not expose backend stack traces in bot replies.
