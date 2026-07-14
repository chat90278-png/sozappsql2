# AŞAMA 5B — GÜNDEMİM CONTROLLED CURRENT-MAIN INTEGRATION

Tarih: 2026-07-14

## 1. Karar sınırı

Bu belge, kabul edilmiş Gündemim kaynaklarının exact current-main tabanı üzerinde kontrollü biçimde bütünleştirilmesini ve Stage 5B-R1 online correction sonucunu kaydeder.

Bu aşama:

- Gündemim kaynak entegrasyonunu tamamlar;
- şema sürümünü 18'e taşır;
- gerçek `17 → 18` migration adımını ekler;
- v18 structural fingerprint sözleşmesini tamamlar;
- Gündemim arayüzünü current-main pencere ve tool-window mimarisiyle bütünleştirir;
- current-main runtime-fix kaynaklarını korur;
- Windows/PySide6 üzerinde source, schema, UI, smoke ve full pytest doğrulamalarını çalıştırır.

Bu aşama Stage 5B-V runtime differential acceptance değildir ve main merge yetkisi vermez.

## 2. Exact refs

- Repository: `chat90278-png/sozappsql2`
- Exact current-main base: `e1ed9a66318e19178f132602d3114a97880fa27f`
- Accepted Agenda feature: `b45d6f2e2b2948d1bbf9dcf1f83c8b04386a5c98`
- Original feature/main merge base: `2931fa267560397d4d849d6365acde504f376775`
- Integration branch: `integration/gundemim-current-main-20260713`
- Initial Stage 5B candidate: `80b6f927d0c0f3a89e8b2cb7cef603892c60202d`
- Accepted Stage 5B-R1 final HEAD: `7cd24e7706599d0b92b5cfb4343a9cf107fc75ca`

Final integration branch durumu:

```text
status: ahead
ahead_by: 10
behind_by: 0
merge_base:
e1ed9a66318e19178f132602d3114a97880fa27f
```

`main` ve `feature/gundemim-agenda-system` refleri entegrasyon boyunca değiştirilmemiştir.

## 3. Entegrasyon stratejisi

Integration branch exact current-main tabanından oluşturulmuştur.

Kabul edilmiş Gündemim kaynakları path-by-path uygulanmıştır. Feature branch history'si:

- merge edilmemiştir;
- rebase edilmemiştir;
- cherry-pick edilmemiştir;
- main branch'e yazılmamıştır.

Current-main ancestry ve runtime kaynakları source of truth olarak korunmuştur.

Kabul edilmiş Agenda domain, provider, service, repository, bağımsız UI, test ve tarihsel doküman dosyaları source blob kimliği korunarak taşınmıştır. Current-main ile semantik bütünleştirme gerektiren dosyalar manuel olarak uyarlanmıştır.

## 4. Kalıcı commit dizisi

Stage 5B ürün entegrasyonu:

1. `c00355edba16c06373c8ef755d9c8063c57ccf32`  
   `Add accepted Agenda core to current main`

2. `667881fb855d422a3463468bc58e72829f07d57c`  
   `Integrate Agenda schema version 18 upgrade`

3. `f653239eb78297aa16c191566a8783bae539ad13`  
   `Integrate Agenda into current main UI`

4. `ee3219faffd09f881b2e8abaad3ebeb11585b22d`  
   `Add Agenda current-main integration coverage`

5. `80b6f927d0c0f3a89e8b2cb7cef603892c60202d`  
   `Record Stage 5B controlled integration`

Stage 5B-R1 correction sonucu:

6. `7cd24e7706599d0b92b5cfb4343a9cf107fc75ca`  
   `Complete Stage 5B-R1 online correction [stage5b-r1-applied]`

Online correction için kullanılan geçici workflow ve executor dosyaları final commit içinde silinmiştir. Final tree geçici validation workflow'u veya patcher içermez.

## 5. Accepted-feature kaynak grupları

Aşağıdaki gruplar accepted Agenda feature kaynağından taşınmıştır:

- tarihsel `docs/agenda/*` Stage 1–4 belgeleri;
- Agenda transaction karar belgesi;
- `src/domain/agenda/**`;
- Agenda provider'ları;
- `agenda_context_factory.py`;
- `agenda_source_repository.py`;
- `agenda_state_repository.py`;
- `personal_agenda_facade.py`;
- `staff_agenda_service.py`;
- `agenda_compact_widget.py`;
- `agenda_detail_window.py`;
- Agenda domain/provider/repository/facade/service/widget testleri;
- `tests/smoke_sts_agenda_schema.py`.

