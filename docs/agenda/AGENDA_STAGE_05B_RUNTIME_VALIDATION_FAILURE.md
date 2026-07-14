# Agenda Stage 5B-V Runtime Validation Failure

- baseline_main: `9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`
- product_candidate: `bbfc14292c8239221f992c228515008f9504f171`
- control_head: `64f814fa53ca9c7803adb9dd43d1889f24709176`
- guard: `success`
- install: `success`
- compile: `success`
- baseline_full: `success`
- candidate_targeted: `success`
- candidate_full: `success`
- runtime_validator: `failure`
- finalize: `skipped`

## guard.log tail
```text
From https://github.com/chat90278-png/sozappsql2
 * branch            main       -> FETCH_HEAD
 * branch            integration/gundemim-after-activity-20260714 -> FETCH_HEAD
Preparing worktree (detached HEAD 9ec9bde)
HEAD is now at 9ec9bde Merge pull request #336 from chat90278-png/feature/activity-history-redesign
Preparing worktree (detached HEAD bbfc142)
HEAD is now at bbfc142 Merge Gündemim Agenda after Activity History with schema v19
control_head=64f814fa53ca9c7803adb9dd43d1889f24709176
baseline=9ec9bded1a51fd6d4cf94e9f20f36134a709aebe
candidate=bbfc14292c8239221f992c228515008f9504f171
```

## install.log tail
```text
Requirement already satisfied: pip in C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages (26.1.2)
Collecting pytest
  Downloading pytest-9.1.1-py3-none-any.whl.metadata (7.6 kB)
Collecting pytest-qt
  Downloading pytest_qt-4.5.0-py3-none-any.whl.metadata (7.9 kB)
Collecting PySide6==6.11.1 (from -r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 1))
  Downloading pyside6-6.11.1-cp310-abi3-win_amd64.whl.metadata (5.5 kB)
Collecting openpyxl==3.1.5 (from -r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 2))
  Downloading openpyxl-3.1.5-py2.py3-none-any.whl.metadata (2.5 kB)
Collecting PyInstaller==6.21.0 (from -r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 3))
  Downloading pyinstaller-6.21.0-py3-none-win_amd64.whl.metadata (8.5 kB)
Collecting shiboken6==6.11.1 (from PySide6==6.11.1->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 1))
  Downloading shiboken6-6.11.1-cp310-abi3-win_amd64.whl.metadata (2.5 kB)
Collecting PySide6_Essentials==6.11.1 (from PySide6==6.11.1->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 1))
  Downloading pyside6_essentials-6.11.1-cp310-abi3-win_amd64.whl.metadata (3.8 kB)
Collecting PySide6_Addons==6.11.1 (from PySide6==6.11.1->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 1))
  Downloading pyside6_addons-6.11.1-cp310-abi3-win_amd64.whl.metadata (4.2 kB)
Collecting et-xmlfile (from openpyxl==3.1.5->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 2))
  Downloading et_xmlfile-2.0.0-py3-none-any.whl.metadata (2.7 kB)
Collecting altgraph (from PyInstaller==6.21.0->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 3))
  Downloading altgraph-0.17.5-py2.py3-none-any.whl.metadata (7.5 kB)
Collecting packaging>=22.0 (from PyInstaller==6.21.0->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 3))
  Downloading packaging-26.2-py3-none-any.whl.metadata (3.5 kB)
Collecting pefile>=2022.5.30 (from PyInstaller==6.21.0->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 3))
  Downloading pefile-2024.8.26-py3-none-any.whl.metadata (1.4 kB)
Collecting pyinstaller-hooks-contrib>=2026.6 (from PyInstaller==6.21.0->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 3))
  Downloading pyinstaller_hooks_contrib-2026.6-py3-none-any.whl.metadata (16 kB)
Collecting pywin32-ctypes>=0.2.1 (from PyInstaller==6.21.0->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 3))
  Downloading pywin32_ctypes-0.2.3-py3-none-any.whl.metadata (3.9 kB)
Requirement already satisfied: setuptools>=42.0.0 in C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\site-packages (from PyInstaller==6.21.0->-r D:\a\_temp/agenda-stage-05b-v-candidate/requirements.txt (line 3)) (65.5.0)
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
   ---------------------------------------- 168.8/168.8 MB 48.4 MB/s  0:00:03
Downloading pyside6_essentials-6.11.1-cp310-abi3-win_amd64.whl (77.5 MB)
   ---------------------------------------- 77.5/77.5 MB 50.5 MB/s  0:00:01
Downloading shiboken6-6.11.1-cp310-abi3-win_amd64.whl (1.2 MB)
   ---------------------------------------- 1.2/1.2 MB 30.0 MB/s  0:00:00
Downloading pytest-9.1.1-py3-none-any.whl (386 kB)
Downloading pluggy-1.6.0-py3-none-any.whl (20 kB)
Downloading pytest_qt-4.5.0-py3-none-any.whl (37 kB)
Downloading colorama-0.4.6-py2.py3-none-any.whl (25 kB)
Downloading iniconfig-2.3.0-py3-none-any.whl (7.5 kB)
Downloading packaging-26.2-py3-none-any.whl (100 kB)
Downloading pefile-2024.8.26-py3-none-any.whl (74 kB)
Downloading pygments-2.20.0-py3-none-any.whl (1.2 MB)
   ---------------------------------------- 1.2/1.2 MB 64.6 MB/s  0:00:00
Downloading pyinstaller_hooks_contrib-2026.6-py3-none-any.whl (457 kB)
Downloading pywin32_ctypes-0.2.3-py3-none-any.whl (30 kB)
Downloading altgraph-0.17.5-py2.py3-none-any.whl (21 kB)
Downloading et_xmlfile-2.0.0-py3-none-any.whl (18 kB)
Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Installing collected packages: altgraph, typing_extensions, shiboken6, pywin32-ctypes, pygments, pluggy, pefile, packaging, iniconfig, et-xmlfile, colorama, pytest, PySide6_Essentials, pyinstaller-hooks-contrib, openpyxl, pytest-qt, PySide6_Addons, PyInstaller, PySide6

Successfully installed PyInstaller-6.21.0 PySide6-6.11.1 PySide6_Addons-6.11.1 PySide6_Essentials-6.11.1 altgraph-0.17.5 colorama-0.4.6 et-xmlfile-2.0.0 iniconfig-2.3.0 openpyxl-3.1.5 packaging-26.2 pefile-2024.8.26 pluggy-1.6.0 pygments-2.20.0 pyinstaller-hooks-contrib-2026.6 pytest-9.1.1 pytest-qt-4.5.0 pywin32-ctypes-0.2.3 shiboken6-6.11.1 typing_extensions-4.16.0
```

