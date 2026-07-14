# Gündemim — Source of Truth Audit

**Audit ref:** `feature/gundemim-agenda-system`  
**BASE_SHA:** `2931fa267560397d4d849d6365acde504f376775`  
**Audit scope:** Aşama 1A; branch isolation ve repo source-of-truth doğrulaması. Foundation/UI/provider/engine kodu bu aşamada yazılmamıştır.

## 1. Auth / Staff / Permission

### Current staff akışı

- `app.py::main()` içinde `auth.ensure_system_admin_setup(selected_path)` sonrası `staff = auth.require_staff_login(selected_path)` çağrılır.
- Aynı startup akışı `MainWindow(initial_path=selected_path, current_staff=staff)` ile personel snapshot'ını UI root'una geçirir.
- `src/ui/main_window.py::MainWindow.__init__(..., current_staff: Optional[dict] = None)` içinde `self.current_staff = current_staff or auth.current_staff` kullanılır.
- `src/auth.py` modülünde global `current_staff: Optional[dict[str, Any]] = None` bulunur.
- `src/auth.py::require_staff_login(db_or_path, parent=None)` aktif cihaz/personel eşleşmesini çözer, `enrich_staff_permissions(...)` ile permission snapshot'ını ekler, global `current_staff` değerini set eder ve staff dict döndürür.
- `src/ui/main_window.py::_permission_db()` mevcut `STSStore.db.conn` varsa aynı canlı SQLite connection'ı, aksi halde path'i permission resolver'a verir.

### Permission registry ve resolver source of truth

**File:** `src/auth.py`

- `PERMISSION_GROUPS`: permission code registry/source-of-truth.
- `DEFAULT_PERMISSIONS`: registry'nin flatten edilmiş code set'i.
- `DEFAULT_ROLE_PERMISSIONS`: manager/personnel/viewer sistem rollerinin başlangıç permission map'i.
- `LEGACY_PERMISSION_ALIASES`: legacy code canonicalization.
- `FULL_ACCESS_PERMISSIONS = {"manage_staff", "manage_roles"}`.

Exact resolver:

```python
def has_permission(
    current_user: Optional[dict[str, Any]],
    permission_code: str,
    db_or_path: sqlite3.Connection | str | Path | None = None,
) -> bool
```

Davranış:

1. `current_user` yoksa global `current_staff` kullanılır.
2. Boş code `False`.
3. Aktif `is_admin` staff tüm permission'larda `True`.
4. Permission restrictions disabled ise `True`.
5. Staff yok/pasif ise `False`.
6. Legacy alias canonical code'a çevrilir.
7. DB context yoksa `staff["permissions"]` snapshot'ı kontrol edilir.
8. DB context varsa active staff + `role_id` + `role_permissions` üzerinden exact SQL resolution yapılır.
9. Gerekirse legacy alias rows da kontrol edilir.

Exact guard:

```python
def require_permission(
    current_user,
    permission_code,
    db_or_path=None,
) -> None
```

`has_permission(...)` false ise `PermissionError` yükseltir. Ayrıca `staff_has_permission`, `has_any_permission`, `require_any_permission` mevcuttur.

`src/auth.py::has_role(...)` intentional olarak `RuntimeError` yükseltir; fixed role-name authorization kullanılmamalıdır. Gündem görünürlük/action kararları role adına göre değil `has_permission`/permission snapshot üzerinden kurulmalıdır.

### Authorization schema

`roles`:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `name TEXT NOT NULL UNIQUE`
- `display_name TEXT NOT NULL`
- `is_system INTEGER NOT NULL DEFAULT 1`
- `created_at TEXT DEFAULT CURRENT_TIMESTAMP`
- `updated_at TEXT`

`permissions`:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `code TEXT NOT NULL UNIQUE`
- `display_name TEXT NOT NULL`
- `description TEXT`
- `category TEXT`

`role_permissions`:

- `role_id INTEGER NOT NULL`
- `permission_code TEXT NOT NULL`
- `is_allowed INTEGER NOT NULL DEFAULT 0`
- `PRIMARY KEY(role_id, permission_code)`
- role/permission FK'leri `ON DELETE CASCADE`.

### Staff exact schema

`src/auth.py::ensure_staff_table(...)` source-of-truth:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `device_name TEXT NOT NULL UNIQUE`
- `full_name TEXT NOT NULL`
- `password_hash TEXT NOT NULL`
- `role TEXT DEFAULT 'personnel'`
- `role_id INTEGER`
- `is_active INTEGER DEFAULT 1`
- `last_login_at TEXT`
- `created_at TEXT DEFAULT CURRENT_TIMESTAMP`
- `updated_at TEXT`
- `FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE SET NULL`

### Default role semantics

