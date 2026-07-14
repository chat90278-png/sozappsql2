# Agenda Stage 5B-V Isolated Runtime Failure

- baseline_main: `9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`
- product_candidate: `bbfc14292c8239221f992c228515008f9504f171`
- control_head: `04d3f668265253c497c00118c39b0627c9318be6`
- guard: `success`
- install: `success`
- compile: `success`
- runtime: `success`
- finalize: `failure`

## Runtime log tail
```text
Agenda Stage 5B-V PASS: 17 runtime checks
```

# Agenda Stage 5B-V Runtime Differential Evidence

- baseline_main: `9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`
- product_candidate: `bbfc14292c8239221f992c228515008f9504f171`
- observed_main: `9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`
- validator_result: `PASS`

## Runtime checks

| Check | Status | Detail |
|---|---:|---|
| `exact_git_heads` | **PASS** | baseline=9ec9bded1a51fd6d4cf94e9f20f36134a709aebe; candidate=bbfc14292c8239221f992c228515008f9504f171 |
| `candidate_lineage_and_merge_shape` | **PASS** | parents=['187bc9edca699bd01be47f1422914efbcfa56713', '66681d51877ad09db7379b6bbd7049a7436af1fc'] |
| `current_main_critical_file_preservation` | **PASS** | identical=6 files |
| `static_schema_contract` | **PASS** | schema v18 Activity + v19 Agenda contract present |
| `startup_worker_gate_order` | **PASS** | upgrade gate → STSStore verification → finished |
| `static_qt_runtime_contract` | **PASS** | status → Agenda → calendar composition and registry hooks present |
| `schema_fresh_v19` | **PASS** | D:\a\sozappsql2\sozappsql2\evidence\runtime\schema-runtime\fresh\fresh-v19.sts |
| `schema_real_v18_to_v19_upgrade` | **PASS** | backup=real-v18__backup_before_migration_v18_to_v19__2026-07-14_15-31.sts |
| `schema_state_persistence_and_staff_cascade` | **PASS** | persistence=PASS; cascade=PASS |
| `schema_migration_rollback_on_malformed_v18` | **PASS** | schema_version=18; malformed shape preserved; partial indexes absent |
| `schema_fail_closed_current_and_future` | **PASS** | malformed current and future schema rejected before mutation |
| `qt_status_agenda_calendar_and_idempotency` | **PASS** | order=1<2<3; compact=1; timer=1 |
| `qt_single_signal_connections` | **PASS** | timer timeout=1 receiver; open_details=1 receiver |
| `qt_agenda_detail_registry_reuse_and_reopen` | **PASS** | stable registry reuse=PASS; close/reopen=PASS |
| `qt_file_switch_reset_cleanup` | **PASS** | timer/detail/facade/db/snapshot/widget cleanup=PASS |
| `qt_real_facade_refresh` | **PASS** | real PersonalAgendaFacade load=PASS |
| `qt_main_window_close_cleanup` | **PASS** | MainWindow close timer/detail cleanup=PASS |
