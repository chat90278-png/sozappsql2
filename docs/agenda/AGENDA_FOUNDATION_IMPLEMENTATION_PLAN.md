# Gündemim — Aşama 1B Foundation Implementation Plan

**Planning ref:** `feature/gundemim-agenda-system`  
**BASE_SHA:** `2931fa267560397d4d849d6365acde504f376775`  
**Base `CURRENT_SCHEMA_VERSION`:** `17`  
**Feature migration target:** `18`

Bu doküman Aşama 1A source-of-truth audit sonucuna göre hazırlanmış implementation planıdır. Kod değildir. Aşama 1B yalnız domain/state foundation kuracaktır; provider, engine ve UI kapsam dışıdır.

## 1. Exact file plan

### New domain package

```text
src/domain/agenda/__init__.py
src/domain/agenda/constants.py
src/domain/agenda/models.py
src/domain/agenda/keys.py
src/domain/agenda/deadline_stage.py
src/domain/agenda/priority.py
```

`priority.py` yalnız severity/stage rank foundation için kullanılacak. Full final priority engine yazılmayacak.

### New service

```text
src/services/agenda_state_repository.py
```

SQL yalnız bu repository içinde kalacak. UI, future `StaffAgendaService` veya provider modüllerine state SQL dağılmayacak.

### Central migration touch

```text
src/services/sts_database.py
```

Başka existing core file Aşama 1B'de değiştirilmemeli.

### New tests

```text
tests/test_agenda_keys.py
tests/test_agenda_deadline_stage.py
tests/test_agenda_state_repository.py
tests/smoke_sts_agenda_schema.py
```

Existing regression targets:

```text
tests/smoke_sts_database.py
```

## 2. Domain model exact field plan

Repo typed dataclass convention'ına uyumlu olarak agenda foundation immutable/frozen dataclass'lar kullanacak. Persisted enum/code values `str` tabanlı stable enum veya string enum karakterinde tutulacak; UI display text key/version üretiminde kullanılmayacak.

### `AgendaLifecycleType`

`src/domain/agenda/constants.py`

Stable persisted values:

- `CONDITION`
- `EVENT`

### `AgendaSeverity`

Stable values:

- `INFO`
- `ATTENTION`
- `CRITICAL`

Central deterministic rank:

```text
INFO      -> 0
ATTENTION -> 1
CRITICAL  -> 2
```

Rank map tek yerde tutulacak ve future snooze severity/version comparison tarafından reuse edilebilecek.

### `AgendaPresentationProfileCode`

Stable presentation codes:

- `PERSONAL`
- `MANAGEMENT`
- `SYSTEM`
- `VIEW_ONLY`

Bu enum role değildir. `manager/personnel/viewer` role adına göre karar vermeyecek.

### `AgendaItem`

`src/domain/agenda/models.py`

Planned frozen dataclass fields:

```text
key: str
provider_code: str
kind: str
lifecycle_type: AgendaLifecycleType
title: str
description: str
priority: int
severity: AgendaSeverity
version: str
presentation_scope: AgendaPresentationProfileCode | None
contract_id: int | None
platform: str
contract_no: str
contract_type: str
system_id: int | None
delivery_id: int | None
share_package_id: str
actor_staff_id: int | None
actor_name: str
event_at: datetime | str | None
effective_date: date | datetime | str | None
remaining_days: int | None
reason_code: str
reason_text: str
detail_payload: Mapping[str, Any]
action_hints: tuple[str, ...]
supports_snooze: bool
```

Defaults:

- string metadata fields `""`
- nullable IDs/date fields `None`
- `detail_payload` safe immutable-facing default via `field(default_factory=dict)`; frozen dataclass mutability caveat nedeniyle `__post_init__` içinde shallow defensive copy / `MappingProxyType` yalnız repo compatibility uygunsa değerlendirilecek. En az mutable shared default kesinlikle olmayacak.
- `action_hints=()`.

Foundation action hints yalnız typed storage surface'tir; permission-specific action routing uygulanmayacak.

### `AgendaItemState`

`src/domain/agenda/models.py`

```text
staff_id: int
agenda_key: str
first_presented_at: str | None
last_presented_at: str | None
seen_at: str | None
seen_version: str
snoozed_until: str | None
snoozed_version: str
snoozed_severity: str
dismissed_at: str | None
dismissed_version: str
created_at: str | None
updated_at: str | None
```

DB row -> model conversion için repository-local `_row_to_state(row)` veya model classmethod `from_row` kullanılabilir. SQL bilgisi domain model'e gömülmemeli; tercih repository-local mapper'dır.

### `AgendaPresentationProfile`

