# Civicquant Docs Knowledge Base

This `/docs` directory is organized as a staged, retrieval-friendly knowledge base for a Telegram wire-bulletin intelligence pipeline.
For canonical digest ownership, synthesis contracts, adapter boundaries, and local schema adoption/reset guidance, start with [`digest_pipeline.md`](./digest_pipeline.md), [`03-architecture/digest_canonical_pipeline.md`](./03-architecture/digest_canonical_pipeline.md), and [`04-operations/operations_and_scheduling.md`](./04-operations/operations_and_scheduling.md).

Current implementation ownership follows a context-first modular monolith:
- `app/contexts/*` for bounded contexts
- `app/workflows/*` for cross-context orchestration
- `app/digest/*` as canonical reporting/digest implementation

Historical records:
- Files in [`05-audit/`](./05-audit/) and [`feed-api/`](./feed-api/) may describe earlier repo layouts.
- Those documents now include "Current status" notes where path/ownership references have drifted.

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

## Recommended Reading Order

1. [`01-overview/README.md`](./01-overview/README.md)
2. [`01-overview/ARCHITECTURE.md`](./01-overview/ARCHITECTURE.md)
3. [`02-flows/DATA_FLOW.md`](./02-flows/DATA_FLOW.md)
4. [`03-architecture/digest_canonical_pipeline.md`](./03-architecture/digest_canonical_pipeline.md)
5. [`digest_pipeline.md`](./digest_pipeline.md)
6. [`03-interfaces/schemas_and_storage_model.md`](./03-interfaces/schemas_and_storage_model.md)
7. [`04-operations/operations_and_scheduling.md`](./04-operations/operations_and_scheduling.md)
8. [`05-audit/spec_vs_impl_audit.md`](./05-audit/spec_vs_impl_audit.md)

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

