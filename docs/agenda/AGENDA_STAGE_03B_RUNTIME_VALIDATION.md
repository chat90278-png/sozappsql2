# Gündemim Stage 3B Runtime Validation

## Scope

This validation covers the isolated Stage 3B implementation only:

- `ReturnedShareAgendaSource`;
- immutable `AgendaSourceBundle`;
- personal-scope RETURNED share registry reads;
- `ReturnedShareAgendaProvider`;
- `StaffAgendaService` default-provider integration;
- generic Stage 3A compact/detail Qt rendering of the new item.

No product, test, provider, repository, service, UI, schema, transaction, agenda-state or share-lifecycle source was changed during this validation.

## Validated Refs

- Accepted Stage 3A baseline: `e8db57adff333693b050bd6244d9847b148745b3`
- Stage 3B implementation head before validation files: `85c0d34bc80cbd8b0557556731ef8c7aab716778`
- Exact Stage 3B validation head: `531c5e13014f418c368c960d4ff4aefd01832cb7`
- Current main observed: `9e60beca5b33c2b821d5c8f54d88aba74793a5bf`
- Temporary draft PR: `#325`
- Workflow: `Gundemim Stage 3B Runtime Validation`
- Run ID: `29222885222`
- Job ID: `86731362538`
- Artifact ID: `8268802028`

The PR was created only to trigger validation and was not authorized for merge.

## Environment

- Runner OS: Microsoft Windows Server 2025 Datacenter
- Runner image: `windows-2025-vs2026`
- Runner image version: `20260628.158.1`
- CPython: `3.11.9`
- PySide6: `6.11.1`
- Qt platform: `offscreen`
- Token permission: `Contents: read`

## Exact SHA / Requirements

| Check | Expected | Actual | Result |
|---|---|---|---|
| Stage 3A baseline | `e8db57adff333693b050bd6244d9847b148745b3` | same | PASS |
| Stage 3B validation head | `531c5e13014f418c368c960d4ff4aefd01832cb7` | same | PASS |
| `requirements.txt` bytes | equal | equal | PASS |

Both refs use the same requirements, including `PySide6==6.11.1`.

## Targeted Runtime

Feature compile command:

```text
python -m compileall -q src tests
```

Result: exit `0`.

The exact Stage 3B and prior Agenda targeted suite contained 17 test modules and completed with:

```text
263 passed in 12.48s
```

Targeted pytest exit: `0`.

## Real RETURNED Registry / Facade Smoke

A real schema-18 temporary STS database was created with:

- one platform;
- one active staff member;
- one responsible contract with merge UID and revision;
- one exact `share_packages.status=RETURNED` registry row.

Production classes used:

- `STSDatabase`;
- `AgendaSourceRepository`;
- `PersonalAgendaFacade`;
- official `SHARE_STATUS_RETURNED` and `SHARE_STATUS_MERGED` constants.

Observed proof:

```text
RETURNED_SHARE_SMOKE_BEGIN
SCHEMA_VERSION=18
RETURNED_COUNT=1
KEY=returned_share:share_package:stage3b-runtime-package
VERSION=RETURNED:4:stage3b-base-hash
SEEN_REMAINS_ACTIVE=1
SNOOZE_HIDES=1
CLEAR_RESTORES=1
FINAL_STATUS_REMOVES=1
READ_ONLY_SOURCE=1
MERGE_ACTION_PRESENT=0
RETURNED_SHARE_SMOKE=PASS
RETURNED_SHARE_SMOKE_END
```

The source read preserved `sqlite3.Connection.total_changes`. No activity-log or file-metadata inference was used. The produced action hints contained only `open_contract`.

## Generic Qt Render

### Scale 100%

- Bootstrap: PASS
- Child exit: `0`
- QApplication: constructed
- Schema version: `18`
- PySide6: `6.11.1`
- DPR: `1.0`
- Logical DPI: `96.0`
- Returned key: `returned_share:share_package:stage3b-render-package`
- Returned version: `RETURNED:4:stage3b-render-base`
- Compact logical size: `420 × 112`
- Compact returned-share rows: `1`
- Compact geometry offenders: `0`
- Compact open-contract signal: exact contract ID `1`
- Dwell before approximately 500 ms: `0`
- Dwell after total 750 ms: `1`
- Detail logical size: `760 × 560`
- Detail returned-share rows: `1`
- Snooze control: present
- Snooze preset codes: `tomorrow`, `three_days`, `one_week`
- Detail open-contract signal: exact contract ID `1`
- `Qt.Tool`: PASS
- `Qt.NonModal`: PASS
- Result: PASS

