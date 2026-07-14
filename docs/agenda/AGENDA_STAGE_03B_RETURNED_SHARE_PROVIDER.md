# Gündemim Stage 3B — Personal Returned Share Provider

## Scope

Stage 3B adds a personal `returned_share` CONDITION source to the isolated `feature/gundemim-agenda-system` branch. The accepted Stage 3A baseline is `e8db57adff333693b050bd6244d9847b148745b3`.

The implementation is limited to:

- immutable `AgendaSourceBundle`;
- immutable `ReturnedShareAgendaSource`;
- personal contract-scoped reads from the source STS `share_packages` registry;
- pure `ReturnedShareAgendaProvider` domain projection;
- default `StaffAgendaService` provider integration;
- source and service tests.

No Qt UI source, schema, transaction, agenda state SQL, share lifecycle writer or merge action was changed.

## Share Lifecycle Source of Truth

Official package statuses are:

- `OPEN`;
- `RETURNED`;
- `MERGED`;
- `PARTIALLY_MERGED`;
- `REJECTED`;
- `CANCELLED`.

The existing lifecycle service treats `OPEN` and `RETURNED` as active. Final statuses are `MERGED`, `PARTIALLY_MERGED`, `REJECTED` and `CANCELLED`.

The exact RETURNED writer remains `prepare_share_merge_plan(...)`. After successful package validation and merge-plan preparation, `_mark_package_returned_if_open(...)` performs only:

```sql
UPDATE share_packages
SET status='RETURNED'
WHERE share_package_id=?
  AND contract_merge_uid=?
  AND status='OPEN'
```

No new status writer was added. A production `REJECTED` writer was not inferred or implemented.

## Why the Registry Is Authoritative

The provider reads only the main STS `share_packages` registry joined to `contracts`. It does not infer lifecycle state from:

- `activity_logs`;
- exported filenames;
- share package file metadata;
- directory scans;
- `read_share_metadata(...)`;
- merge UI state.

A returned-share condition exists only while the exact registry row has status `RETURNED`.

## Agenda Source Bundle

Provider input is now the immutable `AgendaSourceBundle`:

```text
calendar: tuple[AgendaCalendarSource, ...]
returned_shares: tuple[ReturnedShareAgendaSource, ...]
```

Both collections are defensive tuple snapshots and validate their member types. The bundle contains no DB connection and makes no lifecycle or business decision.

Existing `DeadlineAgendaProvider` and `UnknownDateAgendaProvider` read only `sources.calendar`; their keys, versions, priorities and output behavior are unchanged.

## ReturnedShareAgendaSource

The frozen source model carries the exact registry and contract presentation fields needed by the provider:

- registry/package/contract identity;
- contract merge UID, number, type and multi-platform label;
- official status;
- source revision and snapshot hashes;
- permission and format versions;
- creation/import metadata;
- exported filename;
- return count.

IDs and counters are validated, strings are stripped defensively and status is normalized to an official uppercase value.

## Personal Contract Scope

`StaffAgendaService` keeps the existing `view_contracts` gate and personal responsibility scope from `contract_responsible_engineers`. It asks `AgendaSourceRepository` for one bundle covering only the selected personal contract IDs.

A RETURNED package belonging only to an unassigned contract is not visible to the personal user. No manager/admin/global scope is introduced.

## Multi-platform Presentation

Platform names are read from both `contract_platforms` and the legacy/current `contracts.platform_id` relation. Names are stripped, case-insensitively deduplicated, deterministically sorted and joined with `" / "`.

Platform relations do not multiply `share_packages` rows: the repository emits exactly one returned-share source per registry row.

## Provider Identity and Version

Provider code:

```text
returned_share
```

Stable key:

```text
returned_share:share_package:<share_package_id>
```

The key does not use registry row ID, filename, contract title or platform display fields.

Stable version:

```text
RETURNED:<source_contract_revision>:<base_snapshot_sha256>
```

Filename, platform, return count and import timestamp do not affect the version.

## Condition Semantics

Returned shares are CONDITION items with:

- priority `850`;
- severity `ATTENTION`;
- `supports_snooze=True`;
- action hints only `("open_contract",)`.

Seen state removes NEW status but leaves the item visible while the registry remains RETURNED. A matching condition snooze hides the item temporarily. A revision/hash version change resurfaces the stable key as new.

When the registry moves to `MERGED`, `PARTIALLY_MERGED`, `CANCELLED` or `REJECTED`, the repository no longer emits the source and the condition disappears. Existing agenda interaction rows may remain; no explicit resolved/dismissed state write or stale-state cleanup is added.

`OPEN` does not create an item because the share has not returned yet. EVENT TTL does not apply.

## Priority Relative to Existing Providers

The default raw provider order is:

1. `DeadlineAgendaProvider`;
2. `ReturnedShareAgendaProvider`;
3. `UnknownDateAgendaProvider`.

Final service sorting remains authoritative. Priority `850` places a returned share below critical deadline stages (`900+`) and above upcoming deadline stages (`700/600`) and unknown-date items (`500`), subject to the existing NEW-first ordering.

## Generic UI Compatibility

Stage 3A compact/detail widgets already render generic immutable `AgendaItem` values. The new condition therefore appears without UI changes. It supports existing open-contract navigation, seen dwell and condition snooze behavior.

No `merge_share` action hint, merge button, file picker or “Paylaşımı Birleştir” route was introduced.

## Tests

Coverage includes:

- source model and bundle validation/immutability;
- RETURNED-only registry filtering;
- exclusion of OPEN and final statuses;
- personal-scope exclusion;
- exact registry field mapping;
- multi-platform dedupe/order;
- deterministic source order;
- read-only `total_changes` proof;
- no activity-log inference;
- stable provider key/version/payload/action hints;
- seen, snooze and version-resurface lifecycle behavior;
- default service integration, coexistence, sorting and counts;
- duplicate key failure;
- raw test transition from RETURNED to MERGED;
- existing Deadline/UnknownDate bundle compatibility.

Runtime execution is deferred to the separate Stage 3B-V gate when an executable repository environment is available.

## Explicit Exclusions

Stage 3B does not add:

- `ActivityProvider`;
- `DocumentLockProvider`;
- global manager/admin/viewer scope;
- merge UI or merge action routing;
- a `REJECTED` writer;
- schema/DDL/migration changes;
- share lifecycle/apply changes;
- raw file or metadata scanning.

## Main Integration Risk

Current `main` has advanced independently and still requires reconciliation with the isolated feature. Main integration additionally requires explicit schema v17→v18 migration/fingerprint support and a current-main runtime/visual differential validation.

## Main Merge Gate

CLOSED.

This Stage 3B implementation does not authorize a merge, rebase, branch sync or write to `main`.
