from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal


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
        store=None,
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
        self._store = store

    def _open_store(self):
        """Return the active STS store; this worker no longer opens Excel files."""
        if not str(self.path).lower().endswith(".sts"):
            raise RuntimeError("Sözleşme kaydetme işlemi yalnızca STS veri dosyalarında desteklenir.")
        if self._store is None:
            raise RuntimeError("STS veri dosyası bağlantısı hazır değil; işlem başlatılamadı.")
        if not hasattr(self._store, "db"):
            raise RuntimeError("Geçerli bir STS store bulunamadı.")
        return self._store

    def run(self):
        _t0 = time.perf_counter()
        try:
            self.progress.emit(10, "Hazırlanıyor...")
            store = self._open_store()
            self.progress.emit(20, "STS veri dosyası kullanılıyor...")

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
                    self.progress.emit(95, "STS veri dosyasına kaydediliyor...")
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
                    self.progress.emit(95, "STS veri dosyasına kaydediliyor...")
                    store.save()
                    payload = {
                        "action": "delete",
                        "platform": self.platform,
                        "contract_no": self.contract_no,
                        "start_row": self.start_row,
                        "result": result or {},
                    }
                elif self.action == "migrate_cf":
                    self.progress.emit(100, "STS veri dosyasında CF migration gerekmiyor.")
                    payload = {"action": "migrate_cf", "migrated": []}
            total_ms = (time.perf_counter() - _t0) * 1000
            try:
                from src.services.perf_tracker import record as _pr, OP_CONTRACT_SAVE, OP_CONTRACT_DELETE
                if self.action == "write":
                    op = OP_CONTRACT_SAVE
                elif self.action == "delete":
                    op = OP_CONTRACT_DELETE
                else:
                    op = self.action or "contract_action"
                _pr(op, self.path, total_ms,
                    meta={"platform": self.platform, "contract_no": self.contract_no})
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
                    op = self.action or "contract_action"
                _pr(op, self.path, (time.perf_counter() - _t0) * 1000,
                    success=False, meta={"error": str(exc)})
            except Exception:
                pass
            self.failed.emit(str(exc))
