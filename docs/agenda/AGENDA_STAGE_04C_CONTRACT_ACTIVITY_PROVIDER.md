# AGENDA STAGE 04C — CONTRACT ACTIVITY EVENT PROVIDER

## 1. Accepted Stage 4B-V baseline

- Stage 4B-V accepted feature HEAD / Stage 4C exact starting HEAD: `c52c59ca15756ca0accd0a3910a1e20b9c66c4ea`
- Stage 4B source HEAD: `8088d2e65bbf7daee3ff07667e0f438b2099e96e`
- Working branch: `feature/gundemim-agenda-system`
- Stage 4B static/source gate: `PASS`
- Stage 4B runtime differential gate: `PASS`
- Activity Provider development gate: `OPEN`
- Main/default branch was not modified or synchronized.

This document records Stage 4C source implementation and source-test scope only. Runtime acceptance remains pending a separate Stage 4C-V differential validation.

## 2. Scope

Stage 4C adds a contract-level Agenda EVENT provider backed by existing `activity_logs` rows whose contract aggregate identity is exact and whose changed fields are explicitly whitelisted.

Implemented source actions:

- `contract_updated`
  - `completion_date`
  - `acceptance_date`
- `contract_status_changed`
  - `status`

No system, delivery, note, component, responsible-staff, share, document-lock, create, delete, or text-inferred activity event is introduced.

## 3. Exact activity_logs schema

The existing source of truth is unchanged:

```sql
CREATE TABLE IF NOT EXISTS activity_logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor TEXT,
    source TEXT,
    device_name TEXT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    entity_key TEXT,
    platform_id INTEGER,
    contract_no TEXT,
    message TEXT,
    before_json TEXT,
    after_json TEXT,
    payload_json TEXT,
    FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE SET NULL
)
```

No DDL, migration, schema version, log writer, `STSDatabase.add_log(...)`, or authorization behavior changes were made.

## 4. Stable identity limitations

- Stable event identity is `activity_logs.id`.
- Stable contract identity is the exact `entity_type='contract'` and exact `entity_id == str(contracts.id)` relation.
- `contract_no` is presentation metadata and is never aggregate identity.
- `actor` is display text only.
- `device_name` is display/audit metadata only.
- There is no stable `actor_staff_id` column in the current schema.

## 5. Exact action and field whitelist

The pure domain policy is immutable:

```python
CONTRACT_ACTIVITY_FIELDS_BY_ACTION = MappingProxyType({
    "contract_updated": (
        "completion_date",
        "acceptance_date",
    ),
    "contract_status_changed": (
        "status",
    ),
})
```

Unsupported action and field values do not produce activity items.

## 6. Duplicate status decision

`contract_updated.status` is intentionally excluded. Status activity is emitted only from the dedicated `contract_status_changed` row, preventing duplicate status events from one save operation.

## 7. Actor identity limitation

Every projected activity item has:

```text
actor_staff_id = None
actor_name = activity_logs.actor
```

Actor text is presentation metadata. It is not joined to `staff`, and no stable person identity is inferred from actor name or device name.

## 8. No self-filter decision

Activity events are not hidden when:

- actor display name equals the current staff full name;
- device name equals the current staff device name.

A future actor-principal schema/migration is required before trustworthy self-filtering can be implemented.

## 9. Contract-only identity decision

The repository joins only:

```sql
activity_logs AS l
JOIN contracts AS c
  ON TRIM(l.entity_id) = CAST(c.id AS TEXT)
```

It does not resolve identity through:

- `contract_no`;
- platform display text;
- `entity_key` parsing;
- message parsing;
- numeric casting of mixed entity text;
- actor or device lookup.

## 10. System and delivery deferral

System and delivery activity is deferred because current audit rows do not provide a uniformly reliable direct contract aggregate identity for all relevant operations. Stage 4C does not invent an aggregate relation from message, display, contract number, platform, or entity-key text.

## 11. Pure domain activity policy

`src/domain/agenda/activity.py` defines:

- `ACTIVITY_PROVIDER_CODE = "activity"`
- `ACTIVITY_SOURCE_LOOKBACK_DAYS = 8`
- immutable action/field policy;
- immutable field presentation metadata;
- `activity_source_cutoff(now)`.

The module imports no SQL, database, Qt, or auth code. Timezone-aware inputs are snapshotted as naive datetimes according to the existing Agenda convention.

## 12. Activity source model

`ActivityAgendaSource` is a frozen dataclass with:

- positive non-bool `log_id` and `contract_id`;
- exact whitelisted `action`;
- required `created_at`;
- exact normalized `entity_type='contract'`;
- exact `entity_id == str(contract_id)`;
- stripped contract/audit display text;
- defensive shallow copies of `before_values` and `after_values` exposed as `MappingProxyType`.

No actor staff ID field, SQL logic, permission decision, or lifecycle decision exists in the model.

`AgendaSourceBundle` now carries immutable tuples for:

- calendar;
- returned shares;
- document locks;
- activities.

## 13. Repository exact query

`AgendaSourceRepository.list_activity_sources(...)`:

- normalizes and de-duplicates supplied contract IDs;
- returns empty without querying for empty IDs;
- uses a set-based `activity_logs JOIN contracts` query;
- requires exact contract entity identity;
- filters to the central action whitelist;
- rejects empty timestamps;
- applies `created_at > activity_since` when a cutoff is provided;
- orders by `created_at DESC, log_id DESC`;
- reuses the batched platform lookup;
- performs no commit, transaction, auth lookup, staff lookup, activity mutation, or N+1 contract query.

