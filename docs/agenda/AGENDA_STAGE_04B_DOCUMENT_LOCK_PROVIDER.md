# AGENDA STAGE 04B — DOCUMENT LOCK CONDITION PROVIDER

## 1. Accepted baseline

- Stage 4A-V runtime differential gate: `PASS`
- Exact Stage 4B starting HEAD: `55d6c6da4fae99c4074532302f7f11ce6c091623`
- Working branch: `feature/gundemim-agenda-system`
- Main/default branch is not modified or synchronized.

This document records source implementation and source-test scope only. Stage 4B runtime acceptance remains pending a separate Stage 4B-V differential validation.

## 2. Scope

Stage 4B adds a permission-first, contract-scope-aware Agenda CONDITION provider for active document locks. It does not add direct lock/unlock actions, new UI, schema changes, migration changes, auth changes, activity-log inference, system-admin operational Agenda, or stale-lock escalation policy.

## 3. Source of truth

The source is the existing `document_locks` table created by `src.auth.ensure_document_locks_table(...)`:

```sql
CREATE TABLE IF NOT EXISTS document_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL UNIQUE,
    is_locked INTEGER NOT NULL DEFAULT 0,
    locked_by_staff_id INTEGER,
    locked_by_device_name TEXT,
    locked_by_full_name TEXT,
    locked_at TEXT,
    updated_at TEXT,
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
    FOREIGN KEY(locked_by_staff_id) REFERENCES staff(id) ON DELETE SET NULL
)
```

Stable aggregate identity is `contract_id`. Activity log records, actor display text, and device names are not lock identity.

## 4. Active condition filter

A repository source exists only when:

```sql
document_locks.is_locked = 1
AND document_locks.locked_at IS NOT NULL
```

No `documents_locked` or `documents_unlocked` activity log is read to infer current state.

## 5. Permission/capability matrix

| Permission snapshot | Provider enabled | Visible conditions |
|---|---:|---|
| no unlock permission | no | none |
| `lock_documents` only | no | none |
| `unlock_own_documents` | yes | only rows whose `locked_by_staff_id == context.staff_id` |
| `unlock_all_documents` | yes | all active lock rows in resolved contract scope |
| both unlock permissions | yes | all active lock rows in resolved contract scope, emitted once |

`view_contracts` remains the existing `StaffAgendaService` top-level gate. Role names do not enable the provider and `auth.has_permission` is not called by the provider.

## 6. Own identity

“Own” is established only through a stable positive staff identity:

```text
source.locked_by_staff_id == context.staff_id
```

Full name or device-name equality never establishes ownership. A `NULL` owner is visible only with `unlock_all_documents`.

## 7. Profile and scope behavior

| Profile/scope | Result |
|---|---|
| PERSONAL / RESPONSIBLE | lock sources only from responsible contracts, then permission filter |
| VIEW_ONLY / ALL_VISIBLE | no lock item without explicit unlock capability |
| MANAGEMENT / ALL_VISIBLE | all scoped locks with `unlock_all_documents`; own locks only with own capability |
| custom / RESPONSIBLE | explicit permission snapshot only; no role-derived capability |
| SYSTEM / ALL_VISIBLE | existing Stage 4A fail-closed service guard returns safe empty before source/provider/state access |
| explicit contract override | exact override IDs; default scope queries are bypassed |

## 8. Source model

`DocumentLockAgendaSource` is a frozen dataclass containing contract metadata, active-lock status, owner staff/device/display metadata, `locked_at`, and `updated_at`.

- `contract_id` must be positive and cannot be bool.
- `locked_by_staff_id` is `None` or a positive non-bool integer.
- `is_locked` is normalized to deterministic bool.
- text fields are stripped.
- empty `locked_at` is rejected.
- `AgendaSourceBundle.document_locks` is an immutable tuple snapshot and rejects wrong source types.

## 9. Repository behavior

