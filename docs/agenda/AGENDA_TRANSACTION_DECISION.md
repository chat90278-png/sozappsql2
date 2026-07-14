# Gündemim — Transaction Contract Decision

## Problem

`STSDatabase.tx()` docstring'i nested çağrıların `SAVEPOINT` kullanmasını, inner work'ün outer transaction'ı erken commit etmemesini ve outer rollback ile atomicity'nin korunmasını vaat eder.

Eski outer path ilk `yield` öncesinde SQL transaction başlatmıyordu. Python `sqlite3` deferred/lazy transaction davranışında outer `with db.tx():` context'ine girildiği anda `conn.in_transaction` false kalabiliyordu.

## Reproduction

Problem karakteri:

```text
outer db.tx()
  -> henüz gerçek SQL transaction yok
  -> inner repository db.tx()
  -> inner INSERT implicit transaction başlatır
  -> inner tx success commit eder
  -> outer exception rollback artık inner commit'i geri alamaz
```

Bu davranış `AgendaStateRepository` mutation'larının caller-owned outer transaction içinde atomic kalması beklentisiyle çelişir.

## Manager Decision

Outer `STSDatabase.tx()` path'i `yield` öncesinde normal SQL `BEGIN` çalıştıracaktır:

```python
else:
    self.conn.execute("BEGIN")
    try:
        yield
        self.conn.commit()
    except Exception:
        self.conn.rollback()
        raise
```

Existing nested `SAVEPOINT` path'i korunur.

## Why BEGIN, not BEGIN IMMEDIATE

Normal `BEGIN`, transaction ownership'ını context girişinde açıkça başlatır ve nested `db.tx()` çağrılarının outer transaction'ı `conn.in_transaction` üzerinden görmesini sağlar.

`BEGIN IMMEDIATE` kullanılmaz. Böylece ilk write öncesinde gereksiz reserved write lock alınmaz ve mevcut deferred lock/concurrency karakteri korunur. `BEGIN EXCLUSIVE` de kullanılmaz.

## Contract After Fix

- Standalone successful transaction commit edilir.
- Standalone exception transaction'ı rollback eder.
- Nested successful work outer transaction'ın parçasıdır.
- Nested failure mevcut `SAVEPOINT` path'iyle inner work'ü rollback eder; outer transaction devam edebilir.
- Outer failure, daha önce başarıyla tamamlanmış nested work'ü de rollback eder.
- Existing raw transaction içinde `db.tx()` `SAVEPOINT` kullanır ve raw outer transaction'ı commit etmez.
- Read-only outer `db.tx()` context'i de transaction'ı context girişinde active hale getirir ve success exit'te kapatır.

## Agenda Impact

`AgendaStateRepository` mevcut persistence contract'ını korur:

```python
with self.db.tx():
    self.conn.execute(...)
```

Repository yeni SQLite connection açmaz ve unconditional `commit()` çağırmaz. Böylece caller-owned outer transaction rollback'i agenda state mutation'larını da kapsar.

## Main Integration Risk

Bu değişiklik merkezi `STSDatabase.tx()` helper'ını etkiler. Main entegrasyonunda current main `tx()` implementation'ı yeniden okunmalı; feature dosyası current main üzerine kör biçimde overwrite edilmemelidir.

Transaction regression testleri, agenda repository rollback testi, mevcut STS database smoke ve full suite yeniden çalıştırılmalıdır. Parallel schema/migration değişiklikleri varsa current main source-of-truth ayrıca uzlaştırılmalıdır.
