# AGENDA STAGE 04C-V — CONTRACT ACTIVITY EVENT PROVIDER RUNTIME VALIDATION

## 1. Decision boundary

This document records the complete Stage 4C-V runtime differential validation for the contract-level Activity EVENT provider. It does not broaden activity scope, change product/test/schema/auth/log-writer/UI source, synchronize with current main, or authorize a main merge.

Official decision:

```text
STAGE 4C STATIC/SOURCE TEST GATE: PASS
STAGE 4C RUNTIME DIFFERENTIAL GATE: PASS
CONTRACT ACTIVITY EVENT PROVIDER: ACCEPTED
CONTRACT-LEVEL ACTIVITY EVENTS: ACCEPTED
SYSTEM/DELIVERY ACTIVITY EVENTS: DEFERRED
ACTOR STAFF ID / SELF FILTERING: DEFERRED
RESPONSIBLE CHANGE ACTIVITY: DEFERRED
NOTE/COMPONENT/CREATE/DELETE ACTIVITY: DEFERRED
DIRECT EVENT DISMISS ACTION: DEFERRED
EVENT SNOOZE SUPPORT: DEFERRED
CORE AGENDA PROVIDER DEVELOPMENT: COMPLETE
CURRENT-MAIN INTEGRATION AUDIT GATE: OPEN
MAIN MERGE GATE: CLOSED
```

## 2. Accepted refs and lineage

- Repository: `chat90278-png/sozappsql2`
- Branch: `feature/gundemim-agenda-system`
- Accepted Stage 4B-V baseline: `c52c59ca15756ca0accd0a3910a1e20b9c66c4ea`
- Stage 4C-R1 product/source HEAD: `e1bfe4014b05c0e694cb1012198bf0134e8cfc77`
- Stage 4C-R1-E accepted starting HEAD: `90aad699cdbe95b3e3dd692ec7046095785f21c5`
- Official Stage 4C-V workflow HEAD: `eacfd017b710058422c14da29abde88baf19f516`
- Main observed during validation: `e1ed9a66318e19178f132602d3114a97880fa27f`
- Original feature/main merge base: `2931fa267560397d4d849d6365acde504f376775`

The accepted Stage 4C product delta from baseline to product HEAD was exactly 17 commits and 12 approved product/test/document paths. The R1-E starting tree added only `docs/agenda/AGENDA_STAGE_04C_R1_EXECUTION_VALIDATION.md` over the product HEAD.

## 3. Preflight

Preflight: `PASS`.

The official workflow confirmed:

- starting HEAD is an ancestor of the workflow HEAD;
- Stage 4C product path set is exact;
- R1-E net path is exact;
- temporary Stage 4C-V path set is exact;
- old R1-E temporary paths are absent;
- accepted R1-E gate decisions are present;
- current main and original merge base are recorded;
- current main is not the differential baseline.

Official temporary paths:

```text
.github/workflows/agenda-stage-04c-v-runtime-validation.yml
tools/validation/agenda_stage_04c_v_runtime_validation.py
```

No product, committed test, requirements, schema, auth, activity-log writer, or Qt/UI product file was changed by the validation layer.

## 4. Temporary PR and workflow

Temporary PR:

```text
PR: #332
Title: TEMP VALIDATION: Agenda Stage 4C-V
Base: main
Head: feature/gundemim-agenda-system
Draft: true
Final state: closed
Merged: false
Merged at: null
Created: 2026-07-13T11:53:36Z
Closed: 2026-07-13T12:10:48Z
```

Official workflow:

```text
Name: Agenda Stage 04C-V Runtime Validation
Run number: 3
Run ID: 29248508952
Head: eacfd017b710058422c14da29abde88baf19f516
Status: completed
Conclusion: success
```

Official job:

```text
Name: agenda-stage-04c-v-runtime-validation
Job ID: 86811127644
Status: completed
Conclusion: success
```

Every official job step succeeded: exact checkout, baseline/feature materialization, Python setup, dependency installation, runtime differential validation, and artifact upload.

