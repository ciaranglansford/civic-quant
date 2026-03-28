# Local Development

## Setup

1. Create/activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure `.env` (see `docs/configuration.md`).

## Run Order (Telegram Query Flow)

1. Start backend API:

```bash
uvicorn app.main:app --reload
```

2. Start source ingestion listener:

```bash
python -m listener.telegram_listener
```

3. Process ingested messages into queryable events:

```bash
python -m app.jobs.run_phase2_extraction
```

4. Start Telegram command bot:

```bash
python -m bot.telegram_bot
```

5. In Telegram group, run:
- `/news iran 4h`
- `/summary iran 4h`

## Optional Jobs

- Deep enrichment:

```bash
python -m app.jobs.run_deep_enrichment
```

- Pipeline inspection:

```bash
python -m app.jobs.inspect_pipeline --limit 20
```

## Targeted Tests

```bash
pytest -q tests/test_query_api.py tests/test_query_service.py tests/test_summary_service.py tests/test_telegram_bot.py
```