R1 correction yalnız current-main ile semantik bütünleştirme gerektiren production, test ve persistent-document yollarını değiştirmiştir.

## 6. Current-main kaynaklarının korunması

Aşağıdaki current-main kaynakları değiştirilmemiştir:

- `app.py`
- `requirements.txt`
- `src/auth.py`
- `src/ui/main_window.py`
- `src/ui/main_page_final_window.py`
- `src/ui/widgets/contract_status_summary.py`
- `src/ui/widgets/corner_menu_layer.py`
- `src/ui/contract/contract_work_window.py`
- `src/workers/sts_load_worker.py`
- current runtime-fix modülleri
- performans telemetry ve monitoring kaynakları

Bunun sonucu olarak:

- schema upgrade gate ownership worker tarafında korunmuştur;
- normal STS startup sırası korunmuştur;
- share startup yolu korunmuştur;
- Analysis Center ve Corner Menu source of truth korunmuştur;
- mevcut runtime-fix kurulum sırası değiştirilmemiştir.

## 7. Schema version 18

Candidate içinde:

```text
CURRENT_SCHEMA_VERSION = 18
```

Migration registry contiguous durumdadır:

```text
14 → 15
15 → 16
16 → 17
17 → 18
```

Yeni exact step:

```text
v17_to_v18_staff_agenda_state
```

Current-main upgrade engine'in aşağıdaki davranışları korunmuştur:

- verified backup;
- `BEGIN IMMEDIATE`;
- step-by-step schema version update;
- integrity check;
- foreign-key validation;
- rollback validation;
- backup restore fallback;
- current-schema no-op;
- future-schema fail-closed.

## 8. Tek canonical Agenda schema owner

`staff_agenda_state` sözleşmesinin canonical sahibi:

```text
src/services/sts_database.py
```

Canonical helper:

```python
ensure_staff_agenda_state_schema(conn)
```

Helper:

- transaction-neutral çalışır;
- commit veya rollback yapmaz;
- ikinci connection açmaz;
- parent `staff.id` varlığını doğrular;
- malformed preexisting table üzerinde fail-closed davranır;
- exact kolon sırasını doğrular;
- exact primary-key sırasını doğrular;
- exact foreign-key ve `ON DELETE CASCADE` sözleşmesini doğrular;
- exact index adlarını ve kolon sırasını doğrular;
- `agenda_items` tablosunu yasaklar;
- ikinci çağrıda idempotent davranır.

Exact kolon sözleşmesi:

```text
staff_id
agenda_key
first_presented_at
last_presented_at
seen_at
seen_version
snoozed_until
snoozed_version
snoozed_severity
dismissed_at
dismissed_version
created_at
updated_at
```

Exact key ve foreign key:

```text
PRIMARY KEY(staff_id, agenda_key)
FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
```

Exact indexes:

```text
idx_staff_agenda_state_staff(staff_id)
idx_staff_agenda_state_snoozed(staff_id, snoozed_until)
```

Fresh/legacy `STSDatabase.init_schema()` yolu ve explicit `17 → 18` migration yolu aynı helper'ı kullanır.

Önceki runtime monkey-patch/compatibility-export yaklaşımı kaldırılmıştır. State table ve index DDL ownership'i tek yerde toplanmıştır.

## 9. V18 structural fingerprint

`src/services/sts_schema_upgrade_gate.py` v18 için aşağıdaki yapıyı fail-closed doğrular:

- `staff.id`;
- exact `staff_agenda_state` kolonları;
- exact composite PK `(staff_id, agenda_key)`;
- exact FK `staff_id → staff.id`;
- exact `ON DELETE CASCADE`;
- exact index adları;
- exact index kolon sıraları;
- `sts_metadata.sts_instance_id`;
- `agenda_items` yokluğu.

V14–v17 fingerprint sözleşmeleri kendi tarihsel şekillerini korur. V17 fingerprint, Agenda state tablosunu zorunlu tutmaz. V18 structural drift kabul edilmez.

## 10. Gerçek tarihsel v17 fixture