Seed edilen normal sistem rolleri: `manager`, `personnel`, `viewer`. `admin` normal role-based authorization değildir; system-admin staff snapshot'ındaki `is_admin` special path ile tam yetki elde eder. `NORMAL_ROLE_NAMES = {"manager", "personnel", "viewer"}`.

- `manager`: contract/operation/SQL/history/database/document lock alanlarında geniş permission set.
- `personnel`: `view_contracts`, `create_contracts`, `edit_contracts`, `export_data`, `open_sql_panel`, `sql_read`, `lock_documents`, `unlock_own_documents`.
- `viewer`: `view_contracts`.

### Gündem için güvenli permission snapshot

Minimum source-of-truth:

```python
staff = auth.enrich_staff_permissions(db_or_conn, current_staff)
permissions = frozenset(staff.get("permissions") or ())
```

Canlı action validation için yine `auth.has_permission(staff, code, conn)` kullanılmalıdır. Presentation profile bir role değildir; role name hardcode edilmemelidir.

## 2. Contract Responsibility

### Exact schema

`src/services/sts_database.py::init_schema()`:

```sql
CREATE TABLE IF NOT EXISTS contract_responsible_engineers (
    contract_id INTEGER NOT NULL,
    staff_id INTEGER NOT NULL,
    sort_order INTEGER DEFAULT 0,
    is_primary INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(contract_id, staff_id),
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
    FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
)
```

Indexes:

- `idx_contract_resp_eng_contract(contract_id)`
- `idx_contract_resp_eng_staff(staff_id)`

### Store methods

`src/services/sts_store.py::list_staff_for_engineer_selection()`:

- `staff` tablosundan yalnız `COALESCE(is_active,1)=1` rows.
- `id`, `staff_id`, `full_name`, `device_name`, `role_id`, `is_active` döndürür.

`STSStore.get_contract_responsible_engineers(contract_id=None, platform=None, contract_no=None, contract_type="Ana Sözleşme")`:

- `contract_id` yoksa `_resolve_contract_id(...)` kullanır.
- CRE -> staff JOIN yapar.
- **Active staff filter uygulamaz.** Bu, `inactive_responsible` condition audit'i için önemlidir.
- Order: `sort_order ASC, is_primary DESC, full_name COLLATE NOCASE`.

`STSStore.set_contract_responsible_engineers(contract_id: int, staff_ids: List[int]) -> None`:

- input IDs dedupe edilir.
- yalnız active staff IDs korunur.
- ilgili contract rows tamamen silinir.
- sıralı yeniden insert yapılır.
- ilk row `is_primary=1`.
- kendi başına commit etmez.

### Multi-platform / contract identity

`contract_platforms` bridge contract'ı birden fazla platform presentation'ına bağlar. `STSStore._resolve_contract_id(...)` `contracts -> contract_platforms -> platforms` JOIN'iyle contract ID çözer. `list_main_contracts(platform)` aynı `contracts.id` aggregate'ını bağlı olduğu her platform view'ında gösterebilir.

Sonuç: Gündem aggregate identity için `contract_id` source-of-truth'tur. Aynı contract birden fazla platform presentation'ında görünse de personal responsibility set'i platform başına çoğaltılmamalıdır.

### Personal contract IDs için minimum güvenli source

```sql
SELECT DISTINCT cre.contract_id
FROM contract_responsible_engineers cre
JOIN staff s ON s.id = cre.staff_id
WHERE cre.staff_id = ?
  AND COALESCE(s.is_active, 1) = 1
```

Bu query role name kullanmaz ve `contract_id` identity'sini korur.

`inactive_responsible` provider ileride ayrı query kullanmalı ve relation rows'u active filter ile kaybetmemelidir.

### Önemli write-path limiti

`STSStore.write_contract(...)` mevcut UI projection'dan tek `responsible_engineer_id` seçip:

```python
set_contract_responsible_engineers(cid, [responsible_engineer_id] if responsible_engineer_id else [])
```

çağırır. Normal contract save path'i bridge'i fiilen tek responsible row'a indirger.

Ayrıca `contract_updated` before/after shape içinde responsible staff IDs/names yoktur. Bu nedenle mevcut activity logdan “sorumlu personel değişti” event'i güvenli şekilde çıkarılamaz.

## 3. Activity Logs

### Exact schema

`src/services/sts_database.py::init_schema()`:

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

Indexes:

- `idx_logs_created_at(created_at)`
- `idx_logs_action(action)`
- `idx_logs_entity(entity_type, entity_id)`
- `idx_activity_logs_platform_contract(platform_id, contract_no)`

**Actor identity:** `actor_staff_id` kolonu yoktur. Actor yalnız display text `actor` alanıdır; `device_name` ayrıca vardır. Bu nedenle stable person identity activity log source-of-truth'ta doğrudan mevcut değildir.

