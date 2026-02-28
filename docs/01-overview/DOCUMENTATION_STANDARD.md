# Documentation Standard

## Purpose

This file defines required documentation behavior for this repository.

## Folder Responsibilities

- `01-overview`: intent, architecture framing, glossary, and documentation standards.
- `02-flows`: runtime flow of data and control between jobs/services/DB/external APIs.
- `03-interfaces`: API contracts, schemas, and storage contracts used by code.
- `04-operations`: runtime procedures, job commands, scheduling, and troubleshooting.
- `05-audit`: verification of spec vs implementation and change-risk audits.

## Update Rules

Every new feature or behavior change MUST update:

1. `02-flows` with runtime data/control flow changes.
2. `03-interfaces` with contract/schema/storage changes.
3. `04-operations` with runbooks/commands/validation guidance.
4. `05-audit` with implementation verification and known gaps.

## Definition of Done

A feature is incomplete if code is merged without required documentation updates in:

- flow docs,
- interface/schema docs,
- operations docs,
- audit docs.
