# AŞAMA 18 — Release Cleanup, Dead Code and Excel Import Audit

## Commit Scope Audit

- Checked commit: `27d63bd000c7d7beec54e1b790d41b77f20e56df`.
- Result: commit contains only stage report artifacts:
  - `docs/stage_reports/ASAMA_16_WINDOWS_QT_PILOT.md`
  - `docs/stage_reports/ASAMA_17_PERFORMANCE_CRASH_AUDIT.md`
- `src/services/share_merge_service.py`, `tests/test_share_merge_end_to_end.py`, and `tests/test_share_merge_prepare.py` are not part of `27d63bd`; they are from the previous lifecycle commit / cumulative PR diff view.

## Excel Import Chain Audit

- UI entry point for startup file selection accepts only `.sts` files.
- Application startup rejects non-`.sts` data source paths with the existing Excel-disabled message.
- Share merge file pickers accept only `.sts` share packages.
- No active Excel data-source import action/menu/parser/worker path was found for opening `.xlsx`/`.xls` as product data.
- Existing Excel references are export/report/document attachment/legacy compatibility references, not Excel data import:
  - STS Excel export
  - delivery schedule Excel report export
  - platform delivery report Excel export
  - document attachments with `.xls/.xlsx/.xlsm` extensions
  - legacy `ExcelStore` compatibility imports used by shared UI type paths

## Removal Decision

- Excel data import was already disabled in production startup and no live import call chain was found.
- No production Excel import component was removed because there was no active import chain to delete safely.
- Excel export/report functionality was intentionally preserved.

## Dependency Decision

- `openpyxl` remains required for STS export and Excel report generation.
- PyInstaller `openpyxl` collection remains required for export/report packaging.
- No dependency was removed.

## Share/Lifecycle Dead Code Audit

- `RETURNED` is active production lifecycle state and producer; kept.
- `REJECTED` remains compatibility/final guard status; kept.
- V1 share handling remains legacy compatibility for old share packages; kept.
- No unreachable RETURNED/REJECTED action code or safely removable share helper was proven.

## Error Handling Audit

- Broad/silent exception sites were reviewed around share create, prepare, apply, history, lifecycle cancel, and file export/write paths.
- No measured or test-proven raw traceback leak, expected-error crash logging issue, or sensitive snapshot/BLOB log issue was found in this stage.
- No error-handling production patch was made.

## Tests

- `python -m pytest -q`: `110 passed, 3 skipped`
- `python -m pytest -q tests/test_share_history_presenter.py tests/test_share_history_service.py`: passed
- `python -m pytest -q tests/test_share_merge_apply.py tests/test_share_merge_prepare.py tests/test_share_merge_resolution.py tests/test_share_merge_end_to_end.py`: passed
- `python -m compileall -q app.py src`: passed
- `git diff --check`: passed
- `python -m pytest -q -rs`: `110 passed, 3 skipped`

## Remaining Risk

- AŞAMA 16 Windows/Qt validation remains blocked by the Linux container missing `libGL.so.1`; it still needs a real Windows/Qt runtime.
- Legacy `ExcelStore` compatibility code remains because it is intertwined with shared UI/store type paths and Excel export/report dependencies; removing it would require a separate targeted migration.

## Decision

- AŞAMA 18 PASS: release cleanup audit completed, Excel import was confirmed disabled/no-live-chain, export/report dependencies preserved, and no production cleanup patch was justified beyond this report artifact.
