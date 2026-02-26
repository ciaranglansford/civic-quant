# Spec vs Implementation Audit (Docs `/docs` vs Runtime Code)

## 1) Docs files/sections indexed

- `docs/README.md`
- `docs/01-overview/README.md`
- `docs/01-overview/ARCHITECTURE.md`
- `docs/01-overview/architecture_overview.md`
- `docs/01-overview/DECISIONS.md`
- `docs/01-overview/GLOSSARY.md`
- `docs/01-overview/README_INDEX.md`
- `docs/02-flows/README.md`
- `docs/02-flows/DATA_FLOW.md`
- `docs/02-flows/data_flow_telegram_to_storage.md`
- `docs/02-flows/agents_and_services.md`
- `docs/03-interfaces/README.md`
- `docs/03-interfaces/API.md`
- `docs/03-interfaces/schemas_and_storage_model.md`
- `docs/04-operations/README.md`
- `docs/04-operations/DEPLOYMENT.md`
- `docs/04-operations/operations_and_scheduling.md`
- `docs/04-operations/IMPROVEMENTS.md`

## 2) Code entry points inspected

Primary runtime entry points and persistence boundaries:

- FastAPI app factory and routes: `app/main.py:create_app`, `app/routers/ingest.py:ingest_telegram`
- Digest job CLI: `app/jobs/run_digest.py:main`
- Telegram listener CLI: `listener/telegram_listener.py:main`
- Pipeline core: `app/services/ingest_pipeline.py:process_ingest_payload`
- Event dedup/upsert: `app/services/event_manager.py:upsert_event`
- Routing engine: `app/services/routing_engine.py:route_extraction`
- Extraction agent: `app/services/extraction_agent.py:ExtractionAgent.extract`
- Digest query/build/publish: `app/services/digest_query.py:get_events_for_digest`, `app/services/digest_builder.py:build_digest`, `app/services/digest_runner.py:run_digest`, `app/services/telegram_publisher.py:send_digest_to_vip`
- Persistence boundary: SQLAlchemy ORM models in `app/models.py`, DB/session in `app/db.py`
- Strong behavioral evidence tests: `tests/test_e2e_backend.py`

---

## Step 1 — Section classification index

Legend:
- **A = INTENDED SPEC**
- **B = CURRENT IMPLEMENTATION DESCRIPTION**
- **C = REFERENCE**
- **D = UNCLEAR**

### `docs/01-overview/README.md`
- `# Civicquant Documentation (Code-Derived)` + `Project Summary` → **B** (explicitly says code-derived).
- `Quickstart`, `Key Commands`, `Repository Map` → **C** (operational/how-to index).
- `Notes on Source of Truth` → **B** (meta statement: docs derived from code).

### `docs/01-overview/ARCHITECTURE.md`
- `architecture-overview`, `entry-points`, `runtime-*`, `module-dependency-graph`, `configuration-model`, `data-storage-model`, `external-integrations` → **B** (describes observed structure).
- `architecture-uncertainties` → **D** (meta uncertainty, not normative).

### `docs/01-overview/architecture_overview.md`
- `Components`, `High-Level Data Stores` → **B** (current architecture narrative).
- `Non-Functional Requirements (Summary)` → **A** (normative language: latency target, safety policy).

### `docs/01-overview/DECISIONS.md`
- All sections (`decision-1`..`decision-7`) → **B** (title says inferred from code).

### `docs/01-overview/GLOSSARY.md`, `README_INDEX.md`
- Entire documents → **C** (reference/index).

### `docs/02-flows/DATA_FLOW.md`
- `overview` and all flows/steps mostly → **B** (explicitly “derived from executable code paths”).
- `uncertainties` → **D**.

### `docs/02-flows/data_flow_telegram_to_storage.md`
- `Purpose`, Steps 1/2/3/5/6/7/8 with “Phase 1 MVP” framing → **A** (normative expected flow for MVP).
- `Step 4 – Evidence (Phase 2+)` → **A** (future intended behavior).
- `Sequence Diagram` → **C** (illustrative reference).

### `docs/02-flows/agents_and_services.md`
- `ExtractionAgent`, `Routing Rules Engine`, `EventManagerAgent`, `PublisherAgent` responsibilities and phase statuses → **A** (service contracts / intended responsibilities).
- `EvidenceAgent`, `RoutingAgent (Optional)` phase 2+ and optional behavior → **A** (future intended).

### `docs/03-interfaces/API.md`
- Endpoint definitions, fields, and error behavior → **B** (describes implemented API).
- `Auth: none implemented in code` → **B**.
- Examples → **C**.

