# 0003 - Deterministic Workflow and AI Boundaries

## Status
Accepted (implemented 2026-03-18).

## Decision
Deterministic code owns:
- event-to-theme matching
- enrichment provider selection
- lens/pattern activation
- scoring and gating
- duplicate suppression/material-update decisions
- persistence and state transitions

AI usage is optional and bounded to drafting/polish only. The system must operate correctly with AI drafting disabled.

## Why it matters
Maintains reproducibility, debuggability, and safe publication behavior.

## Consequences
- Deterministic template-based card generation is first-class.
- Optional AI seams must always have deterministic fallback.

## Last updated
2026-03-18
