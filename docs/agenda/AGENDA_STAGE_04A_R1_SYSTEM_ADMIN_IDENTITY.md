# Gündemim Stage 4A-R1 System-Admin Identity Correction

## Detected Contradiction

Stage 4A initially mapped an exact system-admin session's `admin_id` into `AgendaContext.staff_id`. That mapping was unsafe because the two identifiers belong to different tables.

## Exact Auth Session

`auth.build_system_admin_session(...)` produces:

- `id = 0`;
- `admin_id = system_admins.id`;
- `is_admin = True`;
- `is_active`;
- display/device fields;
- no `permissions` field.

Auth remains unchanged. The context factory does not synthesize permissions from `is_admin`, role or profile.

## Exact Agenda-State Foreign Key

Schema 18 defines:

```sql
CREATE TABLE IF NOT EXISTS staff_agenda_state(
    staff_id INTEGER NOT NULL,
    agenda_key TEXT NOT NULL,
    ...,
    PRIMARY KEY(staff_id, agenda_key),
    FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
);
```

`system_admins.id` is not a `staff.id`.

## Risk

Reusing `admin_id` as `staff_id` created two unsafe outcomes:

1. if no `staff` row had the same numeric ID, a state write could fail foreign-key validation;
2. if an unrelated `staff` row happened to have the same numeric ID, system-admin state could be read from or written into that staff member's agenda state.

A numerical coincidence is not a valid principal linkage.

## Fail-Closed Decision

Stage 4A-R1 keeps the presentation foundation while disabling unsafe persistence:

- exact system-admin sessions still resolve to profile `SYSTEM`;
- their default contract scope remains `ALL_VISIBLE` as presentation/future-provider character;
- `AgendaContext.staff_id` is `None`;
- `admin_id` remains available only in the immutable safe staff snapshot;
- `StaffAgendaService` returns an empty SYSTEM-profile result before source, provider or state access;
- explicit/injected permissions do not bypass the missing principal identity;
- explicit contract overrides do not bypass the missing principal identity;
- mark-seen, snooze and clear-snooze interactions fail before repository mutation.

No fake success is returned for state interactions.

## Code Changes

### Context Factory

`PersonalAgendaContextFactory` no longer converts `system_admins.id` into `AgendaContext.staff_id`.

Normal staff behavior remains unchanged: positive `staff.id` values continue to be required and used for RESPONSIBLE scope and agenda-state persistence.

### Staff Agenda Service

The build order is now:

1. missing `view_contracts` → empty result;
2. SYSTEM profile with no persistent staff identity → empty result;
3. other missing/invalid staff identity → fail-fast `ValueError`;
4. existing scope, provider, lifecycle and state flow.

The SYSTEM guard runs before:

- `list_personal_contract_ids`;
- `list_all_contract_ids`;
- `load_personal_sources`;
- provider capability/build calls;
- state lookup;
- `touch_presented`.

### Facade

`PersonalAgendaFacade` product source was not changed.

Its existing interaction context already requires a valid positive `staff_id`. With the corrected context factory, exact system-admin interactions raise `AgendaInteractionError` before a state repository call.

## Tests

Source tests cover:

- production `auth.build_system_admin_session(...)` shape;
- no synthetic permission field in the real session;
- SYSTEM + ALL_VISIBLE profile resolution;
- `staff_id is None` for exact system-admin sessions;
- preservation of `admin_id` in the safe snapshot;
- explicit permissions not creating staff identity;
- system-admin load with no permissions returning empty without source/provider/state queries;
- injected permissions still returning empty without source/provider/state queries;
- explicit contract override still returning empty without source/provider/state queries;
- mark-seen, snooze and clear-snooze rejection with zero repository mutations;
- unchanged personnel, viewer and manager scope/capability behavior.

Real repository runtime validation remains deferred to Stage 4A-V.

## Deferred Principal-State Design Options

No schema choice is implemented in Stage 4A-R1. Future design must explicitly choose and migrate one stable principal model, such as:

### Principal Type / Principal ID

A state table keyed by an explicit principal discriminator and identifier, for example:

- `principal_type = STAFF | SYSTEM_ADMIN`;
- `principal_id` belonging to the matching source table.

This requires new schema, migration, indexes and repository semantics.

### Separate System-Admin Agenda State

A dedicated system-admin state table could reference `system_admins(id)`. This avoids mixed foreign keys but duplicates state persistence behavior and requires coordinated lifecycle handling.

### Authenticated Staff Linkage

A system-admin identity could be explicitly linked to a real `staff` principal. Such linkage must be persisted and authenticated; numeric ID coincidence or implicit lookup is not acceptable.

Each option requires a separate architecture decision, schema/migration plan, runtime differential validation and manager authorization.

## Explicit Exclusions

Stage 4A-R1 does not modify:

- schema version or DDL;
- `staff_agenda_state` foreign keys;
- `AgendaStateRepository`;
- `auth.py`;
- `app.py`;
- Qt UI;
- `PersonalAgendaFacade` product source;
- share lifecycle/status writers;
- workflows or pull requests;
- main integration.

## Main Merge Gate

CLOSED.

System-admin operational Agenda support remains blocked until a stable principal/state persistence design and separate runtime validation are accepted.
