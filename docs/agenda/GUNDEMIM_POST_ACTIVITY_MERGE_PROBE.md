# Gündemim Post-Activity Merge Probe

- target_branch: `integration/gundemim-after-activity-20260714`
- target_head: `5c6b3e79cbbd194cd776b719f6ea8a6c94e0c7e9`
- source_branch: `integration/gundemim-current-main-20260713`
- source_head: `66681d51877ad09db7379b6bbd7049a7436af1fc`
- merge_base: `e1ed9a66318e19178f132602d3114a97880fa27f`
- merge_exit: `1`

## Unmerged paths
```text
src/services/sts_database.py
src/services/sts_schema_upgrade.py
src/services/sts_schema_upgrade_gate.py
tests/test_sts_schema_upgrade.py
tests/test_sts_schema_upgrade_gate.py
```

## Merge status
```text
A  docs/agenda/AGENDA_FOUNDATION_IMPLEMENTATION_PLAN.md
A  docs/agenda/AGENDA_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_SOURCE_OF_TRUTH_AUDIT.md
A  docs/agenda/AGENDA_STAGE_02A_PERSONAL_CONDITION_ENGINE.md
A  docs/agenda/AGENDA_STAGE_02A_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_02B_APPLICATION_FACADE.md
A  docs/agenda/AGENDA_STAGE_02B_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_03A_PERSONAL_QT_UI.md
A  docs/agenda/AGENDA_STAGE_03A_RUNTIME_VISUAL_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_03B_RETURNED_SHARE_PROVIDER.md
A  docs/agenda/AGENDA_STAGE_03B_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_04A_MULTI_PROFILE_SCOPE.md
A  docs/agenda/AGENDA_STAGE_04A_R1_SYSTEM_ADMIN_IDENTITY.md
A  docs/agenda/AGENDA_STAGE_04A_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_04B_DOCUMENT_LOCK_PROVIDER.md
A  docs/agenda/AGENDA_STAGE_04B_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_04C_CONTRACT_ACTIVITY_PROVIDER.md
A  docs/agenda/AGENDA_STAGE_04C_R1_EXECUTION_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_04C_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_05B_CONTROLLED_INTEGRATION.md
A  docs/agenda/AGENDA_TRANSACTION_DECISION.md
A  src/domain/agenda/__init__.py
A  src/domain/agenda/activity.py
A  src/domain/agenda/constants.py
A  src/domain/agenda/deadline_stage.py
A  src/domain/agenda/keys.py
A  src/domain/agenda/lifecycle.py
A  src/domain/agenda/models.py
A  src/domain/agenda/presentation.py
A  src/domain/agenda/priority.py
A  src/domain/agenda/providers/__init__.py
A  src/domain/agenda/providers/activity.py
A  src/domain/agenda/providers/base.py
A  src/domain/agenda/providers/deadline.py
A  src/domain/agenda/providers/document_lock.py
A  src/domain/agenda/providers/returned_share.py
A  src/domain/agenda/providers/unknown_date.py
A  src/domain/agenda/source_models.py
A  src/services/agenda_context_factory.py
A  src/services/agenda_source_repository.py
A  src/services/agenda_state_repository.py
A  src/services/personal_agenda_facade.py
A  src/services/staff_agenda_service.py
UU src/services/sts_database.py
UU src/services/sts_schema_upgrade.py
UU src/services/sts_schema_upgrade_gate.py
A  src/ui/agenda_compact_widget.py
A  src/ui/agenda_detail_window.py
M  src/ui/main_page_analysis_window.py
A  tests/smoke_sts_agenda_schema.py
M  tests/smoke_sts_database.py
A  tests/test_activity_agenda_provider.py
A  tests/test_agenda_compact_widget.py
A  tests/test_agenda_context_factory.py
A  tests/test_agenda_current_main_composition.py
A  tests/test_agenda_deadline_stage.py
A  tests/test_agenda_detail_window.py
A  tests/test_agenda_keys.py
A  tests/test_agenda_lifecycle.py
A  tests/test_agenda_models.py
A  tests/test_agenda_presentation.py
A  tests/test_agenda_schema_v18_integration.py
A  tests/test_agenda_source_repository.py
A  tests/test_agenda_startup_upgrade_integration.py
A  tests/test_agenda_state_repository.py
A  tests/test_deadline_agenda_provider.py
A  tests/test_document_lock_agenda_provider.py
A  tests/test_main_page_agenda_integration.py
A  tests/test_personal_agenda_facade.py
A  tests/test_returned_share_agenda_provider.py
A  tests/test_staff_agenda_service.py
A  tests/test_sts_database_transactions.py
UU tests/test_sts_schema_upgrade.py
UU tests/test_sts_schema_upgrade_gate.py
A  tests/test_unknown_date_agenda_provider.py
?? merge-probe.md
```
