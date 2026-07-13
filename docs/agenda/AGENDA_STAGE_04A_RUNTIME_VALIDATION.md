# AGENDA STAGE 04A RUNTIME DIFFERENTIAL VALIDATION

## 1. Tarih ve ortam

- Validation tarihi: **2026-07-13**
- Runner: **GitHub Actions `windows-latest`**
- İşletim sistemi kanıtı: **Windows 10.0.26100 / Windows Server 2025 runner**
- Python: **3.11.9**, MSC v.1938, 64-bit
- pip: **26.1.2**
- pytest: **8.4.2** (yalnız validation environment test aracı)
- PySide6 import/version: **6.11.1**
- Qt: `QT_QPA_PLATFORM=offscreen`

## 2. Repo / branch

- Repo: `chat90278-png/sozappsql2`
- Çalışma branch'i: `feature/gundemim-agenda-system`
- Main/default branch'e write yapılmadı.
- Feature current main ile sync edilmedi; merge/rebase/cherry-pick/force-push yapılmadı.

## 3. Exact ref seti

- Runtime-accepted Stage 3B baseline: `bc5feca2aa755b4e12c98b9932810778ec08d6cb`
- Stage 4A initial source head: `019dca0277df506c6bb300ba9ff15ae7990f5223`
- Exact preflight product/feature SHA: `973c96af0bc431029a0d027ec39dea3e5261e275`
- Successful validation head SHA: `9de74e04c33479e652b15ecff625751b8f68c46b`
- Validation sırasında gözlenen current main SHA: `15cbebc2e3478bf93cd0d1ebda562235d271b8d7`
- Main/feature merge base: `2931fa267560397d4d849d6365acde504f376775`
- Main compare (validation başlangıcı): feature **137 ahead / 22 behind**.
- Successful validation head compare: feature **141 ahead / 22 behind**; artış yalnız temporary validation commitlerinden kaynaklandı.

### Exact R1 compare

`019dca0277df506c6bb300ba9ff15ae7990f5223...973c96af0bc431029a0d027ec39dea3e5261e275`

- Status: `ahead`
- Ahead: `7`
- Behind: `0`
- Total commits: `7`
- Exact changed paths:
  - `src/services/agenda_context_factory.py`
  - `src/services/staff_agenda_service.py`
  - `tests/test_agenda_context_factory.py`
  - `tests/test_staff_agenda_service.py`
  - `tests/test_personal_agenda_facade.py`
  - `docs/agenda/AGENDA_STAGE_04A_MULTI_PROFILE_SCOPE.md`
  - `docs/agenda/AGENDA_STAGE_04A_R1_SYSTEM_ADMIN_IDENTITY.md`

## 4. Temporary validation diff allowlist

Successful validation head ile product ancestor arasındaki exact paths:

- `.github/workflows/agenda-stage-04a-v-runtime-validation.yml`
- `tools/validation/agenda_stage_04a_v_runtime_validation.py`

Başka product/test/schema/auth/UI path'i değiştirilmedi.

## 5. Draft PR ve workflow

- Temporary draft PR: **#328 — `TEMP VALIDATION: Agenda Stage 4A-V`**
- Head: `feature/gundemim-agenda-system`
- Base: `main`
- Merge durumu: **UNMERGED**
- Final PR durumu: **CLOSED / UNMERGED** (cleanup doğrulamasıyla kesinleştirildi)
- Resmî evidence workflow run: **29229958946**
- Workflow URL: `https://github.com/chat90278-png/sozappsql2/actions/runs/29229958946`
- Job ID: `86751822035`
- Artifact ID: `8271212551`
- Artifact digest: `sha256:4a299d053c1188e2bf8f312ff1b27601226116a40045f54457e6946819694c0c`
- Artifact retention expiry: `2026-10-11`

İlk iki attempt validation harness/environment preflight sorunlarıydı:
- Run `29229586123`: temporary validator aktarımı bozuldu; product testleri başlamadı.
- Run `29229873936`: repo requirements parity geçti ancak `pytest` requirements içinde olmadığı için test runner başlamadı.
- Bu iki attempt ürün/runtime sonucu olarak değerlendirilmedi. Temporary harness düzeltildi; product veya mevcut test kaynaklarına dokunulmadı.

## 6. Requirements byte parity