## compile.log tail
```text
/d/a/_temp/agenda-stage-05b-v-baseline /d/a/sozappsql2/sozappsql2
/d/a/sozappsql2/sozappsql2
/d/a/_temp/agenda-stage-05b-v-candidate /d/a/sozappsql2/sozappsql2
/d/a/sozappsql2/sozappsql2
baseline_compile=PASS
candidate_compile=PASS
```

## baseline-full-pytest.log tail
```text
/d/a/_temp/agenda-stage-05b-v-baseline /d/a/sozappsql2/sozappsql2
........................................................................ [  8%]
........................................................................ [ 16%]
........................................................................ [ 25%]
........................................................................ [ 33%]
........................................................................ [ 41%]
........................................................................ [ 50%]
........................................................................ [ 58%]
........................................................................ [ 66%]
........................................................................ [ 75%]
........................................................................ [ 83%]
........................................................................ [ 91%]
.....................................................................    [100%]
861 passed in 82.55s (0:01:22)
/d/a/sozappsql2/sozappsql2
```

## candidate-targeted-pytest.log tail
```text
/d/a/_temp/agenda-stage-05b-v-candidate /d/a/sozappsql2/sozappsql2
........................................................................ [ 11%]
........................................................................ [ 23%]
........................................................................ [ 35%]
........................................................................ [ 46%]
........................................................................ [ 58%]
........................................................................ [ 70%]
........................................................................ [ 82%]
........................................................................ [ 93%]
......................................                                   [100%]
614 passed in 34.25s
agenda_schema=PASS
schema_version=19
ok
/d/a/sozappsql2/sozappsql2
```

## candidate-full-pytest.log tail
```text
/d/a/_temp/agenda-stage-05b-v-candidate /d/a/sozappsql2/sozappsql2
........................................................................ [  5%]
........................................................................ [ 10%]
........................................................................ [ 16%]
........................................................................ [ 21%]
........................................................................ [ 27%]
........................................................................ [ 32%]
........................................................................ [ 38%]
........................................................................ [ 43%]
........................................................................ [ 49%]
........................................................................ [ 54%]
........................................................................ [ 60%]
........................................................................ [ 65%]
........................................................................ [ 71%]
........................................................................ [ 76%]
........................................................................ [ 82%]
........................................................................ [ 87%]
........................................................................ [ 92%]
........................................................................ [ 98%]
.....................                                                    [100%]
1317 passed in 88.64s (0:01:28)
/d/a/sozappsql2/sozappsql2
```

## runtime-validator.log tail
```text
Traceback (most recent call last):
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 718, in main
    _assert_lineage(
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 113, in _assert_lineage
    run.check("candidate_lineage_and_merge_shape", check)
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 35, in check
    value = fn()
            ^^^^
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 110, in check
    run.require(baseline_sha in parents[1:], "current main is not a direct merge parent")
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 46, in require
    raise ValidationFailure(message)
ValidationFailure: current main is not a direct merge parent

```

## finalize.log tail
```text
(no log)
```

# Agenda Stage 5B-V Runtime Differential Evidence

- baseline_main: `9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`
- product_candidate: `bbfc14292c8239221f992c228515008f9504f171`
- observed_main: `9ec9bded1a51fd6d4cf94e9f20f36134a709aebe`
- validator_result: `FAIL`

## Runtime checks

| Check | Status | Detail |
|---|---:|---|
| `exact_git_heads` | **PASS** | baseline=9ec9bded1a51fd6d4cf94e9f20f36134a709aebe; candidate=bbfc14292c8239221f992c228515008f9504f171 |
| `candidate_lineage_and_merge_shape` | **FAIL** | ValidationFailure: current main is not a direct merge parent |

## Error

```text
Traceback (most recent call last):
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 718, in main
    _assert_lineage(
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 113, in _assert_lineage
    run.check("candidate_lineage_and_merge_shape", check)
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 35, in check
    value = fn()
            ^^^^
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 110, in check
    run.require(baseline_sha in parents[1:], "current main is not a direct merge parent")
  File "D:\a\sozappsql2\sozappsql2\tools\validation\agenda_stage_05b_v_runtime_validation.py", line 46, in require
    raise ValidationFailure(message)
ValidationFailure: current main is not a direct merge parent

```
