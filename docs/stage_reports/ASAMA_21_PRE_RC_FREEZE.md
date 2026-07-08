# AŞAMA 21 — Pre-RC Freeze Preparation

## Scope

- Repo-side audit only.
- Windows/Qt/`STS.exe` runtime validation was not attempted and remains a manual Windows task.
- Core merge, lifecycle, and schema v17 behavior were left frozen.
- New feature work was not added.

## Release blocker audit

- `TODO`/`FIXME`, broad exception handlers, debug prints, temporary hooks, production `test_mode`, hardcoded dev paths, missing resources, secrets, merge markers, stale index locks, and duplicate build/spec entries were audited with repository text search and git/file checks.
- Broad exception handlers exist in legacy/UI/export paths, but no new release-blocking data-loss or user-facing crash risk was proven in this stage.
- No unresolved merge markers or stale `.git/index.lock` were found.
- One real repository hygiene blocker was found: tracked Python bytecode under `src/ui/**/__pycache__/` despite `.gitignore` coverage. These generated files were removed from git tracking.

## Version / build metadata audit

- No dedicated application version source was found.
- Startup sets application name/display name to `STS`, but no about/window application version binding was found.
- Schema version remains separate database metadata and is not treated as an application version.
- `STS.spec` is the build source of truth, uses `app.py` as entry point, and names the executable `STS`.
- `README.md` documents the release build command as `pyinstaller --clean --noconfirm STS.spec`.

## Gitignore / build artifact audit

- `.gitignore` covers `/build/`, `/dist/`, `__pycache__/`, and `*.py[cod]`.
- Local generated `__pycache__`/`.pyc` files may exist after tests/compileall, but are ignored.
- `git ls-files | rg '\.ico$'` returned no tracked binary `.ico` files; the AŞAMA 19 text-only icon source remains preserved.
- No tracked `build/` or `dist/` artifact was found.

## Stage report audit

- Existing reports for AŞAMA 16, 17, 18, 19 exe hardening, 19 binary PR fix, and 20 Windows RC smoke are present.
- AŞAMA 16 and AŞAMA 20 correctly leave Windows/Qt validation blocked or pending instead of marking it PASS.
- AŞAMA 17 and AŞAMA 18 report repo-side PASS with the Windows blocker still open.
- AŞAMA 19 reports static/spec/icon hardening and the later text-only binary fix.

## Test matrix summary

- `python -m compileall -q app.py src`: PASS.
- `git diff --check`: PASS.
- `python -m pytest -q`: `110 passed, 3 skipped`.
- `python -m pytest -q -rs`: `110 passed, 3 skipped`.
- Linux Qt skips are not counted as Windows validation PASS:
  - `tests/test_share_history_dialog.py`: PySide6 Qt runtime unavailable because `libGL.so.1` is missing.
  - `tests/test_share_merge_dialog.py`: PySide6 Qt runtime unavailable because `libGL.so.1` is missing.
  - `tests/test_share_merge_window_orchestration.py`: PySide6 Qt runtime unavailable because `libGL.so.1` is missing.

## Repo-side RC readiness

- Repo-side RC readiness: YES, conditional on the documented manual Windows validation.
- Windows manual validation: PENDING.
- Final RC READY is not declared until AŞAMA 20 passes on a real Windows machine.