```text
code: AgendaPresentationProfileCode
display_name: str
description: str
permissions: frozenset[str]
```

Permission snapshot immutable olacaktır. Role name field eklenmeyecek.

### `AgendaResult`

```text
profile: AgendaPresentationProfile
items: tuple[AgendaItem, ...]
new_count: int
active_count: int
counts_by_kind: Mapping[str, int]
```

Full engine yoktur; result model future engine output contract'ını taşır.

### `AgendaContext`

```text
now: datetime
today: date
current_staff: Mapping[str, Any] | None
staff_id: int | None
permissions: frozenset[str]
personal_contract_ids: frozenset[int]
presentation_profile: AgendaPresentationProfile
```

Domain context canlı `sqlite3.Connection`, `STSDatabase`, `STSStore` veya `QWidget` taşımayacak.

## 3. Deterministic agenda key builder

### File

```text
src/domain/agenda/keys.py
```

### Public API

```python
def build_agenda_key(
    *,
    provider_code: str,
    entity_type: str,
    entity_id: object,
    discriminator: object | None = None,
) -> str:
    ...
```

Keyword-only API manual positional mix-up riskini azaltır.

### Validation

- `provider_code`: `str(value).strip()` sonrası boşsa `ValueError`.
- `entity_type`: aynı validation.
- `entity_id`: `None` reject; string normalization sonrası boş reject.
- `discriminator`: optional; `None` veya normalized empty ise segment eklenmez.

### Normalization

- leading/trailing whitespace strip edilir.
- internal display capitalization/case dönüştürülmez; locale-dependent lower/upper/casefold uygulanmaz.
- numeric IDs `str(value)` olur.
- UI display text key component'i olarak kullanılmamalıdır.

### Separator safety / encoding

Key separator `:` olacak.

Her segment UTF-8 byte sequence üzerinden RFC 3986 unreserved karakter seti dışındakileri percent-encode eden deterministic helper ile encode edilecek. Öneri:

```python
urllib.parse.quote(segment, safe="-._~")
```

Bu sayede `:`, `%`, `/`, whitespace ve non-ASCII değerler collision oluşturmadan stable olur.

Key format:

```text
<provider>:<entity_type>:<entity_id>
<provider>:<entity_type>:<entity_id>:<discriminator>
```

Examples:

```text
deadline:contract:42
unknown_date:contract:57
stale_lock:contract:42
share_returned:share_package:9ee2...
activity:contract:42:completion_date
```

Provider'lar future stages'de manuel string concat yapmamalıdır.

## 4. Deadline stage/version exact plan

### File

```text
src/domain/agenda/deadline_stage.py
```

### Stable stage values

- `OVERDUE`
- `CRITICAL_1`
- `CRITICAL_3`
- `CRITICAL_7`
- `CRITICAL_15`
- `UPCOMING_30`
- `UPCOMING_60`
- `NONE`

### Boundary function

```python
def deadline_stage_for_remaining_days(remaining_days: int | None) -> DeadlineStage:
```

Exact order:

```text
None   -> NONE
< 0    -> OVERDUE
<= 1   -> CRITICAL_1
<= 3   -> CRITICAL_3
<= 7   -> CRITICAL_7
<= 15  -> CRITICAL_15
<= 30  -> UPCOMING_30
<= 60  -> UPCOMING_60
> 60   -> NONE
```

Required boundaries:

```text
-1  OVERDUE
0   CRITICAL_1
1   CRITICAL_1
2   CRITICAL_3
3   CRITICAL_3
4   CRITICAL_7
7   CRITICAL_7
8   CRITICAL_15
15  CRITICAL_15
16  UPCOMING_30
30  UPCOMING_30
31  UPCOMING_60
60  UPCOMING_60
61  NONE
None NONE
```

### Stage severity

Central mapping:

```text
OVERDUE     -> CRITICAL
CRITICAL_1  -> CRITICAL
CRITICAL_3  -> CRITICAL
CRITICAL_7  -> CRITICAL
CRITICAL_15 -> CRITICAL
UPCOMING_30 -> ATTENTION
UPCOMING_60 -> ATTENTION
NONE        -> INFO
```

### Stage rank

Deterministic urgency rank, lower ambiguity and future ordering use:

```text
NONE        -> 0
UPCOMING_60 -> 10
UPCOMING_30 -> 20
CRITICAL_15 -> 30
CRITICAL_7  -> 40
CRITICAL_3  -> 50
CRITICAL_1  -> 60
OVERDUE     -> 70
```

Exact numeric values internal foundation constants olabilir; tests stability'yi enforce edecek.

