# AŞAMA 19 — Binary PR Blocker Fix

## Blocker

- Codex PR/merge flow cannot carry binary `.ico` file changes.
- AŞAMA 19 introduced binary icon changes for:
  - `assets/sts_icon.ico`
  - `src/ui/assets/sts_icon.ico`

## Fix

- Removed tracked `.ico` files from the branch.
- Preserved the same valid ICO bytes as text-only base64 source:
  - `src/ui/assets/sts_icon.ico.b64`
- Added `.gitattributes` so removed historical `.ico` paths are diffed as text for numstat instead of binary `- -` markers.

## Build-Time Icon Generation

- `STS.spec` reads `src/ui/assets/sts_icon.ico.b64`.
- The spec decodes it into `build/generated/sts_icon.ico` during PyInstaller analysis.
- The generated `.ico` is used as the `EXE(icon=...)` source.
- Generated build outputs are ignored and are not committed.

## Runtime Window Icon

- Runtime icon lookup now materializes the base64 source into a temp/cache path.
- The source tree and PyInstaller `_MEIPASS` bundle are not used as writable icon output locations.
- Existing `app_icon_path()` API is preserved for QApplication/MainWindow icon setup.
- Windows AppUserModelID behavior was not changed.

## Static Evidence

- `git ls-files | rg '\.ico$'`: no tracked `.ico` files.
- Base64 decode result starts with ICO header `00 00 01 00`.
- `git diff --numstat 08a1989d67dbe507bce1654720d8591148b657b0..HEAD`: text-only numstat after this fix; no binary `- -` marker.
- `STS.spec` syntax compile: passed.

## Tests

- `python -m compileall -q app.py src`: passed.
- `python -m py_compile app.py`: passed.
- `python -m pytest -q`: `110 passed, 3 skipped`.
- `git diff --check`: passed.

## Decision

- Binary PR blocker fixed while preserving the icon fix through text/base64 source and build/runtime generation.
