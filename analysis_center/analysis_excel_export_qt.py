from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

from .analysis_excel_export import (
    DashboardExcelExportResult,
    DashboardExportCollection,
    export_dashboard_collection_excel,
)
from .analysis_registry import AnalysisRegistry


class DashboardExcelExportWorker(QObject):
    """Write an already-resolved Dashboard snapshot outside the Qt UI thread."""

    finished = Signal(object)
    failed = Signal(object, str)

    def __init__(
        self,
        *,
        output_path: Path | str,
        collection: DashboardExportCollection,
        registry: AnalysisRegistry,
        source: Any = None,
        workspace_card_count: int | None = None,
        exporter: Callable[..., DashboardExcelExportResult] = export_dashboard_collection_excel,
    ) -> None:
        super().__init__()
        self.output_path = output_path
        self.collection = collection
        self.registry = registry
        self.source = source
        self.workspace_card_count = workspace_card_count
        self.exporter = exporter

    @Slot()
    def run(self) -> None:
        try:
            result = self.exporter(
                self.output_path,
                collection=self.collection,
                registry=self.registry,
                source=self.source,
                workspace_card_count=self.workspace_card_count,
            )
        except Exception as exc:  # Qt boundary: preserve traceback for the main-thread logger.
            self.failed.emit(exc, traceback.format_exc())
            return
        self.finished.emit(result)


__all__ = ["DashboardExcelExportWorker"]
