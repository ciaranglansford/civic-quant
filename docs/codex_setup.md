# Codex + MCP Setup (Civicquant)

## What Was Added

- `AGENTS.md`: repo-level operating rules for Civicquant investigations and safe change behavior.
- `.codex/config.toml`: project-scoped Codex config with one local MCP server (`civicquant_db`).
- `.codex/agents/db-investigator.toml`: read-only custom investigator role for event/extraction/routing issues.
- `.agents/skills/event-debugger/SKILL.md`: single workflow for event-debug investigations.
- `.agents/skills/event-debugger/scripts/render_event_report.py`: helper to render compact markdown from structured output.
- `tools/db_mcp_contracts.py`: shared MCP tool contracts and limits.
- `tools/db_mcp_service.py`: read-only DB/domain investigation service logic.
- `tools/db_mcp_server.py`: thin STDIO MCP transport layer.

## How It Is Wired

- Codex starts MCP from `.codex/config.toml`:
  - server name: `civicquant_db`
  - command: `python tools/db_mcp_server.py`
  - env options: `CIVICQUANT_MCP_DATABASE_URL` (preferred) or `DATABASE_URL`
- `tools/db_mcp_server.py` only handles transport and method dispatch.
- `tools/db_mcp_service.py` owns all SQL/domain logic and enforces read-only behavior.
- `tools/db_mcp_contracts.py` defines tool names, input schemas, and caps.

## Database URL Behavior

- Primary source: `CIVICQUANT_MCP_DATABASE_URL`.
- Fallback sources: `DATABASE_URL`, then app settings `database_url`.
- Postgres sessions are opened with read-only transaction settings.

## Tool Surface

1. `get_event(event_id)`
2. `get_raw_message(raw_message_id)`
3. `get_event_lineage(event_id)`
4. `compare_extraction_to_event(raw_message_id)`
5. `find_duplicate_candidate_events(event_id)`
6. `run_readonly_sql(query, max_rows=100)`

`run_readonly_sql` rules:
- SELECT/CTE only
- mutating keywords rejected
- single-statement only
- strict row cap

## Start and Use

1. Open Codex in this repo.
2. Ensure `CIVICQUANT_MCP_DATABASE_URL` is set, or that `DATABASE_URL` points to the intended database.
3. Use the `event-debugger` skill directly in prompts, or invoke `db_investigator` as a subagent role.

## First Workflow (Worked Story)

Scenario:
- A raw message appears to have created a new event when it should likely have attached to an existing related event.

Recommended investigation sequence:
1. Identify `raw_message_id` (or `event_id`).
2. `get_raw_message(raw_message_id)` to inspect extraction + routing + event links.
3. `compare_extraction_to_event(raw_message_id)` to surface mismatched fields.
4. `get_event_lineage(event_id)` for the linked event and neighboring messages.
5. `find_duplicate_candidate_events(event_id)` to inspect likely duplicate cluster candidates.
6. Summarize root cause, then inspect owning code path and propose smallest safe fix only if needed.

## Example Prompts

```text
Use $event-debugger to investigate raw_message_id=1234. I suspect it created a new event instead of attaching to an existing one. Gather MCP evidence first, then summarize root cause and smallest safe fix.
```

```text
Use the db_investigator agent to analyze event_id=77 for duplicate-candidate events and extraction/event inconsistencies. Return evidence, root cause, risk, and targeted validation steps.
```

## Current Limitations

- SQLAlchemy-backed read path for Postgres (and SQLite fallback for local compatibility).
- Read-only by design; no write or migration capabilities.
- Heuristic duplicate detection is deterministic but intentionally lightweight.
- Focused on event/extraction/routing debugging only.

## Extraction-Ready Boundaries

Extraction-ready now:
- `tools/db_mcp_contracts.py` (stable tool contracts and limits)
- `tools/db_mcp_service.py` (domain logic boundary)
- tool semantics and response shapes

Local-only today:
- STDIO transport process lifecycle
- project-level environment setup
- project-scoped Codex config placement

## Future AWS Split (Likely Path)

Target split:
1. Civicquant app (existing)
2. DB investigation MCP service (future standalone deployable)
3. Optional Codex orchestration/config layer
4. Future worker/reporting service

Expected migration steps:
- Move `tools/db_mcp_contracts.py` + `tools/db_mcp_service.py` into a standalone service package.
- Replace STDIO transport with HTTP MCP transport in a new server wrapper.
- Keep tool names, input schemas, and output semantics unchanged.
- Replace local fallback assumptions with deployment env config (container-safe paths/secrets).
- Add auth/network controls at service boundary.

## Local Dev Assumptions

- Python is available in PATH for `python tools/db_mcp_server.py`.
- The target DB URL is reachable and readable by the current user.
- Codex skill auto-discovery is used for `.agents/skills` (no skill registration block required in config).
