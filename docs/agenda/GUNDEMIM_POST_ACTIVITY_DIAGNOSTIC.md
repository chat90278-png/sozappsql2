# Gündemim Post-Activity Diagnostic

- target_base_head: `96f191c07c533e167b4395fe869c2c968a8d98c6`
- source_head: `66681d51877ad09db7379b6bbd7049a7436af1fc`
- resolve: `success`
- install: `success`
- compile: `failure`
- targeted: `skipped`

## resolve log tail
```text
From https://github.com/chat90278-png/sozappsql2
 * branch            integration/gundemim-current-main-20260713 -> FETCH_HEAD
 * branch            integration/gundemim-after-activity-20260714 -> FETCH_HEAD
Auto-merging src/services/sts_database.py
CONFLICT (content): Merge conflict in src/services/sts_database.py
Auto-merging src/services/sts_schema_upgrade.py
CONFLICT (content): Merge conflict in src/services/sts_schema_upgrade.py
Auto-merging src/services/sts_schema_upgrade_gate.py
CONFLICT (content): Merge conflict in src/services/sts_schema_upgrade_gate.py
Auto-merging tests/test_sts_schema_upgrade.py
CONFLICT (content): Merge conflict in tests/test_sts_schema_upgrade.py
Auto-merging tests/test_sts_schema_upgrade_gate.py
CONFLICT (content): Merge conflict in tests/test_sts_schema_upgrade_gate.py
Automatic merge failed; fix conflicts and then commit the result.
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
M  src/services/sts_database.py
M  src/services/sts_schema_upgrade.py
M  src/services/sts_schema_upgrade_gate.py
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
A  tests/test_agenda_schema_v19_integration.py
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
M  tests/test_sts_schema_upgrade.py
M  tests/test_sts_schema_upgrade_gate.py
A  tests/test_unknown_date_agenda_provider.py
```

