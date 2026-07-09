# Analysis Center test merge decision

Base main SHA: `802f883798630405addc3b656528b541e787b50d`

The supplied `tests.zip` was compared path-by-path with current `main` by Git blob SHA.

## Decision summary

- 39 Analysis Center test/smoke/performance files are absent from current main: add the Tur 21 versions.
- 26 general STS smoke files are byte-identical: keep current repo files; do not rewrite them.
- `tests/smoke_sts_database.py` differs: keep current main. It contains schema v17 merge UID, revision, share package and newer index/unique coverage.
- `tests/smoke_sts_latest_schema_manual_file.py` differs: keep current main. It contains current merge UID and share package schema columns.
- Two current-main integration tests were added on this branch:
  - `tests/test_analysis_current_main_integration_qt.py`
  - `tests/test_analysis_current_main_schema.py`

## Production integration boundary

- Tur 21 `analysis_center/` remains the Analysis Center subsystem source of truth.
- The approved compact UI remains the application UI source of truth.
- `src/ui/main_page_analysis_window.py` subclasses the compact window rather than replacing its layout.
- `src/ui/analysis_center_window.py` injects current `export_data` permission before Dashboard Excel export.
- `app.py` only changes its `MainWindow` import route.

Do not overwrite current general STS/share tests with older Tur 21 snapshot copies.