| Ref | Byte length | SHA-256 |
|---|---:|---|
| Baseline | 55 | `1e07f23f98b0ad45f9bd45c63a1788284ca863cfaef3274eedbf4ef5ff6a313c` |
| Feature | 55 | `1e07f23f98b0ad45f9bd45c63a1788284ca863cfaef3274eedbf4ef5ff6a313c` |

Byte-for-byte eşitlik: **PASS**

Tek environment feature `requirements.txt` üzerinden kuruldu. `pytest==8.4.2`, product dependency drift yaratmadan yalnız validation runner aracı olarak aynı environment'a eklendi.

## 7. Compile gate

Komut:

```text
python -m compileall -q src tests
```

- Absolute exit code: `0`
- Sonuç: **PASS**

## 8. Targeted test gate

Komut:

```text
python -m pytest -q tests/test_agenda_context_factory.py tests/test_agenda_source_repository.py tests/test_deadline_agenda_provider.py tests/test_unknown_date_agenda_provider.py tests/test_returned_share_agenda_provider.py tests/test_staff_agenda_service.py tests/test_personal_agenda_facade.py tests/test_agenda_lifecycle.py tests/test_agenda_models.py tests/test_agenda_state_repository.py tests/test_sts_database_transactions.py tests/test_agenda_presentation.py tests/test_agenda_compact_widget.py tests/test_agenda_detail_window.py tests/test_main_page_agenda_integration.py --junitxml=<evidence>/targeted.xml
```

JUnit totals:

| Tests | Passed | Failures | Errors | Skipped | Exit |
|---:|---:|---:|---:|---:|---:|
| 293 | 293 | 0 | 0 | 0 | 0 |

Sonuç: **PASS**

## 9. Real schema-18 capability / scope smoke

Gerçek geçici `.sts`, gerçek `STSDatabase`, production schema initialization, production source repository/context factory/service/provider'ları ve yalnız call-count için delegating spy'lar kullanıldı.

| Senaryo | Profil / Scope | Contract sonucu | Capability / çağrı kanıtı | Sonuç |
|---|---|---|---|---|
| Personnel | `PERSONAL / RESPONSIBLE` | yalnız contract `1` | personal scope 1 kez; all scope 0; source load `[1]` 1 kez; Deadline + Returned Share üretildi | **PASS** |
| Viewer | `VIEW_ONLY / ALL_VISIBLE` | contracts `1,2` | all scope 1; Returned Share `build=0`; Deadline/TBD mevcut | **PASS** |
| Manager | `MANAGEMENT / ALL_VISIBLE` | contracts `1,2` | all scope 1; Deadline/TBD/Returned Share üretildi; source bundle 1 kez | **PASS** |
| Custom role | `PERSONAL / RESPONSIBLE` | yalnız contract `2` | yalnız explicit `view_contracts`; permission sentezi yok; Returned Share `build=0` | **PASS** |
| Explicit override | default scope bypass | yalnız contract `2` | personal scope 0; all scope 0; source load exact `[2]` 1 kez | **PASS** |
| Manager no-view | `MANAGEMENT / ALL_VISIBLE` | empty | source query 0; tüm provider `is_enabled=0`, `build=0`; state 0 | **PASS** |
| Manager view/no-edit | `MANAGEMENT / ALL_VISIBLE` | contracts `1,2` | Deadline/TBD; Returned Share `build=0` | **PASS** |
| Personnel view/no-edit | `PERSONAL / RESPONSIBLE` | contract `1` | Deadline; Returned Share `build=0` | **PASS** |
| Disabled provider | Manager | normal diğer items | disabled provider `is_enabled=1`, `build=0` | **PASS** |

### All-visible source read-only kanıtı

- Exact returned IDs: `[1, 2]`
- `connection.total_changes`: `178` → `178`
- `connection.in_transaction`: `False` → `False`
- SQL trace: yalnız `SELECT id FROM contracts ORDER BY id`
- Commit/insert/update/delete: yok
- Sonuç: **PASS**

### Source bundle exactly once

Manager senaryosunda üç production provider ve bir disabled provider bulunmasına rağmen:
- `load_personal_sources` çağrı sayısı: `1`
- Exact loaded set: `[1, 2]`
- Sonuç: **PASS**

### State flow

- Normal valid staff ID: `1`
- `touch_presented=False`: touch çağrısı `0`
- `touch_presented=True` ve visible item: touch çağrısı `1`, staff ID `1`
- Sonuç: **PASS**

## 10. Exact system-admin fail-closed smoke

