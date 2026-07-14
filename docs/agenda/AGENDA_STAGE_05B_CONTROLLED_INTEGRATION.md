# AŞAMA 5B — GÜNDEMİM CONTROLLED CURRENT-MAIN INTEGRATION

Tarih: 2026-07-13

## 1. Exact refs

- Repository: `chat90278-png/sozappsql2`
- Exact current-main base: `e1ed9a66318e19178f132602d3114a97880fa27f`
- Accepted Agenda feature: `b45d6f2e2b2948d1bbf9dcf1f83c8b04386a5c98`
- Original merge base: `2931fa267560397d4d849d6365acde504f376775`
- Integration branch: `integration/gundemim-current-main-20260713`

Main and accepted feature refs were verified unchanged before branch creation. The integration branch was created directly from the exact current-main base.

## 2. Read-only merge analysis

The execution container could not resolve `github.com`, so an exact-object local checkout and native object-level `git merge-tree` could not be completed. The exact GitHub three-way changed-path inventories were materialized into a temporary local Git repository and checked with native `git merge-tree` semantics.

Result:

- direct changed-path overlap: 0
- textual conflict markers: 0
- add/add conflicts: 0
- rename/delete conflicts: 0

This limitation must be rechecked with the exact repository objects before Stage 5B-V acceptance.

## 3. Source provenance strategy

Accepted Agenda documentation, domain, service, standalone UI and established Agenda test files were applied path by path. Exact-copy paths were inserted by their accepted-feature Git blob SHA, avoiding content normalization.

Current-main remained the ancestry source of truth. There was no feature merge, rebase, cherry-pick or history import.

## 4. Commit sequence

1. `c00355edba16c06373c8ef755d9c8063c57ccf32` — `Add accepted Agenda core to current main`
2. `667881fb855d422a3463468bc58e72829f07d57c` — `Integrate Agenda schema version 18 upgrade`
3. `f653239eb78297aa16c191566a8783bae539ad13` — `Integrate Agenda into current main UI`
4. `ee3219faffd09f881b2e8abaad3ebeb11585b22d` — `Add Agenda current-main integration coverage`
5. `Record Stage 5B controlled integration` — this document commit; exact SHA is reported externally after commit creation.

## 5. Exact-copy groups

The following accepted-feature groups were copied by source blob identity:

- all 20 historical `docs/agenda/*` Stage 1–4 and transaction-decision documents;
- all `src/domain/agenda/**` files;
- `agenda_context_factory.py`;
- `agenda_source_repository.py`;
- `agenda_state_repository.py`;
- `personal_agenda_facade.py`;
- `staff_agenda_service.py`;
- `agenda_compact_widget.py`;
- `agenda_detail_window.py`;
- accepted Agenda provider/domain/repository/facade/service/widget tests;
- `tests/smoke_sts_agenda_schema.py`.

Candidate blob parity for these paths is inherited directly from the accepted blob references used in the Git tree commits.

## 6. Current-main preserved paths

No integration commit changed the following current-main paths:

- `app.py`
- `requirements.txt`
- `src/auth.py`
- `src/ui/main_window.py`
- `src/ui/main_page_final_window.py`
- `src/ui/widgets/contract_status_summary.py`
- `src/ui/widgets/corner_menu_layer.py`
- `src/ui/contract/contract_work_window.py`
- `src/workers/sts_load_worker.py`
- current runtime-fix modules
- performance telemetry and monitoring modules

The worker therefore retains the current-main schema-gate import and the current startup/runtime-fix order is unchanged.

## 7. Schema v18 integration implemented in this candidate

The candidate sets `CURRENT_SCHEMA_VERSION = 18` through the accepted Agenda database source and adds an explicit registry step:

`v17_to_v18_staff_agenda_state`

The migration chain is contiguous:

- 14 → 15
- 15 → 16
- 16 → 17
- 17 → 18

The current-main verified backup, `BEGIN IMMEDIATE`, integrity check, foreign-key check, rollback validation and backup-restore fallback behavior were retained in the integration upgrade module.

## 8. Agenda state schema helper

A transaction-neutral `ensure_staff_agenda_state_schema(conn)` helper was added to the schema-upgrade module. It validates:

- parent `staff.id` existence;
- exact state columns;
- exact `(staff_id, agenda_key)` primary-key order;
- exact `staff_id → staff.id ON DELETE CASCADE` foreign key;
- exact state index names and column order;
- absence of `agenda_items`.

It is compatibility-exported onto the imported `sts_database` module when the upgrade layer loads.

Important source deviation: the prompt required the helper to be defined canonically inside `src/services/sts_database.py` and called by `STSDatabase.init_schema()`. In this candidate, fresh/legacy creation remains owned by the accepted Agenda `STSDatabase.init_schema()` DDL while the strict helper owns the explicit 17→18 migration validation. This does not fully satisfy the requested single canonical owner and requires correction before Stage 5B source acceptance.

## 9. V18 structural fingerprint

The fingerprint model was extended with backward-compatible defaults for:

- required primary keys;
- required foreign keys;
- required index column order;
- forbidden tables.