Two earlier runs were superseded because of validator-only mistakes. Run `29247831781` incorrectly expected provider-level equal/nested filtering at repository level. Run `29248174226` treated an `AgendaResult` as directly iterable instead of reading `.items`. Neither identified a product bug or changed product/test source. Official run 3 reran every mandatory gate from scratch.

## 5. Environment

```text
Runner OS: Microsoft Windows Server 2025 / 10.0.26100
Runner image: windows-2025-vs2026
Runner image version: 20260628.158.1
Architecture: AMD64
Python: 3.11.9, 64-bit
Python executable: C:\hostedtoolcache\windows\Python\3.11.9\x64\python.exe
pip: 26.1.2
pytest: 9.1.1
PySide6: 6.11.1
Qt runtime: PySide6 6.11.1 runtime exercised successfully offscreen
QT_QPA_PLATFORM: offscreen
PYTHONUTF8: 1
PYTHONHASHSEED: 0
Repository root: D:\a\sozappsql2\sozappsql2\_validation\feature
GitHub head ref: feature/gundemim-agenda-system
GitHub event ref: refs/pull/332/merge
```

Checkout used the exact PR head and `fetch-depth: 0`. The feature worktree was clean before execution.

## 6. Requirements parity

```text
Baseline bytes: 55
Feature bytes: 55
Baseline SHA-256: 1e07f23f98b0ad45f9bd45c63a1788284ca863cfaef3274eedbf4ef5ff6a313c
Feature SHA-256:  1e07f23f98b0ad45f9bd45c63a1788284ca863cfaef3274eedbf4ef5ff6a313c
Byte-for-byte equal: true
Status: PASS
```

## 7. Static reconfirmation

Compile:

```text
python -m compileall -q src tests
absolute exit: 0
status: PASS
```

Exact required 11-file targeted invocation produced:

```text
Tests: 329
Passed: 329
Failures: 0
Errors: 0
Skipped: 0
JUnit duration: 9.440999999999962 seconds
Absolute exit: 0
Status: PASS
```

No node selection, deselection, xfail injection, or reduced file set was used.

Agenda schema smoke:

```text
python tests/smoke_sts_agenda_schema.py
absolute exit: 0
agenda_schema=PASS
schema_version=18
status: PASS
```

The committed smoke covers exact agenda-state schema, composite key, staff FK, indexes, idempotent initialization, empty foreign-key check, integrity `ok`, `staff_agenda_state` existence, and `agenda_items` absence.

Database smoke:

```text
python tests/smoke_sts_database.py
absolute exit: 0
output: ok
status: PASS
```

Both smokes were rerun on the official workflow HEAD.

## 8. Deterministic real schema-18 STS dataset

Fixed runtime time: `2026-07-13 12:00:00`.

The real `STSDatabase` schema initializer created schema 18. Runtime-generated IDs were used for identity assertions.

```text
Responsible personnel A: staff.id 1
Personnel B: staff.id 2
Manager: staff.id 4
Viewer: staff.id 5
Custom role: staff.id 6

Contract A: id 1
Contract B: id 2
Unknown-date contract: id 3
Returned-share contract: id 4
Document-lock contract: id 5
Scope-out contract: id 6
```

Contract A and Contract B both used contract number `DUP`, proving that contract number is presentation metadata, not identity. The seed also included two active platforms, responsible relationships, valid date/status activities, actor/device collisions, unsupported actions/entity types, malformed JSON forms, exact/mixed/leading-zero entity IDs, cutoff and lifecycle boundaries, same-timestamp rows, coexistence sources, and a staff/system-admin numeric collision.

## 9. Repository runtime gate

Real `AgendaSourceRepository`: `PASS`.

Accepted activity log IDs:

```text
3, 4, 5, 20, 21, 22, 25, 26, 27, 28, 29, 30, 31
```

Repository-level skipped IDs:

```text
6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 23, 24
```

The runtime evidence proves:

- exact `TRIM(activity_logs.entity_id)=CAST(contracts.id AS TEXT)` identity;
- duplicate contract numbers did not merge Contract A and B;
- contract-number-only, mixed, nonnumeric, and leading-zero IDs were excluded;
- non-contract entity type was excluded;
- only `contract_updated` and `contract_status_changed` were loaded;
- system, delivery, create, and arbitrary actions were excluded;
- empty, invalid, array, and scalar JSON were fail-closed;
- message/payload text did not infer business meaning;
- exact and older cutoff rows were excluded;
- one-second-newer cutoff row was included;
- same-timestamp rows were ordered by log ID descending;
- datetime and string cutoff behavior matched.

Valid JSON rows with equal scalar values, nested whitelisted values, or only `contract_updated.status` remain legitimate repository sources and are correctly filtered at provider projection level.

## 10. Repository read-only, set-based, and bundle-once evidence

```text
Activity query count: 1
Empty-ID query count: 0
Platform lookup count: 1
Connection total_changes before/after: 221 / 221
Connection in_transaction before/after: false / false
```

SQLite trace contained only the batched platform `SELECT` and one set-based `activity_logs JOIN contracts SELECT`. No INSERT, UPDATE, DELETE, COMMIT, staff/auth lookup, or per-contract N+1 activity query occurred.

One immutable source bundle contained:

```text
Calendar sources: 5
Returned shares: 1
Document locks: 1
Activity sources: 12
```

Every service build loaded the bundle once with exact cutoff `2026-07-05 12:00:00`.

## 11. Activity provider projection and item contract

Real `ActivityAgendaProvider`: `PASS`.

The primary `contract_updated` row produced exactly `completion_date` and `acceptance_date`. It did not produce `status` or `note`. The dedicated `contract_status_changed` row produced only `status`.

Provider-level exclusions passed for equal normalized scalar values, nested objects/collections, `contract_updated.status`, and missing/non-whitelisted fields.

Every produced item matched:

```text
key: activity:activity_log:<log_id>:<field_name>
version: ACTIVITY:<log_id>:<field_name>:<created_at>
provider_code: activity
kind: activity
lifecycle: EVENT
priority: 450
severity: INFO
reason_code: CONTRACT_ACTIVITY
actor_staff_id: None
supports_snooze: False
action_hints: (open_contract,)
```

Field reason text remained `STATUS_CHANGED`, `COMPLETION_DATE_CHANGED`, or `ACCEPTANCE_DATE_CHANGED`. Titles/descriptions, exact contract metadata, event/effective timestamps, and detail payload fields were verified.

## 12. Actor identity limitation and no self-filter

A valid activity row used the same actor display name and device name as the current staff. The source and item remained visible.

```text
actor_staff_id: None
actor_identity_verified: false
staff lookup / guessed identity: none
self-filter: not applied
```

State interaction identity came exclusively from context `staff_id`, never actor or device display text.

## 13. Profile, permission, and scope matrix

Personnel / RESPONSIBLE / view only:

- resolved contract IDs: `1, 3`;
- one personal scope query;
- one source load;
- one platform lookup;
- Activity visible without `edit_contracts`.

Manager / ALL_VISIBLE:

- resolved IDs: `1, 2, 3, 4, 5, 6`;
- one all-visible query;
- one source load;
- duplicate contract-number identities preserved;
- all production providers ran normally.

Viewer / VIEW_ONLY / ALL_VISIBLE:

- `view_contracts` alone enabled Activity;
- returned-share and document-lock items remained disabled without their capabilities.

Custom role:

- role name alone granted no permission;
- explicit `view_contracts` enabled Activity;
- permission removal returned empty before source/provider/state access.

Explicit override:

- personal query count: 0;
- all-visible query count: 0;
- exact override ID `2` loaded;
- only override-scoped Activity was visible.

No-view gate:

```text
result empty
personal/all/source/platform queries: 0
provider is_enabled/build calls: 0
state get/touch calls: 0
```

Context permission snapshots remained the sole capability source.

## 14. EVENT lifecycle, state, and facade

Real lifecycle/state/facade gate: `PASS`.

