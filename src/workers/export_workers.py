from __future__ import annotations
from PySide6.QtCore import QObject, Signal


class ExcelExportWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, store, output_path, options):
        super().__init__()
        self.store = store
        self.output_path = output_path
        self.options = options or {}

    def run(self):
        try:
            res = self.store.export_to_excel(self.output_path, options=self.options, progress_cb=lambda p, m: self.progress.emit(int(p), str(m)))
            self.finished.emit(res or {})
        except Exception as exc:
            self.failed.emit(str(exc))
