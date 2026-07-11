# Gündemim Stage 3A Runtime and Visual Validation

## Scope

This validation covered the Stage 3A personal Qt UI without changing product, UI, test, schema, transaction, state SQL, provider, lifecycle or facade source:

- `AgendaCompactWidget`;
- `AgendaDetailWindow`;
- 650 ms seen-dwell interaction;
- condition snooze preset signals;
- main-page status → agenda → calendar integration;
- real offscreen targeted Qt tests;
- 100%, 125% and 150% scale visual probes;
- Agenda and STS database smoke tests;
- accepted Stage 2B versus Stage 3A full-pytest JUnit failure-node differential.

## Validated Refs

- accepted Stage 2B baseline: `0088006620c25a2508cbc3b7885d173bb5662292`
- Stage 3A code head: `85cad2c7f4788a1ae946f98446bf942835cdf0c6`
- Stage 3A validation head: `74bb3fadd7931972a677bec02bcc6c828544cd1e`
- current main observed when the temporary PR was created: `61f72eaf85357f105a15a247c3f2a92da61524b6`
- temporary validation PR: `#321`
- workflow run: `29147862580`
- validation job: `86532366417`

The temporary PR was draft-only and was not authorized for merge.

## Environment

- GitHub Actions hosted runner
- operating system: Microsoft Windows Server 2025, version `10.0.26100`
- runner image: `windows-2025-vs2026`
- image version: `20260628.158.1`
- Python: CPython `3.11.9`
- PySide6: `6.11.1`
- Qt platform: `offscreen`
- workflow permission: `contents: read`
- source materialization occurred before `actions/setup-python`
- setup-python dependency cache was not used

PySide6 import proof completed successfully before the Stage 3A gate script was executed.

## Exact SHA / Requirements

| Check | Expected | Actual | Result |
|---|---|---|---|
| Baseline SHA | `0088006620c25a2508cbc3b7885d173bb5662292` | `0088006620c25a2508cbc3b7885d173bb5662292` | PASS |
| Feature SHA | `74bb3fadd7931972a677bec02bcc6c828544cd1e` | `74bb3fadd7931972a677bec02bcc6c828544cd1e` | PASS |
| `requirements.txt` bytes | equal | equal | PASS |

Both refs used the same requirements blob and dependency environment.

## Targeted Runtime

### Feature compile

```text
python -m compileall -q src tests
```

- exit: `0`
- result: PASS

### Real offscreen Stage 3A + Stage 2B + foundation suite

The exact targeted command covered:

- `tests/test_agenda_compact_widget.py`
- `tests/test_agenda_detail_window.py`
- `tests/test_main_page_agenda_integration.py`
- `tests/test_agenda_context_factory.py`
- `tests/test_agenda_presentation.py`
- `tests/test_personal_agenda_facade.py`
- `tests/test_agenda_lifecycle.py`
- `tests/test_agenda_source_repository.py`
- `tests/test_deadline_agenda_provider.py`
- `tests/test_unknown_date_agenda_provider.py`
- `tests/test_staff_agenda_service.py`
- `tests/test_agenda_state_repository.py`
- `tests/test_sts_database_transactions.py`
- `tests/test_agenda_keys.py`
- `tests/test_agenda_deadline_stage.py`
- `tests/test_agenda_models.py`

Result:

- exit: `0`
- exact summary: `209 passed in 11.09s`

### Agenda schema smoke

- exit: `0`
- output:

```text
agenda_schema=PASS
schema_version=18
```

### Existing STS database smoke

- exit: `0`
- output: `ok`

## Scale Probes

All three visual child processes failed before QApplication construction and before any real widget, geometry, interaction or screenshot check was reached.

The common failure was:

```text
ModuleNotFoundError: No module named 'src'
```

The parent process launched the validation script by its absolute `.github/validation` path from the materialized feature checkout. In that child interpreter, the repository root was not placed on `sys.path`, so the first project import failed. This is a temporary validation-harness import-path bootstrap defect; it is not a failing Stage 3A product/test assertion.