## install log tail
```text
Requirement already satisfied: pip in C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages (26.1.2)
Collecting pytest
  Downloading pytest-9.1.1-py3-none-any.whl.metadata (7.6 kB)
Collecting pytest-qt
  Downloading pytest_qt-4.5.0-py3-none-any.whl.metadata (7.9 kB)
Collecting PySide6==6.11.1 (from -r requirements.txt (line 1))
  Downloading pyside6-6.11.1-cp310-abi3-win_amd64.whl.metadata (5.5 kB)
Collecting openpyxl==3.1.5 (from -r requirements.txt (line 2))
  Downloading openpyxl-3.1.5-py2.py3-none-any.whl.metadata (2.5 kB)
Collecting PyInstaller==6.21.0 (from -r requirements.txt (line 3))
  Downloading pyinstaller-6.21.0-py3-none-win_amd64.whl.metadata (8.5 kB)
Collecting shiboken6==6.11.1 (from PySide6==6.11.1->-r requirements.txt (line 1))
  Downloading shiboken6-6.11.1-cp310-abi3-win_amd64.whl.metadata (2.5 kB)
Collecting PySide6_Essentials==6.11.1 (from PySide6==6.11.1->-r requirements.txt (line 1))
  Downloading pyside6_essentials-6.11.1-cp310-abi3-win_amd64.whl.metadata (3.8 kB)
Collecting PySide6_Addons==6.11.1 (from PySide6==6.11.1->-r requirements.txt (line 1))
  Downloading pyside6_addons-6.11.1-cp310-abi3-win_amd64.whl.metadata (4.2 kB)
Collecting et-xmlfile (from openpyxl==3.1.5->-r requirements.txt (line 2))
  Downloading et_xmlfile-2.0.0-py3-none-any.whl.metadata (2.7 kB)
Collecting altgraph (from PyInstaller==6.21.0->-r requirements.txt (line 3))
  Downloading altgraph-0.17.5-py2.py3-none-any.whl.metadata (7.5 kB)
Collecting packaging>=22.0 (from PyInstaller==6.21.0->-r requirements.txt (line 3))
  Downloading packaging-26.2-py3-none-any.whl.metadata (3.5 kB)
Collecting pefile>=2022.5.30 (from PyInstaller==6.21.0->-r requirements.txt (line 3))
  Downloading pefile-2024.8.26-py3-none-any.whl.metadata (1.4 kB)
Collecting pyinstaller-hooks-contrib>=2026.6 (from PyInstaller==6.21.0->-r requirements.txt (line 3))
  Downloading pyinstaller_hooks_contrib-2026.6-py3-none-any.whl.metadata (16 kB)
Collecting pywin32-ctypes>=0.2.1 (from PyInstaller==6.21.0->-r requirements.txt (line 3))
  Downloading pywin32_ctypes-0.2.3-py3-none-any.whl.metadata (3.9 kB)
Requirement already satisfied: setuptools>=42.0.0 in C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages (from PyInstaller==6.21.0->-r requirements.txt (line 3)) (65.5.0)
Collecting colorama>=0.4 (from pytest)
  Downloading colorama-0.4.6-py2.py3-none-any.whl.metadata (17 kB)
Collecting iniconfig>=1.0.1 (from pytest)
  Downloading iniconfig-2.3.0-py3-none-any.whl.metadata (2.5 kB)
Collecting pluggy<2,>=1.5 (from pytest)
  Downloading pluggy-1.6.0-py3-none-any.whl.metadata (4.8 kB)
Collecting pygments>=2.7.2 (from pytest)
  Downloading pygments-2.20.0-py3-none-any.whl.metadata (2.5 kB)
Collecting typing_extensions (from pytest-qt)
  Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
Downloading pyside6-6.11.1-cp310-abi3-win_amd64.whl (578 kB)
   ---------------------------------------- 578.4/578.4 kB 10.2 MB/s  0:00:00
Downloading openpyxl-3.1.5-py2.py3-none-any.whl (250 kB)
Downloading pyinstaller-6.21.0-py3-none-win_amd64.whl (1.4 MB)
   ---------------------------------------- 1.4/1.4 MB 24.2 MB/s  0:00:00
Downloading pyside6_addons-6.11.1-cp310-abi3-win_amd64.whl (168.8 MB)
   ---------------------------------------- 168.8/168.8 MB 52.6 MB/s  0:00:03
Downloading pyside6_essentials-6.11.1-cp310-abi3-win_amd64.whl (77.5 MB)
   ---------------------------------------- 77.5/77.5 MB 62.6 MB/s  0:00:01
Downloading shiboken6-6.11.1-cp310-abi3-win_amd64.whl (1.2 MB)
   ---------------------------------------- 1.2/1.2 MB 20.5 MB/s  0:00:00
Downloading pytest-9.1.1-py3-none-any.whl (386 kB)
Downloading pluggy-1.6.0-py3-none-any.whl (20 kB)
Downloading pytest_qt-4.5.0-py3-none-any.whl (37 kB)
Downloading colorama-0.4.6-py2.py3-none-any.whl (25 kB)
Downloading iniconfig-2.3.0-py3-none-any.whl (7.5 kB)
Downloading packaging-26.2-py3-none-any.whl (100 kB)
Downloading pefile-2024.8.26-py3-none-any.whl (74 kB)
Downloading pygments-2.20.0-py3-none-any.whl (1.2 MB)
   ---------------------------------------- 1.2/1.2 MB 20.6 MB/s  0:00:00
Downloading pyinstaller_hooks_contrib-2026.6-py3-none-any.whl (457 kB)
Downloading pywin32_ctypes-0.2.3-py3-none-any.whl (30 kB)
Downloading altgraph-0.17.5-py2.py3-none-any.whl (21 kB)
Downloading et_xmlfile-2.0.0-py3-none-any.whl (18 kB)
Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Installing collected packages: altgraph, typing_extensions, shiboken6, pywin32-ctypes, pygments, pluggy, pefile, packaging, iniconfig, et-xmlfile, colorama, pytest, PySide6_Essentials, pyinstaller-hooks-contrib, openpyxl, pytest-qt, PySide6_Addons, PyInstaller, PySide6

Successfully installed PyInstaller-6.21.0 PySide6-6.11.1 PySide6_Addons-6.11.1 PySide6_Essentials-6.11.1 altgraph-0.17.5 colorama-0.4.6 et-xmlfile-2.0.0 iniconfig-2.3.0 openpyxl-3.1.5 packaging-26.2 pefile-2024.8.26 pluggy-1.6.0 pygments-2.20.0 pyinstaller-hooks-contrib-2026.6 pytest-9.1.1 pytest-qt-4.5.0 pywin32-ctypes-0.2.3 shiboken6-6.11.1 typing_extensions-4.16.0
```

## compile log tail
```text
*** Error compiling 'tests\\test_sts_schema_upgrade_gate.py'...
  File "tests\test_sts_schema_upgrade_gate.py", line 241
    "v18_to_v19_staff_agenda_state",
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
SyntaxError: invalid syntax

```

## targeted log tail
```text
(no log)
```
