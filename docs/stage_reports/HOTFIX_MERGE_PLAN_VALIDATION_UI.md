# HOTFIX — Merge Plan Validation UI

## Root cause

`ShareMergeDecisionController` karar değişiminde stale state tutmuyordu; `set_decision()` ve `clear_decision()` her seferinde `resolve_merge_plan()` çağırıyordu. Gerçek hata resolution graph validation context plumbing içindeydi.

`prepare_share_merge_plan()` BASE, LOCAL ve REMOTE snapshotlarını okuyup `build_merge_plan()` için kullanıyor, fakat yalnız çıplak `MergePlan` döndürüyordu. Dialog controller daha sonra `resolve_merge_plan(plan, decisions)` çağırınca `base_snapshot`, `local_snapshot` ve `remote_snapshot` parametreleri `None` kalıyordu. `_projected_graph_issues()` bu durumda final graphı boş LOCAL entity setlerinden başlatıyordu.

Mevcut bir sistem altına eklenmiş remote teslimat için `ADD_DELIVERY` operation'ı doğru `system_merge_uid` taşımasına rağmen mevcut parent system validation graphında görünmüyordu. Sonuç sahte `ABSENT_DELIVERY_PARENT_SYSTEM` structural issue idi. Bu yüzden UI'da `Çözülmemiş çakışma: 0` olsa bile `structural_issue_count > 0` kalıyor ve `Değişiklikleri Birleştir` butonu disabled oluyordu. Assignment/unit hotfix bu bugı oluşturmadı; mixed delivery/unit senaryosu daha önce gizli olan context gap'ini görünür hale getirdi.

## Fix

- `prepare_share_merge_plan()` sonucu, public `MergePlan` davranışını değiştirmeyen private `_PreparedShareMergePlan` ile BASE/LOCAL/REMOTE resolution context taşıyor. Snapshot context alanları repr/equality dışı.
- `resolve_merge_plan()` explicit snapshot argümanı verilmemişse prepared plan üzerindeki resolution context'i kullanıyor. Explicit argümanlar hâlâ öncelikli ve eski pure `build_merge_plan()` test/call path'i korunuyor.
- Validation bypass edilmedi. Operation hash, graph validation, stale/replay ve apply preflight guardları korunuyor.
- Remote-added delivery full nested component/unit state'i `ADD_DELIVERY` operation'ında taşımaya devam ediyor; aynı delivery için duplicate `SET_DELIVERY_COMPONENT_FIELD` operation üretilmediği regression ile doğrulandı.
- Structural issue UI metni raw issue message/UID/JSON/hash göstermeyen bounded presenter formatter'a taşındı. İlk actionable reason ve varsa `(+N sorun)` gösteriliyor.
- `Karar:` label `shareMergeDecisionCaption` objectName aldı ve yalnız `QDialog#shareMergeDialog` scope'unda transparent/background-border-free style uygulandı. Global QLabel style değiştirilmedi.

## Button enable contract

Decision combo signal -> `_on_decision_changed()` -> controller `set_decision/clear_decision` -> `resolve_merge_plan()` -> projected graph validation -> `live_summary()` -> `_refresh_summary()` zinciri korunuyor.

Buton yalnız:

- `unresolved_conflict_count == 0`
- `structural_issue_count == 0`
- submit/busy state kapalı

koşullarında aktif.

## Regression coverage

- mixed assignment units conflict + contract conflict + remote-added delivery/units
- prepared graph context mevcut parent system'i doğru görür
- all REMOTE_USE sonrası unresolved=0, structural=0 ve controller apply-ready
- remote-added delivery unit payloadı ADD_DELIVERY içinde bir kez taşınır
- duplicate child unit field operation yok
- apply sonrası unit row source DB'ye bir kez gelir
- structural validation message raw UID/JSON/hash sızdırmaz
- Qt dialog: son karar button enable, kararı tekrar unresolved yapınca disable
- Qt dialog: decision caption scoped style selector mevcut

## Windows retest

1. Seri/kuyruk no conflict ve iki tarafta farklı eklenen teslimatlar içeren paylaşım dosyasını aç.
2. Conflict kartlarının tamamında karar ver.
3. `Çözülmemiş çakışma: 0` ve `structural issue` olmadığı durumda `Değişiklikleri Birleştir` aktif olmalı.
4. Bir conflict kararını tekrar `Karar seçin` durumuna getir; buton tekrar disabled olmalı.
5. `Karar:` metni arkasında gri dikdörtgen olmamalı.
6. Merge sonrası yeni teslimat seri/kuyruk satırlarının ana STS'ye tek kopya geldiğini doğrula.

## Final test output

```text
........................................................................ [ 55%]
..........................................................               [100%]
=========================== short test summary info ============================
SKIPPED [1] tests/test_share_history_dialog.py:9: PySide6 Qt runtime unavailable: libEGL.so.1: cannot open shared object file: No such file or directory
SKIPPED [1] tests/test_share_merge_dialog.py:12: PySide6 Qt runtime unavailable: libEGL.so.1: cannot open shared object file: No such file or directory
SKIPPED [1] tests/test_share_merge_window_orchestration.py:11: PySide6 Qt runtime unavailable: libEGL.so.1: cannot open shared object file: No such file or directory
130 passed, 3 skipped in 5.41s
```