### Scale 100

- requested scale: `1.00`
- child exit: `1`
- result: FAIL
- failure: `ModuleNotFoundError: No module named 'src'`
- QApplication constructed: NO
- device pixel ratio: NOT OBSERVED
- logical DPI: NOT OBSERVED
- compact logical size: NOT OBSERVED
- compact row count: NOT OBSERVED
- compact geometry offenders: NOT EVALUATED
- detail row count: NOT OBSERVED
- Qt.Tool / NonModal / WA_DeleteOnClose: NOT EVALUATED
- dwell before/after counts: NOT EVALUATED
- signal checks: NOT EVALUATED
- MainWindow constructed: NO
- header order: NOT EVALUATED
- PNG files: NONE

### Scale 125

- requested scale: `1.25`
- child exit: `1`
- result: FAIL
- failure: `ModuleNotFoundError: No module named 'src'`
- QApplication constructed: NO
- device pixel ratio: NOT OBSERVED
- logical DPI: NOT OBSERVED
- compact logical size: NOT OBSERVED
- compact row count: NOT OBSERVED
- compact geometry offenders: NOT EVALUATED
- detail row count: NOT OBSERVED
- Qt.Tool / NonModal / WA_DeleteOnClose: NOT EVALUATED
- dwell before/after counts: NOT EVALUATED
- signal checks: NOT EVALUATED
- MainWindow constructed: NO
- header order: NOT EVALUATED
- PNG files: NONE

### Scale 150

- requested scale: `1.50`
- child exit: `1`
- result: FAIL
- failure: `ModuleNotFoundError: No module named 'src'`
- QApplication constructed: NO
- device pixel ratio: NOT OBSERVED
- logical DPI: NOT OBSERVED
- compact logical size: NOT OBSERVED
- compact row count: NOT OBSERVED
- compact geometry offenders: NOT EVALUATED
- detail row count: NOT OBSERVED
- Qt.Tool / NonModal / WA_DeleteOnClose: NOT EVALUATED
- dwell before/after counts: NOT EVALUATED
- signal checks: NOT EVALUATED
- MainWindow constructed: NO
- header order: NOT EVALUATED
- PNG files: NONE

## Screenshot Evidence

Artifact metadata:

- artifact ID: `8247311676`
- artifact name: `gundemim-stage3a-runtime-visual-validation`
- size: `51184` bytes
- expired: `false`
- digest: `sha256:397fdbdd869dd8d175ab93fa6dcf56551eab963d87fbd0d8eb652deecff4b5b8`
- workflow head SHA: `74bb3fadd7931972a677bec02bcc6c828544cd1e`

Artifact files included structured summary, scale JSON/text files, targeted/smoke output and both full-suite JUnit/raw outputs. No PNG file was produced because every visual child stopped at the project import boundary.

Actual image inspection was therefore not possible. No visual approval is claimed.

## Full Pytest Absolute Results

### Accepted Stage 2B baseline

- pytest exit: `1`
- tests: `823`
- failures: `42`
- errors: `0`
- skipped: `0`
- JUnit time: `60.301`
- raw pytest summary: `42 failed, 781 passed in 60.40s (0:01:00)`

### Stage 3A validation feature

- pytest exit: `1`
- tests: `869`
- failures: `42`
- errors: `0`
- skipped: `0`
- JUnit time: `62.397`
- raw pytest summary: `42 failed, 827 passed in 62.49s (0:01:02)`

Both absolute suites remained non-zero and are not described as absolute full-suite passes.

## Failure Differential

Failure identity was `<classname>::<name>`. Both JUnit `failure` and `error` testcase nodes were included.

- baseline failure/error node count: `42`
- feature failure/error node count: `42`
- shared node count: `42`
- baseline-only node count: `0`
- feature-only node count: `0`