Schema testleri artık v18 database'i yalnız metadata değiştirerek sahte v17 olarak etiketlemez.

Genuine v17 fixture upgrade öncesinde:

- `schema_version == 17`;
- `staff` ve `staff.id` mevcut;
- `staff_agenda_state` yok;
- iki Agenda state index'i yok.

Upgrade sonrasında:

- yalnız `v17_to_v18_staff_agenda_state` uygulanır;
- final version 18 olur;
- exact table, PK, FK/CASCADE ve index sözleşmesi oluşur;
- v18 fingerprint PASS olur.

Ayrıca aşağıdaki durumlar test edilir:

- missing parent reject;
- malformed preexisting table reject;
- transaction ownership;
- idempotency;
- reopen persistence;
- staff delete cascade;
- forbidden `agenda_items`;
- current v18 no-op;
- future version reject;
- rollback ve restore davranışı.

## 11. Current-main UI composition

Gündemim current-main ana pencere kompozisyonuna eklenmiştir.

Korunan yapı:

- `CompactMainWindow` tabanı;
- Analysis Center route;
- current contract status widget;
- current CornerMenuOverlay;
- current calendar;
- existing update/start/file-switch hooks.

Header semantic order:

```text
Contract status → Agenda → Calendar
```

Status ve Agenda install işlemleri idempotent hale getirilmiştir:

- repeated install yeni status widget oluşturmaz;
- repeated install yeni Agenda widget oluşturmaz;
- repeated install yeni refresh timer oluşturmaz;
- signal bağlantıları creation sırasında yalnız bir kez yapılır;
- stale/deleted Qt objeleri güvenli biçimde yeniden oluşturulur;
- duplicate veya orphan widget bırakılmaz.

## 12. Agenda detail tool-window registry

Agenda detail penceresi private cache-only yaklaşımından current-main tool-window registry'sine taşınmıştır.

Stable key:

```text
agenda:detail
```

Kullanılan current-main lifecycle:

```python
open_or_raise_tool_window(
    "agenda:detail",
    "Gündemim",
    self._create_agenda_detail_window,
)
```

Kapatma/reset yolu:

```python
close_tool_window("agenda:detail")
```

Doğrulanan davranışlar:

- iki open çağrısı aynı canlı instance'ı raise eder;
- duplicate signal connection oluşmaz;
- permission loss detail penceresini kapatır;
- file switch ve facade rebind detail penceresini kapatır;
- main close timer'ı durdurur ve registry üzerinden detail'ı kapatır;
- close/reopen temiz yeni instance üretir;
- exact contract-ID navigation korunur.

## 13. Test düzeltmelerinin niteliği

R1 sırasında iki eski source-string testi güncel mimariye göre düzeltilmiştir:

1. Agenda close testi eski `detail.close()` private-cache davranışını değil, doğru registry çağrısı olan `close_tool_window("agenda:detail")` sözleşmesini doğrular.

2. Startup testi docstring içindeki `STSStore` kelimesini false-positive olarak yakalamaz. `ast.Call` düğümleri üzerinden gerçekten yapılan `STSLoadWorker` ve `STSStore` çağrılarını doğrular.

Bu değişiklikler assertion zayıflatma değildir; testleri güncel production mimarisinin gerçek davranışına bağlar.

## 14. Windows/PySide6 online validation

Validation ortamı:

```text
Runner: windows-latest
Python: 3.11
QT_QPA_PLATFORM: offscreen
PYTHONUTF8: 1
PYTHONHASHSEED: 0
```

Exact integration branch checkout edilmiştir. Exact current-main, accepted feature ve Stage 5B starting candidate objeleri doğrulanmıştır.

Çalıştırılan gates:

### Compile

```text
python -m compileall -q src tests
status: PASS
```

### Schema targeted tests

Kapsam:

- schema upgrade;
- upgrade gate;
- orchestration;
- Agenda schema-v18 integration;
- STS database transactions.

Sonuç:

```text
32 passed
failures: 0
errors: 0
status: PASS
```

### UI targeted tests

Kapsam:

- main-page Agenda integration;
- current-main composition;
- startup/upgrade integration;
- compact widget;
- detail window;
- Analysis Qt integration;
- Analysis builder Qt integration.

Sonuç:

```text
76 passed
failures: 0
errors: 0
status: PASS
```

### Full Stage 5B targeted tests

