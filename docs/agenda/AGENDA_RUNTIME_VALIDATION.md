# Gündemim Foundation Runtime Validation

## Attempt 1 — Push Trigger

### Validated Ref

- branch: `feature/gundemim-agenda-system`
- VALIDATION_HEAD_SHA: `89c4a484e54208cb68be0edc17a2fd3952e9688d`
- BASE_SHA: `2931fa267560397d4d849d6365acde504f376775`
- schema version: `18`

### Environment

- execution target: GitHub Actions
- workflow runner configuration: `windows-latest`
- workflow Python configuration: `3.11`
- `QT_QPA_PLATFORM=offscreen`
- actual runner allocation/version details: NOT OBSERVED because the push-triggered workflow run could not be discovered through the available Actions read surface

### Workflow Run

- workflow name: `Gundemim Feature Validation`
- run id: NOT FOUND
- expected head branch: `feature/gundemim-agenda-system`
- expected head SHA: `89c4a484e54208cb68be0edc17a2fd3952e9688d`
- status: NOT OBSERVED
- conclusion: NOT OBSERVED
- created_at: NOT OBSERVED
- updated_at: NOT OBSERVED

The temporary workflow was committed successfully and fetched back from the exact feature ref. Repeated commit-status reads returned no statuses. The available commit-workflow-run connector action is limited to pull-request-triggered runs and returned an empty run list for the validation SHA. Public GitHub Actions HTML fetch through the available web read surface also returned a cache miss. Because this validation task forbids opening a pull request and forbids product/test changes, no alternate PR-context trigger or source mutation was used.

### Commands and Results

`python -m compileall -q src tests`

- RESULT: NOT RUN / NOT OBSERVED
- exact output: unavailable because no matching workflow run/job/log could be discovered

`python -m pytest -q tests/test_sts_database_transactions.py tests/test_agenda_keys.py tests/test_agenda_deadline_stage.py tests/test_agenda_models.py tests/test_agenda_state_repository.py`

- RESULT: NOT RUN / NOT OBSERVED
- exact pytest summary: unavailable because no matching workflow run/job/log could be discovered

`python tests/smoke_sts_agenda_schema.py`

- RESULT: NOT RUN / NOT OBSERVED
- exact output: unavailable; `agenda_schema=PASS` and `schema_version=18` were not runtime-observed in this validation gate

`python tests/smoke_sts_database.py`

- RESULT: NOT RUN / NOT OBSERVED
- exact output: unavailable because no matching workflow run/job/log could be discovered

`python -m pytest -q`

- RESULT: NOT RUN / NOT OBSERVED
- exact pytest summary: unavailable because no matching workflow run/job/log could be discovered

### Transaction Contract Validation

The following runtime contracts remain NOT RUN / NOT OBSERVED in Attempt 1:

- outer transaction active before first write
- standalone commit
- standalone rollback
- outer rollback includes successful inner transaction
- inner SAVEPOINT rollback does not poison outer transaction
- raw outer transaction is not committed by `db.tx()`
- read-only transaction closes after successful exit

No static source review result is promoted to runtime PASS.

### Agenda Foundation Validation

The following runtime validations remain NOT RUN / NOT OBSERVED in Attempt 1:

- deterministic agenda key encoding
- deadline stage boundaries and stable mapping
- immutable-facing agenda model snapshots
- agenda state repository persistence behavior
- agenda repository outer transaction rollback
- agenda schema version 18
- `agenda_items` table absence in a runtime-created STS database

No static source review result is promoted to runtime PASS.

### Attempt 1 Result

INCOMPLETE

Runtime validation could not be completed because the exact push-triggered GitHub Actions run for `VALIDATION_HEAD_SHA` could not be discovered through the available Actions/status read surface, so no job steps or logs were available as runtime evidence.

## Attempt 2 — Draft PR Pull Request Trigger

### Validated Ref

- branch: `feature/gundemim-agenda-system`
- VALIDATION_HEAD_SHA: `22d9b1094549c170b85ffd3a866e64ef6156e9ed`
- BASE_SHA: `2931fa267560397d4d849d6365acde504f376775`
- schema version: `18`
- validation PR: `#310`

### Environment

- execution target: GitHub Actions
- runner OS observed in job logs: `Microsoft Windows Server 2025` / `10.0.26100` / `Datacenter`
- runner image observed in job logs: `windows-2025-vs2026`, image version `20260628.158.1`
- workflow Python configuration: `3.11`
- exact Python micro version: not extracted because the available decoded-log connector response rendered only the first 110 lines of a 1,532-line job log
- `QT_QPA_PLATFORM=offscreen`
- `PYTHONUNBUFFERED=1`
- observed GitHub token permission: `Contents: read`; metadata read was also reported by the runner

### Workflow Run

