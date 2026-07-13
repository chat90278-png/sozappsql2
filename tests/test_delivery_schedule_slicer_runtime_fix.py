from pathlib import Path
import zipfile

from src.services import delivery_schedule_slicer_runtime_fix as slicer_fix


def _write_slicer_package(path: Path, count: int = 8) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        for index in range(1, count + 1):
            archive.writestr(f"xl/slicers/slicer{index}.xml", "<slicer />")
            archive.writestr(
                f"xl/slicerCaches/slicerCache{index}.xml",
                "<cache />",
            )


def test_xlsx_slicer_parts_counts_package_entries(tmp_path):
    report = tmp_path / "report.xlsx"
    _write_slicer_package(report, count=8)

    assert slicer_fix._xlsx_slicer_parts(report) == (8, 8)


def test_xlsx_slicer_parts_accepts_binary_cache_parts(tmp_path):
    report = tmp_path / "binary-cache.xlsx"
    with zipfile.ZipFile(report, "w") as archive:
        archive.writestr("xl/slicers/slicer1.xml", "<slicer />")
        archive.writestr("xl/slicerCaches/slicerCache1.bin", b"cache")
        archive.writestr(
            "xl/slicerCaches/_rels/slicerCache1.bin.rels",
            "<Relationships />",
        )

    assert slicer_fix._xlsx_slicer_parts(report) == (1, 1)


def test_transaction_keeps_original_when_slicer_phase_fails(
    tmp_path,
    monkeypatch,
):
    report = tmp_path / "report.xlsx"
    original = b"base-report-remains-safe"
    report.write_bytes(original)

    def fail_install(_exporter, temporary_path):
        temporary_path.write_bytes(b"damaged-temporary-copy")
        raise RuntimeError("simulated COM failure")

    monkeypatch.setattr(slicer_fix, "_install_slicers_once", fail_install)
    ok, count, warning = slicer_fix._add_slicers_transactionally(
        object(),
        report,
        attempts=1,
    )

    assert not ok
    assert count == 0
    assert "simulated COM failure" in warning
    assert report.read_bytes() == original
    assert not list(tmp_path.glob(".*.slicers-*.xlsx"))


def test_transaction_replaces_original_only_after_validation(
    tmp_path,
    monkeypatch,
):
    report = tmp_path / "report.xlsx"
    report.write_bytes(b"base-report")

    def successful_install(_exporter, temporary_path):
        _write_slicer_package(temporary_path, count=8)
        return 8

    monkeypatch.setattr(slicer_fix, "_install_slicers_once", successful_install)
    ok, count, warning = slicer_fix._add_slicers_transactionally(
        object(),
        report,
        attempts=1,
    )

    assert ok
    assert count == 8
    assert warning == ""
    assert slicer_fix._xlsx_slicer_parts(report) == (8, 8)


def test_export_wrapper_keeps_base_success_when_slicers_fail(
    tmp_path,
    monkeypatch,
):
    import sys
    from types import ModuleType, SimpleNamespace

    services = sys.modules.get("src.services")
    if services is None:
        services = ModuleType("src.services")
        monkeypatch.setitem(sys.modules, "src.services", services)

    report = tmp_path / "fallback-report.xlsx"

    def base_export(_store, output_path, filters=None, progress_cb=None):
        Path(output_path).write_bytes(b"valid-base-report")
        return {"output_path": str(output_path), "row_count": 3}

    fake_exporter = SimpleNamespace(
        export_delivery_schedule_report=base_export,
        DASHBOARD_SLICERS_ENABLED=True,
        _ensure_excel=lambda: None,
        _uninitialize_excel_com=lambda: None,
        _safe_filename=lambda value: str(value),
        add_unique_slicer=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        services,
        "delivery_schedule_excel_exporter",
        fake_exporter,
        raising=False,
    )
    monkeypatch.setitem(
        sys.modules,
        "src.services.delivery_schedule_excel_exporter",
        fake_exporter,
    )
    monkeypatch.setattr(
        slicer_fix,
        "_add_slicers_transactionally",
        lambda _exporter, _path, attempts=2: (
            False,
            0,
            "simulated slicer failure",
        ),
    )

    slicer_fix.install_delivery_schedule_slicer_fix()
    result = fake_exporter.export_delivery_schedule_report(None, report)

    assert report.read_bytes() == b"valid-base-report"
    assert result["row_count"] == 3
    assert result["slicers_enabled"] is False
    assert result["partial_success"] is True
    assert "simulated slicer failure" in result["slicer_warning"]
