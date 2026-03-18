# Known Gaps

## Status
Documented known gaps for this POC scope.

## Why it matters
Prevents accidental over-interpretation of POC outputs as production-complete intelligence.

## Current implementation
- Single theme and two lenses only.
- Internal-only admin endpoints without auth.
- Optional AI drafting seam present but no production-grade drafting policy stack.
- Duplicate similarity is deterministic signature-based; not semantic NLP similarity.

## What remains
- Multi-theme validation and false positive/negative analysis.
- Auth + authorization boundary for admin theme endpoints.
- More robust contradiction interpretation and confidence calibration.

## Files/modules involved
- `app/routers/admin_theme.py`
- `app/contexts/opportunities/thesis_cards.py`
- `app/contexts/opportunities/scoring.py`

## Next recommended move
- Add human review sampling for emitted/updated/suppressed cards and feed outcomes back into thresholds.

## Last updated
2026-03-18