### Feature-only nodes

```text
NONE
```

Stage 3A introduced no new failing JUnit node relative to the exact accepted Stage 2B baseline.

## Result

FAIL

Exact refs and requirements parity were proven. Feature compile, the real offscreen targeted suite, Agenda schema smoke, existing STS database smoke and full-suite JUnit differential all completed successfully for their respective gate prerequisites. However, the gate contract requires all 100%, 125% and 150% visual child probes to exit successfully and produce geometry, interaction, MainWindow/header and PNG evidence.

All three visual child processes exited `1` at the repository import boundary. Consequently:

- visual-all-pass is false;
- MainWindow construction is not proven;
- header order is not proven at runtime;
- 112 px scale geometry is not proven;
- 2/20 row visual projection is not proven;
- 650 ms QTest dwell is not proven by the visual child;
- screenshot evidence is absent.

The Stage 3A runtime/visual differential gate is therefore FAIL despite `FEATURE_ONLY_FAILURE_NODE_COUNT=0`.

## Further Isolated Development Gate

Further development remains blocked pending manager review.

The blocker is the temporary validation harness child-import bootstrap, not a demonstrated product regression. A new manager-authorized validation run must add the materialized feature root to the child interpreter import path before importing `src` and must then collect all required scale/PNG/MainWindow evidence.

## Main Merge Gate

CLOSED.

This document does not authorize integration to `main`.

## Integration Risk

- current main has advanced independently of the isolated feature;
- current main contains the automatic STS schema upgrade engine;
- feature schema 18 still requires explicit v17→v18 migration and fingerprint reconciliation before integration;
- a final current-main differential and visual smoke remains mandatory;
- no merge, rebase, update-ref or main write was authorized or performed;
- no product/test/UI source was modified during this validation.

## Attempt 2 — Visual Child Import Bootstrap Retry

### Import Bootstrap Fix

Attempt 2 changed only the temporary validation harness. Before importing PySide6 or any `src` module, every visual child:

- resolved `SCRIPT_PATH = Path(__file__).resolve()`;
- resolved the materialized feature root with `SCRIPT_PATH.parents[2]`;
- removed duplicate root entries and inserted the exact root at `sys.path[0]`;
- changed the working directory to the exact materialized feature root;
- asserted `src`, compact, detail and main-page production paths;
- emitted a `VISUAL_BOOTSTRAP_BEGIN/END` proof block.

The parent process also launched every child with the exact materialized feature root as `cwd` and as the first `PYTHONPATH` entry.

All three scale children recorded:

- bootstrap result: PASS;
- `VISUAL_REPO_ROOT`, `VISUAL_CWD` and `VISUAL_SYS_PATH_0` equal to the exact materialized feature root;
- `VISUAL_SRC_EXISTS=1`;
- `VISUAL_SCRIPT_EXISTS=1`.

### Validated Refs and Run

- accepted Stage 2B baseline: `0088006620c25a2508cbc3b7885d173bb5662292`
- Stage 3A code head: `85cad2c7f4788a1ae946f98446bf942835cdf0c6`
- Attempt 1 cleanup head: `978f733d8ccaa219b6cf0d8b8780df3874dc3c5a`
- Attempt 2 validation head: `2176608f7a7f2ad63172f26d3763394c12a29c83`
- current main observed when the Attempt 2 PR was created: `9e60beca5b33c2b821d5c8f54d88aba74793a5bf`
- temporary draft PR: `#324`
- workflow run: `29149911551`
- validation job: `86537637403`

The temporary PR remained draft-only and was not authorized for merge.

### Environment

- GitHub Actions hosted runner;
- Microsoft Windows Server 2025, version `10.0.26100`;
- runner image `windows-2025-vs2026`;
- image version `20260628.158.1`;
- CPython `3.11.9`;
- PySide6 `6.11.1`;
- Qt platform `offscreen`;
- workflow permission `contents: read`;
- exact feature source was materialized before `actions/setup-python`;
- setup-python dependency cache was not used.

