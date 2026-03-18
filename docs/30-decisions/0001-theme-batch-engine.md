# 0001 - Theme Batch Engine

## Status
Accepted (implemented 2026-03-18).

## Decision
Introduce an additive batch thematic thesis engine that runs on scheduled windows and persists:
- `theme_runs`
- `event_theme_evidence`
- `theme_opportunity_assessments`
- `thesis_cards`
- `theme_brief_artifacts`

Continuous processing is limited to deterministic event-to-theme evidence matching.

## Why it matters
- Preserves existing continuous pipeline behavior.
- Enables thesis generation only at batch time.
- Creates an extensible seam for additional themes.

## Consequences
- New batch orchestration and admin inspection surface are added.
- Existing public feed and digest contracts remain unchanged.

## Last updated
2026-03-18
