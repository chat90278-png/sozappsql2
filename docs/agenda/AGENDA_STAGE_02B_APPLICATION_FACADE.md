# Gündemim Aşama 2B — Personal Application Facade

## Scope

Bu aşama, Aşama 2A personal condition engine üzerine UI bağımsız application katmanını ekler. `current_staff` session snapshot'ı `AgendaContext` modeline dönüştürülür; `StaffAgendaService` facade üzerinden çağrılır; seen ve condition snooze interaction'ları tek bir personal application API'sinde toplanır; compact/detail sunum projeksiyonu immutable snapshot olarak üretilir.

Qt widget, pencere, main page veya main window entegrasyonu bu aşamada yoktur.

## Current staff ve context kaynağı

Gerçek auth akışı `build_current_staff(...)` ile `id`, `is_active`, role metadata ve cihaz/personel alanlarını oluşturur; normal login/register akışı `auth.enrich_staff_permissions(db_or_path, staff)` ile `permissions` setini ve mümkünse `db_path` değerini session'a ekler.

`PersonalAgendaContextFactory`:

- `current_staff.id` için pozitif personel kimliği ister;
- pasif personeli reddeder;
- mevcut enriched `permissions` alanını defensive `frozenset` snapshot'a dönüştürür;
- permissions eksik ve session'da `db_path`/`_db_path` varsa gerçek `auth.enrich_staff_permissions(db_or_path, staff)` imzasıyla fallback enrichment yapar;
- role adından capability üretmez;
- `view_contracts` bulunmasa da context üretir; read gate'i `StaffAgendaService`, interaction gate'i facade uygular;
- timezone-aware `datetime` girdisini mevcut naive runtime yaklaşımına normalize eder;
- positive personal contract override ID'lerini dedupe ederek `frozenset` üretir.

## Permission ve personal profile

Tek presentation profile:

- code: `PERSONAL`
- display name: `Kişisel kapsam`
- description: `Sorumlu olduğunuz sözleşmelerde dikkat isteyen maddeler.`
- permissions: current session capability snapshot

Admin, manager, personnel veya viewer role adları authorization amacıyla kullanılmaz.

## Sensitive field exclusion

UI/application-facing context snapshot'ından şu alanlar çıkarılır:

- `password_hash`
- `password`
- `password_salt`
- `secret`
- `token`

Input `current_staff` mapping'i mutate edilmez.

## Application graph

`PersonalAgendaFacade` dependency graph'i:

1. shared `AgendaStateRepository(db)`
2. `PersonalAgendaContextFactory()`
3. `StaffAgendaService(db, state_repository=shared_state_repository)`
4. `project_agenda_result(...)`

Facade ve service aynı state repository instance'ını paylaşır. Yeni SQLite connection açılmaz; repository mevcut `STSDatabase.conn` bağlantısını kullanır.

## Load

`PersonalAgendaFacade.load(...)`:

1. current staff'tan personal `AgendaContext` oluşturur;
2. `StaffAgendaService.build(context, touch_presented=...)` çağırır;
3. `AgendaResult` değerini immutable `AgendaPresentationSnapshot` modeline projekte eder.

Load akışı `mark_seen` veya `snooze` çağırmaz. `touch_presented=False` pure-read preview akışları için korunur.

## Seen interaction

`mark_seen(current_staff, item, seen_at=...)`:

- current staff identity ve `view_contracts` permission'ını doğrular;
- public raw `staff_id` almaz;
- item'ın exact effective `key` ve `version` değerlerini `AgendaStateRepository.mark_seen(...)` çağrısına geçirir;
- repository değer döndürmezse persisted row'u `get_states(...)` ile tekrar okur;
- otomatik agenda rebuild yapmaz.

Item içindeki `actor_staff_id` state write hedefi olarak kullanılmaz.

## Snooze ve clear snooze

`snooze(...)` yalnız:

- lifecycle type `CONDITION`,
- `supports_snooze=True`,
- future `until`

şartlarıyla çalışır. Exact effective item version ve `item.severity.value` state repository'ye yazılır. EVENT item'ları ve non-snoozable condition'lar reddedilir.

Preset kodları:

- `tomorrow`: sonraki takvim günü 09:00
- `three_days`: now + 3 gün, second/microsecond sıfırlanmış
- `one_week`: now + 7 gün, second/microsecond sıfırlanmış

`clear_snooze(...)` mevcut row yoksa `None` döndürür ve boş row oluşturmaz. Mevcut row'da seen ve dismiss alanları repository davranışıyla korunur.

EVENT dismiss facade API'si bu aşamada özellikle eklenmemiştir.

## Presentation projection

`project_agenda_result(...)`, `StaffAgendaService` sırasını değiştirmeden merkezi presentation policy uygular:

- compact default limit: 2
- detail default limit: 20
- `all_items`: bütün visible item'lar
- `compact_items`: ilk compact limit
- `detail_items`: ilk detail limit
- `has_more`: `active_count > detail_limit`
- severity counts: stable `AgendaSeverity.value`

`AgendaPresentationSnapshot` frozen dataclass'tır. Tuple/frozenset ve `MappingProxyType` defensive copy'leri kullanır. Compact ve detail limitleri birbirinden bağımsızdır; negatif ve boolean limitler reddedilir.

## Excluded

Bu aşamada özellikle yoktur:

- Qt UI veya widget wiring
- main window / main page değişikliği
- ActivityProvider
- ShareProvider
- DocumentLockProvider
- manager/admin/viewer presentation scope
- raw activity log
- actor identity inference
- EVENT dismiss public API
- Stage 2A provider/lifecycle/source rule değişikliği
- schema, transaction veya agenda state SQL değişikliği

## Tests

Source testleri:

- `tests/test_agenda_context_factory.py`
- `tests/test_agenda_presentation.py`
- `tests/test_personal_agenda_facade.py`

Kapsam:

- staff validation ve active gate
- enriched permission snapshot ve role-name non-authorization
- personal profile/time/contract override
- sensitive field exclusion ve input immutability
- compact/detail projection, order, counts ve immutable mappings
- facade load ve `touch_presented` forwarding
- shared state repository / no new SQLite connection
- exact effective version ile mark seen
- condition-only snooze, future validation ve severity snapshot
- clear snooze seen-state preservation
- preset calculations
- cross-staff write prevention

## Main ve schema integration riski

Feature schema version 18 olarak kalır. Current main, feature base'inden ilerlemiştir ve automatic STS schema upgrade engine taşır. Main entegrasyonundan önce:

- explicit v17→v18 migration contract,
- schema v18 fingerprint registry/manifest reconciliation,
- current main'in integration baseline olarak alınması,
- final current-main differential validation

zorunludur.

## Main Merge Gate

CLOSED.

Bu belge izole feature geliştirmesini belgeler; main merge yetkisi vermez.