### `STSDatabase.add_log`

Exact signature:

```python
def add_log(
    self,
    action: str,
    entity_type: str = "",
    entity_key: str = "",
    message: str = "",
    payload: dict | None = None,
    actor: str | None = None,
    source: str | None = None,
    device: str | None = None,
    entity_id: str | int | None = None,
    platform: str | None = None,
    contract_no: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
)
```

- `created_at=now_iso()`.
- `before`, `after`, `payload` `json.dumps(..., ensure_ascii=False)` ile JSON text olur.
- `entity_id` string persist edilir.
- platform string `_platform_id` üzerinden FK ID'ye çevrilir.
- exception swallow edilir.
- **unconditional `self.conn.commit()` yapar.** Bu davranış AgendaStateRepository için kopyalanmamalıdır.

### `STSDatabase.list_logs`

Exact signature:

```python
def list_logs(
    self,
    limit: int = 500,
    action: str | None = None,
    entity_type: str | None = None,
    platform: str | None = None,
    contract_no: str | None = None,
    search: str | None = None,
)
```

- `activity_logs l` + platform name select edilir.
- Optional exact filters uygulanır.
- Search: message/entity_key/actor/source/device/action/platform/contract_no.
- `ORDER BY created_at DESC`.
- positive limit varsa `LIMIT ?`.

`STSStore.list_logs(...)` aynı parametreleri `db.list_logs(...)` wrapper'ına geçirir.

### Proven action/shape matrix

| Action code | Source file / function | Entity | before shape | after shape | payload shape | Gündem event adayı |
|---|---|---|---|---|---|---|
| `contract_created` | `STSStore.write_contract` | `contract` | `None` | `{status,note,completion_date,acceptance_date}` | `{system_count,delivery_count,component_count}` | Hayır; creation noise |
| `contract_updated` | `STSStore.write_contract` | `contract` | `{status,note,completion_date,acceptance_date}` | aynı keys | counts | **Whitelist adayı**, yalnız proven fields |
| `contract_status_changed` | `STSStore.write_contract` | `contract` | `{status}` | `{status}` | none | **Whitelist adayı** |
| `system_created` | `STSStore.write_contract` | `system` | none | flat system + nested `components` | none | Hayır/sonraki karar |
| `system_deleted` | `STSStore.write_contract` | `system` | system shape | none | none | Hayır/sonraki karar |
| `system_updated` | `STSStore.write_contract` | `system` | system shape | system shape | none | **Whitelist adayı**, field whitelist şart |
| `system_component_updated` | `STSStore.write_contract` | `system` | `{components}` | `{components}` | none | Şimdilik hayır; high-volume |
| `delivery_created` | `STSStore.write_contract` | `delivery` | none | delivery shape | none | Hayır/sonraki karar |
| `delivery_deleted` | `STSStore.write_contract` | `delivery` | delivery shape | none | none | Hayır/sonraki karar |
| `delivery_updated` | `STSStore.write_contract` | `delivery` | delivery shape excluding `id` | delivery shape | none | **Whitelist adayı**, field whitelist şart |
| `delivery_status_changed` | `STSStore.write_contract` | `delivery` | `{status}` | `{status}` | none | **Whitelist adayı** |
| `documents_locked` | `STSStore.lock_documents` | `document_lock` | none | none | `{contract_id,locked_by_device_name}` | Condition source değil; lock table kullanılmalı |
| `documents_unlocked` | `STSStore.unlock_documents` | `document_lock` | none | none | `{contract_id}` | Condition source değil |
| `document_folder_created` | `STSStore.create_contract_file_folder` | `document_folder` | none | none | `{name,parent_id,path}` | Hayır |
| `document_folder_deleted` | `STSStore.delete_contract_file_folder` | `document_folder` | `{name,parent_id,file_count,subfolder_count}` | none | none | Hayır |
| `document_deleted` | `STSStore.delete_contract_file` | `document` | DB row subset | none | none | Hayır |
| `document_moved` | `STSStore.move_contract_file` | `document` | `{folder_id}` | `{folder_id}` | none | Hayır |
| `document_folder_moved` | `STSStore.move_contract_file_folder` | `document_folder` | `{parent_id}` | `{parent_id}` | none | Hayır |
| `share_merge_applied` | `share_merge_apply_service._insert_audit_log` | `share_package` | none | none | package/operation/hash/revision summary | Generic aggregate audit; field-level event için yetersiz |

### Exact business JSON shapes

`contract_updated` before/after **full contract snapshot değildir**. Exact keys:

```json
{
  "status": "...",
  "note": "...",
  "completion_date": "...",
  "acceptance_date": "..."
}
```

