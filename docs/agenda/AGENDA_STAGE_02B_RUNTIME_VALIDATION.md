# Gündemim Stage 2B Runtime Validation

## Scope

This validation covers the Stage 2B personal agenda application layer without changing product or test source:

- `PersonalAgendaContextFactory`
- `AgendaPresentationSnapshot` and `project_agenda_result`
- `PersonalAgendaFacade`
- current-staff permission/profile snapshots
- mark-seen interaction
- condition snooze and clear-snooze interactions
- tomorrow / three-days / one-week presets
- compact/detail presentation projection

Qt UI, Activity/Share/Lock providers, schema changes, transaction changes and agenda-state SQL changes were outside this validation scope.

## Validated Refs

- accepted Stage 2A baseline: `8b17332a68468684b6b5cf5393798de8c1425f64`
- Stage 2B validation head: `e040cc9de09751e8b8ca7268e533b6da866dbd8d`
- current main observed when the temporary PR was created: `a2f3923eb21c1aaf2ed3a59b169fb1dae686d5d5`
- temporary validation PR: `#320`
- workflow run: `29146059736`
- validation job: `86527700018`

The temporary PR remained draft and was used only to trigger PR-scoped GitHub Actions validation. It was not authorized for merge.

## Environment

- GitHub Actions hosted runner
- operating system: Microsoft Windows Server 2025
- runner image: `windows-2025-vs2026`
- image version: `20260628.158.1`
- Python: CPython `3.11.9`
- Qt platform: `offscreen`
- workflow permission: `contents: read`

The exact feature source was materialized before `actions/setup-python`. Setup Python used no dependency cache.

## Exact SHA / Requirements

| Check | Expected | Actual | Result |
|---|---|---|---|
| Baseline SHA | `8b17332a68468684b6b5cf5393798de8c1425f64` | `8b17332a68468684b6b5cf5393798de8c1425f64` | PASS |
| Feature SHA | `e040cc9de09751e8b8ca7268e533b6da866dbd8d` | `e040cc9de09751e8b8ca7268e533b6da866dbd8d` | PASS |
| `requirements.txt` bytes | equal | equal | PASS |

Both refs used the same `requirements.txt` content and dependency environment.

## Targeted Runtime

### Compile

```text
python -m compileall -q src tests
```

- exit: `0`
- result: PASS

### Stage 2B + Stage 2A + foundation suite

```text
python -m pytest -q
  tests/test_agenda_context_factory.py
  tests/test_agenda_presentation.py
  tests/test_personal_agenda_facade.py
  tests/test_agenda_lifecycle.py
  tests/test_agenda_source_repository.py
  tests/test_deadline_agenda_provider.py
  tests/test_unknown_date_agenda_provider.py
  tests/test_staff_agenda_service.py
  tests/test_agenda_state_repository.py
  tests/test_sts_database_transactions.py
  tests/test_agenda_keys.py
  tests/test_agenda_deadline_stage.py
  tests/test_agenda_models.py
```

- exit: `0`
- exact summary: `163 passed in 4.13s`

### Agenda schema smoke

```text
python tests/smoke_sts_agenda_schema.py
```

- exit: `0`
- output:

```text
agenda_schema=PASS
schema_version=18
```

### Existing STS database smoke

```text
python tests/smoke_sts_database.py
```

- exit: `0`
- output: `ok`

## Full Pytest Absolute Results

### Accepted Stage 2A baseline

- pytest exit: `1`
- tests: `787`
- failures: `42`
- errors: `0`
- skipped: `0`
- JUnit time: `55.121`
- raw pytest summary: `42 failed, 745 passed in 55.21s`

### Stage 2B feature

- pytest exit: `1`
- tests: `823`
- failures: `42`
- errors: `0`
- skipped: `0`
- JUnit time: `69.108`
- raw pytest summary: `42 failed, 781 passed in 69.19s (0:01:09)`

Both absolute suites remained non-zero. These results are not described as absolute full-suite passes.

## Failure Differential

- baseline failure/error node count: `42`
- feature failure/error node count: `42`
- shared node count: `42`
- baseline-only node count: `0`
- feature-only node count: `0`

### Feature-only nodes

```text
NONE
```

Failure identity was computed as `<classname>::<name>`. Both JUnit `failure` and `error` testcase nodes were included. Parameterized testcase suffixes were preserved by the JUnit testcase name.

The Stage 2B feature introduced no new failing test node relative to the exact runtime-accepted Stage 2A baseline.

## Artifact Evidence

- artifact ID: `8246783645`
- artifact name: `gundemim-stage2b-runtime-validation`
- size: `47177` bytes
- expired: `false`
- digest: `sha256:e9b2e329d50850f4933cb57123061614eb96ea2659dc29ffe34010c9a996a400`

Parsed files:

- `stage2b-summary.json`
- `stage2b-targeted.txt`
- `agenda-schema-smoke.txt`
- `sts-db-smoke.txt`
- `feature-compile.txt`
- `baseline.xml`
- `feature.xml`
- `baseline.txt`
- `feature.txt`

`stage2b-summary.json` is the authoritative structured evidence for exact SHAs, requirements parity, command exits, JUnit totals, failure-node sets and gate result.

## Result

PASS

The exact runtime-accepted Stage 2A baseline and exact Stage 2B validation head were materialized and verified in the same Windows/Python/Qt/dependency environment. Compile, the real Stage 2B plus Stage 2A and foundation targeted suite, Agenda schema smoke and existing STS database smoke passed. Both full suites produced parseable JUnit evidence and `FEATURE_ONLY_FAILURE_NODE_COUNT=0`. The validation script returned `GATE=PASS` and the workflow completed successfully.

## UI Development Gate

Stage 2B accepted. Personal Gündemim Qt UI development may proceed on the isolated feature branch.

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
