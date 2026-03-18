# Civicquant Docs Knowledge Base

This `/docs` directory is organized as a staged, retrieval-friendly knowledge base for a Telegram wire-bulletin intelligence pipeline.
For canonical digest ownership, synthesis contracts, adapter boundaries, and local schema adoption/reset guidance, start with [`digest_pipeline.md`](./digest_pipeline.md), [`03-architecture/digest_canonical_pipeline.md`](./03-architecture/digest_canonical_pipeline.md), and [`04-operations/operations_and_scheduling.md`](./04-operations/operations_and_scheduling.md).

Current implementation ownership follows a context-first modular monolith:
- `app/contexts/*` for bounded contexts
- `app/workflows/*` for cross-context orchestration
- `app/digest/*` as canonical reporting/digest implementation
- `app/contexts/themes/*` + `app/contexts/opportunities/*` for batch thematic thesis capability

Historical records:
- Files in [`05-audit/`](./05-audit/) and [`feed-api/`](./feed-api/) may describe earlier repo layouts.
- Those documents now include "Current status" notes where path/ownership references have drifted.

Living theme-batch documentation:
- [`00-current-state/`](./00-current-state/)
- [`10-roadmap/`](./10-roadmap/)
- [`20-work-registry/`](./20-work-registry/)
- [`30-decisions/`](./30-decisions/)

## Structure

- [`01-overview/`](./01-overview/)
  - System framing, architecture, glossary, and documentation standards.
- [`02-flows/`](./02-flows/)
  - Current and target-state data/control flows.
- [`03-architecture/`](./03-architecture/)
  - Focused architecture deep-dives.
- [`03-interfaces/`](./03-interfaces/)
  - API contracts and storage/schema semantics.
- [`04-operations/`](./04-operations/)
  - Deployment and stage-oriented runtime operations.
- [`05-audit/`](./05-audit/)
  - Spec/implementation consistency and known divergences.
- [`00-current-state/`](./00-current-state/)
  - Snapshot of active system/module status for prompt-driven work.
- [`10-roadmap/`](./10-roadmap/)
  - Theme-batch architecture direction, first-theme plan, deferred scope.
- [`20-work-registry/`](./20-work-registry/)
  - Active work registry, known gaps, tech debt, validation backlog.
- [`30-decisions/`](./30-decisions/)
  - Decision log for theme-batch architecture boundaries.

## Recommended Reading Order

1. [`01-overview/README.md`](./01-overview/README.md)
2. [`01-overview/ARCHITECTURE.md`](./01-overview/ARCHITECTURE.md)
3. [`02-flows/DATA_FLOW.md`](./02-flows/DATA_FLOW.md)
4. [`03-architecture/digest_canonical_pipeline.md`](./03-architecture/digest_canonical_pipeline.md)
5. [`digest_pipeline.md`](./digest_pipeline.md)
6. [`03-interfaces/schemas_and_storage_model.md`](./03-interfaces/schemas_and_storage_model.md)
7. [`04-operations/operations_and_scheduling.md`](./04-operations/operations_and_scheduling.md)
8. [`05-audit/spec_vs_impl_audit.md`](./05-audit/spec_vs_impl_audit.md)
9. [`00-current-state/system_overview.md`](./00-current-state/system_overview.md)
10. [`10-roadmap/theme_run_architecture.md`](./10-roadmap/theme_run_architecture.md)
11. [`20-work-registry/active_work_items.md`](./20-work-registry/active_work_items.md)
12. [`30-decisions/0001-theme-batch-engine.md`](./30-decisions/0001-theme-batch-engine.md)

## Full Document Index

### 01-overview
- [`README.md`](./01-overview/README.md)
- [`ARCHITECTURE.md`](./01-overview/ARCHITECTURE.md)
- [`architecture_overview.md`](./01-overview/architecture_overview.md)
- [`DECISIONS.md`](./01-overview/DECISIONS.md)
- [`GLOSSARY.md`](./01-overview/GLOSSARY.md)
- [`DOCUMENTATION_STANDARD.md`](./01-overview/DOCUMENTATION_STANDARD.md)

### 02-flows
- [`README.md`](./02-flows/README.md)
- [`DATA_FLOW.md`](./02-flows/DATA_FLOW.md)
- [`data_flow_telegram_to_storage.md`](./02-flows/data_flow_telegram_to_storage.md)
- [`agents_and_services.md`](./02-flows/agents_and_services.md)
- [`phase2_extraction_flow.md`](./02-flows/phase2_extraction_flow.md)

### 03-interfaces
- [`README.md`](./03-interfaces/README.md)
- [`API.md`](./03-interfaces/API.md)
- [`schemas_and_storage_model.md`](./03-interfaces/schemas_and_storage_model.md)

### 03-architecture
- [`digest_canonical_pipeline.md`](./03-architecture/digest_canonical_pipeline.md)

### Root docs
- [`digest_pipeline.md`](./digest_pipeline.md)

### 04-operations
- [`README.md`](./04-operations/README.md)
- [`DEPLOYMENT.md`](./04-operations/DEPLOYMENT.md)
- [`operations_and_scheduling.md`](./04-operations/operations_and_scheduling.md)
- [`jobs_reference.md`](./04-operations/jobs_reference.md)
- [`IMPROVEMENTS.md`](./04-operations/IMPROVEMENTS.md)

### 05-audit
- [`spec_vs_impl_audit.md`](./05-audit/spec_vs_impl_audit.md)
- [`2026-03-16_modularization_completion_debrief.md`](./05-audit/2026-03-16_modularization_completion_debrief.md)
- [`refactor_audit_2026-03-18.md`](./05-audit/refactor_audit_2026-03-18.md)

### 00-current-state
- [`system_overview.md`](./00-current-state/system_overview.md)
- [`module_map.md`](./00-current-state/module_map.md)
- [`implementation_status.md`](./00-current-state/implementation_status.md)

### 10-roadmap
- [`theme_run_architecture.md`](./10-roadmap/theme_run_architecture.md)
- [`first_theme_poc.md`](./10-roadmap/first_theme_poc.md)
- [`deferred_work.md`](./10-roadmap/deferred_work.md)

### 20-work-registry
- [`active_work_items.md`](./20-work-registry/active_work_items.md)
- [`known_gaps.md`](./20-work-registry/known_gaps.md)
- [`tech_debt.md`](./20-work-registry/tech_debt.md)
- [`validation_backlog.md`](./20-work-registry/validation_backlog.md)
- [`quality_questions.md`](./20-work-registry/quality_questions.md)

### 30-decisions
- [`0001-theme-batch-engine.md`](./30-decisions/0001-theme-batch-engine.md)
- [`0002-themes-vs-lenses.md`](./30-decisions/0002-themes-vs-lenses.md)
- [`0003-deterministic-workflow-ai-boundaries.md`](./30-decisions/0003-deterministic-workflow-ai-boundaries.md)