- completion date exact key: `completion_date`
- acceptance date exact key: `acceptance_date`
- status exact key: `status`
- responsible staff değişikliği: **shape içinde yok**

System write shape flat top-level fields + nested components map karakterindedir:

```text
status
completion_date
acceptance_date
components: {component_name: qty}
```

Delivery write shape flat top-level fields + nested components map karakterindedir:

```text
status
planned_acceptance_date
acceptance_date
note
components: {
  component_name: {planned, delivered}
}
```

`planned_acceptance_date` exact key adı budur.

### Actor identity risk

1. `activity_logs` stable `actor_staff_id` taşımaz.
2. Actor display string ile identity kurmak isim değişimi/aynı isim riskine açıktır.
3. Bazı `write_contract` system/delivery log çağrıları explicit actor geçmez; `add_log` default actor'a düşebilir ve `"Kullanıcı"` görülebilir.
4. `share_merge_applied` service kendi `_ApplyContext.current_staff_id` değerini taşır ancak audit row schema'ya staff ID yazmaz; payload'da da actor staff ID yoktur.

Sonuç: ActivityProvider gelecekte actor text'i stable identity gibi kullanmamalıdır. “Kendi yaptığım değişiklikleri filtrele” kuralı mevcut log schema ile tam güvenli değildir. Provider yalnız audit ile kanıtlanan action/field whitelist'inden başlamalı; stable actor identity gerekiyorsa ayrı ürün/migration kararı gerekir.

### Güvenli ilk whitelist adayları

- `contract_updated`: `completion_date`, `acceptance_date`, `status` değişikliği.
- `contract_status_changed`: `status`.
- `system_updated`: yalnız `completion_date`, `acceptance_date`, `status`.
- `delivery_updated`: yalnız `planned_acceptance_date`, `acceptance_date`, `status`.
- `delivery_status_changed`: `status`.

`note`, nested components, generic share merge payload ve responsible change bu audit ile güvenli ActivityProvider input'u olarak onaylanmamıştır.

## 4. Share Lifecycle

### Status source of truth

`src/models/share_models.py`:

- `SHARE_STATUS_OPEN = "OPEN"`
- `SHARE_STATUS_RETURNED = "RETURNED"`
- `SHARE_STATUS_MERGED = "MERGED"`
- `SHARE_STATUS_PARTIALLY_MERGED = "PARTIALLY_MERGED"`
- `SHARE_STATUS_REJECTED = "REJECTED"`
- `SHARE_STATUS_CANCELLED = "CANCELLED"`

`SHARE_PACKAGE_STATUSES` tüm altı değeri içerir.

`src/services/share_lifecycle_service.py`:

- `ACTIVE_SHARE_STATUSES = {OPEN, RETURNED}`
- `CANCELABLE_SHARE_STATUSES = {OPEN, RETURNED}`
- `FINAL_SHARE_STATUSES = {MERGED, PARTIALLY_MERGED, CANCELLED, REJECTED}`
- `CANCEL_SHARE_PERMISSION = "edit_contracts"`