### `docs/03-interfaces/schemas_and_storage_model.md`
- Extraction/evidence schemas and table descriptions → **A** (interface/data-model contract style), with some partial drift vs code.
- Indexing summary → **B** where explicitly matching existing indexes, otherwise **D** where “optional/expected”.

### `docs/04-operations/DEPLOYMENT.md`
- Inferred deployment/runtime requirements and lifecycle → **B** (descriptive).

### `docs/04-operations/operations_and_scheduling.md`
- Runtime operations for Phase 1 and “Future Scheduling – Phase 2+” → **A** (intended operational behavior).

### `docs/04-operations/IMPROVEMENTS.md`
- Entire backlog (`P0/P1/P2`) → **A** (explicit desired change set/acceptance criteria).

### `docs/README.md`, section README indexes
- Structure/index/navigation → **C**.

---

## Step 2 — Capability extraction (stable IDs)

### ING-01 — Telegram ingest API contract
- **Expected behavior (spec):** Accept Telegram payload fields and validate schema; return `created|duplicate` plus IDs.
- **Claimed current behavior:** API doc says exactly those request/response models and generic 500 on unexpected errors.
- **Edge/error cases:** 422 validation errors; 500 on unhandled runtime errors.
- **Data model expectations:** `raw_messages` record per unique source+message.

### ING-02 — Idempotent raw message ingest
- **Expected behavior (spec):** Duplicate source message should not create duplicate records.
- **Claimed current behavior:** Unique key + duplicate status path.
- **Edge/error cases:** insert races should remain idempotent.
- **Data expectations:** uniqueness on `(source_channel_id, telegram_message_id)`.

### ING-03 — Deterministic normalization + extraction
- **Expected behavior (spec):** normalize text, produce well-formed extraction schema object.
- **Claimed current behavior:** stub extraction in phase 1.
- **Edge cases:** empty text; timestamp normalization; constrained confidence/impact ranges.
- **Data expectations:** one extraction linked to raw message.

### ING-04 — Routing decision generation
- **Expected behavior (spec):** deterministic routing with destination(s), priority, evidence flag, action, flags.
- **Claimed current behavior:** rule-based routing module in phase 1.
- **Edge cases:** high impact/breaking thresholds; ignore path.
- **Data expectations:** `routing_decisions` row per raw message.

### EVT-01 — Event dedup/upsert and linkage
- **Expected behavior (spec):** fingerprint + time-window dedup, create/update canonical event, link message.
- **Claimed current behavior:** implemented with create/update logs.
- **Edge cases:** macro/breaking/default windows; event field update strategy.
- **Data expectations:** `events` + `event_messages` updates.

### PUB-01 — Digest build/publish with dedup
- **Expected behavior (spec):** query events in `VIP_DIGEST_HOURS`, build topic-grouped digest, publish, store publish record, skip duplicates.
- **Claimed current behavior:** separate digest job + content-hash dedup.
- **Edge cases:** missing bot config; duplicate digest window.
- **Data expectations:** `published_posts` rows with content hash/timestamp.

### OPS-01 — Runtime composition and scheduling
- **Expected behavior (spec):** 3-process model (API/listener/digest), cron-like scheduling for digest.
- **Claimed current behavior:** all three entrypoints exist.
- **Edge cases:** deployment orchestration unspecified.
- **Data expectations:** DB required.

### SEC-01 — Ingest endpoint authentication
- **Expected behavior (spec):** improvements backlog requires explicit authn/authz for ingest (P0).
- **Claimed current behavior:** API docs explicitly no auth implemented.
- **Edge cases:** unauthorized requests should fail 401/403 once implemented.
- **Data expectations:** secret config for listener/backend.

### NFR-01 — Non-functional/safety constraints
- **Expected behavior (spec):** latency target ≤ 30s, no investment advice language, uncorroborated labeling.
- **Claimed current behavior:** digest includes explicit “no investment advice” note and corroboration label placeholder.
- **Edge cases:** no latency enforcement instrumentation.
- **Data expectations:** none hard DB; mostly output and operations behavior.

---

## Step 3 — Capability to code mapping with status

### Traceability matrix