`AgendaSourceRepository.list_document_lock_sources(...)`:

- normalizes and de-duplicates supplied contract IDs;
- returns empty without querying for empty IDs;
- uses a set-based `document_locks JOIN contracts` query;
- applies active-condition predicates in SQL;
- derives platform display through the existing batched platform lookup;
- orders by contract number case-insensitively and then contract ID;
- performs no commit, transaction, auth call, permission decision, or activity-log read.

`load_personal_sources(...)` performs one shared platform lookup and adds `document_locks` beside calendar and returned-share source families.

## 10. Provider projection

Provider code: `document_lock`

```text
key        = document_lock:contract:<contract_id>
kind       = document_lock
lifecycle  = CONDITION
priority   = 800
severity   = ATTENTION
version    = LOCKED:<locked_by_staff_id_or_0>:<locked_at>
reason     = DOCUMENT_LOCKED / OWN_LOCK | OTHER_LOCK
actions    = (open_contract,)
snooze     = supported
```

The projected item carries exact contract metadata, owner actor fields, event/effective timestamp, permission snapshot flags, and owner relation (`OWN`, `OTHER`, or `UNKNOWN`).

Priority intent is:

```text
critical/overdue deadline > returned share 850 > document lock 800
> upcoming deadline 700/600 > unknown date 500
```

## 11. Lifecycle semantics

Document lock is a CONDITION item:

- seen items remain visible but are not NEW;
- snoozed items are temporarily filtered by the generic lifecycle engine;
- when the active source disappears or becomes inactive, the item disappears naturally;
- provider does not persist or mutate lock state.

## 12. Action hints

Only `open_contract` is emitted. Direct unlock is intentionally excluded because live unlock authorization, ownership/password validation, and mutation remain responsibilities of the existing document manager/UI flow.

## 13. System-admin fail-closed

Exact system-admin sessions retain `SYSTEM / ALL_VISIBLE / staff_id=None`. The existing Stage 4A guard returns safe empty before source queries, provider calls, or state access. Stage 4B does not attempt to operationalize system-admin Agenda.

## 14. Stale-age policy

No stale-lock threshold is defined in Stage 4B. No local-time age calculation, escalation threshold, or `stale_lock` provider is introduced. Stale-age policy is deferred to a separate product decision.

## 15. Tests

Source tests cover:

- source model normalization and validation;
- bundle tuple/type behavior;
- active SQL filtering, contract scope, metadata, deterministic ordering, duplicate IDs, empty input, read-only guarantees, and shared platform loading;
- permission-first provider enablement and stable-ID ownership;
- exact AgendaItem projection and presentation fallbacks;
- RESPONSIBLE, ALL_VISIBLE, custom role, explicit override, provider coexistence/order, key uniqueness, seen/snooze, source removal, source single-load, and SYSTEM fail-closed regressions.

Runtime differential acceptance is not claimed by these source tests.

## 16. Explicit exclusions

- direct lock/unlock mutation or action hint
- password dialog or document manager UI changes
- agenda UI special rendering
- auth, schema, version, migration, or permission-default changes
- activity-log inference
- stale-age threshold
- ActivityProvider
- system-admin principal/state design
- main integration or workflow/PR changes
- baseline full-suite failure fixes

## 17. Runtime validation

Stage 4B runtime acceptance is `PENDING`. A separate Stage 4B-V prompt must validate Windows/Python runtime behavior, real schema source reads, profile/scope/capability matrices, fail-closed system-admin behavior, and differential full-suite evidence.

## 18. Gate state

```text
STAGE 4B DOCUMENT LOCK PROVIDER: SOURCE IMPLEMENTED
STAGE 4B RUNTIME ACCEPTANCE: PENDING
SYSTEM-ADMIN OPERATIONAL AGENDA: DEFERRED
ACTIVITY PROVIDER DEVELOPMENT GATE: BLOCKED
MAIN MERGE GATE: CLOSED
```