### `share_packages` exact schema

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `share_package_id TEXT NOT NULL UNIQUE`
- `contract_id INTEGER NOT NULL`
- `contract_merge_uid TEXT NOT NULL`
- `source_contract_revision INTEGER NOT NULL`
- `permission_mode TEXT NOT NULL`
- `share_format_version INTEGER NOT NULL`
- `snapshot_format_version INTEGER NOT NULL`
- `base_snapshot_sha256 TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `created_by_staff_id INTEGER`
- `created_by_username TEXT NOT NULL DEFAULT ''`
- `created_by_full_name TEXT NOT NULL DEFAULT ''`
- `exported_filename TEXT NOT NULL DEFAULT ''`
- `status TEXT NOT NULL DEFAULT 'OPEN'`
- `last_imported_at TEXT`
- `last_imported_by_staff_id INTEGER`
- `last_remote_snapshot_sha256 TEXT NOT NULL DEFAULT ''`
- `merge_result_sha256 TEXT NOT NULL DEFAULT ''`
- `merge_result_operations_applied INTEGER`
- `merge_result_operations_skipped INTEGER`
- `merged_at TEXT`
- `return_count INTEGER NOT NULL DEFAULT 0`
- `cancelled_at TEXT`
- `cancelled_by_staff_id INTEGER`
- `cancelled_by_username TEXT NOT NULL DEFAULT ''`
- `cancelled_by_full_name TEXT NOT NULL DEFAULT ''`

Indexes:

- `idx_share_packages_contract_merge_uid(contract_merge_uid)`
- `idx_share_packages_contract_status(contract_merge_uid,status)`
- `idx_share_packages_created_at(created_at)`

### Transition source of truth

**Create/Open**

- `ContractWorkWindow.create_contract_share_file(...)` V2 share dosyasını/temp path'i, immutable base snapshot ve metadata'yı oluşturur.
- `SharePackageRegistryEntry(... status=SHARE_STATUS_OPEN)` üretir.
- `STSStore.register_share_package(entry)` source registry'ye row insert eder; `SHARE_PACKAGE_STATUSES` validation ve duplicate identity consistency uygular; `db.tx()` kullanır.

**Open/import validation**

- `share_package_service.validate_share_package(...)`, `read_share_metadata(...)`, `parse_share_metadata(...)` package metadata/base snapshot integrity source'udur.

**Return**

- `share_merge_service.prepare_share_merge_plan(...)` valid V2 package provenance ve source registry doğrulamasından sonra `_mark_package_returned_if_open(...)` çağırır.
- Exact transition: `OPEN -> RETURNED`, yalnız matching `share_package_id + contract_merge_uid` ve `status=OPEN` row için.
- Existing transaction varsa commit etmez; yoksa commit eder.

**Merge**

- `share_merge_apply_service.apply_resolved_share_merge(...)` preflight + backup sonrası `BEGIN IMMEDIATE` ile operation apply yapar.
- Status validation CANCELLED/REJECTED'i reddeder; OPEN/RETURNED/MERGED/PARTIALLY_MERGED kabul edilen current statuses içindedir.
- Registry sonucu `MERGED` veya `PARTIALLY_MERGED` olur.
- `_update_registry(...)` last import, remote/post hashes, applied/skipped counts, `merged_at` ve `return_count` alanlarını günceller.
- Transaction success commit; exception rollback.

**Cancel**

- `share_lifecycle_service.ensure_can_cancel_share_package(...)` share-mode'u reddeder, `auth.has_permission(current_staff, "edit_contracts", conn)` doğrular, package/contract identity ve status kontrol eder.
- `cancel_share_package(...)` yalnız `OPEN`/`RETURNED` row'u atomik olarak `CANCELLED` yapar ve cancel actor/timestamp metadata'sını yazar.
- STSStore varsa `db.tx()` kullanır; raw connection fallback `BEGIN IMMEDIATE/commit/rollback` kullanır.

**Rejected**

- `REJECTED` constant/final-state semantics ve merge validation'da blocking davranışı doğrulandı.
- Bu audit sırasında `REJECTED` durumuna yazan exact transition function **doğrulanamadı**. Activity/provider tasarımında varsayılmamalıdır.

### Returned-share condition için exact source

Provider ileride activity log veya share file metadata'dan inference yapmamalı. Source registry query kullanılmalıdır:

```sql
SELECT sp.*
FROM share_packages sp
WHERE sp.status = ?
```

parameter: `SHARE_STATUS_RETURNED`.

Presentation için contract JOIN `sp.contract_id = contracts.id` üzerinden yapılabilir. Condition key `share_package_id` stable package identifier üzerinden kurulmalıdır.

## 5. Document Locks

### Exact schema/source

`src/auth.py::ensure_document_locks_table(...)`:

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

Per-contract lock key: unique `contract_id`.

### Read/write semantics

- `auth.get_document_lock_state(db_or_path, contract_id)` exact row'u okur; row yoksa explicit unlocked dict döndürür.
- `auth.lock_documents(...)` UPSERT ile `is_locked=1`, staff/device/full_name owner metadata ve `locked_at=CURRENT_TIMESTAMP`, `updated_at=CURRENT_TIMESTAMP` yazar.
- `auth.unlock_documents(...)` UPSERT ile `is_locked=0`, owner fields ve `locked_at` clear eder; `updated_at=CURRENT_TIMESTAMP`.
- Bu auth helper'lar commit eder.
- `STSStore.document_lock_state(...)` contract ID çözerek auth read helper'ına gider.
- `STSStore.lock_documents(...)` ve `unlock_documents(...)` state write sonrası activity log ekler.

### Owner/access semantics

`auth.can_current_staff_access_documents(lock_state, staff)`:

1. unlocked => `True`
2. active `is_admin` => `True`
3. staff yok => `False`
4. normal staff => current `device_name == locked_by_device_name`

`auth.require_document_unlock_password(...)` lock owner `locked_by_staff_id` ile active staff row çözer ve kilitleyen staff'ın password hash'ini doğrular; success'te `unlock_documents(...)` çağırır.

Permission registry'de exact codes vardır:

- `lock_documents`
- `unlock_own_documents`
- `unlock_all_documents`

Önemli ayrım: auth low-level `unlock_documents(...)` helper'ı kendi içinde permission-code check yapmaz. Action permission routing UI/service caller sorumluluğundadır. Future provider visibility/action hint üretirken permission set kullanmalı; repository/state katmanı bu business policy'yi üstlenmemelidir.

### Stale-lock age source

Exact source: `document_locks.locked_at`.

Write source `SQLite CURRENT_TIMESTAMP` olduğundan persisted text karakteri `YYYY-MM-DD HH:MM:SS` olur. Future stale-lock provider mümkünse SQLite `julianday('now')`/`julianday(locked_at)` ile aynı clock semantics içinde age hesaplamalı veya timestamp'i açıkça normalize etmelidir. `now_iso()` local wall-clock ile doğrudan naive subtraction yaparak timezone varsayımı eklenmemelidir.

Condition filter minimum:

```sql
WHERE is_locked = 1
  AND locked_at IS NOT NULL