## 14. JSON fail-closed policy

Repository-local parsing accepts a row only when both `before_json` and `after_json` decode to JSON objects.

The row is skipped when either value is:

- empty;
- invalid JSON;
- an array;
- a scalar.

`payload_json` and `message` are not parsed for business meaning. A malformed audit row does not fail the complete Agenda build.

## 15. Eight-day source lookback

The service derives:

```python
activity_since = context.now.replace(tzinfo=None) - timedelta(days=8)
```

The source query uses strict `created_at > cutoff` behavior.

Eight days is a loading window, not a new lifecycle policy:

- unseen EVENT visibility remains seven days;
- a seen event remains visible for twenty-four hours after `seen_at`;
- invalid timestamps remain fail-closed;
- existing `AgendaLifecycleEngine` is unchanged.

## 16. Provider item contract

Provider code: `activity`

Each genuinely changed whitelisted scalar field produces one item:

```text
key               activity:activity_log:<log_id>:<field_name>
version           ACTIVITY:<log_id>:<field_name>:<created_at>
kind              activity
lifecycle         EVENT
priority          450
severity          INFO
reason_code       CONTRACT_ACTIVITY
supports_snooze   False
action_hints      (open_contract,)
actor_staff_id    None
```

Titles:

- `<contract> durumu değişti`
- `<contract> tamamlanma tarihi değişti`
- `<contract> kabul tarihi değişti`

Description:

```text
<old value or Boş> → <new value or Boş>
```

Nested collection/object values are skipped. Equal normalized scalar values produce no item.

## 17. EVENT lifecycle and state boundary

The provider defines no TTL and performs no state operation.

Expected generic behavior remains:

- initial valid event is NEW;
- `mark_seen` persists exact key/version;
- seen event remains visible for less than twenty-four hours and is not NEW;
- unseen event expires at seven days;
- seen event expires at twenty-four hours after `seen_at`;
- EVENT snooze is rejected by the existing facade;
- direct dismiss action hints are not emitted.

`AgendaStateRepository`, `PersonalAgendaFacade`, and `AgendaLifecycleEngine` product sources were not changed.

## 18. Permission, profile, and scope matrix

- Provider capability is exactly `view_contracts`.
- `edit_contracts` is not required.
- Role names do not grant capability.
- RESPONSIBLE scope receives only responsible contract activity sources.
- ALL_VISIBLE receives activity sources for all resolved visible contracts.
- Explicit contract override remains exact.
- No-view top-level gate remains safe empty before scope/source/provider/state access.
- SYSTEM profile with `staff_id=None` remains fail-closed before source/provider/state access.

## 19. Service registration and bundle-once behavior

Default order is:

```python
(
    DeadlineAgendaProvider(),
    ReturnedShareAgendaProvider(),
    DocumentLockAgendaProvider(),
    UnknownDateAgendaProvider(),
    ActivityAgendaProvider(),
)
```

`load_personal_sources(...)` is called once per Agenda build. The real repository receives the exact eight-day cutoff and returns all source families in one bundle. Existing pre-activity repository adapters/test doubles remain callable without changing provider orchestration.

Priority placement is:

```text
critical deadline > returned share 850 > document lock 800
> upcoming deadline 700/600 > unknown date 500 > activity 450
```

## 20. Source tests and execution state

Committed source tests cover:

- immutable policy and exact lookback;
- source-model validation and defensive mapping snapshots;
- bundle type behavior;
- permission capability;
- field whitelist and duplicate-status exclusion;
- scalar normalization and nested-value fail-closed behavior;
- exact key/version/item payload;
- actor identity limitation and no self-filter;
- presentation and empty-value fallbacks;
- source/context immutability.

Development validation performed during implementation:

```text
python -m compileall -q src tests
result: PASS in the materialized Stage 4C development harness

focused committed-test-equivalent harness:
29 passed, 0 failed

expanded repository/service/facade development harness:
38 passed, 0 failed
```

The prompt's exact eleven-file repository targeted command and the two repository smoke commands were not run on a complete checkout in this implementation session. Therefore the official static/source execution gate is not claimed as PASS.

## 21. Explicit exclusions and deferred decisions

Not implemented:

- system/delivery activity;
- note/component/responsible-staff activity;
- create/delete activity;
- share/document-lock activity inference;
- actor staff ID migration or lookup;
- self-filtering;
- schema/version/migration/log-writer changes;
- direct dismiss action;
- UI changes;
- lifecycle TTL changes;
- main integration.

## 22. Runtime and gate state

```text
STAGE 4C CONTRACT ACTIVITY PROVIDER: SOURCE IMPLEMENTED
STAGE 4C STATIC/SOURCE TEST GATE: NOT RUN
STAGE 4C RUNTIME ACCEPTANCE: PENDING
CONTRACT-LEVEL ACTIVITY EVENTS: IMPLEMENTED
SYSTEM/DELIVERY ACTIVITY EVENTS: DEFERRED
ACTOR STAFF ID / SELF FILTERING: DEFERRED
RESPONSIBLE CHANGE ACTIVITY: DEFERRED
MAIN MERGE GATE: CLOSED
```

Stage 4C-V must provide complete checkout static execution, real schema-18 runtime evidence, and baseline/feature differential evidence before runtime acceptance or broader activity scope can be opened.