- workflow name: `Gundemim PR Runtime Validation`
- run id: `29140724498`
- event: `pull_request` (`fetch_commit_workflow_runs` exposes PR-triggered runs and this run was discovered from the exact validation head SHA after opening PR #310)
- expected head branch: `feature/gundemim-agenda-system`
- validation head SHA: `22d9b1094549c170b85ffd3a866e64ef6156e9ed`
- status: `completed`
- conclusion: `failure`
- run number: `1`
- workflow id: `311101616`
- compact run response created_at: NOT EXPOSED
- compact run response updated_at: NOT EXPOSED
- first observed job-log timestamp: `2026-07-11T05:07:57.3605945Z`
- validation job id: `86513152835`
- validation job name: `validate`
- validation job status: `completed`
- validation job conclusion: `failure`
- compact job response started_at: NOT EXPOSED
- compact job response completed_at: NOT EXPOSED

### Exact Checkout Verification

- checkout action ref observed in logs: `22d9b1094549c170b85ffd3a866e64ef6156e9ed`
- checkout command observed in logs: checkout exact `22d9b1094549c170b85ffd3a866e64ef6156e9ed`
- checkout log observed: `HEAD is now at 22d9b10 ci: add temporary PR validation for gundemim foundation`
- `checked_out_sha`: `22d9b1094549c170b85ffd3a866e64ef6156e9ed`
- `expected_head_sha`: `22d9b1094549c170b85ffd3a866e64ef6156e9ed`
- VALIDATION_HEAD_SHA: `22d9b1094549c170b85ffd3a866e64ef6156e9ed`
- verification step conclusion: `success`
- match: PASS

The decoded-log connector response rendered the first 110 lines only; the literal `checked_out_sha=` / `expected_head_sha=` print lines were outside that rendered slice. The exact values above are established by the checkout ref and checkout command/log together with the successful verification step, whose PowerShell script throws on inequality.

### Commands and Results

`python -m compileall -q src tests`

- RESULT: PASS
- GitHub Actions step conclusion: `success`
- exact command output: no compile error was reported; the exact log slice for this step was outside the connector-rendered first 110 lines

`python -m pytest -q tests/test_sts_database_transactions.py tests/test_agenda_keys.py tests/test_agenda_deadline_stage.py tests/test_agenda_models.py tests/test_agenda_state_repository.py`

- RESULT: PASS
- GitHub Actions step conclusion: `success`
- exact pytest summary/count/duration: not extractable from the connector-rendered first 110 lines of the 1,532-line decoded job log
- failed tests observed by step conclusion: none
- traceback observed: none

`python tests/smoke_sts_agenda_schema.py`

- RESULT: PASS
- GitHub Actions step conclusion: `success`
- runtime assertions in the smoke completed successfully, including schema version 18 and `agenda_items` absence
- exact terminal output lines were outside the connector-rendered first 110 lines; no output text is fabricated

`python tests/smoke_sts_database.py`

- RESULT: PASS
- GitHub Actions step conclusion: `success`
- exact terminal output was outside the connector-rendered first 110 lines; no output text is fabricated

`python -m pytest -q`

- RESULT: FAIL
- GitHub Actions step conclusion: `failure`
- exact pytest passed/failed/error/skipped/xfailed/xpassed counts: not extractable from the connector-rendered first 110 lines of the 1,532-line decoded job log
- duration: not extractable from the rendered log slice
- failing test names: not extractable from the rendered log slice
- first relevant traceback/error: not extractable from the rendered log slice
- classification: code/test regression layer; exact failing test/root cause remains unclassified because the pytest tail and traceback were not rendered by the available decoded-log connector response

The workflow failure is not classified as setup, dependency, checkout, compile, targeted agenda/transaction, agenda schema smoke, or existing STS database smoke failure because all of those steps completed with `success`. No product or test source was changed after the failure.

### Transaction Runtime Contract

The targeted transaction and agenda pytest step completed with `success`. The seven transaction regression tests have no conditional skip gate in their source, so the following runtime contracts are PASS in Attempt 2:

- PASS — outer transaction active before first write
- PASS — standalone commit
- PASS — standalone rollback
- PASS — outer rollback includes successful inner transaction
- PASS — inner SAVEPOINT rollback does not poison outer transaction
- PASS — raw outer transaction is not committed by `db.tx()`
- PASS — read-only transaction closes after successful exit

### Agenda Foundation Runtime Contract

The targeted pytest and agenda schema smoke steps both completed with `success`:

- PASS — deterministic agenda key encoding
- PASS — deadline stage boundaries and stable mapping
- PASS — immutable-facing agenda model snapshots
- PASS — agenda state repository persistence behavior
- PASS — agenda repository outer transaction rollback
- PASS — agenda schema version 18 runtime assertions
- PASS — `agenda_items` table absence in a runtime-created STS database

### Attempt 2 Result

FAIL

The exact feature-head SHA was checked out and verified successfully. Compile, targeted transaction/agenda tests, agenda schema smoke, and the existing STS database smoke all passed on the GitHub Actions Windows runner. The full pytest regression step failed, so the runtime gate cannot pass. The available decoded-log connector response rendered only the first 110 of 1,532 lines and did not expose the pytest failure tail; therefore failing test names, counts, duration, and traceback are not guessed.

## Attempt 3 — Full Pytest Failure Diagnostic

### Diagnostic Ref

- branch: `feature/gundemim-agenda-system`
- DIAGNOSTIC_HEAD_SHA: `607c096586a7391fe75c70ab561677f5415a7344`
- BASE_SHA: `2931fa267560397d4d849d6365acde504f376775`
- diagnostic PR: `#310`
- schema version: `18`

### Diagnostic Workflow

- workflow name: `Gundemim Full Pytest Diagnostic`
- trigger: `pull_request` activity type `reopened`, base branch `main`
- expected head branch: `feature/gundemim-agenda-system`
- expected head SHA: `607c096586a7391fe75c70ab561677f5415a7344`
- run id: NOT FOUND
- job id: NOT FOUND
- status: NOT OBSERVED
- conclusion: NOT OBSERVED
- artifact id: NOT AVAILABLE because no matching run id was discovered
- artifact name expected: `gundemim-full-pytest-diagnostic`

The standard-library diagnostic script and reopened-PR workflow were created sequentially on the feature branch and fetched back from the exact feature ref before PR #310 was reopened. The workflow creation commit `607c096586a7391fe75c70ab561677f5415a7344` was verified identical to the current feature ref before the PR mutation. PR #310 reopened as a draft, remained unmerged, targeted `main`, and reported head SHA `607c096586a7391fe75c70ab561677f5415a7344`.

Repeated `fetch_commit_workflow_runs` reads for the exact `DIAGNOSTIC_HEAD_SHA` returned an empty workflow run list. A supplementary read using the PR merge SHA also returned an empty run list. The available public GitHub Actions HTML read surface returned a cache miss. No unrelated or historical run was substituted.

### Exact Checkout

- `GUNDEMIM_CHECKOUT_SHA`: NOT OBSERVED
- `GUNDEMIM_EXPECTED_SHA`: `607c096586a7391fe75c70ab561677f5415a7344`
- DIAGNOSTIC_HEAD_SHA: `607c096586a7391fe75c70ab561677f5415a7344`
- match: NOT OBSERVED because no matching diagnostic workflow run/job/log was discovered

### JUnit Summary

- `PYTEST_EXIT_CODE`: NOT OBSERVED
- `PYTEST_TOTAL`: NOT OBSERVED
- `PYTEST_FAILURES`: NOT OBSERVED
- `PYTEST_ERRORS`: NOT OBSERVED
- `PYTEST_SKIPPED`: NOT OBSERVED
- `PYTEST_TIME`: NOT OBSERVED

The sentinel range `GUNDEMIM_PYTEST_DIAG_BEGIN` through `GUNDEMIM_PYTEST_DIAG_END` could not be extracted because no matching run/job log was discoverable. Artifact extraction could not be attempted by run id because no matching diagnostic run id was available.

### Failed Tests

No exact failed or error testcase was extracted in Attempt 3. Test names, failure kinds, messages, traceback evidence, and agenda/transaction relation are therefore not guessed.

### Raw Pytest Final Summary

NOT AVAILABLE. The expected `validation-out/full-pytest.txt` artifact file could not be fetched without a matching workflow run and artifact id.

### Root Cause Status

INCOMPLETE

Attempt 2 remains the last real runtime evidence: the targeted transaction/agenda suite, agenda schema smoke, and existing STS database smoke passed, while the full pytest regression step failed. Attempt 3 did not produce a discoverable `Gundemim Full Pytest Diagnostic` run for `DIAGNOSTIC_HEAD_SHA`, so the exact failing node/count/message/root-cause evidence remains unclassified.

### Manager Gate

Provider/engine development remains blocked pending manager review.

### Attempt 3 Result

DIAGNOSIS INCOMPLETE

## Attempt 4 — Exact Baseline vs Feature Differential Gate

### Manager Gate Decision

For isolated branch regression validation, the absolute full-pytest zero-exit rule is replaced by an exact baseline-vs-feature JUnit failure-node differential. This follows the validated repository precedent documented in `docs/stage_reports/STS_SCHEMA_UPGRADE_ENGINE.md`: the exact baseline and feature are run in the same environment, failure/error testcase identities are compared as `<classname>::<name>`, and an absolute non-zero result does not by itself prove a feature regression when the feature introduces no new failing node.

### Validated Refs

- original BASE_SHA: `2931fa267560397d4d849d6365acde504f376775`
- DIFFERENTIAL_HEAD_SHA: `3c61efcbf8aa55f629b308135d3af6e56b291c7b`
- current main observed SHA: `abb66421e05f8dc76e63c2d8e58d9782782af0ff`
- validation PR: `#316`
- feature branch: `feature/gundemim-agenda-system`
- schema version: `18`

### Environment

- execution target: GitHub Actions
- workflow name: `Gundemim Baseline Differential Validation`
- run id: `29142024367`
- job id: `86516904535`
- run status: `completed`
- run conclusion: `failure`
- job status: `completed`
- job conclusion: `failure`
- runner OS observed in logs: `Microsoft Windows Server 2025` / `10.0.26100` / `Datacenter`
- runner image observed in logs: `windows-2025-vs2026`, image version `20260628.158.1`
- Python observed in setup logs: `CPython 3.11.9`
- `QT_QPA_PLATFORM=offscreen`
- `PYTHONUNBUFFERED=1`
- `PIP_DISABLE_PIP_VERSION_CHECK=1`
- observed GitHub token permission: `Contents: read`; metadata read was also reported by the runner

The workflow failed during `actions/setup-python@v5` cache initialization before repository materialization. The exact setup error was: `No file in D:\a\sozappsql2\sozappsql2 matched to [**/requirements.txt or **/pyproject.toml], make sure you have checked out the target repository`.

### Targeted Foundation Results

- compile: NOT RUN / NOT OBSERVED; `Prepare exact feature source` and the differential gate step were skipped after Setup Python failed
- targeted transaction + agenda tests: NOT RUN / NOT OBSERVED
- agenda schema smoke: NOT RUN / NOT OBSERVED
- existing STS database smoke: NOT RUN / NOT OBSERVED

Attempt 2 remains prior evidence that these targeted foundation commands passed on a Windows GitHub Actions runner, but Attempt 4 does not reuse that earlier SHA as proof for the current `DIFFERENTIAL_HEAD_SHA` gate.

### Full Pytest Absolute Results

BASELINE:

- pytest exit: NOT RUN / NOT OBSERVED
- tests: NOT OBSERVED
- failures: NOT OBSERVED
- errors: NOT OBSERVED
- skipped: NOT OBSERVED
- time: NOT OBSERVED

FEATURE:

- pytest exit: NOT RUN / NOT OBSERVED
- tests: NOT OBSERVED
- failures: NOT OBSERVED
- errors: NOT OBSERVED
- skipped: NOT OBSERVED
- time: NOT OBSERVED

No absolute suite result is labeled PASS or FAIL in Attempt 4 because neither suite reached execution.

### Failure Node Differential

- baseline failure node count: NOT OBSERVED
- feature failure node count: NOT OBSERVED
- shared failure node count: NOT OBSERVED
- baseline-only failure node count: NOT OBSERVED
- feature-only failure node count: NOT OBSERVED
- feature-only details: NOT AVAILABLE

The `GUNDEMIM_DIFF_GATE_BEGIN` / `GUNDEMIM_DIFF_GATE_END` sentinel was never produced because the differential script step was skipped. The artifact upload step ran with `if: always()` but reported that no `validation-out/*.json`, `*.xml`, or `*.txt` files existed; the run artifact list was empty. Therefore `differential-summary.json` and both JUnit files are unavailable.

### Differential Gate Result

INCOMPLETE

Exact reason: the workflow prerequisite failed in Setup Python's pip-cache initialization before exact feature materialization, exact SHA verification, requirements parity runtime verification, targeted checks, baseline JUnit, feature JUnit, and failure-node comparison could run. This is validation infrastructure/orchestration failure, not evidence of a feature-only failing node and not a feature regression classification.

### Main Drift / Integration Note

Current main advanced after the feature's original BASE_SHA and includes the automatic STS schema upgrade engine documented in `docs/stage_reports/STS_SCHEMA_UPGRADE_ENGINE.md`.

Because Attempt 4 is INCOMPLETE:

- isolated provider/engine development remains blocked;
- main merge remains forbidden;
- before any future integration, schema v18 must be reconciled with the current migration registry and fingerprint contract;
- current main must be the new integration baseline;
- final current-main baseline-vs-integrated-feature differential validation is required.

### Attempt 4 Result

INCOMPLETE

## Final Result

INCOMPLETE

## Provider / Engine Development Gate

BLOCKED. Differential runtime evidence is incomplete. Provider/engine development remains blocked pending a completed exact BASE_SHA-vs-feature differential gate.

## Main Integration Gate

Main merge remains forbidden until current-main schema-upgrade reconciliation and final integration validation are completed.