| Capability ID | Spec reference(s) | Description reference(s) | Code reference(s) | Test reference(s) | Status | Gap summary |
|---|---|---|---|---|---|---|
| ING-01 | `data_flow_telegram_to_storage.md` Step 1, `schemas_and_storage_model.md` extraction/table contracts | `API.md` endpoint contract & errors | `app/routers/ingest.py:ingest_telegram`; `app/schemas.py:TelegramIngestPayload/IngestResponse` | `tests/test_e2e_backend.py::test_ingest_creates_rows_and_is_idempotent` | ✅ | Request/response shape and validation/500 behavior align. |
| ING-02 | `data_flow_telegram_to_storage.md` Step 7 idempotent constraints | `DATA_FLOW.md` flow-1 step 5/9 | `app/models.py:RawMessage uq_raw_source_msg`; `app/services/ingest_pipeline.py:_get_existing_raw/process_ingest_payload` | `tests/test_e2e_backend.py::test_ingest_creates_rows_and_is_idempotent` | ✅ | Duplicate returns `duplicate` and reuses IDs; race handled with `IntegrityError` fallback. |
| ING-03 | `data_flow_telegram_to_storage.md` Step 2/3 | `agents_and_services.md` ExtractionAgent | `app/services/normalization.py:normalize_message_text`; `app/services/extraction_agent.py:ExtractionAgent.extract` | (none unit-level) | ⚠️ | Implemented stub, but extraction determinism/edge cases are under-tested (called out in improvements). |
| ING-04 | `data_flow_telegram_to_storage.md` Step 5 | `agents_and_services.md` Routing Rules Engine | `app/services/routing_engine.py:route_extraction`; `app/config_routing.py:DEFAULT_ROUTING_CONFIG`; `app/services/ingest_pipeline.py:store_routing_decision` | Indirect via e2e tests | ⚠️ | Core routing works, but `requires_evidence` is effectively disabled (`evidence_enabled=False`) so documented conditional evidence gating is only partial in phase 1. |
| EVT-01 | `data_flow_telegram_to_storage.md` Step 6 | `DATA_FLOW.md` flow-1 step 8 | `app/services/event_manager.py:upsert_event/update_event_from_extraction`; `app/services/event_windows.py:get_event_time_window`; `app/models.py:Event/EventMessage` | `tests/test_e2e_backend.py::test_dedup_updates_existing_event` | ✅ | Fingerprint+window upsert and event-message linking implemented. |
| PUB-01 | `operations_and_scheduling.md` Scheduling – Digests | `DATA_FLOW.md` flow-2 | `app/jobs/run_digest.py:main`; `app/services/digest_runner.py:run_digest/has_recent_duplicate`; `app/services/digest_builder.py:build_digest`; `app/services/telegram_publisher.py:send_digest_to_vip` | `tests/test_e2e_backend.py::test_digest_build_and_publish_record` | ✅ | Digest flow with duplicate hash suppression and publish record exists. |
| OPS-01 | `operations_and_scheduling.md` Runtime Components | `ARCHITECTURE.md` entry-points | `app/main.py`, `listener/telegram_listener.py`, `app/jobs/run_digest.py` | indirect | ✅ | Three-runtime architecture exists and is runnable via documented entrypoints. |
| SEC-01 | `IMPROVEMENTS.md` item 2 (P0 authn/authz) | `API.md` “Auth: none implemented” | `app/routers/ingest.py` (no auth checks) | none | ❌ | Security spec/backlog says add auth; code currently unauthenticated. |
| NFR-01 | `architecture_overview.md` NFR summary | `DEPLOYMENT.md` observability notes | `app/services/digest_builder.py` disclaimer line; no latency instrumentation in runtime code | none | 🔄 | Safety language partly met; latency target is not measured/enforced. |

### Overall decision

- **Code meets most documented current implementation descriptions.**
- **Code does not fully meet all intended-spec content** because at least one explicit P0 intended requirement (ingest auth) is unimplemented, and some intended non-functional goals (latency objective, richer evidence behavior) are not enforceable yet.

---

## Step 4 — Doc conflicts and inconsistencies

1. **Listener trigger style conflict (description vs description)**
   - `ARCHITECTURE.md` says listener “subscribes to `events.NewMessage`” while actual code is polling loop with `get_messages` and `last_seen_id`.
   - **Canonical should be code** (polling), and docs should be corrected.

2. **Health endpoint contradiction (spec vs implementation description)**
   - `operations_and_scheduling.md` says “Confirm health via `/health` endpoint (to be implemented)” but `/health` already exists.
   - **Canonical should be code + API docs**; operations doc is outdated.

3. **Settings contract mismatch (spec/ops docs vs code)**
   - Ops/deployment docs imply listener variables are only needed for listener process; code-level `Settings` requires listener fields globally, causing API/tests to fail without them.
   - **Canonical should be intended operational model** (listener vars optional for backend), so code likely needs refactor of settings boundaries.

4. **Schema expectation ambiguity for one-extraction-per-message**
   - `schemas_and_storage_model.md` calls uniqueness on `extractions.raw_message_id` optional; code enforces de facto one row via service logic but lacks DB unique constraint.
   - **Canonical should be explicit spec decision**; currently ambiguous (**UNCLEAR**) whether strict DB-level uniqueness is required.