Production auth yolu kullanıldı:

- `auth.create_system_admin(...)`
- `auth.verify_system_admin_login(...)`
- `auth.build_system_admin_session(...)`

### Session shape

| Alan | Kanıt |
|---|---|
| `id` | `0` |
| `admin_id` | `1` |
| `is_admin` | `True` |
| `is_active` | `1` |
| `permissions` | gerçek session'da alan yok |

Sonuç: **PASS**

### Numeric collision ve context

Aynı gerçek schema-18 STS içinde:
- `staff.id == 1`
- `system_admins.id == 1`

Production session context:
- profile: `SYSTEM`
- scope: `ALL_VISIBLE`
- `staff_id`: `None`
- `current_staff.id`: `0`
- `current_staff.admin_id`: `1`
- permissions: empty frozenset
- role/is_admin üzerinden permission sentezi: yok

Sonuç: **PASS**

### Fail-closed load matrisi

| Session | Override | Sonuç | Source | Providers | State |
|---|---|---|---|---|---|
| gerçek permissions'sız system-admin | empty | empty | personal/all/load = 0 | enabled/build = 0 | get/touch = 0 |
| injected `view_contracts + edit_contracts` | empty | empty | personal/all/load = 0 | enabled/build = 0 | get/touch = 0 |
| injected permissions | contract `[1]` | empty | personal/all/load = 0 | enabled/build = 0 | get/touch = 0 |

Sonuç: **PASS**

### Interaction fail-closed

Gerçek permissions'sız session ve injected `view_contracts` session için:
- `mark_seen`
- `snooze`
- `clear_snooze`

Toplam altı interaction denemesi `AgendaInteractionError` ile kapandı.

- state `mark_seen` mutation: `0`
- state `snooze` mutation: `0`
- state `clear_snooze` mutation: `0`
- fallback `get_states`: `0`
- `admin_id` herhangi bir state parametresine gitmedi
- Sonuç: **PASS**

### Foreign key proof

`PRAGMA foreign_key_list(staff_agenda_state)` exact relevant row:

```text
[0, 0, "staff", "staff_id", "id", "NO ACTION", "CASCADE", "NONE"]
```

- child: `staff_id`
- parent table: `staff`
- parent column: `id`
- Sonuç: **PASS**

### Collision row integrity

`staff_id=1, agenda_key=collision:seed` satırı system-admin load/interaction senaryolarından önce ve sonra field-equivalent aynı kaldı:

```text
first_presented_at=2026-07-01
last_presented_at=2026-07-02
seen_at=2026-07-03
seen_version=V1
updated_at=2026-07-03
```

Sonuç: **PASS**

## 11. Existing smoke testleri

### Agenda schema smoke

```text
python tests/smoke_sts_agenda_schema.py
```

- Absolute exit code: `0`
- Output: `agenda_schema=PASS`, `schema_version=18`
- Sonuç: **PASS**

### STS database smoke

```text
python tests/smoke_sts_database.py
```

- Absolute exit code: `0`
- Output: `ok`
- Aynı feature runtime environment'ında `CURRENT_SCHEMA_VERSION == 18`
- Sonuç: **PASS**

## 12. Full baseline pytest

Exact ref: `bc5feca2aa755b4e12c98b9932810778ec08d6cb`

```text
python -m pytest -q --junitxml=<evidence>/baseline-full.xml
```

- Absolute exit code: `1`
- Tests: `923`
- Passed: `881`
- Failures: `42`
- Errors: `0`
- Skipped: `0`
- JUnit parse: valid
- Infrastructure exit `2/3/4/5`: yok

### Baseline failure/error node list

