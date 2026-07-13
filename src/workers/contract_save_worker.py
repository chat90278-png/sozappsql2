from __future__ import annotations

# PATCH: Thread-affinity fix for STS files.
#
# ÖNCE (sorunlu):
#   .sts için ana thread'de oluşturulmuş STSStore doğrudan worker thread'e
#   geçiriliyordu. sqlite3 default check_same_thread=True ile bu ProgrammingError
#   veya sessiz veri bozulması riskiydi.
#
# SONRA (bu dosya):
#   .sts için worker kendi thread-local STSStore'unu açar ve finally'de kapatır.
#   Ana thread STSStore'undan yalnızca path ve actor alınır — connection'a dokunulmaz.
#   Excel (.xlsx/.xlsm) akışı değişmedi.
#
# Referans: STSIndexWorker aynı pattern'i kullanıyor (sts_index_worker.py).

import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.excel_store import ExcelStore


def _is_sts_path(path: Path) -> bool:
    return str(path).lower().endswith(".sts")


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
        actor_context=None,
        session_id: str = "",
        store=None,   # Excel: bellekteki wb'yi atlatmak için. STS: path+actor/context için okunur.
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
        self.actor_context = dict(actor_context or {})
        self.session_id = str(session_id or "")
        self._store = store
        if self._store is not None and hasattr(self._store, "current_actor_context"):
            inherited = self._store.current_actor_context()
            if not self.actor_context:
                self.actor_context = dict(inherited or {})
            if not self.session_id:
                self.session_id = str((inherited or {}).get("session_id") or "")

    def _open_store(self):
        """
        Çalışan thread için güvenli bir store döner.

        STS (.sts):
            Ana thread store'undan SADECE path ve actor okunur; connection'a
            dokunulmaz.  Worker kendi STSStore'unu (dolayısıyla kendi sqlite3
            connection'ını) açar — check_same_thread ihlali olmaz.
            opened_new=True döner; run() finally bloğu store'u kapatır.

        Excel (.xlsx / .xlsm):
            Eski davranış korundu. Bellekteki wb varsa doğrudan kullanılır
            (opened_new=False); yoksa yeni ExcelStore açılır (opened_new=True).
        """
        if _is_sts_path(self.path):
            # Ana thread store'undan actor bilgisini al (varsa), connection'a bakma.
            actor = self.actor
            if self._store is not None and hasattr(self._store, "current_actor"):
                actor = self._store.current_actor() or actor

            # Geç import — döngüsel bağımlılığı önler, ExcelStore olmayan ortamlarda çalışır.
            from src.services.sts_store import STSStore  # noqa: PLC0415
            store = STSStore(
                self.path,
                actor=actor,
                source="Contract Save Worker",
                actor_context=self.actor_context or None,
                session_id=self.session_id or None,
            )
            return store, True  # opened_new=True → finally'de kapat

        # ── Excel yolu (değişmedi) ─────────────────────────────────────────
        s = self._store
        if s is not None and getattr(s, "wb", None) is not None:
            return s, False  # bellekteki wb — kapatma
        return ExcelStore(self.path), True

    def run(self):
        _t0 = time.perf_counter()
        store = None
        opened_new = False
        try:
            self.progress.emit(10, "Hazırlanıyor...")
            store, opened_new = self._open_store()

            if opened_new:
                if _is_sts_path(self.path):
                    self.progress.emit(20, "Veritabanı bağlantısı açılıyor...")
                else:
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
                    self.progress.emit(95, "Kaydediliyor...")
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
                    self.progress.emit(95, "Kaydediliyor...")
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
                    op = self.action or "contract_action"
                _pr(
                    op, self.path, total_ms,
                    meta={
                        "platform": self.platform,
                        "contract_no": self.contract_no,
                        "reused_wb": not opened_new,
                    },
                )
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
                _pr(
                    op, self.path, (time.perf_counter() - _t0) * 1000,
                    success=False, meta={"error": str(exc)},
                )
            except Exception:
                pass
            self.failed.emit(str(exc))

        finally:
            # STS için kendi açtığımız store'u kapat.
            # Excel için opened_new=False (bellekteki wb) ise kapatma — sahibi ana thread.
            if opened_new and store is not None and _is_sts_path(self.path):
                try:
                    store.db.close()
                except Exception:
                    pass
