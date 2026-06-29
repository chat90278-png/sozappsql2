from __future__ import annotations

import time
from pathlib import Path
from typing import List

from PySide6.QtCore import QObject, Signal

from src.services.excel_store import ExcelStore


class UserSaveWorker(QObject):
    progress = Signal(int, str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, path: Path, users_payload: List[dict], actor: str):
        super().__init__()
        self.path = Path(path)
        self.users_payload = [dict(x or {}) for x in list(users_payload or [])]
        self.actor = str(actor or "Sistem")

    def run(self):
        try:
            if str(self.path).lower().endswith(".sts"):
                raise RuntimeError("STS dosyası Excel worker ile açılamaz; STSStore kullanılmalı.")
            self.progress.emit(10, "Excel açılıyor...")
            store = ExcelStore(self.path)
            with store.batch_save():
                self.progress.emit(42, "Kullanıcılar kaydediliyor...")
                store.write_users(self.users_payload, actor=self.actor)
                self.progress.emit(94, "Excel kaydediliyor...")
                store.save()
            self.progress.emit(100, "Tamamlandı")
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))



class ContractSaveWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        path: Path,
        action: str,
        platform: str,
        contract_no: str,
        ci=None,
        systems=None,
        deliveries=None,
        old_contract_no: str = "",
        old_start_row: int = 0,
        start_row: int = 0,
        actor: str = "",
        store=None,   # Bellekteki store — load_workbook'u atlatır
    ):
        super().__init__()
        self.path = Path(path)
        self.action = action
        self.platform = platform
        self.contract_no = contract_no
        self.ci = ci
        self.systems = systems or []
        self.deliveries = deliveries or {}
        self.old_contract_no = old_contract_no
        self.old_start_row = old_start_row
        self.start_row = start_row
        self.actor = actor or "Sistem"
        self._store = store  # Varsa wb yeniden açılmaz

    def _open_store(self):
        """
        Mevcut bellekteki store'da wb yüklüyse doğrudan kullan.
        Yoksa yeni ExcelStore aç (yavaş yol — sadece ilk kayıtta).
        """
        s = self._store
        if str(self.path).lower().endswith(".sts"):
            if s is not None:
                return s, False
            raise RuntimeError("STS dosyası Excel worker ile açılamaz; STSStore kullanılmalı.")
        if s is not None and getattr(s, 'wb', None) is not None:
            return s, False  # (store, opened_new=False)
        return ExcelStore(self.path), True

    def run(self):
        _t0 = time.perf_counter()
        try:
            self.progress.emit(10, "Hazırlanıyor...")
            store, opened_new = self._open_store()
            if opened_new:
                self.progress.emit(20, "Excel açılıyor...")
            else:
                self.progress.emit(20, "Bellekteki Excel kullanılıyor...")

            payload = None
            with store.batch_save():
                if self.action == "write":
                    self.progress.emit(30, "Sözleşme yazılıyor...")
                    new_row = store.write_contract(
                        self.ci,
                        self.systems,
                        self.deliveries,
                        old_contract_no=self.old_contract_no or None,
                        old_start_row=self.old_start_row or None,
                    )
                    self.progress.emit(70, "Stiller uygulanıyor...")
                    store.flush_pending_styles()
                    self.progress.emit(95, "Excel kaydediliyor...")
                    store.save()
                    payload = {
                        "action": "write",
                        "platform": self.platform,
                        "contract_no": self.contract_no,
                        "start_row": int(new_row or 0),
                    }
                elif self.action == "delete":
                    self.progress.emit(40, "Sözleşme siliniyor...")
                    result = store.delete_contract(
                        self.platform,
                        self.contract_no,
                        start_row=self.start_row or None,
                        actor=self.actor or None,
                        progress_cb=lambda p, m: self.progress.emit(
                            40 + int(p * 0.5), m
                        ),
                    )
                    self.progress.emit(95, "Excel kaydediliyor...")
                    store.save()
                    payload = {
                        "action": "delete",
                        "platform": self.platform,
                        "contract_no": self.contract_no,
                        "start_row": self.start_row,
                        "result": result or {},
                    }
                elif self.action == "migrate_cf":
                    self.progress.emit(10, "CF kuralları kontrol ediliyor...")
                    migrated = store.migrate_platform_cf_rules()
                    self.progress.emit(90, f"{len(migrated)} platform güncellendi...")
                    payload = {"action": "migrate_cf", "migrated": migrated}
            total_ms = (time.perf_counter() - _t0) * 1000
            try:
                from src.services.perf_tracker import record as _pr, OP_CONTRACT_SAVE, OP_CONTRACT_DELETE
                if self.action == "write":
                    op = OP_CONTRACT_SAVE
                elif self.action == "delete":
                    op = OP_CONTRACT_DELETE
                else:
                    op = self.action or "excel_action"
                _pr(op, self.path, total_ms,
                    meta={"platform": self.platform, "contract_no": self.contract_no,
                          "reused_wb": not opened_new})
            except Exception:
                pass
            if payload is not None:
                self.finished.emit(payload)
        except Exception as exc:
            try:
                from src.services.perf_tracker import record as _pr, OP_CONTRACT_SAVE, OP_CONTRACT_DELETE
                if self.action == "write":
                    op = OP_CONTRACT_SAVE
                elif self.action == "delete":
                    op = OP_CONTRACT_DELETE
                else:
                    op = self.action or "excel_action"
                _pr(op, self.path, (time.perf_counter() - _t0) * 1000,
                    success=False, meta={"error": str(exc)})
            except Exception:
                pass
            self.failed.emit(str(exc))