- `tests.test_analysis_builder_qt::test_analysis_builder_navigation_and_registry_dataset_options`
- `tests.test_analysis_builder_qt::test_dataset_change_refreshes_field_controls_from_registry`
- `tests.test_analysis_builder_qt::test_filter_row_add_remove_and_operator_options_follow_field_type`
- `tests.test_analysis_builder_qt::test_invalid_form_shows_user_message_without_crash`
- `tests.test_analysis_builder_qt::test_preview_click_uses_real_engine_and_existing_card_renderer`
- `tests.test_analysis_builder_qt::test_refresh_preserves_builder_screen_and_draft_but_clears_stale_preview`
- `tests.test_analysis_builder_qt::test_table_preview_selected_fields_sort_and_limit`
- `tests.test_analysis_builder_qt::test_visualization_mode_updates_visible_controls`
- `tests.test_analysis_excel_export_qt::test_dashboard_excel_action_visible_normal_hidden_edit_and_does_not_refresh_source`
- `tests.test_analysis_excel_export_qt::test_dashboard_excel_worker_keeps_qt_event_loop_responsive`
- `tests.test_analysis_qt_integration::test_analysis_center_pins_live_card_to_persistent_dashboard_without_engine_refresh`
- `tests.test_analysis_qt_integration::test_analysis_center_refresh_preserves_selected_screen`
- `tests.test_analysis_qt_integration::test_analysis_center_window_renders_dashboard_and_tur9_analysis_screens`
- `tests.test_analysis_qt_integration::test_dashboard_auto_scroll_helper_is_bounded_and_canvas_is_idle_safe`
- `tests.test_analysis_qt_integration::test_dashboard_canvas_viewport_resize_changes_pixel_rect_not_logical_layout`
- `tests.test_analysis_qt_integration::test_dashboard_edit_mode_real_mouse_drag_resize_history_and_cancel`
- `tests.test_analysis_qt_integration::test_dashboard_edit_save_persists_and_reset_cancel_restores_saved_layout`
- `tests.test_analysis_qt_integration::test_dashboard_locked_affordances_are_hidden_and_remove_is_undoable`
- `tests.test_analysis_qt_integration::test_dashboard_mouse_preview_does_not_persist_or_reload_analysis_payload`
- `tests.test_analysis_qt_integration::test_dashboard_tur12_edit_chrome_placeholder_and_toolbar_hierarchy`
- `tests.test_analysis_tur17_builder_ux_qt::test_components_group_combo_hides_id_and_uses_semantic_default`
- `tests.test_analysis_tur17_builder_ux_qt::test_count_kpi_preview_uses_integer_default_and_explicit_decimal_is_preserved`
- `tests.test_analysis_tur17_builder_ux_qt::test_form_section_order_panel_width_and_visual_settings_are_collapsible`
- `tests.test_analysis_tur17_builder_ux_qt::test_high_cardinality_donut_shows_guidance_without_mutating_result`
- `tests.test_analysis_tur17_builder_ux_qt::test_preview_card_is_bounded_and_donut_does_not_fill_giant_host`
- `tests.test_analysis_visual_settings_qt::test_chart_settings_preview_uses_palette_legend_values_and_category_transform`
- `tests.test_analysis_visual_settings_qt::test_kpi_visual_settings_apply_subtitle_prefix_suffix_and_decimal`
- `tests.test_analysis_visual_settings_qt::test_saved_visual_settings_hydrate_and_reload_in_builder`
- `tests.test_analysis_visual_settings_qt::test_table_column_order_buttons_change_preview_header_order`
- `tests.test_analysis_visual_settings_qt::test_visual_setting_change_marks_dirty_and_invalidates_old_preview`
- `tests.test_analysis_visual_settings_qt::test_visual_settings_controls_follow_visualization`
- `tests.test_contract_status_summary_widget::test_contract_status_widget_matches_calendar_hover_and_balances_inner_layout`
- `tests.test_contract_status_summary_widget::test_main_page_keeps_calendar_fixed_and_uses_analysis_engine`
- `tests.test_share_merge_dialog::test_dialog_instantiation_unresolved_conflict_and_explicit_decision`
- `tests.test_share_merge_dialog::test_duplicate_submit_busy_guard_and_failure_state`
- `tests.test_share_merge_dialog::test_skip_partial_warning_and_button_state`
- `tests.test_share_merge_window_orchestration::test_active_warning_cancel_and_close_are_no_create_paths`
- `tests.test_share_merge_window_orchestration::test_active_warning_history_choice_reuses_history_callback_and_has_no_create_side_effect`
- `tests.test_share_merge_window_orchestration::test_active_warning_multiple_open_returned_count_uses_active_helper_result`
- `tests.test_share_merge_window_orchestration::test_active_warning_no_active_continues_to_file_picker_without_warning`
- `tests.test_share_merge_window_orchestration::test_active_warning_open_row_is_shown_before_file_picker_and_continue_continues`
- `tests.test_share_merge_window_orchestration::test_active_warning_query_failure_fails_closed_before_file_picker`

## 13. Full feature pytest

Exact successful validation head: `9de74e04c33479e652b15ecff625751b8f68c46b`

