# Gündemim Stage 2A Runtime Validation

## Scope

This gate validates the isolated Stage 2A personal condition engine implementation: personal calendar source models and repository, generic Agenda lifecycle engine, Deadline provider, UnknownDate provider, StaffAgendaService orchestration, AgendaResult extension, and the Stage 2A plus foundation test modules.

## Validated Refs

- accepted Stage 1 baseline SHA: `1cf01400611aa4d0cee9391278664d9b931a4bf5`
- Stage 2A validation head SHA: `29e26157cc32261af634b07ac1e88c3b3472dd85`
- current main observed SHA: `6e33567a9ea390655629a065b023de71feda7364`
- temporary validation PR: `#318`
- workflow name: `Gundemim Stage 2A Runtime Validation`
- workflow run id: `29144853668`
- workflow run conclusion: `success`
- job id: `86524536561`
- job name: `validate-stage2a`
- job conclusion: `success`

## Environment

- execution target: GitHub Actions
- runner OS: `Microsoft Windows Server 2025` / `10.0.26100` / `Datacenter`
- runner image: `windows-2025-vs2026`, version `20260628.158.1`
- Python: `CPython 3.11.9`
- `QT_QPA_PLATFORM=offscreen`
- `PYTHONUNBUFFERED=1`
- `PIP_DISABLE_PIP_VERSION_CHECK=1`
- observed token permission: `Contents: read`; metadata read was also reported by the runner

The exact PR feature source was materialized before Setup Python. Setup Python ran without `cache` or `cache-dependency-path`.

## Exact SHA / Requirements

- baseline expected SHA: `1cf01400611aa4d0cee9391278664d9b931a4bf5`
- baseline actual SHA: `1cf01400611aa4d0cee9391278664d9b931a4bf5`
- baseline SHA match: PASS
- feature expected SHA: `29e26157cc32261af634b07ac1e88c3b3472dd85`
- feature actual SHA: `29e26157cc32261af634b07ac1e88c3b3472dd85`
- feature SHA match: PASS
- baseline/feature `requirements.txt` byte parity: PASS
- `REQUIREMENTS_MATCH=1`

## Targeted Runtime

### Compile

`python -m compileall -q src tests`

- exit: `0`
- result: PASS
- captured output: empty

### Stage 2A + Foundation Targeted Suite

The real feature checkout ran:

`python -m pytest -q tests/test_agenda_lifecycle.py tests/test_agenda_source_repository.py tests/test_deadline_agenda_provider.py tests/test_unknown_date_agenda_provider.py tests/test_staff_agenda_service.py tests/test_sts_database_transactions.py tests/test_agenda_keys.py tests/test_agenda_deadline_stage.py tests/test_agenda_models.py tests/test_agenda_state_repository.py`

- exit: `0`
- result: PASS
- exact pytest summary: `127 passed in 11.03s`

### Agenda Schema Smoke

`python tests/smoke_sts_agenda_schema.py`

- exit: `0`
- result: PASS
- exact output:
  - `agenda_schema=PASS`
  - `schema_version=18`

### Existing STS Database Smoke

`python tests/smoke_sts_database.py`

- exit: `0`
- result: PASS
- exact output: `ok`

## Full Pytest Absolute Results

### Baseline

- pytest exit: `1`
- JUnit tests: `719`
- JUnit failures: `42`
- JUnit errors: `0`
- JUnit skipped: `0`
- JUnit time: `63.76`
- raw pytest summary: `42 failed, 677 passed in 63.85s (0:01:03)`

### Feature

- pytest exit: `1`
- JUnit tests: `787`
- JUnit failures: `42`
- JUnit errors: `0`
- JUnit skipped: `0`
- JUnit time: `61.758`
- raw pytest summary: `42 failed, 745 passed in 61.85s (0:01:01)`

Both absolute suites remain explicitly non-zero. The isolated regression decision is based on the exact same-environment JUnit failure-node differential, not on hiding either absolute result.

## Failure Node Differential

Failure identity is `<classname>::<name>` and includes both JUnit `failure` and `error` testcase nodes.

- baseline failure node count: `42`
- feature failure node count: `42`
- shared failure node count: `42`
- baseline-only failure node count: `0`
- feature-only failure node count: `0`
- feature-only details: NONE

All feature failing nodes were already present in the exact accepted Stage 1 baseline. Stage 2A introduced no new failing test node.

## Artifact Evidence

- artifact id: `8246426747`
- artifact name: `gundemim-stage2a-runtime-validation`
- size: `45301` bytes
- expired: `false`
- digest: `sha256:f8e5018f726f57ed60570d1864def014839bef72a49143127e0c522d61b0e92f`
- parsed files:
  - `stage2a-summary.json`
  - `stage2a-targeted.txt`
  - `agenda-schema-smoke.txt`
  - `sts-db-smoke.txt`
  - `feature-compile.txt`
  - `baseline.xml`
  - `feature.xml`
  - `baseline.txt`
  - `feature.txt`

`stage2a-summary.json` is the authoritative structured evidence for exact SHAs, requirements parity, command exits, JUnit totals, failure-node sets, and gate result.

## Result

PASS

The exact accepted Stage 1 baseline and exact Stage 2A feature validation head were materialized and verified in the same Windows/Python/Qt/dependency environment. Compile, the real Stage 2A plus foundation targeted suite, Agenda schema smoke, and existing STS database smoke passed. Both full suites produced parseable JUnit evidence and `FEATURE_ONLY_FAILURE_NODE_COUNT=0`. The validation script returned `GATE=PASS` and the workflow completed successfully.

## Provider / Engine Development Gate

Stage 2A accepted. Further isolated provider/engine development may proceed.

This approval applies only to `feature/gundemim-agenda-system` and does not authorize integration to `main`.

## Main Merge Gate

CLOSED.

## Integration Risk

- current main has advanced after the feature base;
- current main contains the automatic STS schema upgrade engine;
- feature schema 18 must later be reconciled as an explicit v17→v18 migration and fingerprint contract;
- current main must be treated as the integration baseline;
- final current-main-vs-integrated-feature differential validation is required;
- this document does not authorize merge.