Agenda domain, providers, repositories, facade, service, UI, schema, Analysis ve current-main runtime-fix test aileleri tek invocation içinde çalıştırılmıştır.

```text
failures: 0
errors: 0
status: PASS
```

### Schema smokes

```text
python tests/smoke_sts_agenda_schema.py
agenda_schema=PASS
schema_version=18
```

```text
python tests/smoke_sts_database.py
ok
```

Her iki smoke exit code 0 ile tamamlanmıştır.

### Full candidate pytest

```text
python -m pytest -q
failures: 0
errors: 0
status: PASS
```

Test seçimi gizlenmemiş, xfail eklenmemiş ve assertion sözleşmeleri zayıflatılmamıştır.

## 15. Final tree temizliği

Online correction için geçici olarak kullanılan:

```text
.github/workflows/agenda-stage-05b-r1-online-fix.yml
tools/validation/apply_agenda_stage_05b_r1.py
tools/validation/run_agenda_stage_05b_r1_hotfix.py
```

dosyaları successful validation sonrasında final commit içinde silinmiştir.

Final tree:

- geçici workflow içermez;
- executor/patcher içermez;
- validation-output dosyalarını commit etmez;
- requirements değişikliği içermez;
- main write içermez;
- accepted-feature write içermez;
- force push veya history rewrite içermez.

## 16. Final safety sonucu

Final integration branch:

```text
HEAD:
7cd24e7706599d0b92b5cfb4343a9cf107fc75ca

base:
e1ed9a66318e19178f132602d3114a97880fa27f

ahead_by: 10
behind_by: 0
merge_base:
e1ed9a66318e19178f132602d3114a97880fa27f
```

Final permanent değişiklikler Stage 5B/R1 allowlist'i içindedir.

`main` değişmemiştir:

```text
e1ed9a66318e19178f132602d3114a97880fa27f
```

Accepted feature değişmemiştir:

```text
b45d6f2e2b2948d1bbf9dcf1f83c8b04386a5c98
```

## 17. Deferred scope

Aşağıdaki kapsamlar bu aşamada eklenmemiştir:

- system/delivery activity;
- actor staff-ID self filtering;
- responsible-change activity;
- note/component/create/delete activity;
- direct EVENT dismiss;
- EVENT snooze;
- Document Lock direct actions;
- stale-lock age policy;
- system-admin operational Agenda;
- unrelated UI redesign;
- requirements değişikliği;
- release/deploy.

## 18. Final gate status

```text
STAGE 5A CURRENT-MAIN INTEGRATION AUDIT: ACCEPTED
STAGE 5B CONTROLLED INTEGRATION SOURCE: IMPLEMENTED
SCHEMA V18 SINGLE CANONICAL OWNER: ACCEPTED
V17 TO V18 MIGRATION: ACCEPTED
V18 STRUCTURAL FINGERPRINT: ACCEPTED
UI COMPOSITION INTEGRATION: ACCEPTED
AGENDA DETAIL TOOL-WINDOW REGISTRY: ACCEPTED
AGENDA UI INSTALL IDEMPOTENCY: ACCEPTED
CURRENT-MAIN RUNTIME FIXES: PRESERVED
STAGE 5B STATIC/SOURCE TEST GATE: PASS
STAGE 5B RUNTIME DIFFERENTIAL ACCEPTANCE: PENDING
STAGE 5B-V INTEGRATION VALIDATION GATE: OPEN
MAIN MERGE GATE: CLOSED
```

## 19. Sonraki aşama

Sıradaki aşama Stage 5B-V integrated runtime differential validation'dır.

Stage 5B-V:

- exact baseline olarak current main'i kullanmalıdır;
- exact candidate olarak `7cd24e7706599d0b92b5cfb4343a9cf107fc75ca` kullanmalıdır;
- Windows/PySide6 runtime doğrulaması yapmalıdır;
- baseline/candidate full JUnit node differential üretmelidir;
- schema 17→18 gerçek upgrade senaryolarını çalıştırmalıdır;
- Agenda UI lifecycle ve current-main composition davranışlarını runtime olarak doğrulamalıdır;
- temporary PR/workflow kullanılırsa sonunda kapatılıp temizlenmelidir;
- main branch'e merge yapmamalıdır.

Stage 5B-V kabul edilmeden Main Merge Gate açılmaz.