```text
python -m pytest -q --junitxml=<evidence>/feature-full.xml
```

- Absolute exit code: `1`
- Tests: `982`
- Passed: `940`
- Failures: `42`
- Errors: `0`
- Skipped: `0`
- JUnit parse: valid
- Infrastructure exit `2/3/4/5`: yok

### Feature failure/error node list

- `tests.test_analysis_builder_qt::test_analysis_builder_navigation_and_registry_dataset_options`
- `tests.test_analysis_builder_qt::test_dataset_change_refreshes_field_controls_from_registry`
- `tests.test_analysis_builder_qt::test_filter_row_add_remove_and_operator_options_follow_field_type`
- `tests.test_analysis_builder_qt::test_invalid_form_shows_user_message_without_crash`
- `tests.test_analysis_builder_qt::test_preview_click_uses_real_engine_and_existing_card_renderer`
- `tests.test_analysis_builder_qt::test_refresh_preserves_builder_screen_and_draft_but_clears_stale_preview`
- `tests.test_analysis_builder_qt::test_table_preview_selected_fields_sort_and_limit`
- `tests.test_analysis_builder_qt::test_visualization_mode_updates_visible_controls`
- `tests.test_analysis_excel_export_qt::test_dashboard_excel_action_visible_normal_hidden_edit_and_does_not_refresh_source`
- `tests.test_analysis_excel_export_qt::test_dashboard_excel_worker_keeps_qt_event_loop_responsive`
- `tests.test_analysis_qt_integration::test_analysis_center_pins_live_card_to_persistent_dashboard_without_engine_refresh`
- `tests.test_analysis_qt_integration::test_analysis_center_refresh_preserves_selected_screen`
- `tests.test_analysis_qt_integration::test_analysis_center_window_renders_dashboard_and_tur9_analysis_screens`
- `tests.test_analysis_qt_integration::test_dashboard_auto_scroll_helper_is_bounded_and_canvas_is_idle_safe`
- `tests.test_analysis_qt_integration::test_dashboard_canvas_viewport_resize_changes_pixel_rect_not_logical_layout`
- `tests.test_analysis_qt_integration::test_dashboard_edit_mode_real_mouse_drag_resize_history_and_cancel`
- `tests.test_analysis_qt_integration::test_dashboard_edit_save_persists_and_reset_cancel_restores_saved_layout`
- `tests.test_analysis_qt_integration::test_dashboard_locked_affordances_are_hidden_and_remove_is_undoable`
- `tests.test_analysis_qt_integration::test_dashboard_mouse_preview_does_not_persist_or_reload_analysis_payload`
- `tests.test_analysis_qt_integration::test_dashboard_tur12_edit_chrome_placeholder_and_toolbar_hierarchy`
- `tests.test_analysis_tur17_builder_ux_qt::test_components_group_combo_hides_id_and_uses_semantic_default`
- `tests.test_analysis_tur17_builder_ux_qt::test_count_kpi_preview_uses_integer_default_and_explicit_decimal_is_preserved`
- `tests.test_analysis_tur17_builder_ux_qt::test_form_section_order_panel_width_and_visual_settings_are_collapsible`
- `tests.test_analysis_tur17_builder_ux_qt::test_high_cardinality_donut_shows_guidance_without_mutating_result`
- `tests.test_analysis_tur17_builder_ux_qt::test_preview_card_is_bounded_and_donut_does_not_fill_giant_host`
- `tests.test_analysis_visual_settings_qt::test_chart_settings_preview_uses_palette_legend_values_and_category_transform`
- `tests.test_analysis_visual_settings_qt::test_kpi_visual_settings_apply_subtitle_prefix_suffix_and_decimal`
- `tests.test_analysis_visual_settings_qt::test_saved_visual_settings_hydrate_and_reload_in_builder`
- `tests.test_analysis_visual_settings_qt::test_table_column_order_buttons_change_preview_header_order`
- `tests.test_analysis_visual_settings_qt::test_visual_setting_change_marks_dirty_and_invalidates_old_preview`
- `tests.test_analysis_visual_settings_qt::test_visual_settings_controls_follow_visualization`
- `tests.test_contract_status_summary_widget::test_contract_status_widget_matches_calendar_hover_and_balances_inner_layout`
- `tests.test_contract_status_summary_widget::test_main_page_keeps_calendar_fixed_and_uses_analysis_engine`
- `tests.test_share_merge_dialog::test_dialog_instantiation_unresolved_conflict_and_explicit_decision`
- `tests.test_share_merge_dialog::test_duplicate_submit_busy_guard_and_failure_state`
- `tests.test_share_merge_dialog::test_skip_partial_warning_and_button_state`
- `tests.test_share_merge_window_orchestration::test_active_warning_cancel_and_close_are_no_create_paths`
- `tests.test_share_merge_window_orchestration::test_active_warning_history_choice_reuses_history_callback_and_has_no_create_side_effect`
- `tests.test_share_merge_window_orchestration::test_active_warning_multiple_open_returned_count_uses_active_helper_result`
- `tests.test_share_merge_window_orchestration::test_active_warning_no_active_continues_to_file_picker_without_warning`
- `tests.test_share_merge_window_orchestration::test_active_warning_open_row_is_shown_before_file_picker_and_continue_continues`
- `tests.test_share_merge_window_orchestration::test_active_warning_query_failure_fails_closed_before_file_picker`