### Exact SHA / Requirements

| Check | Expected | Actual | Result |
|---|---|---|---|
| Baseline SHA | `0088006620c25a2508cbc3b7885d173bb5662292` | `0088006620c25a2508cbc3b7885d173bb5662292` | PASS |
| Feature SHA | `2176608f7a7f2ad63172f26d3763394c12a29c83` | `2176608f7a7f2ad63172f26d3763394c12a29c83` | PASS |
| `requirements.txt` bytes | equal | equal | PASS |

### Targeted Runtime and Smokes

- feature compile exit: `0`;
- real offscreen targeted suite exit: `0`;
- exact targeted summary: `209 passed in 9.63s`;
- Agenda schema smoke exit: `0`;
- Agenda schema output: `agenda_schema=PASS`, `schema_version=18`;
- existing STS database smoke exit: `0`;
- existing STS database smoke output: `ok`.

### Scale 100

- scale: `1.00`;
- bootstrap: PASS;
- child exit: `0`;
- result: PASS;
- QApplication constructed: YES;
- device pixel ratio: `1.0`;
- logical DPI: `96.0`;
- compact logical size: `420 × 112`;
- compact minimum/maximum height: `112`;
- compact rows: `2`;
- 420 px geometry offenders: `0`;
- 250 px geometry offenders: `0`;
- dwell before 500 ms: `0`;
- dwell after total 750 ms: `1`;
- duplicate key/version seen count remained: `1`;
- selection-switch emitted only: `visual:agenda:01`;
- details signal count: `1`;
- compact contract IDs: `[1000]`;
- detail logical size: `760 × 560`;
- detail rows: `20`;
- detail geometry offenders: `0`;
- Qt.Tool: PASS;
- Qt.NonModal: PASS;
- WA_DeleteOnClose: PASS;
- snooze codes: `tomorrow`, `three_days`, `one_week`;
- detail contract IDs: `[1000]`;
- detail dwell before/after: `0 / 1`;
- pending close late-seen count: `0`;
- MainWindow constructed: YES;
- header indices: status `1`, agenda `2`, calendar `3`;
- header order: PASS;
- header logical height: `146`;
- Agenda widget instances: `1`.

PNG evidence:

- `compact-scale-100.png`: `420 × 112`, `2205` bytes;
- `detail-scale-100.png`: `760 × 560`, `8561` bytes;
- `main-header-scale-100.png`: `1472 × 146`, `8982` bytes.

### Scale 125

- scale: `1.25`;
- bootstrap: PASS;
- child exit: `0`;
- result: PASS;
- QApplication constructed: YES;
- device pixel ratio: `1.25`;
- logical DPI: `96.0`;
- compact logical size: `420 × 112`;
- compact rows: `2`;
- compact geometry offenders at both widths: `0`;
- detail logical size: `760 × 560`;
- detail rows: `20`;
- detail geometry offenders: `0`;
- Qt.Tool / NonModal / WA_DeleteOnClose: PASS;
- compact and detail dwell, signal, snooze and close-cancellation checks: PASS;
- MainWindow constructed: YES;
- header indices: status `1`, agenda `2`, calendar `3`;
- header order: PASS;
- header logical height: `146`;
- Agenda widget instances: `1`.

PNG evidence:

- `compact-scale-125.png`: `525 × 140`, `3165` bytes;
- `detail-scale-125.png`: `950 × 700`, `11872` bytes;
- `main-header-scale-125.png`: `1840 × 183`, `12970` bytes.

### Scale 150