```

## 6. STS Database / Migration / Transaction

### Source of truth

**File:** `src/services/sts_database.py`

- `CURRENT_SCHEMA_VERSION = 17`
- `STSMigrationError`
- `read_sts_schema_version(path)` read-only `mode=ro` schema read.
- `STSDatabase.__init__(path, source="Main UI")`
- `STSDatabase.init_schema()`
- `STSDatabase._ensure_column(table, name, ddl)`
- `STSDatabase._create_runtime_indexes()`
- `STSDatabase.tx()`
- `_validate_after_migration(...)`

### Migration flow

1. Constructor pre-open schema version okur.
2. Future version `> CURRENT_SCHEMA_VERSION` ise fail.
3. Legacy/old schema için DB açılmadan önce backup path oluşturulur ve `copy2` alınır.
4. SQLite connection açılır; `foreign_keys=ON`, WAL, busy timeout, synchronous/cache settings uygulanır.
5. `init_schema()` çalışır.
6. Migration yapıldıysa post-validation çalışır.
7. Failure'da connection kapatılır ve backup restore edilmeye çalışılır; `STSMigrationError` yükseltilir.
8. Success'te schema migration/database lifecycle logları yazılır.

Backup filename karakteri:

`__backup_before_migration_v<old>_to_v17__<timestamp>.sts`

### `init_schema()` convention

- Büyük `executescript` içinde `CREATE TABLE IF NOT EXISTS` DDL'leri.
- Incremental compatibility için `_ensure_column(...)`.
- Data backfill/normalization gerektiğinde `with self.tx():`.
- Runtime indexes `_create_runtime_indexes()` içinde table/column existence check ile conditional `CREATE INDEX IF NOT EXISTS`.
- Auth/staff ve document lock compatibility helpers mevcut migration flow'a entegre.
- Final `meta.schema_version` current value ile `INSERT OR REPLACE` edilir ve commit edilir.

Post-validation:

- `PRAGMA integrity_check` sonucu exact `ok` olmalı.
- `PRAGMA foreign_key_check` boş olmalı.
- disk schema version `CURRENT_SCHEMA_VERSION` ile eşit olmalı.

### Timestamp source

`now_iso()`:

```python
datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

Local wall-clock, sortable second-resolution text.

### Nested transaction / SAVEPOINT semantics

`STSDatabase.tx()`:

- `conn.in_transaction` true ise unique SAVEPOINT açar.
- success'te RELEASE.
- exception'ta `ROLLBACK TO SAVEPOINT`, sonra RELEASE ve re-raise.
- outer transaction yoksa context success'te `conn.commit()`, exception'ta `conn.rollback()`.

### Future AgendaStateRepository commit strategy

**Repository kendi unconditional commit'ini atmamalıdır.**

Doğru yaklaşım:

- Aynı `STSDatabase` / `sqlite3.Connection` source-of-truth kullanılmalı.
- Mutation metotları `with self.db.tx():` kullanmalı veya caller-owned transaction'ı bozmayan aynı abstraction üzerinden çalışmalı.
- `db.tx()` caller transaction içindeyken SAVEPOINT kullandığı için nested atomicity korunur.
- `STSDatabase.add_log()` içindeki unconditional commit agenda persistence pattern'i olarak örnek alınmamalıdır.

## 7. Main Window / Tool Window / Refresh

### Startup ve MainWindow

`app.py::main()` -> `auth.require_staff_login(...)` -> `MainWindow(initial_path=..., current_staff=staff)`.

Gerçek exported MainWindow `src/ui/main_page_analysis_window.py::MainWindow` olup `src/ui/main_page_final_window.MainWindow` üzerinden legacy `src/ui/main_window.py::MainWindow` davranışını genişletir.

### STS load/index completion

`src/ui/main_window.py::start_sts_load(path)`:

1. `STSLoadWorker` validation/migration preparation.
2. `_on_sts_load_finished()` ana thread'de `STSStore(self.path, actor=...)` açar.
3. `_start_sts_index_build()` `STSIndexWorker` başlatır.
4. `_on_sts_index_finished(index_rows)`:
   - `contract_index` set
   - `_store_loading=False`
   - `_index_ready_for_use=True`
   - loading off
   - `_set_platform_items(...)`
   - `update_alert_strip()`
   - `_apply_platform_selection()`
   - connection label update
   - version baseline remember

Bu completion point future agenda refresh için güçlü initial-load hook'tur; Aşama 1B UI yazmayacaktır.

### `request_refresh`

Exact signature:

```python
def request_refresh(
    self,
    select_platform: Optional[str] = None,
    scope: str = "all",
    platform: Optional[str] = None,
)
```

Başta `_notify_tool_windows_data_changed(scope)` çağırır. `scope="all"` STS mode'da contract index rebuild eder, platform items, `update_alert_strip()`, `refresh_open_calendar()` ve selection UI'ını yeniler. `tags`, `platform`, UI-only yolları ayrı optimize edilmiştir.

Future AgendaWidget refresh için `update_alert_strip` override chain ve/veya `request_refresh` sonrası mevcut composition hook'u kullanılmalı; yeni navigation/refresh bus icat edilmemelidir.

### Alert/status composition hook

`src/ui/main_page_analysis_window.py::MainWindow`:

- `build()` -> super -> compact polish -> `_install_contract_status_widget()`.
- `_install_contract_status_widget()` compact calendar/status composition alanına mevcut status widget'ı yerleştirir.
- `update_alert_strip()` override: `super().update_alert_strip()` sonra `_refresh_contract_status_widget()`.

Future compact AgendaWidget için en düşük coupling integration precedent'i bu composition layer'dır. Legacy `src/ui/main_window.py` içine büyük feature UI gömülmemelidir.

### Tool-window source of truth

Exact signature:

```python
def open_or_raise_tool_window(
    self,
    key: str,
    title: str,
    factory: Callable[[], QWidget],
) -> QWidget
```

- `_tool_windows_by_key` registry'de alive existing window varsa `raise_tool_window(key)`.
- stale/dead registration temizlenir.
- `factory()` sonucu `_prepare_tool_window(...)` ile hazırlanır.
- registry'ye eklenir.
- `_create_tool_window_chip(key,title)` open windows strip'e chip ekler.
- destroyed -> `_unregister_tool_window`.
- show/center/raise/activate.

Mevcut örnek keys:

- `report:activity_logs`
- `report:calendar`
- `report:analysis_center`
- `manager:database`

Future Agenda tool window aynı mekanizmayı kullanmalı; örneğin stable key `report:agenda`/ürün kararında kesinleştirilecek key. Modal/new navigation sistemi kurulmayacak.

### Navigation routes

- `show_contract_summary(row, item)` -> `ContractSummaryDialog(... detail_handler=self.open_summary_event_detail)`.
- `open_summary_event_detail(item)` -> `self.open_contract_item(item)`.
- `open_contract_item(item)` contract row projection'dan `store.load_contract_structure(...)` çağırıp `_open_or_raise_contract_window(...)` kullanır.
- `open_calendar_event_detail(ev)` benzer şekilde structure load + `_open_or_raise_contract_window(...)`.
- `_contract_tool_window_key(ci)` mümkünse stable `contract:<contract_id>` üretir.

Future agenda contract navigation yeni contract-window implementation yazmamalı; item payload contract index projection'a çevrilebiliyorsa `open_contract_item`, exact contract structure gerekiyorsa mevcut load + `_open_or_raise_contract_window` route'u reuse edilmelidir.

## 8. Test Conventions

### Repository configuration

- Root `pytest.ini`: bulunamadı.
- Root `pyproject.toml`: bulunamadı.
- `requirements.txt`: PySide6/openpyxl/PyInstaller içeriyor; pytest burada pinli değil.

### Confirmed direct smoke pattern

`tests/smoke_sts_database.py`:

- `TemporaryDirectory()` kullanır.
- `Path(td) / 'v2.sts'` ile gerçek temp `.sts` oluşturur.
- doğrudan `STSDatabase(p)` açar.
- `PRAGMA table_info`, `sqlite_master`, index list, schema_version, `integrity_check`, `foreign_key_check` assert eder.
- raw `sqlite3.connect(legacy_path)` ile minimal legacy schema üretir, sonra `STSDatabase(legacy_path)` ile real migration çalıştırır.
- script sonunda `print('ok')`.

Bu Aşama 1B migration testleri için doğrudan precedent'tir.

`tests/smoke_sts_delivery_core_parity.py`:

- standalone `main()` + direct `assert` pattern.
- PySide smoke için `QT_QPA_PLATFORM=offscreen`.
- repository root `sys.path` insertion.
- success summary print'leri.