PNG evidence:

- `compact-returned-share-100.png`: `420 × 112`, 2,113 bytes
- `detail-returned-share-100.png`: `760 × 560`, 6,465 bytes

### Scale 150%

- Bootstrap: PASS
- Child exit: `0`
- QApplication: constructed
- Schema version: `18`
- PySide6: `6.11.1`
- DPR: `1.5`
- Logical DPI: `96.0`
- Returned key: `returned_share:share_package:stage3b-render-package`
- Returned version: `RETURNED:4:stage3b-render-base`
- Compact logical size: `420 × 112`
- Compact returned-share rows: `1`
- Compact geometry offenders: `0`
- Compact open-contract signal: exact contract ID `1`
- Dwell before approximately 500 ms: `0`
- Dwell after total 750 ms: `1`
- Detail logical size: `760 × 560`
- Detail returned-share rows: `1`
- Snooze control: present
- Snooze preset codes: `tomorrow`, `three_days`, `one_week`
- Detail open-contract signal: exact contract ID `1`
- `Qt.Tool`: PASS
- `Qt.NonModal`: PASS
- Result: PASS

PNG evidence:

- `compact-returned-share-150.png`: `630 × 168`, 3,415 bytes
- `detail-returned-share-150.png`: `1140 × 840`, 11,479 bytes

All four PNGs were present, larger than 500 bytes, non-uniform and not transparent-only. Image inspection showed the returned-share row, contract action and detail snooze area without overlap or clipping. The hosted offscreen environment rendered Turkish text glyphs as square fallback characters; the screenshots were not blank or single-colour.

Stage 3A MainWindow/header validation was not repeated because Stage 3B changed no UI files. The prior accepted Stage 3A status → agenda → calendar and MainWindow evidence remains authoritative.

## Agenda / STS Smokes

Agenda schema smoke:

```text
agenda_schema=PASS
schema_version=18
```

Exit: `0`.

Existing STS database smoke:

```text
ok
```

Exit: `0`.

## Full Pytest Absolute Results

### Accepted Stage 3A baseline

- pytest exit: `1`
- tests: `869`
- failures: `42`
- errors: `0`
- skipped: `0`
- JUnit time: `66.907`
- raw summary: `42 failed, 827 passed in 67.00s (0:01:07)`

### Stage 3B validation feature

- pytest exit: `1`
- tests: `923`
- failures: `42`
- errors: `0`
- skipped: `0`
- JUnit time: `65.557`
- raw summary: `42 failed, 881 passed in 65.66s (0:01:05)`

Both full suites remain absolute non-zero and are not described as absolute PASS.

## Failure Differential

Failure identity:

```text
<classname>::<name>
```

Both `failure` and `error` testcase elements were included.

- Baseline failure/error nodes: `42`
- Feature failure/error nodes: `42`
- Shared nodes: `42`
- Baseline-only nodes: `0`
- Feature-only nodes: `0`

Feature-only nodes: `NONE`.

## Artifact

- Name: `gundemim-stage3b-runtime-validation`
- Artifact ID: `8268802028`
- Size: `72,711` bytes
- Expired: `false`
- Digest: `sha256:d43a907e1f6766b27f91e4f7b8150e6ada818e93fdda6f44d7ca55880305be3a`
- Run: `29222885222`
- Head SHA: `531c5e13014f418c368c960d4ff4aefd01832cb7`

The artifact contains structured JSON, targeted/smoke outputs, baseline/feature JUnit XML and raw outputs, two scale JSON files, two scale logs and four PNGs.

## Result

# PASS

Reason:

```text
Exact refs, requirements parity, targeted runtime, RETURNED registry/facade lifecycle,
both generic Qt render probes, four PNGs, Agenda/STS smokes and JUnit differential
passed with zero feature-only failure nodes.
```

## Further Isolated Development Gate

OPEN.

Stage 3B accepted. Further isolated provider/scope hardening may proceed.

## Main Merge Gate

CLOSED.

This result does not authorize merge, auto-merge, rebase, cherry-pick, branch synchronization or a write to `main`.

## Integration Risk

Current main has advanced independently. Main integration still requires:

- reconciliation with the automatic schema-upgrade engine;
- explicit v17→v18 migration/fingerprint support;
- final current-main differential validation;
- final current-main visual smoke;
- separate manager authorization.
