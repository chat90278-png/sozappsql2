# Gündemim Aşama 2A — Personal Condition Engine

## Scope

Bu aşama yalnız `feature/gundemim-agenda-system` üzerinde kişisel sorumluluk kapsamındaki ilk üretim Gündem motorunu kurar. UI, ActivityProvider, paylaşım, document-lock, manager/admin/viewer scope ve main entegrasyonu kapsam dışıdır.

## Katman sınırları

- `AgendaSourceRepository` yalnız mevcut STS connection üzerinden read-only SQL çalıştırır ve `AgendaCalendarSource` üretir.
- Provider katmanı saf domain logic'tir; SQL ve state repository kullanmaz.
- `AgendaLifecycleEngine` yalnız `AgendaItem`, `AgendaItemState` ve injected `now` ile görünürlük/new/seen/snooze/TTL kararı verir.
- `StaffAgendaService` source, provider, lifecycle ve state repository orkestrasyonunu yapar.
- Agenda listesinde görünmek `seen` olmak değildir; build hiçbir zaman `mark_seen`, `snooze` veya `dismiss` çağırmaz.

## Personal responsibility source

Kişisel sözleşme kapsamı `contract_responsible_engineers.staff_id -> contract_id` ilişkisinden ve aktif staff filtresinden gelir. Role name authorization kullanılmaz. Görüntüleme gate'i canonical `view_contracts` permission code'udur.

## Multi-platform contract dedupe

Contract identity `contracts.id` değeridir. Contract source bir kez üretilir. Bağlı platform isimleri trim/dedupe/case-insensitive deterministic sort ile `" / "` kullanılarak birleştirilir. System ve delivery platformu `COALESCE(system.platform_id, contract.platform_id)` üzerinden çözülür.

## Deadline provider

`calendar_effective_date_raw`, `calendar_date_kind`, `parse_calendar_date` ve `classify_calendar_event` mevcut source-of-truth helper'ları kullanılır. Yalnız exact ve tamamlanmamış tarihler değerlendirilir. 60 günden uzak tarihler skip edilir. Key stage/date/title/platform içermediği için stage değişiminde stable kalır; version deadline stage değeridir. Deadline condition snooze destekler.

## Unknown-date provider

Yalnız `fully_unknown`, `month_unknown_day` ve `year_only` date kind'ları adaydır. Exact, `na`, malformed veya tamamlanmış source skip edilir. Key entity identity ile stable, version date kind ve raw date ile değişkendir. Payload `resurface_interval_days=7` taşıdığı için unresolved condition yedi günlük cycle ile yeniden NEW olabilir.

## Lifecycle rules

### CONDITION

Provider item üretmişse source condition aktiftir. Seen aynı version için item görünür kalır fakat NEW değildir. Version değişikliği yeniden NEW yapar. Dismiss state condition için ignore edilir.

Aktif snooze yalnız supports-snooze condition için; future valid timestamp, aynı effective version ve current severity'nin saved severity'yi aşmaması şartlarıyla item'ı gizler. Expiry, version değişikliği, severity escalation veya corrupt saved severity snooze'u görünürlük açısından kırar. DB state otomatik temizlenmez.

Resurface cadence provider opt-in payload ile effective version'a `|R<interval>:<cycle>` suffix'i ekler.

### EVENT foundation

ActivityProvider bu aşamada yoktur; engine generic EVENT lifecycle'ını hazırlar. Dismissed current version hidden. Seen event 24 saat dolduğu boundary'de hidden. Unseen event 7 gün dolduğu boundary'de hidden. Missing/invalid event timestamp hidden. EVENT snooze uygulanmaz.

## Service orchestration

- `view_contracts` yoksa source query/state write yok.
- Context personal contract IDs verilirse repository scope override edilir.
- Calendar sources tek batch halinde çekilir.
- Provider duplicate key bug'ı silent dedupe edilmez; `AgendaBuildError` yükselir.
- State tüm raw keys için tek `get_states` batch çağrısıyla alınır.
- Visible items NEW, priority, severity, remaining days, event recency ve key ile deterministic sıralanır.
- Counts yalnız visible items üzerinden hesaplanır.
- `touch_presented=True` visible key'leri presented olarak kaydeder; seen yapmaz.

## Test coverage

- CONDITION seen/version/dismiss/snooze/cadence davranışı
- EVENT 7-day ve seen 24-hour exact boundaries
- personal responsibility ve inactive staff scope
- contract multi-platform dedupe ve stable ordering
- Deadline stage/date/key/version/payload kuralları
- Unknown-date kind/key/version/cadence kuralları
- permission gate, personal scope, batch state, duplicate keys, sorting, counts ve touch-presented service orchestration

## Deliberately excluded

- ActivityProvider
- share provider
- document-lock provider
- manager/admin/viewer scope
- UI wiring
- current-main schema migration/fingerprint integration

## Known integration risk

Current main automatic STS schema upgrade engine taşır ve feature original BASE_SHA'dan ayrışmıştır. Feature schema version 18 olarak kalır. Main entegrasyonundan önce explicit v17→v18 migration, v18 fingerprint registry/manifest reconciliation ve current-main baseline differential validation zorunludur.
