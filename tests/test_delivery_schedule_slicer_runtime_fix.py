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
