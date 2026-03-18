# 0002 - Themes vs Lenses

## Status
Accepted (implemented 2026-03-18).

## Decision
- `Theme` is the batch business unit with cadence, matching rules, output rules, and orchestration hooks.
- `Lens` is a reusable causal template activated at batch time from evidence signals.

First implemented theme:
- `energy_to_agri_inputs`

First implemented lenses:
- `input_cost_pass_through`
- `capacity_curtailment`

## Why it matters
Avoids one-off hardcoded thesis logic and keeps future expansion composable.

## Consequences
- Registry-driven definitions are required.
- Active lenses can be zero/one/many per run.

## Last updated
2026-03-18
