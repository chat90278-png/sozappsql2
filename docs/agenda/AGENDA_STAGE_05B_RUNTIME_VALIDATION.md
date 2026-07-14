# Agenda Stage 5B-V Runtime Differential Evidence

- baseline_main: `9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`
- product_candidate: `bbfc14292c8239221f992c228515008f9504f171`
- observed_main: `9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`
- runtime_evidence_commit: `9f5df9494edb4282b53be0c30df605ca4fa0c259`
- validator_result: `PASS`

## Runtime checks

| Check | Status | Detail |
|---|---:|---|
| `exact_git_heads` | **PASS** | baseline=`9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`; candidate=`bbfc14292c8239221f992c228515008f9504f171` |
| `candidate_lineage_and_merge_shape` | **PASS** | Target parent descends from current main; Agenda source parent=`66681d51877ad09db7379b6bbd7049a7436af1fc` |
| `current_main_critical_file_preservation` | **PASS** | 6 critical current-main files remained byte-identical |
| `static_schema_contract` | **PASS** | Activity History v18 and Gündemim Agenda v19 contracts are both present |
| `startup_worker_gate_order` | **PASS** | schema upgrade gate → `STSStore` verification → worker finished |
| `static_qt_runtime_contract` | **PASS** | status → Agenda → calendar composition and tool-window registry hooks are present |
| `schema_fresh_v19` | **PASS** | Fresh STS creation produced schema v19 with valid fingerprint |
| `schema_real_v18_to_v19_upgrade` | **PASS** | Real v18 fixture upgraded with only `v18_to_v19_staff_agenda_state` and a migration backup |
| `schema_state_persistence_and_staff_cascade` | **PASS** | Agenda state persisted after reopen and was removed by staff cascade |
| `schema_migration_rollback_on_malformed_v18` | **PASS** | Failed migration retained schema v18 and left no partial Agenda indexes |
| `schema_fail_closed_current_and_future` | **PASS** | Malformed current and future schema files were rejected before mutation |
| `qt_status_agenda_calendar_and_idempotency` | **PASS** | Runtime order=`1<2<3`; compact widget count=`1`; Agenda timer count=`1` |
| `qt_single_signal_connections` | **PASS** | Timer timeout and detail-open signals each invoked exactly one receiver |
| `qt_agenda_detail_registry_reuse_and_reopen` | **PASS** | Stable `agenda:detail` registry reuse and close/reopen lifecycle verified |
| `qt_file_switch_reset_cleanup` | **PASS** | Timer, detail, facade, bound DB, snapshot and compact-widget state cleaned |
| `qt_real_facade_refresh` | **PASS** | Real `PersonalAgendaFacade` loaded against the candidate STS database |
| `qt_main_window_close_cleanup` | **PASS** | Main-window close stopped the timer and cleared the detail reference |

## Exact-SHA automated suite gates

- baseline compile: `PASS`
- candidate compile: `PASS`
- baseline main full pytest: `861 passed`
- candidate targeted schema / Agenda / Activity suite: `614 passed`
- candidate Agenda and database smokes: `PASS`
- candidate full pytest: `1317 passed`
- Windows / PySide6 offscreen runtime: `17 checks passed`
- requirements parity: `PASS`
- main modified: `NO`

The automated suites and runtime validator were executed against the immutable baseline and product candidate SHAs recorded above. The initial runtime attempt exposed an over-strict validator assumption about top-level detail windows; after the validator was corrected to inspect the real tool-window registry, all schema and Qt lifecycle checks passed without changing product source files.
