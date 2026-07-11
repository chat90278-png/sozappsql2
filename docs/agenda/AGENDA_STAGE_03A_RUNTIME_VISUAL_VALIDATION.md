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