## 14. Differential node analizi

Set semantics:

```text
feature_only = feature_failure_nodes - baseline_failure_nodes
```

- Baseline failure/error node count: `42`
- Feature failure/error node count: `42`
- Feature-only node list: `[]`
- Feature-only count: `0`
- Baseline-only count: `0`
- Sonuç: **PASS**

Feature full exit `1`, yalnız baseline'da da bulunan aynı 42 failure node nedeniyle kabul edildi. Stage 4A feature'a özgü yeni failure/error node yoktur.

## 15. Gate özeti

| Gate | Sonuç |
|---|---|
| Exact preflight refs | **PASS** |
| Temporary diff allowlist | **PASS** |
| Requirements byte parity | **PASS** |
| Feature compile | **PASS** |
| Targeted tests absolute | **PASS** |
| Real schema-18 capability/scope smoke | **PASS** |
| Exact system-admin fail-closed smoke | **PASS** |
| Numeric collision state-integrity | **PASS** |
| Existing schema smoke | **PASS** |
| Existing DB smoke | **PASS** |
| Baseline full JUnit valid | **PASS** |
| Feature full JUnit valid | **PASS** |
| Feature-only failure/error count = 0 | **PASS** |
| Draft PR unmerged | **PASS** |
| Main write yok | **PASS** |
| Temporary cleanup | **PASS** |
| Final tree allowlist | **PASS** |

## 16. Cleanup ve final tree proof

Cleanup tamamlandı:

- Draft PR #328 kapatıldı ve merge edilmedi.
- `.github/workflows/agenda-stage-04a-v-runtime-validation.yml` branch tree'sinden silindi.
- `tools/validation/agenda_stage_04a_v_runtime_validation.py` branch tree'sinden silindi.
- Açık temporary Stage 4A-V PR kalmadı.
- Main SHA işlem öncesi/sonrası `15cbebc2e3478bf93cd0d1ebda562235d271b8d7`; kendi işlemlerimizden kaynaklı main write yok.
- Product base `973c96af0bc431029a0d027ec39dea3e5261e275` ile final feature HEAD arasındaki exact changed path yalnız:
  - `docs/agenda/AGENDA_STAGE_04A_RUNTIME_VALIDATION.md`

## 17. Deferred / blocked alanlar

- System-admin operational Agenda: **DEFERRED**
- ActivityProvider development: **BLOCKED**
- Main integration/merge: bu validation görevinin kapsamı dışında ve gate **CLOSED**
- Baseline'dan taşınan 42 full-suite failure node bu görevde düzeltilmedi; feature-only regression oluşturmadıkları differential JUnit ile kanıtlandı.
- Product source, mevcut test source, schema, migration, auth ve UI üzerinde düzeltme yapılmadı.

## 18. Resmî karar

```text
STAGE 4A RUNTIME DIFFERENTIAL GATE: PASS
PERSONNEL / VIEWER / MANAGEMENT PROFILE FOUNDATION: ACCEPTED
SYSTEM PROFILE PRESENTATION FOUNDATION: ACCEPTED FAIL-CLOSED
SYSTEM-ADMIN OPERATIONAL AGENDA: DEFERRED
DOCUMENT LOCK PROVIDER DEVELOPMENT GATE: OPEN
ACTIVITY PROVIDER DEVELOPMENT GATE: BLOCKED
MAIN MERGE GATE: CLOSED
```