### Version foundation

Deadline version function:

```python
def deadline_stage_version(stage: DeadlineStage) -> str:
    return stage.value
```

Stable persisted/version comparison string stage code'un kendisi olacak. Future policy:

```text
item.version != state.seen_version
```

aynı agenda key'i re-NEW yapabilir. Aşama 1B NEW policy engine yazmayacak.

## 5. Migration exact plan

### Base and target

Feature branch BASE_SHA source-of-truth:

```text
CURRENT_SCHEMA_VERSION = 17
```

Aşama 1B target:

```text
CURRENT_SCHEMA_VERSION = 18
```

Başka parallel branch'in muhtemel migration bump'ı tahmin edilmeyecek. Main integration anında güncel main schema version yeniden okunup migration number uzlaştırılacak.

### Exact central file

```text
src/services/sts_database.py
```

### Table DDL

```sql
CREATE TABLE IF NOT EXISTS staff_agenda_state (
    staff_id INTEGER NOT NULL,
    agenda_key TEXT NOT NULL,
    first_presented_at TEXT,
    last_presented_at TEXT,
    seen_at TEXT,
    seen_version TEXT NOT NULL DEFAULT '',
    snoozed_until TEXT,
    snoozed_version TEXT NOT NULL DEFAULT '',
    snoozed_severity TEXT NOT NULL DEFAULT '',
    dismissed_at TEXT,
    dismissed_version TEXT NOT NULL DEFAULT '',
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY(staff_id, agenda_key),
    FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
)
```

**`agenda_items` table oluşturulmayacak.**

### Exact indexes

```sql
CREATE INDEX IF NOT EXISTS idx_staff_agenda_state_staff
ON staff_agenda_state(staff_id)
```

```sql
CREATE INDEX IF NOT EXISTS idx_staff_agenda_state_snoozed
ON staff_agenda_state(staff_id, snoozed_until)
```

### Placement strategy

Repo convention'ı korunacak:

1. `CURRENT_SCHEMA_VERSION` yalnız `17 -> 18`.
2. `staff_agenda_state` DDL `init_schema()` existing `CREATE TABLE IF NOT EXISTS` schema block'una minimum diff ile eklenecek.
3. `_create_runtime_indexes()` içindeki `create_if(table, columns, sql)` pattern'ına iki agenda index eklenecek.
4. Existing `_ensure_column`, multi-platform/share/document migration logic refactor edilmeyecek.
5. Final `meta.schema_version` update düzeni değiştirilmeyecek.
6. Backup-before-migration ve `_validate_after_migration` path'i aynen korunacak.

SQLite table creation foreign key parent name'i definition time'da resolve etmek zorunda değildir; `staff` compatibility initialization aynı `init_schema()` içinde tamamlanır ve post-migration `foreign_key_check` doğrular. Alternatif olarak table create'i `ensure_staff_table` sonrasına taşımak, `_create_runtime_indexes` current order'ını değiştirmeyi gerektirebilir. Minimum-churn tercih schema DDL block + existing runtime-index pattern'dır.

### Idempotency

- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS` via current guarded helper
- second `init_schema()` no duplicate table/index failure
- final schema version remains `18`

## 6. AgendaStateRepository exact transaction strategy

### File and constructor

```text
src/services/agenda_state_repository.py
```

Preferred constructor:

```python
class AgendaStateRepository:
    def __init__(self, db: STSDatabase):
        self.db = db
        self.conn = db.conn
```

`STSStore` wrapper zorunlu olmayacak. Yeni SQLite connection açılmayacak.

Raw connection-only constructor tercih edilmeyecek çünkü repo source-of-truth nested transaction abstraction `STSDatabase.tx()` üzerindedir.

### Timestamp strategy

Repository default timestamps için existing `src.services.sts_database.now_iso()` kullanılacak.

Input `datetime | str | None` normalize helper:

```text
None -> now_iso()
datetime -> value.strftime("%Y-%m-%d %H:%M:%S")
str -> strip edilmiş string; empty ise now_iso() yalnız optional "now" params için
```

Timezone framework eklenmeyecek.

### No unconditional commit

Her mutating public method:

```python
with self.db.tx():
    self.conn.execute(...)