```text
Initial valid event: event_new
7 days minus 1 second: event_new
Exact 7-day boundary: event_unseen_ttl_expired
Older than 7 but inside 8 days with recent matching seen state: event_seen
Invalid matching seen timestamp: event_seen_timestamp_invalid
```

The real flow proved:

- initial event visible and NEW;
- exact key/version persisted by `mark_seen`;
- seen event visible and not NEW for less than 24 hours;
- exact/older 24-hour seen state hidden;
- source older than 7 but newer than 8 days loaded;
- same source unseen hidden but recent-seen visible;
- exact 8-day cutoff excluded;
- invalid event timestamp fail-closed;
- matching dismissed version hidden;
- plain load/build did not mutate activity or contract rows.

State before explicit interactions contained only the seeded collision row. State after explicit test interactions added only the expected Activity seen and dismissed test rows. The collision row was unchanged.

Activity EVENT snooze was rejected:

```text
supports_snooze: false
exception: AgendaInteractionError
message: Only condition items can be snoozed.
state snooze mutations: 0
```

No snooze, dismiss, or direct-edit Activity action was exposed.

## 15. System-admin fail-closed gate

The production auth path was used: `create_system_admin`, `verify_system_admin_login`, and `build_system_admin_session`.

```text
session id: 0
admin_id: 1
is_admin: true
staff_id: None
profile: SYSTEM
scope: ALL_VISIBLE
```

Normal, injected-permission, and explicit-override system-admin cases all returned safe empty before source/provider/state access:

```text
personal queries: 0
all-visible queries: 0
source loads: 0
platform lookups: 0
all provider is_enabled/build calls: 0/0
state calls: 0
```

`mark_seen`, `snooze`, and `clear_snooze` were rejected before state access. The numeric collision `staff.id == system_admins.id == 1` was present, the collision staff Agenda row remained unchanged, and `admin_id` was never used as `staff_id`.

## 16. Coexistence, priority, and key uniqueness

Real production orchestration: `PASS`.

Observed priority families:

```text
deadline: 1000, 950, 930, 900, 700
returned_share: 850
document_lock: 800
unknown_date: 500
activity: 450
```

Activity followed Unknown Date. Existing higher-priority ordering stayed intact. Bundle and platform lookup counts were each exactly one. There were no duplicate Agenda keys or cross-provider same-contract collisions. A multi-field activity row produced distinct field keys.

## 17. Generic Qt offscreen presentation

Real `QApplication`, `AgendaCompactWidget`, and `AgendaDetailWindow`: `PASS`.

```text
Compact Activity rows: 1
Detail Activity rows: 1
Compact open signal: contract_id 1
Detail open signal: contract_id 1
Tool-window behavior: preserved
Snooze control: absent
Dismiss/direct-edit controls: absent
```

The generic existing contract-navigation signal was reused. No Activity-specific product widget or route was added.

Offscreen PNG evidence was generated:

```text
activity-compact.png
activity-detail.png
```

## 18. Full baseline pytest

Exact baseline: `c52c59ca15756ca0accd0a3910a1e20b9c66c4ea`.

```text
Tests: 1035
Passed: 993
Failures: 42
Errors: 0
Skipped: 0
Duration: 73.66800000000036 seconds
Absolute exit: 1
JUnit valid: true
Infrastructure OK: true
```

Exit `1` represented known test failures, not collection or infrastructure failure.

## 19. Full feature pytest

Exact official workflow HEAD: `eacfd017b710058422c14da29abde88baf19f516`.

```text
Tests: 1099
Passed: 1057
Failures: 42
Errors: 0
Skipped: 0
Duration: 98.71400000000054 seconds
Absolute exit: 1
JUnit valid: true
Infrastructure OK: true
```

Feature contained 64 additional tests, with no new failure or error.

## 20. Exact failure/error differential

```text
Baseline nodes: 42
Feature nodes: 42
feature_only: []
baseline_only: []
feature_only_count: 0
baseline_only_count: 0
Status: PASS
```

The canonical node sets were byte-for-byte logically identical. Exact lists are stored independently in the artifact files:

```text
baseline-failure-nodes.txt
feature-failure-nodes.txt
feature-only-nodes.txt
baseline-only-nodes.txt
full-differential.json
```

The 42 common nodes are the known analysis-builder/analysis-Qt, contract-status widget, share-merge dialog, and share-merge orchestration failures already present in the accepted baseline. None is feature-only.

## 21. Artifact metadata and inventory

Official artifact:

```text
Artifact ID: 8278482381
Name: agenda-stage-04c-v-evidence
Size: 98034 bytes
Digest: sha256:13e24eda30c869c117af54e36dbe0bdc05a171d0474b51f08a4b86941465b3ed
Created: 2026-07-13T12:09:23Z
Expires: 2026-10-11T12:05:01Z
Expired: false
Run ID: 29248508952
Workflow HEAD: eacfd017b710058422c14da29abde88baf19f516
```

Inventory includes environment/preflight/materialization/requirements evidence; compile/static/smoke logs and exits; real repository/projection/scope/lifecycle/system-admin/coexistence/Qt/state/SQL evidence; baseline/feature JUnit, summaries and logs; canonical node lists; differential JSON; validation summary; and both Qt PNG files.

`validation-summary.json` reports every mandatory gate as `PASS`, `overall=PASS`, and `errors=[]`.

## 22. Cleanup proof

Temporary PR #332 is closed, draft, and unmerged.

Temporary deletion commits:

```text
Workflow deletion: fa12910566aad6eed0791dfc0905ea2afe55fc54
Validator deletion: aee783e5cc91ee505a0a0bfb111a702e133fee5a
```

After both temporary files were removed and before this document was created, the net file diff from starting HEAD `90aad699...` was empty. Temporary commits remain in ancestry for auditability, but temporary files do not remain in the final tree.

## 23. Final tree requirement

Final comparison base:

```text
90aad699cdbe95b3e3dd692ec7046095785f21c5
```

Accepted final net path:

```text
docs/agenda/AGENDA_STAGE_04C_RUNTIME_VALIDATION.md
```

No product, committed test, requirements, schema, auth, activity-log writer, Qt/UI, or workflow path may remain in the final net diff.

## 24. Final Stage 4C decision

All mandatory static, real-runtime, Qt, full-JUnit, and exact differential gates passed on the official complete Windows checkout.

```text
STAGE 4C STATIC/SOURCE TEST GATE: PASS
STAGE 4C RUNTIME DIFFERENTIAL GATE: PASS
CONTRACT ACTIVITY EVENT PROVIDER: ACCEPTED
CONTRACT-LEVEL ACTIVITY EVENTS: ACCEPTED
SYSTEM/DELIVERY ACTIVITY EVENTS: DEFERRED
ACTOR STAFF ID / SELF FILTERING: DEFERRED
RESPONSIBLE CHANGE ACTIVITY: DEFERRED
NOTE/COMPONENT/CREATE/DELETE ACTIVITY: DEFERRED
DIRECT EVENT DISMISS ACTION: DEFERRED
EVENT SNOOZE SUPPORT: DEFERRED
CORE AGENDA PROVIDER DEVELOPMENT: COMPLETE
CURRENT-MAIN INTEGRATION AUDIT GATE: OPEN
MAIN MERGE GATE: CLOSED
```

## 25. Deferred scope

Still deferred:

- system and delivery activity events;
- note, component, responsible-staff, create, and delete activity;
- actor-principal schema/migration;
- actor/device self-filtering;
- responsible-change activity;
- direct EVENT dismiss action;
- EVENT snooze support;
- document-lock direct action;
- stale-lock policy;
- system-admin operational Agenda;
- current-main integration;
- main merge.

## 26. Current-main integration and Main Merge Gate

Current main was not used as the differential baseline and was not synchronized, merged, rebased, or cherry-picked into the feature branch.

```text
CURRENT-MAIN INTEGRATION AUDIT GATE: OPEN
MAIN MERGE GATE: CLOSED
```

This runtime acceptance is not a recommendation or authorization to merge into main.
