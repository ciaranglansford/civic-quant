# Deferred Work

## Status
Explicitly deferred in this pass to keep the scope as a vertical slice.

## Why it matters
Keeps delivery focused while preserving clean extension seams.

## Current implementation
Deferred items:
- public thesis APIs (`/api/*`) and UI
- auth/users/JWT for admin theme endpoints
- broad external market/trade/weather integrations
- multi-theme scheduler platform
- broad refactors/microservice splits
- per-event thesis emission

## What remains
- security hardening for admin endpoints
- additional theme catalog and lens library growth
- better scoring calibration against human review outcomes
- richer brief rendering and optional AI drafting quality controls

## Files/modules involved
- Existing seams: `app/contexts/opportunities/providers.py`, `app/contexts/opportunities/thesis_cards.py`

## Next recommended move
- Prioritize auth for admin endpoints before any non-local deployment.

## Last updated
2026-03-18