### Aşama 1B test recommendation

Yeni pure domain/service tests PySide import etmemelidir. Önerilen exact files:

- `tests/test_agenda_keys.py`
- `tests/test_agenda_deadline_stage.py`
- `tests/test_agenda_state_repository.py`
- `tests/smoke_sts_agenda_schema.py`

Recommended commands:

```text
python -m pytest -q tests/test_agenda_keys.py tests/test_agenda_deadline_stage.py tests/test_agenda_state_repository.py
python tests/smoke_sts_agenda_schema.py
python tests/smoke_sts_database.py
python -m pytest -q
```

Root pytest config olmaması nedeniyle explicit paths kullanmak hedefli validation için daha güvenlidir. Full pytest environment'da pytest'in ayrıca kurulu olması gerekir.

Repository rollback proof için Agenda repository testinde gerçek `STSDatabase`, gerçek active staff row ve outer `with db.tx():` içinde mutation + deliberate exception kullanılmalı; outer rollback sonrası state row yokluğu assert edilmelidir.

## 9. High-Churn / Parallel Main Integration Risk

| Path | Gündem aşaması | Dokunma gerekli mi? | Churn riski | Main integration strategy |
|---|---|---:|---|---|
| `src/services/sts_database.py` | 1B | Evet | Yüksek | Yalnız schema version + agenda table/index diff'i; refactor/format churn yok. Integration anında current main version yeniden okunur; başka branch migration numarası tahmin edilmez. |
| `src/services/sts_store.py` | 1B | Hayır | Yüksek | AgendaStateRepository aynı DB source'u doğrudan kullanır; store'a wrapper ekleme. Provider aşamasında read source'ları gerekirse mevcut methods/SQL ile consume et. |
| `src/auth.py` | 1B | Hayır | Yüksek | Foundation models permission snapshot taşır; resolver değiştirilmez. Future engine `has_permission`/enriched snapshot kullanır. |
| `src/ui/main_window.py` | 1B | Hayır | Çok yüksek | Foundation'da sıfır diff. Future UI mevcut `request_refresh`, `update_alert_strip`, tool-window route'larını reuse eder. |
| `src/ui/main_page_analysis_window.py` | 1B | Hayır | Yüksek | Foundation'da sıfır diff. Future compact widget composition hook burada değerlendirilmeli. |
| `src/domain/calendar_timing.py` | 1B | Hayır | Orta/Yüksek | Agenda deadline stage ayrı pure domain module olur; calendar's 60-day classifier değiştirilmez. Date semantics ileride source comparison için audit edilir. |
| `src/services/share_merge_service.py` | 1B | Hayır | Yüksek | Returned-share condition registry status'tan okunur; merge service değiştirilmez. |
| `src/services/share_merge_apply_service.py` | 1B | Hayır | Çok yüksek | Foundation'da sıfır diff. Generic merge audit payload ActivityProvider için field event source sayılmaz. |
| `src/services/share_lifecycle_service.py` | 1B | Hayır | Orta/Yüksek | Existing status sets consume edilir; lifecycle write code değiştirilmez. |
| `src/models/share_models.py` | 1B | Hayır | Orta | Status constants import/read source olarak kalır. |
| `tests/` | 1B | Evet, yeni files | Orta | Existing tests'i rewrite etmeden yeni isolated agenda domain/repository/schema tests eklenir; `smoke_sts_database.py` regression olarak ayrıca çalıştırılır. |

## 10. Foundation placement conclusion

Repo gerçeklerine göre Aşama 1B için önerilen düşük-coupling placement:

```text
src/domain/agenda/
    __init__.py
    constants.py
    models.py
    keys.py
    deadline_stage.py
    priority.py          # yalnız merkezi rank foundation gerekiyorsa

src/services/agenda_state_repository.py

tests/test_agenda_keys.py
tests/test_agenda_deadline_stage.py
tests/test_agenda_state_repository.py
tests/smoke_sts_agenda_schema.py
```

Merkezi zorunlu diff yalnız `src/services/sts_database.py` migration source-of-truth dosyasında olmalıdır.

## 11. Audit conclusion / provider constraints

Foundation planıyla repo arasında Aşama 1B'yi durduracak kritik çelişki bulunmadı.

Ancak future ActivityProvider için iki kanıtlanmış sınır vardır:

1. stable `actor_staff_id` activity schema'da yoktur ve actor string güvenilir identity değildir;
2. responsible engineer changes normal contract activity before/after shape'inde yoktur.

Bu iki eksik provider aşamasında varsayımla doldurulmamalıdır. Aşama 1B domain/state foundation bu alanlara bağımlı olmadığı için implementation'a geçebilir.
