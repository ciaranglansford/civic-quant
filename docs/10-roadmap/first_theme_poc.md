# First Theme POC

## Status
Implemented theme:
- `energy_to_agri_inputs`

Implemented lenses:
- `input_cost_pass_through`
- `capacity_curtailment`

## Why it matters
Demonstrates reusable theme/lens architecture while solving one concrete business path end-to-end.

## Current implementation
- Energy/gas/LNG and supply-side evidence is matched continuously into `event_theme_evidence`.
- Batch run aggregates evidence and supports downstream inference even when raw bulletins do not literally mention fertilizer.
- Assessments persist structured reasoning fields and separated score components.
- Thesis cards are derived objects with deterministic template output.
- Emission is batch-only and gated.

## What remains
- Tune thresholds from observed run quality.
- Add richer contradiction handling and confidence calibration.

## Files/modules involved
- `app/contexts/themes/definitions.py`
- `app/contexts/themes/matching.py`
- `app/contexts/opportunities/assessment.py`
- `app/contexts/opportunities/thesis_cards.py`

## Next recommended move
- Add a second theme to validate generality of archetype/pattern registries and lens reuse.

## Last updated
2026-03-18
