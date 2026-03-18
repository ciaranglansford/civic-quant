# Quality Questions

## Status
Open quality questions to guide next calibration cycles.

## Why it matters
Captures unresolved judgment calls that influence thesis precision/recall.

## Current implementation
- Conservative gating and duplicate suppression are in place.
- Deterministic evidence interpretation is lens-driven.

## What remains
- Are current evidence/confidence/priority thresholds too strict or too loose by cadence?
- Should contradiction weighting vary by archetype family?
- Should weekly runs allow a different material-update delta policy than daily runs?

## Files/modules involved
- `app/contexts/opportunities/scoring.py`
- `app/contexts/opportunities/thesis_cards.py`
- `app/workflows/theme_batch_pipeline.py`

## Next recommended move
- Review 2-4 weeks of run outputs and resolve each question with explicit threshold decisions.

## Last updated
2026-03-18
