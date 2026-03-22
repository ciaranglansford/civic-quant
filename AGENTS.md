# Civicquant Agent Guidelines

## Domain Truth Model

- Events, extractions, and digests represent reported claims, not confirmed facts.
- Preserve attribution and uncertainty language from source material.
- Do not rewrite behavior in ways that imply factual certainty without explicit evidence.

## Working Style

- Gather evidence before proposing fixes.
- Prefer the smallest safe change that addresses the verified failure mode.
- Keep edits scoped to the owning module; avoid broad refactors during investigations.
- Preserve existing contracts unless a change is required for correctness.

## Database and Investigation Safety

- Prefer read-only database investigation first.
- Do not perform production or ad-hoc database writes from agent workflows.
- Use deterministic, inspectable queries and keep outputs structured.
- If a schema assumption is uncertain, inspect the real schema before acting.

## Civicquant Debug Flow (Event/Extraction/Routing)

1. Identify target `event_id` or `raw_message_id`.
2. Collect evidence from data rows first (raw message, extraction, routing, event linkage).
3. Summarize root cause hypothesis with concrete row/field evidence.
4. Inspect owning code paths before editing:
   - `app/contexts/events/event_manager.py`
   - `app/contexts/triage/*`
   - `app/contexts/extraction/processing.py`
   - `app/workflows/phase2_pipeline.py`
5. Apply the smallest safe code fix only when needed.

## Validation Expectations

- Run targeted validation only for touched behavior.
- Prefer focused tests/jobs over full-suite reruns during investigation loops.
- Report what was validated and what remains unvalidated.
