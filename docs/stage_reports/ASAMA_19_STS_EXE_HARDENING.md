# AŞAMA 19 — STS.exe / PyInstaller Release Hardening

## Build Source of Truth

- Expected HEAD at start: `5593bc1c61daeefcde22fff7416e55b1feb6a5cc`.
- Real build source of truth: `STS.spec`.
- No `SozAppSQL.spec` was found.
- No `main.py` entry point was found; executable entry point is `app.py`.
- Executable name in spec: `STS`.
- Build mode: one-file style `EXE(...)` spec, `console=False` / windowed behavior.
- Recommended build command documented in `README.md`: `pyinstaller --clean --noconfirm STS.spec`.

## Icon, Taskbar and AppUserModelID Audit

- Application startup calls `configure_windows_app_identity()` before creating/showing the main window.
- `configure_windows_app_identity()` is platform guarded for `win32` and sets `APP_ID` through `SetCurrentProcessExplicitAppUserModelID`.
- `QApplication.setWindowIcon(...)` and top-level `MainWindow.setWindowIcon(...)` use `app_icon_path()`.
- Finding: `STS.spec` and runtime config expected `src/ui/assets/sts_icon.ico`, but the repository only had `assets/sts_icon.ico`; additionally that file contained raw PNG bytes under an `.ico` name.
- Patch: converted the existing PNG payload into a valid ICO container and added the expected bundled/runtime icon at `src/ui/assets/sts_icon.ico` while preserving the root asset.

## Frozen Resource Paths

- `STS.spec` bundles `src/ui/assets` into `src/ui/assets`, matching the runtime icon/logo lookup used by `app_icon_path()`.
- No writable runtime data is directed to `_MEIPASS`.
- `.sts` files, merge backups and migration backups remain next to the selected source database / `yedekler` folder.
- Crash logs use the application data/log helper path; performance logs are tied to the `.sts` path/log folder, not bundled resources.

## Qt / PyInstaller Audit

- PyInstaller version in this environment: `6.21.0`.
- PySide6 Qt runtime remains blocked in this Linux container by missing `libGL.so.1`; Windows Qt validation remains open from AŞAMA 16.
- Existing PyInstaller hooks are relied on for PySide6 collection; no broad collect-all rewrite was made.
- `openpyxl` hidden imports remain because Excel export/report functionality still needs them.

## SQLite / File Handle / Onefile Risk

- Static audit found `.sts` paths remain external user-selected files; they are not mixed with onefile extraction paths.
- Backup/temp share export paths are created beside the requested target/source path, not inside the bundle.
- Real Windows file-handle validation cannot be closed in this Linux environment.

## Patch Summary

- Fixed STS icon packaging/runtime availability:
  - `assets/sts_icon.ico`
  - `src/ui/assets/sts_icon.ico`
- Documented the single release build command in `README.md`.
- No core merge, lifecycle, schema or UI workflow semantics changed.

## Checks

- `python -m pytest -q`: baseline `110 passed, 3 skipped`.
- `pyinstaller --version`: `6.21.0`.
- ICO static validation: valid ICO header with PNG payload for both icon paths.
- `STS.spec` syntax compile: passed.
- `python -m py_compile app.py`: passed.
- `main.py`: not present; no main entry point to compile.

## Windows Blocker

- AŞAMA 19 is PARTIAL: static/spec/resource hardening completed, but Windows release validation and actual STS.exe runtime/taskbar/file-handle behavior cannot be marked PASS until run on a real Windows environment with working Qt runtime.
