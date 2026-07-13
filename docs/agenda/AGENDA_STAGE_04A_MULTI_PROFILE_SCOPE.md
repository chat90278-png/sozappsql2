# Gündemim Stage 4A Multi-Profile Scope Foundation

## Accepted Baseline

- Runtime-accepted Stage 3B feature head: `bc5feca2aa755b4e12c98b9932810778ec08d6cb`
- Stage 3B runtime differential gate: PASS
- Further isolated development gate: OPEN
- Main merge gate: CLOSED

## Scope

Stage 4A converts the personal-only context and contract-source selection into a capability-first multi-profile foundation without changing the Stage 3A Qt UI or existing provider projections.

Implemented foundation:

- stable `AgendaContractScopeCode`;
- PERSONAL / MANAGEMENT / VIEW_ONLY / SYSTEM presentation profiles;
- RESPONSIBLE and ALL_VISIBLE contract-source scopes;
- explicit contract-ID override compatibility;
- read-only all-contract repository API;
- generic provider capability protocol;
- capability-gated provider orchestration.

## Role and Permission Separation

Role is used only to select presentation character and default contract scope.

Role does not create permissions, does not enable a provider and does not add action hints.

The permission snapshot remains the exact active `current_staff.permissions` snapshot produced by the existing auth/enrichment path.

- `manager` selects MANAGEMENT + ALL_VISIBLE.
- `viewer` selects VIEW_ONLY + ALL_VISIBLE.
- the exact system-admin session shape (`is_admin=True`, `id=0`, positive `admin_id`) selects SYSTEM + ALL_VISIBLE.
- `personnel`, legacy `staff`, empty and custom roles select PERSONAL + RESPONSIBLE.

Unknown/custom roles fail safely to PERSONAL and receive no permission grant.

## Profile Resolution Matrix

| Identity character | Profile | Contract scope |
|---|---|---|
| Exact system-admin session | SYSTEM | ALL_VISIBLE |
| `manager` role | MANAGEMENT | ALL_VISIBLE |
| `viewer` role | VIEW_ONLY | ALL_VISIBLE |
| personnel / legacy staff / custom fallback | PERSONAL | RESPONSIBLE |

Profile permissions are exactly the immutable permission snapshot supplied by auth.

A manager or system profile without `view_contracts` still produces an empty agenda because the service top-level permission gate remains authoritative.

## Contract Scope

### RESPONSIBLE

The service calls `AgendaSourceRepository.list_personal_contract_ids(staff_id)` and loads sources only for contracts assigned through `contract_responsible_engineers`.

### ALL_VISIBLE

The service calls `AgendaSourceRepository.list_all_contract_ids()`.

`ALL_VISIBLE` means all positive `contracts.id` values in the current STS. No team hierarchy, manager hierarchy or invented status filter is used.

### Explicit Override

The public `personal_contract_ids` field and facade argument remain for backward compatibility.

When non-empty, the exact normalized IDs are used regardless of profile or default scope. Neither responsible-scope nor all-visible-scope repository query is called.

## All-Contract Source

`AgendaSourceRepository.list_all_contract_ids()` performs a read-only query on the existing connection:

```sql
SELECT id
FROM contracts
ORDER BY id
```

It does not commit or mutate the database and contains no role or permission logic.

Existing `load_personal_sources(contract_ids)` is retained as the backward-compatible source-bundle loader name.

## Provider Capability Protocol

`AgendaProvider` now requires:

```python
is_enabled(context: AgendaContext) -> bool
```

The service calls this generic capability method before `build(...)`. Disabled providers are not built.

No provider-specific `isinstance`, provider-code branch or role-name branch was added.

Provider capability matrix:

| Provider | Required capability |
|---|---|
| Deadline | `view_contracts` |
| Unknown/TBD date | `view_contracts` |
| Returned Share | `edit_contracts` |

Provider `build(...)` remains a pure projection and keeps its existing key, version, priority, severity, payload and action-hint behavior.

## Behavior Matrix

- Personnel with `view_contracts` + `edit_contracts`: responsible deadline/TBD and returned-share items.
- Personnel with only `view_contracts`: responsible deadline/TBD; no returned share.
- Viewer with `view_contracts`: all-current-STS deadline/TBD; no returned share.
- Manager with `view_contracts` + `edit_contracts`: all-current-STS deadline/TBD/returned-share items.
- Manager without `view_contracts`: MANAGEMENT profile, empty result.
- Manager without `edit_contracts`: all-current-STS deadline/TBD; no returned share.
- Exact system profile with `view_contracts` + `edit_contracts`: all-visible operational foundation.
- Exact system profile without `edit_contracts`: deadline/TBD only.
- Custom role: PERSONAL + RESPONSIBLE; permissions alone determine provider visibility.
- Explicit contract override: only override IDs, with both scope queries skipped.

## Compatibility

The following public names and signatures are preserved:

- `PersonalAgendaContextFactory`
- `PersonalAgendaFacade`
- `PersonalAgendaFacade.load(..., personal_contract_ids=())`
- `AgendaSourceRepository.load_personal_sources(...)`

Existing personal behavior remains RESPONSIBLE by default.

Stage 3A compact/detail UI remains unchanged and consumes the same generic presentation snapshot.

## Tests

Source tests cover:

- exact auth/session profile resolution;
- role/permission separation;
- explicit override behavior;
- all-contract source reads and database immutability;
- provider capability methods;
- generic disabled-provider orchestration;
- PERSONAL/VIEW_ONLY/MANAGEMENT/SYSTEM scope behavior;
- viewer and read-only personnel exclusions;
- facade profile compatibility and unchanged public signature.

Real repository runtime validation is deferred to Stage 4A-V.

## Explicit Exclusions

Stage 4A does not add or modify:

- DocumentLockProvider;
- ActivityProvider;
- lock actions;
- Qt UI;
- schema, DDL or migrations;
- `STSDatabase.tx`;
- `AgendaStateRepository`;
- auth source;
- share lifecycle/status writers;
- team or manager hierarchy;
- main integration;
- workflows or pull requests.

## Integration Risk

Current main has advanced independently and still uses schema 17 while the isolated feature uses schema 18.

Main integration remains blocked pending:

- current-main reconciliation;
- automatic schema-upgrade engine review;
- explicit v17→v18 migration/fingerprint support;
- Stage 4A runtime differential validation;
- final current-main runtime and visual smoke;
- separate manager authorization.

## Main Merge Gate

CLOSED.
