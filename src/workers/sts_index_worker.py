from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.sts_store import STSStore


class STSIndexWorker(QObject):
    """Build an STS contract index using a thread-local store/connection."""

    progress = Signal(str)
    finished = Signal(list)
    failed = Signal(str, str)

    def __init__(self, path: Path | str):
        super().__init__()
        self.path = Path(path)

    def run(self) -> None:
        store = None
        try:
            self.progress.emit("Sözleşme indeksi hazırlanıyor...")
            store = STSStore(
                self.path,
                actor="Index Worker",
                source="STS Index Worker",
                actor_context={"actor_type": "SYSTEM", "actor_display_name": "Index Worker"},
            )
            index = [dict(row) for row in store.build_contract_index()]
            self.finished.emit(index)
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())
        finally:
            if store is not None:
                try:
                    store.db.close()
                except Exception:
                    pass
