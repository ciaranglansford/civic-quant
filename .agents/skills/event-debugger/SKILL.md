---
name: event-debugger
description: Investigate Civicquant event, extraction, and routing issues using read-only MCP evidence before proposing any fix.
---

# Event Debugger

Use this skill for Civicquant investigations where:
- a raw message was attached to the wrong event
- a duplicate event was created instead of merging/attaching
- extraction output and event state look inconsistent

## Required Workflow

1. Identify the target `event_id` or `raw_message_id`.
2. Gather database evidence first with MCP tools:
   - `get_event`
   - `get_raw_message`
   - `get_event_lineage`
   - `compare_extraction_to_event`
   - `find_duplicate_candidate_events`
   - `run_readonly_sql` only as fallback
3. Summarize evidence before proposing any fix.
4. Inspect owning code paths after evidence:
   - `app/contexts/events/event_manager.py`
   - `app/contexts/triage/decisioning.py`
   - `app/contexts/extraction/processing.py`
   - `app/workflows/phase2_pipeline.py`
5. Propose the smallest safe code change only if needed.
6. Run targeted validation only for touched behavior.

## Constraints

- Keep DB investigation read-only.
- Do not run broad refactors.
- Preserve attribution/uncertainty semantics (reported claims, not confirmed facts).
- Keep conclusions evidence-backed and field-specific.

## Required Output

### Root Cause
Most likely failure mechanism, tied to concrete rows/fields.

### Evidence
Key MCP outputs and code-path observations that support the diagnosis.

### Proposed Fix
Smallest safe fix, or explicit statement that no code change is needed.

### Regression Risk
Likely side effects and what could regress.

### Validation Steps
Targeted tests/jobs/queries run (and any remaining validation).