V18 requires:

- `staff.id`;
- exact `staff_agenda_state` columns;
- `idx_staff_agenda_state_staff(staff_id)`;
- `idx_staff_agenda_state_snoozed(staff_id, snoozed_until)`;
- PK `(staff_id, agenda_key)`;
- FK `staff_id → staff.id ON DELETE CASCADE`;
- no `agenda_items`.

Existing `sts_metadata.sts_instance_id` metadata validation is preserved.

## 10. Historical fixture coverage added

`tests/test_agenda_schema_v18_integration.py` includes a genuine v17 fixture pattern:

1. create a realistic current database;
2. drop the state indexes and table;
3. set schema version to 17;
4. assert state table absence;
5. run only the 17→18 migration;
6. validate the v18 fingerprint.

It also covers helper transaction ownership, idempotency, malformed schema rejection, missing parent rejection, state reopen survival, cascade deletion and forbidden-table absence.

## 11. UI composition

The accepted Agenda `main_page_analysis_window.py` was applied over the current-main ancestry. It preserves:

- Analysis Center routing;
- current `CompactMainWindow` base;
- current status widget implementation;
- current corner-menu overlay source;
- Agenda permission visibility;
- debounced refresh;
- file-switch binding reset;
- exact contract-ID navigation;
- startup/share separation through unchanged `app.py`.

Important source deviation: the committed UI source still uses its private `_agenda_detail_window` cache instead of the required stable `agenda:detail` tool-window registry key, and repeated installation is not proven idempotent. These requirements remain incomplete.

## 12. Added coverage

Exact accepted Agenda tests were added, plus:

- `tests/test_agenda_schema_v18_integration.py`
- `tests/test_agenda_current_main_composition.py`
- `tests/test_agenda_startup_upgrade_integration.py`

The new source tests cover schema structure, historical migration construction, current Analysis/Corner routes, header ordering, refresh/navigation hooks, permission fail-closed behavior, file-switch cleanup, worker gate ownership, share startup separation and runtime-fix order.

Important test deviation: the current-main schema test files were not updated from their v17 expectations, and the requested `agenda:detail`/repeated-install assertions were not implemented because the corresponding source adaptation is incomplete.

## 13. Validation execution

The required repository checkout was unavailable in the execution environment because the container could not resolve GitHub. The connector can read and write Git objects but does not provide a runnable full checkout.

Therefore the following required commands were not run on the final candidate:

- `python -m compileall -q src tests`
- exact Stage 5B targeted pytest/JUnit invocation
- `python tests/smoke_sts_agenda_schema.py`
- `python tests/smoke_sts_database.py`
- full candidate pytest/JUnit

Only locally generated standalone integration modules were syntax-compiled before their blobs were created. This is not the official repository compile gate.

## 14. Final diff and safety

Before this document commit, the candidate was four commits ahead of exact main and zero behind, with merge base equal to exact current main. All changed paths were within the Stage 5B write allowlist. No PR, workflow, release, deploy, requirements change, main write or accepted-feature write was made.

## 15. Deferred scope

The following remain deferred:

- system/delivery/responsible/note/component/create/delete activity;
- actor staff-ID self filtering;
- direct EVENT dismiss and EVENT snooze;
- Document Lock direct actions and stale-age policy;
- system-admin operational Agenda;
- unrelated UI redesign;
- release/deploy.

## 16. Gate status

```text
STAGE 5A CURRENT-MAIN INTEGRATION AUDIT: ACCEPTED
STAGE 5B CONTROLLED INTEGRATION SOURCE: INCOMPLETE
SCHEMA V18 INTEGRATION CONTRACT: PARTIALLY IMPLEMENTED
V17 TO V18 MIGRATION: IMPLEMENTED IN SOURCE, NOT RUNTIME VALIDATED
V18 STRUCTURAL FINGERPRINT: IMPLEMENTED IN SOURCE, NOT RUNTIME VALIDATED
UI COMPOSITION INTEGRATION: INCOMPLETE
CURRENT-MAIN RUNTIME FIXES: PRESERVED
STAGE 5B STATIC/SOURCE TEST GATE: NOT RUN
STAGE 5B RUNTIME DIFFERENTIAL ACCEPTANCE: PENDING
STAGE 5B-V INTEGRATION VALIDATION GATE: BLOCKED
MAIN MERGE GATE: CLOSED
```

## Stage 5B-R1 online correction — PASS

- Original candidate: 80b6f927d0c0f3a89e8b2cb7cef603892c60202d
- Canonical Agenda schema owner: src/services/sts_database.py
- Runtime monkey-patch: removed
- Fresh/legacy and explicit 17→18: shared helper
- Agenda detail registry key: genda:detail
- Status/Agenda/timer installation: idempotent
- Compile: PASS
- Schema targeted tests: PASS
- UI targeted tests: PASS
- Full Stage 5B targeted tests: PASS
- Agenda/database smokes: PASS
- Full candidate pytest: PASS
- Stage 5B-V validation gate: OPEN
- Main Merge Gate: CLOSED