```

veya batch executemany yapacak.

Caller outer transaction içindeyse `db.tx()` SAVEPOINT kullanır. Repository hiçbir metotta `self.conn.commit()` çağırmayacak.

### `get_states`

Planned signature:

```python
def get_states(
    self,
    staff_id: int,
    agenda_keys: Sequence[str],
) -> dict[str, AgendaItemState]
```

- keys normalize/dedupe preserving deterministic order.
- empty => `{}`; SQL yok.
- single batch `SELECT ... WHERE staff_id=? AND agenda_key IN (?,...)`.
- SQLite parameter limit için future need olursa chunk helper eklenebilir; foundation minimum tests normal batch size kullanır.
- only requested staff rows.
- result key = `agenda_key`.
- N+1 SELECT yok.

### Common UPSERT semantics

Mutations row yokken create edebilmeli. Base insert values:

```text
staff_id
agenda_key
created_at = timestamp
updated_at = timestamp
```

Each method `INSERT ... ON CONFLICT(staff_id,agenda_key) DO UPDATE SET ...` kullanacak. Unrelated state columns update listesine eklenmeyecek.

### `mark_seen`

```python
def mark_seen(
    self,
    staff_id: int,
    agenda_key: str,
    version: str,
    seen_at: datetime | str | None = None,
) -> AgendaItemState
```

Set:

- `seen_at`
- `seen_version`
- `updated_at`

Create'te `created_at`.

Preserve:

- presented fields
- snooze fields
- dismissed fields

### `snooze`

```python
def snooze(
    self,
    staff_id: int,
    agenda_key: str,
    version: str,
    severity: str,
    until: datetime | str,
) -> AgendaItemState
```

Set:

- `snoozed_until`
- `snoozed_version`
- `snoozed_severity`
- `updated_at`

Other state preserved.

`until` empty reject.

### `clear_snooze`

```python
def clear_snooze(
    self,
    staff_id: int,
    agenda_key: str,
) -> AgendaItemState | None
```

Existing row update:

- `snoozed_until=NULL`
- `snoozed_version=''`
- `snoozed_severity=''`
- `updated_at`

Seen/dismiss/presentation state preserved.

Row yoksa no-op + `None`; sırf clear için empty row create edilmeyecek.

### `dismiss_event`

```python
def dismiss_event(
    self,
    staff_id: int,
    agenda_key: str,
    version: str,
    dismissed_at: datetime | str | None = None,
) -> AgendaItemState
```

Set:

- `dismissed_at`
- `dismissed_version`
- `updated_at`

Repository lifecycle type kontrol etmez. Future engine CONDITION item dismiss'i ignore eder; persistence layer business policy almaz.

### `touch_presented`

```python
def touch_presented(
    self,
    staff_id: int,
    agenda_keys: Sequence[str],
    presented_at: datetime | str | None = None,
) -> None
```

- input keys normalize/dedupe.
- empty => no SQL.
- one timestamp all rows için.
- `executemany` + UPSERT.

UPSERT:

- insert: `first_presented_at=ts`, `last_presented_at=ts`, `created_at=ts`, `updated_at=ts`
- conflict: `first_presented_at=COALESCE(staff_agenda_state.first_presented_at, excluded.first_presented_at)`
- `last_presented_at=excluded.last_presented_at`
- `updated_at=excluded.updated_at`

Seen/snooze/dismiss columns conflict update listesinde olmayacak.

## 7. Exact tests

### `tests/test_agenda_keys.py`

Proposed cases:

```text
test_build_agenda_key_is_deterministic
test_build_agenda_key_strips_segment_whitespace
test_build_agenda_key_adds_discriminator
test_build_agenda_key_rejects_empty_provider_code
test_build_agenda_key_rejects_empty_entity_type
test_build_agenda_key_rejects_missing_entity_id
test_build_agenda_key_percent_encodes_separator_and_special_characters
test_build_agenda_key_does_not_apply_locale_case_conversion
```

Critical assertion: `entity_id="a:b"` key'i raw colon segment collision üretmemeli.

### `tests/test_agenda_deadline_stage.py`

Proposed parameterized boundary test:

```text
test_deadline_stage_boundaries
```

Values:

`-1,0,1,2,3,4,7,8,15,16,30,31,60,61,None`.

Additional:

```text
test_deadline_stage_severity_mapping_is_stable
test_deadline_stage_rank_is_monotonic_by_urgency
test_deadline_stage_version_is_stable_stage_code
```

### `tests/smoke_sts_agenda_schema.py`

Follow `tests/smoke_sts_database.py` precedent with `TemporaryDirectory` and real `STSDatabase`.

Cases/assertions:

```text
test-by-assert: staff_agenda_state exists
expected exact columns exist
PK order is staff_id=1, agenda_key=2 via PRAGMA table_info
FK staff_id -> staff(id), ON DELETE CASCADE via PRAGMA foreign_key_list
idx_staff_agenda_state_staff exists
idx_staff_agenda_state_snoozed exists
meta schema_version == CURRENT_SCHEMA_VERSION == 18
second db.init_schema() remains valid/idempotent
agenda_items table absent
foreign_key_check == []
integrity_check == ['ok']
```

Script success print:

```text
agenda_schema=PASS
schema_version=18
```

### `tests/test_agenda_state_repository.py`

Use real `STSDatabase(tmp_path / "agenda-state.sts")` and insert a real active staff row satisfying current schema. Do not mock SQLite.

Proposed cases:

```text
test_get_states_empty_keys_returns_empty_dict
test_mark_seen_creates_state_row
test_get_states_batches_multiple_keys
test_get_states_isolates_staff
test_mark_seen_updates_seen_version
test_mark_seen_preserves_snooze_and_dismiss_fields
test_snooze_creates_state_and_sets_version_severity_until
test_clear_snooze_preserves_seen_state
test_dismiss_event_sets_dismissed_fields
test_touch_presented_sets_first_and_last_on_first_touch
test_touch_presented_preserves_first_and_updates_last
test_touch_presented_preserves_seen_and_snooze_state
test_touch_presented_deduplicates_input_keys
test_staff_delete_cascades_agenda_state
test_repository_mutation_rolls_back_with_outer_db_transaction
```

Rollback proof exact shape:

```python
with pytest.raises(RuntimeError):
    with db.tx():
        repo.mark_seen(staff_id, key, "V1", seen_at="2026-07-10 12:00:00")
        raise RuntimeError("rollback")

