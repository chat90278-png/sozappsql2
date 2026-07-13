from __future__ import annotations

"""Safe, two-phase Excel slicer installation for delivery schedule reports.

The base exporter intentionally creates and saves the workbook without slicers
because Excel COM may terminate while ``SlicerCaches`` are being created. This
runtime fix keeps that reliable path intact, then adds slicers to a temporary
copy in a fresh Excel process. The original report is replaced only after the
temporary workbook has been saved, closed and validated as an XLSX package.
"""

from functools import wraps
import os
from pathlib import Path
import shutil
import time
from typing import Any
import zipfile

_PATCH_FLAG = "_safe_dashboard_slicer_patch_installed"
_SLICER_FIELDS = [
    "Sistem / Paket",
    "Sözleşme Sahibi",
    "Yİ/YD",
    "Yıl",
    "Teslimat",
    "Platform",
    "Sözleşme",
    "Durum",
]


def _xlsx_slicer_parts(path: Path) -> tuple[int, int]:
    """Return (slicer XML count, slicer-cache XML count) for a saved workbook."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except Exception:
        return 0, 0
    slicers = sum(
        1
        for name in names
        if name.startswith("xl/slicers/") and name.endswith(".xml")
    )
    caches = sum(
        1
        for name in names
        if name.startswith("xl/slicerCaches/") and name.endswith(".xml")
    )
    return slicers, caches


def _temporary_workbook_path(output_path: Path, attempt: int) -> Path:
    return output_path.with_name(
        f".{output_path.stem}.slicers-{os.getpid()}-{attempt}{output_path.suffix}"
    )


def _close_excel_session(exporter: Any, workbook: Any, excel: Any) -> None:
    if workbook is not None:
        try:
            workbook.Close(SaveChanges=False)
        except Exception:
            pass
    if excel is not None:
        try:
            excel.Quit()
        except Exception:
            pass
    try:
        exporter._uninitialize_excel_com()
    except Exception:
        pass


def _install_slicers_once(exporter: Any, workbook_path: Path) -> int:
    """Add all dashboard slicers to one workbook and return the created count."""
    excel = None
    workbook = None
    try:
        excel = exporter._ensure_excel()
        workbook = excel.Workbooks.Open(
            str(workbook_path),
            UpdateLinks=0,
            ReadOnly=False,
            IgnoreReadOnlyRecommended=True,
        )
        dashboard = workbook.Worksheets("Dashboard")
        pivot_summary = workbook.Worksheets("Pivot Ozet")
        chart_source = workbook.Worksheets("Grafik Kaynak")

        main_pivot = pivot_summary.PivotTables("ptSiparisDurumu")
        extra_pivots = [
            chart_source.PivotTables("ptParca"),
            chart_source.PivotTables("ptYiyd"),
            chart_source.PivotTables("ptYil"),
        ]

        created_registry: set[tuple[str, str]] = set()
        created_count = 0
        failed_fields: list[str] = []
        left = 1110
        top = 380

        for index, field_name in enumerate(_SLICER_FIELDS):
            slicer = exporter.add_unique_slicer(
                workbook,
                dashboard,
                main_pivot,
                field_name,
                f"sl_{index}_{exporter._safe_filename(field_name)}",
                left,
                top + index * 82,
                170,
                125 if field_name == "Durum" else 75,
                created_registry,
                extra_pivot_tables=extra_pivots,
            )
            if slicer is None:
                failed_fields.append(field_name)
                continue

            created_count += 1
            try:
                cache = slicer.SlicerCache
                connected = cache.PivotTables
                for pivot in extra_pivots:
                    try:
                        connected.AddPivotTable(pivot)
                    except Exception:
                        # It may already be connected by add_unique_slicer().
                        pass

                connected_names: set[str] = set()
                for item_index in range(1, int(connected.Count) + 1):
                    try:
                        connected_names.add(str(connected.Item(item_index).Name))
                    except Exception:
                        pass
                expected_names = {
                    str(main_pivot.Name),
                    *(str(pivot.Name) for pivot in extra_pivots),
                }
                if not expected_names.issubset(connected_names):
                    missing = sorted(expected_names - connected_names)
                    raise RuntimeError(
                        f"{field_name} dilimleyicisi şu pivotlara bağlanamadı: "
                        + ", ".join(missing)
                    )
            except Exception as exc:
                failed_fields.append(f"{field_name} ({exc})")

        if failed_fields:
            raise RuntimeError(
                "Dilimleyici oluşturulamayan alanlar: " + ", ".join(failed_fields)
            )

        if int(workbook.SlicerCaches.Count) < len(_SLICER_FIELDS):
            raise RuntimeError(
                "Çalışma kitabındaki dilimleyici önbellekleri eksik oluşturuldu."
            )

        workbook.Save()
        workbook.Close(SaveChanges=True)
        workbook = None
        return created_count
    finally:
        _close_excel_session(exporter, workbook, excel)


def _add_slicers_transactionally(
    exporter: Any,
    output_path: Path,
    *,
    attempts: int = 2,
) -> tuple[bool, int, str]:
    """Install slicers without risking the already generated base workbook."""
    if not output_path.exists():
        return False, 0, "Temel Excel dosyası bulunamadı."

    errors: list[str] = []
    for attempt in range(1, max(1, int(attempts)) + 1):
        temp_path = _temporary_workbook_path(output_path, attempt)
        try:
            try:
                temp_path.unlink(missing_ok=True)
            except TypeError:  # Python 3.7 compatibility
                if temp_path.exists():
                    temp_path.unlink()

            shutil.copy2(output_path, temp_path)
            created_count = _install_slicers_once(exporter, temp_path)
            slicer_parts, cache_parts = _xlsx_slicer_parts(temp_path)
            if created_count != len(_SLICER_FIELDS):
                raise RuntimeError(
                    f"Beklenen {len(_SLICER_FIELDS)} dilimleyiciden "
                    f"{created_count} tanesi oluşturuldu."
                )
            if slicer_parts < len(_SLICER_FIELDS) or cache_parts < len(_SLICER_FIELDS):
                raise RuntimeError(
                    "Dosyadaki dilimleyici paket kayıtları eksik: "
                    f"slicer={slicer_parts}, cache={cache_parts}."
                )

            os.replace(temp_path, output_path)
            return True, created_count, ""
        except Exception as exc:
            errors.append(f"Deneme {attempt}: {exc}")
            try:
                temp_path.unlink(missing_ok=True)
            except TypeError:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            if attempt < attempts:
                time.sleep(1.0)

    return False, 0, " | ".join(errors)


def install_delivery_schedule_slicer_fix() -> None:
    """Patch the exporter once while preserving its reliable base-export path."""
    try:
        from src.services import delivery_schedule_excel_exporter as exporter
    except Exception:
        return

    if bool(getattr(exporter, _PATCH_FLAG, False)):
        return

    required_helpers = (
        "export_delivery_schedule_report",
        "_ensure_excel",
        "_uninitialize_excel_com",
        "_safe_filename",
        "add_unique_slicer",
    )
    if not all(hasattr(exporter, name) for name in required_helpers):
        return

    original_export = exporter.export_delivery_schedule_report
    # Never create slicers during the fragile first COM session. The wrapper
    # below performs that step on a validated temporary copy instead.
    exporter.DASHBOARD_SLICERS_ENABLED = False

    @wraps(original_export)
    def export_with_safe_slicers(store, output_path, filters=None, progress_cb=None):
        result = original_export(
            store,
            output_path,
            filters=filters,
            progress_cb=progress_cb,
        )
        result = dict(result or {})
        final_path = Path(result.get("output_path") or output_path)

        if progress_cb is not None:
            try:
                progress_cb(92, "Excel dilimleyicileri güvenli oturumda oluşturuluyor")
            except Exception:
                pass

        enabled, count, warning = _add_slicers_transactionally(
            exporter,
            final_path,
            attempts=2,
        )
        result["slicers_enabled"] = enabled
        result["slicer_count"] = count
        if warning:
            result["slicer_warning"] = warning

        if progress_cb is not None:
            try:
                progress_cb(
                    100,
                    "Excel raporu ve dilimleyiciler hazır"
                    if enabled
                    else "Excel raporu hazır; dilimleyiciler eklenemedi",
                )
            except Exception:
                pass

        if not enabled:
            raise RuntimeError(
                "Dilimleyiciler eklenemedi. Temel rapor dosyası korunmuştur: "
                f"{final_path}. Ayrıntı: {warning or 'Bilinmeyen hata'}"
            )
        return result

    exporter.export_delivery_schedule_report = export_with_safe_slicers
    setattr(exporter, _PATCH_FLAG, True)


__all__ = [
    "install_delivery_schedule_slicer_fix",
    "_add_slicers_transactionally",
    "_xlsx_slicer_parts",
]
