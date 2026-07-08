# AŞAMA 20 — Windows RC Smoke Report

## Environment

- Required environment: real Windows worktree with working QtWidgets runtime.
- Actual environment: Linux container.
- Python: 3.12.13.
- Platform: `Linux-6.12.47-x86_64-with-glibc2.39`.
- PySide6 import: 6.11.1 OK.
- QtWidgets import: BLOCKED — `ImportError: libGL.so.1: cannot open shared object file: No such file or directory`.

## Baseline

- HEAD: `9e0e68c99ecef9ad1493169206445c85c3c54321`.
- `git diff --check`: passed.
- `python -m pytest -q`: `110 passed, 3 skipped`.

## Qt Test Result

- Not run as Windows RC validation because this is not Windows and QtWidgets cannot import.
- Existing Linux blocker remains the same as AŞAMA 16.

## STS.exe Build / Startup

- Not run.
- Windows `pyinstaller --clean --noconfirm STS.spec` and `dist/STS.exe` startup validation require a real Windows environment.

## Pilot Scenarios

- Normal merge: BLOCKED.
- Conflict: BLOCKED.
- Partial merge: BLOCKED.
- Cancel: BLOCKED.
- Parallel share: BLOCKED.

## File Handle / Crashlog / Perf

- Windows file-handle smoke: BLOCKED.
- STS.exe crashlog/perf inspection: BLOCKED.

## Patch

- Production patch: none.
- Build artifacts: none committed.

## RC Readiness

- RC READY: NO.
- Reason: AŞAMA 20 explicitly requires real Windows + working QtWidgets runtime. This Linux container is missing `libGL.so.1`, so Qt widget tests, STS.exe build/startup, icon/taskbar/AppUserModelID behavior, file-handle smoke, and five pilot scenarios cannot be validated here.