assert repo.get_states(staff_id, [key]) == {}
```

Bu test repository unconditional commit atarsa fail edecektir.

### Validation commands

Targeted:

```text
python -m pytest -q tests/test_agenda_keys.py tests/test_agenda_deadline_stage.py tests/test_agenda_state_repository.py
python tests/smoke_sts_agenda_schema.py
python tests/smoke_sts_database.py
```

Regression/full, makul environment'da:

```text
python -m pytest -q
```

PySide gerekmediği için agenda domain/repository tests offscreen QApplication oluşturmamalıdır.

## 8. Known blockers / provider-stage constraints

### Not an Aşama 1B blocker: activity actor identity

`activity_logs` stable `actor_staff_id` taşımıyor. `actor` display string ve `device_name` var. Bazı system/delivery log paths explicit actor geçmediği için default `"Kullanıcı"` riski de bulunuyor.

Sonuç: Aşama 1B modelde `actor_staff_id` future-capable nullable field olarak kalabilir, fakat ActivityProvider current logs'dan bu alanı uydurmamalıdır.

### Not an Aşama 1B blocker: responsible-change event

`contract_updated` before/after shape yalnız `status`, `note`, `completion_date`, `acceptance_date` içerir. Responsible engineer relation changes bu log shape'e girmez.

Sonuç: future ActivityProvider “responsible changed” event üretmemelidir; ayrıca audit/migration kararı gerekir.

### Share `REJECTED` write path

Status constant/final-state semantics doğrulandı ancak exact `REJECTED` transition writer bu audit'te doğrulanamadı. Returned-share condition yalnız exact `RETURNED` registry status query'sine dayanacağı için Aşama 1B blocker değildir.

### Schema version concurrency

Base branch version `17`; feature target `18`. Parallel branch migration bump'ı tahmin edilmeyecek. Main integration prompt'u geldiğinde main current `CURRENT_SCHEMA_VERSION` yeniden okunacak ve agenda migration target version tekrar uzlaştırılacaktır.

## 9. Aşama 1B hard boundaries

Aşama 1B uygulayıcı:

- `DeadlineAgendaProvider` yazmayacak.
- `ActivityAgendaProvider` yazmayacak.
- başka provider yazmayacak.
- `StaffAgendaService` engine yazmayacak.
- visibility/new/event TTL policy engine yazmayacak.
- presentation profile auto-resolution yazmayacak.
- role adına hardcode yapmayacak.
- `agenda_items` tablosu oluşturmayacak.
- `main_window.py`, `main_page_analysis_window.py`, calendar UI, share UI, contract UI değiştirmeyecek.
- current `sts_database.py` migration flow'unu refactor etmeyecek.
- repository mutation'larda unconditional commit yapmayacak.

## 10. Implementation readiness conclusion

Aşama 1A audit'ine göre Aşama 1B agenda domain/state foundation için source-of-truth yeterlidir. Uygulama `CURRENT_SCHEMA_VERSION 17 -> 18`, bağımsız `src/domain/agenda` package'i, aynı `STSDatabase.tx()` abstraction'ını kullanan `AgendaStateRepository` ve real temp STS tests ile sınırlandırılabilir.
