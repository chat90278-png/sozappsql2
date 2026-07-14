# AGENDA STAGE 04C — CONTRACT ACTIVITY EVENT PROVIDER

## 1. Accepted baseline and R1 starting ref

- Stage 4B-V accepted feature baseline: `c52c59ca15756ca0accd0a3910a1e20b9c66c4ea`
- Stage 4C source implementation HEAD / Stage 4C-R1 exact starting HEAD: `db3a93995ee0718de891a15bd7a089d30b1bc99f`
- Working branch: `feature/gundemim-agenda-system`
- Original feature/main merge base: `2931fa267560397d4d849d6365acde504f376775`
- Main/default branch was not modified, synchronized, rebased, or merged.

Stage 4C-R1 is a source-correction and committed-test-completion task. It does not provide runtime acceptance; Stage 4C-V remains a separate differential-validation task.

## 2. Implemented activity scope

Stage 4C adds contract-level Agenda EVENT items backed only by exact `activity_logs` contract identity and a narrow immutable action/field whitelist.

Implemented rows:

- `contract_updated`
  - `completion_date`
  - `acceptance_date`
- `contract_status_changed`
  - `status`

Not implemented:

- system or delivery activity;
- note, component, responsible-staff, create, or delete activity;
- share or document-lock activity inference;
- actor staff identity lookup or migration;
- self-filtering;
- direct dismiss or EVENT snooze support;
- schema, log-writer, lifecycle, state-repository, facade-product, or UI changes.

## 3. Source-of-truth and stable identity

The existing table remains unchanged:

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

Identity decisions:

- stable event identity: `activity_logs.id`;
- stable contract identity: exact `entity_type='contract'` and exact trimmed `entity_id == str(contracts.id)`;
- `contract_no` is display metadata only;
- actor and device values are display/audit text only;
- no `actor_staff_id` is inferred.

## 4. Immutable policy and duplicate-status decision

The pure domain policy is:

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

`contract_updated.status` is intentionally excluded. Status activity is generated only from `contract_status_changed`, preventing duplicate status items for one save operation.

## 5. Source model and bundle

`ActivityAgendaSource` is frozen and validates:

- positive non-bool `log_id` and `contract_id`;
- exact whitelisted action;
- required stripped `created_at`;
- exact normalized `entity_type='contract'`;
- exact non-empty `entity_id == str(contract_id)`;
- stripped contract and audit metadata;
- defensive `MappingProxyType` snapshots for before/after objects.

`AgendaSourceBundle` carries four immutable source families:

```text
calendar
returned_shares
document_locks
activities
```

## 6. Repository contract

The repository uses only the exact identity join:

```sql
activity_logs AS l
JOIN contracts AS c
  ON TRIM(l.entity_id) = CAST(c.id AS TEXT)
```

The activity read path:

- filters supplied contract IDs in one set-based query;
- accepts only central whitelist actions;
- requires `entity_type='contract'`;
- rejects empty timestamps;
- uses strict `created_at > activity_since`;
- sorts by `created_at DESC, l.id DESC`;
- reuses one batched platform lookup;
- does not resolve identity from contract number, message, entity key, actor, device, or mixed numeric text;
- performs no write, commit, transaction opening, auth lookup, staff lookup, or per-contract N+1 query.

Both `before_json` and `after_json` must decode to JSON objects. Empty, invalid, array, or scalar JSON skips the row without failing the whole Agenda build. `payload_json` and `message` are not parsed for business meaning.

## 7. Provider item contract

Each genuinely changed whitelisted scalar field produces one item:

```text
provider_code      activity
kind               activity
lifecycle          EVENT
priority           450
severity           INFO
key                activity:activity_log:<log_id>:<field_name>
version            ACTIVITY:<log_id>:<field_name>:<created_at>
reason_code        CONTRACT_ACTIVITY
actor_staff_id     None
supports_snooze    False
action_hints       (open_contract,)
```

Nested values are fail-closed. Equal normalized scalar values produce no item. Actor display text never controls identity or self-filtering.

## 8. Eight-day source window and lifecycle boundary

`ACTIVITY_SOURCE_LOOKBACK_DAYS = 8` is a repository loading window, not a new lifecycle rule.

The unchanged generic EVENT policy remains:

- unseen event: visible for less than seven days;
- seen matching version: visible for less than twenty-four hours after `seen_at`, not NEW;
- matching dismissed version: hidden;
- invalid timestamp: hidden;
- EVENT snooze: rejected by the existing facade.

## 9. Stage 4C-R1 blocker correction

R1 removed the production compatibility fallback based on `inspect.signature(...)`.

The service now calls the repository contract directly and deterministically:

```python
sources = self.source_repository.load_personal_sources(
    contract_ids,
    activity_since=activity_source_cutoff(context.now),
)
```

Consequences:

- `inspect.signature` import and fallback are removed;
- the eight-day cutoff cannot be silently omitted;
- all repository implementations and test doubles must support the explicit keyword contract;
- provider tuple, view gate, SYSTEM fail-closed guard, scope resolution, override, bundle-once, lifecycle, state, and sorting behavior remain unchanged.

## 10. R1 test-double contract

The committed `FakeSourceRepository` now exposes:

```python
def load_personal_sources(
    self,
    contract_ids,
    *,
    activity_since=None,
):
    ...
```

It records:

- `last_activity_since`;
- `activity_since_calls`;
- the selected contract IDs;
- one bundle load count.

The selected fake bundle preserves all four families, including scope-filtered `activities`; activity sources are no longer dropped by the test adapter.

## 11. Committed repository integration tests

`tests/test_agenda_source_repository.py` now commits real `STSDatabase`/schema-18 coverage for:

- valid contract update and status rows with exact metadata;
- unsupported actions and non-contract rows;
- empty, nonnumeric, mixed, and leading-zero entity IDs;
- contract-number non-identity and duplicate contract-number separation by exact entity ID;
- supplied-scope filtering;
- empty, invalid, array, and scalar JSON fail-closed behavior;
- payload/message non-inference;
- strict cutoff and deterministic ordering;
- datetime and string cutoff normalization;
- empty-ID zero-query behavior and duplicate-input de-duplication;
- read-only `total_changes`, transaction state, and SELECT-only trace;
- one set-based activity query with no staff/auth lookup;
- all source families in one bundle, one platform lookup, and exact cutoff forwarding.

## 12. Committed service integration tests

`tests/test_staff_agenda_service.py` now commits coverage for:

- exact default provider order ending with `activity`;
- one source bundle load and exact naive eight-day cutoff;
- RESPONSIBLE, ALL_VISIBLE, viewer, custom-role, and explicit-override activity scope;
- no-view and SYSTEM/no-state fail-closed paths;
- coexistence with deadline, returned share, document lock, and unknown date;
- unknown-date priority 500 before activity priority 450;
- cross-provider and multi-field key uniqueness;
- unseen seven-day and seen twenty-four-hour EVENT boundaries;
- invalid timestamp and dismissed-version fail-closed behavior;
- generic touch-presented behavior and `supports_snooze=False`.

## 13. Committed facade interaction tests

`tests/test_personal_agenda_facade.py` now commits coverage for:

- activity `mark_seen` with exact context staff ID, key, version, and timestamp;
- seen activity remaining visible and not NEW;
- EVENT snooze rejection without state mutation;
- no-view rejection before state access;
- system-admin/staff-ID-none rejection before state access;
- `admin_id` never being used as `staff_id`;
- actor display name being unable to redirect interaction identity.

No product change was made to `PersonalAgendaFacade`.

## 14. Static validation execution state

Required compile command:

```text
python -m compileall -q src tests
```

Result on the final R1 repository HEAD:

```text
NOT RUN
absolute exit: unavailable
```

Required exact targeted command:

```text
python -m pytest -q \
  tests/test_agenda_source_repository.py \
  tests/test_activity_agenda_provider.py \
  tests/test_staff_agenda_service.py \
  tests/test_personal_agenda_facade.py \
  tests/test_agenda_context_factory.py \
  tests/test_agenda_lifecycle.py \
  tests/test_agenda_models.py \
  tests/test_deadline_agenda_provider.py \
  tests/test_unknown_date_agenda_provider.py \
  tests/test_returned_share_agenda_provider.py \
  tests/test_document_lock_agenda_provider.py \
  --junitxml=stage-04c-r1-targeted.xml
```

Result:

```text
NOT RUN
tests/passed/failures/errors/skipped: unavailable
JUnit parse: unavailable
```

Required smokes:

```text
python tests/smoke_sts_agenda_schema.py
python tests/smoke_sts_database.py
```

Results:

```text
schema smoke: NOT RUN
database smoke: NOT RUN
```

Reason: this execution environment did not provide a full repository checkout and direct GitHub materialization was blocked by network/DNS policy. The R1 prompt forbids adding a workflow or opening a PR, so CI was not introduced as a substitute. Source inspection or prior development-harness results are not treated as the official gate.

## 15. Compatibility and exclusions

R1 did not modify:

- activity policy, source model, or provider projection;
- repository production query;
- lifecycle engine;
- Agenda models or presentation;
- Agenda state repository or context factory;
- PersonalAgendaFacade product source;
- STS schema, migration, auth, log writer, or storage writer;
- Qt/UI, requirements, or workflows.

No new activity action, field, self-filter, actor identity, system/delivery event, direct dismiss action, or EVENT snooze behavior was added.

## 16. Gate decision

Because compile, exact targeted, and both smokes were not executed on the final repository HEAD, the R1/static source gate cannot be accepted.

```text
STAGE 4C CONTRACT ACTIVITY PROVIDER: SOURCE IMPLEMENTED
STAGE 4C-R1 INTEGRATION CONTRACT: NOT RUN
STAGE 4C STATIC/SOURCE TEST GATE: NOT RUN
STAGE 4C RUNTIME ACCEPTANCE: PENDING
BROADER ACTIVITY DEVELOPMENT GATE: BLOCKED
SYSTEM/DELIVERY ACTIVITY EVENTS: DEFERRED
ACTOR STAFF ID / SELF FILTERING: DEFERRED
RESPONSIBLE CHANGE ACTIVITY: DEFERRED
MAIN MERGE GATE: CLOSED
```

Stage 4C-V must not start until the exact R1 compile, targeted suite, and both smoke commands pass on a complete checkout. This document is not a main-merge recommendation.