5. **Evidence behavior mismatch (spec vs implementation)**
   - Flow/spec describes conditional evidence gate logic; code contains `requires_evidence` logic but disabled by `evidence_enabled=False`, and no EvidenceAgent exists in phase 1.
   - **Canonical should be phase-tagged spec**: acceptable for Phase 1 if docs explicitly mark this as disabled/not active.

---

## Step 5B — Prioritized change list (P0/P1/P2)

### P0

1. **Add ingest authentication/authorization guard**
   - **What:** code + tests + docs.
   - **Why:** explicit P0 requirement in improvements; endpoint currently open.
   - **Where:** `app/routers/ingest.py`, `listener/telegram_listener.py`, `app/config.py`, `docs/03-interfaces/API.md`, `docs/04-operations/DEPLOYMENT.md`, tests in `tests/test_e2e_backend.py`.
   - **Approach:**
     1. Add shared secret setting(s) (`INGEST_SHARED_SECRET` or API key).
     2. Require `X-Ingest-Signature` (HMAC) or `X-API-Key` in ingest route.
     3. Add listener signing/header injection.
     4. Add 401/403 tests and success path tests.

### P1

2. **Split backend vs listener settings to remove false required env coupling**
   - **What:** code + tests + docs.
   - **Why:** backend/tests currently require listener-only env vars due monolithic `Settings` model.
   - **Where:** `app/config.py`, imports in `app/db.py` and runtime modules, tests setup.
   - **Approach:** separate `BackendSettings` and `ListenerSettings` accessors or make listener fields optional and validate only in listener entrypoint.

3. **Add extraction determinism unit tests**
   - **What:** tests.
   - **Why:** currently only end-to-end checks; extraction/fingerprint heuristics unguarded.
   - **Where:** new `tests/test_extraction_agent.py`.
   - **Approach:** deterministic fixtures for topic detection, number parsing, empty text summary, fingerprint stability.

4. **Update stale docs on listener mode and health endpoint status**
   - **What:** docs only.
   - **Why:** two direct contradictions with code.
   - **Where:** `docs/01-overview/ARCHITECTURE.md`, `docs/04-operations/operations_and_scheduling.md`, optionally `docs/02-flows/DATA_FLOW.md`.
   - **Approach:** replace `events.NewMessage` subscription claim with polling behavior and remove “to be implemented” on `/health`.

### P2

5. **Clarify evidence behavior and phase gating in docs/config**
   - **What:** docs + optional config comment.
   - **Why:** intended evidence logic appears active in docs but is disabled in config.
   - **Where:** `docs/02-flows/data_flow_telegram_to_storage.md`, `docs/02-flows/agents_and_services.md`, `app/config_routing.py` comments.

6. **Consider DB-level unique constraint on `extractions.raw_message_id` if one-to-one is required**
   - **What:** code/migration + docs.
   - **Why:** current one-to-one enforced only in service path.
   - **Where:** `app/models.py`, migration framework once adopted.

---

## Step 5C — Testing plan

- **Auth tests (new):** `tests/test_ingest_auth.py`
  - `test_ingest_rejects_missing_auth_header` → proves 401/403.
  - `test_ingest_rejects_invalid_signature` → proves tamper rejection.
  - `test_ingest_accepts_valid_signature` → proves listener-compatible happy path.

- **Settings boundary tests (new):** `tests/test_config_scoping.py`
  - `test_backend_settings_do_not_require_listener_env` → proves API-only startup works.
  - `test_listener_startup_requires_listener_env` → proves listener still enforces required vars.

- **Extraction determinism tests (new):** `tests/test_extraction_agent.py`
  - `test_topic_hint_classification_central_banks`
  - `test_number_and_ticker_extraction`
  - `test_empty_text_defaults`
  - `test_fingerprint_stability_same_input`

- **Regression e2e updates:** keep `tests/test_e2e_backend.py`, add auth header fixture where needed after auth is added.

---

## Step 5D — Minimum viable compliance path

Smallest change set to align with intended spec first:

1. Implement ingest authentication (header-based API key or HMAC) and enforce in `POST /ingest/telegram`.
2. Update listener to send auth credentials/signature.
3. Add auth tests (unauthorized + authorized).
4. Fix docs contradictions (listener mode, `/health` status, auth requirement in API docs).

This yields immediate compliance on the highest-priority intended requirement (security) without risky refactors.

---

## UNCLEAR items and next files to inspect

1. **Whether extraction must be DB-enforced one-to-one:** inspect planning artifacts under `user-stories/` and `plans/` for explicit acceptance criteria.
2. **Whether event_action should ever be `update` pre-upsert:** inspect any route/rules spec outside `/docs` and product notes in `user-stories/dedup_and_events.md`.
3. **Latency target enforceability:** inspect deployment/SLO docs and monitoring config (if any external repo or infrastructure docs exist).