- scale: `1.50`;
- bootstrap: PASS;
- child exit: `0`;
- result: PASS;
- QApplication constructed: YES;
- device pixel ratio: `1.5`;
- logical DPI: `96.0`;
- compact logical size: `420 × 112`;
- compact rows: `2`;
- compact geometry offenders at both widths: `0`;
- detail logical size: `760 × 560`;
- detail rows: `20`;
- detail geometry offenders: `0`;
- Qt.Tool / NonModal / WA_DeleteOnClose: PASS;
- compact and detail dwell, signal, snooze and close-cancellation checks: PASS;
- MainWindow constructed: YES;
- header indices: status `1`, agenda `2`, calendar `3`;
- header order: PASS;
- header logical height: `146`;
- Agenda widget instances: `1`.

PNG evidence:

- `compact-scale-150.png`: `630 × 168`, `3510` bytes;
- `detail-scale-150.png`: `1140 × 840`, `14168` bytes;
- `main-header-scale-150.png`: `2208 × 219`, `14935` bytes.

### Screenshot Artifact and Image Inspection

- artifact ID: `8247880760`;
- artifact name: `gundemim-stage3a-runtime-visual-validation-r1`;
- size: `123478` bytes;
- expired: `false`;
- digest: `sha256:b1b80deceb0055014e0e0fba734839a754ab7d7079c4be0c4c31995e2b3fd14d`;
- workflow head SHA: `2176608f7a7f2ad63172f26d3763394c12a29c83`;
- PNG count: `9`.

All PNG files existed, had positive dimensions, exceeded 500 bytes, were non-uniform and were not transparent-only.

Actual image inspection was completed for representative 100%, 125% and 150% compact, detail and main-header screenshots. The compact captures showed the header, two rows and footer without overlap. Detail captures showed the header, scroll-list rows and action controls without geometry overlap. Main-header captures showed the status card before the Agenda card and the calendar after it. The hosted offscreen environment rendered text glyphs as square fallback boxes in the captured images; this was recorded as a runner/font-rendering limitation, not a blank, transparent, uniform or geometry-failing screenshot.

### Full Pytest Absolute Results

Accepted Stage 2B baseline:

- pytest exit: `1`;
- tests: `823`;
- failures: `42`;
- errors: `0`;
- skipped: `0`;
- JUnit time: `52.995`;
- raw summary: `42 failed, 781 passed in 53.10s`.

Attempt 2 feature:

- pytest exit: `1`;
- tests: `869`;
- failures: `42`;
- errors: `0`;
- skipped: `0`;
- JUnit time: `57.509`;
- raw summary: `42 failed, 827 passed in 57.61s`.

Both absolute suites remained non-zero and are not described as absolute full-suite passes.

### JUnit Failure Differential

Failure identity was `<classname>::<name>`. Both `failure` and `error` testcase nodes were included and parameter suffixes were preserved.

- baseline failure/error node count: `42`;
- feature failure/error node count: `42`;
- shared node count: `42`;
- baseline-only node count: `0`;
- feature-only node count: `0`.

Feature-only nodes:

```text
NONE
```

### Attempt 2 Result

PASS.

The visual import bootstrap completed at every scale. Exact refs and requirements parity, feature compile, the real offscreen targeted suite, both smoke tests, all three visual probes, actual MainWindow/header construction, nine PNG checks and the full-pytest JUnit differential all satisfied the R1 gate contract. `FEATURE_ONLY_FAILURE_NODE_COUNT=0`.

## Final Result

PASS.

Attempt 1 remains recorded as FAIL because its visual children stopped at the project import boundary. Attempt 2 supersedes the operational gate decision with complete runtime, geometry, interaction, MainWindow/header, screenshot and JUnit evidence.

## Further Isolated Development Gate

OPEN.

Stage 3A accepted. Further isolated Gündemim provider/scope/UI hardening may proceed.

This approval applies only to `feature/gundemim-agenda-system` and does not authorize integration to `main`.

## Main Merge Gate

CLOSED.

Main integration still requires current-main reconciliation, explicit schema v17→v18 migration and fingerprint support, and a final current-main differential plus visual smoke. No merge authorization is granted by this document.
