"""Create a fresh manual STS dataset that exercises the latest SQLite schema."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_store import STSStore

OUTPUT_PATH = ROOT / "manual_latest_v2_test.sts"
MAIN_PLATFORM = "AKINCI"
MAIN_CONTRACT_NO = "AKN-2026-001"
MAIN_CONTRACT_TYPE = "Ana Sözleşme"


def _contract(no: str, platform: str, users: list[str], contract_type: str = MAIN_CONTRACT_TYPE, status: str = "Devam ediyor", parent_no: str = "") -> ContractInfo:
    return ContractInfo(
        no=no,
        platform=platform,
        user=", ".join(users),
        users=users,
        yi_yd="Yİ",
        contract_type=contract_type,
        signature_date="2026-01-15",
        t0_date="2026-02-01",
        t0_months=12,
        completion_date="2027-02-01",
        status=status,
        note=f"{no} manuel test sözleşmesi",
        sd_anchor_no=parent_no,
    )


def _delivery(name: str, user: str, planned: dict[str, float], delivered: dict[str, float], acceptance_date: str) -> DeliveryInfo:
    return DeliveryInfo(
        name=name,
        status="Teslim Edildi",
        acceptance_date=acceptance_date,
        note=f"{name} manuel test kabulü",
        delivery_user=user,
        planned=planned,
        delivered=delivered,
    )


def _add_blob_file(store: STSStore, source_dir: Path, expected_files: dict[int, bytes], platform: str, contract_no: str, contract_type: str, filename: str, content: bytes) -> int:
    source = source_dir / filename
    source.write_bytes(content)
    file_id = store.add_contract_file(platform, contract_no, source, contract_type, note="Manuel test BLOB belgesi")
    assert source.read_bytes() == content
    expected_files[file_id] = content
    return file_id


def create_manual_sts(output_path: Path | str = OUTPUT_PATH) -> Path:
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal"):
        Path(f"{output}{suffix}").unlink(missing_ok=True)

    store = STSStore(output)
    try:
        for platform in ("AKINCI", "KIZILELMA", "TB2"):
            store.create_platform(platform)
        store.write_users([
            {"name": "Ali Yılmaz", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "Ayşe Demir", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "Mehmet Kaya", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "Zeynep Çelik", "yi_yd": "Yİ", "active": True, "note": ""},
        ])
        component_names = (
            "Gövde Kit", "Aviyonik Birim", "Yer Kontrol Modülü", "Kamera Sistemi",
            "Motor Grubu", "Yazılım Paketi", "Güç Dağıtım Ünitesi", "Kablo Seti",
        )
        store.write_components([
            ComponentDef(name=name, version="v1", platforms={"AKINCI": True, "KIZILELMA": True, "TB2": True})
            for name in component_names
        ])
        store.write_tags([
            {"name": "Öncelikli", "color": "#ef4444", "kind": "contract"},
            {"name": "Export Kontrol", "color": "#2563eb", "kind": "contract"},
            {"name": "Takipte", "color": "#f59e0b", "kind": "contract"},
        ])

        contracts = [
            (_contract(MAIN_CONTRACT_NO, MAIN_PLATFORM, ["Ali Yılmaz", "Ayşe Demir"]), [
                SystemInfo(name="AKINCI Sistem 1", components={"Gövde Kit": 1, "Aviyonik Birim": 2, "Kablo Seti": 0}),
                SystemInfo(name="AKINCI Sistem 2", components={"Yer Kontrol Modülü": 1, "Kamera Sistemi": 1}),
            ], {
                "AKINCI Sistem 1": [
                    _delivery("AKN Kabul 1", "Ali Yılmaz", {"Gövde Kit": 1}, {"Gövde Kit": 1}, "2026-03-01"),
                    _delivery("AKN Kabul 2", "Ayşe Demir", {"Aviyonik Birim": 1}, {"Aviyonik Birim": 1}, "2026-03-15"),
                    _delivery("AKN Kabul 3", "Zeynep Çelik", {"Aviyonik Birim": 0, "Kablo Seti": 0}, {"Aviyonik Birim": 1, "Kablo Seti": 0}, "2026-03-20"),
                ],
                "AKINCI Sistem 2": [_delivery("AKN Kabul 4", "", {"Kamera Sistemi": 1}, {"Kamera Sistemi": 0}, "2026-04-01")],
            }),
            (_contract("AKN-2026-001-SD-001", MAIN_PLATFORM, ["Ali Yılmaz"], "SD-001", parent_no=MAIN_CONTRACT_NO), [
                SystemInfo(name="AKINCI SD Sistem", components={"Yazılım Paketi": 1, "Kablo Seti": 2}),
            ], {
                "AKINCI SD Sistem": [_delivery("SD Kabul 1", "Mehmet Kaya", {"Yazılım Paketi": 1}, {"Yazılım Paketi": 1}, "2026-04-10")],
            }),
            (_contract("KIZ-2026-010", "KIZILELMA", ["Mehmet Kaya"], status="Teslim Edildi"), [
                SystemInfo(name="KIZILELMA Sistem 1", components={"Gövde Kit": 1, "Motor Grubu": 1, "Kamera Sistemi": 1}),
            ], {
                "KIZILELMA Sistem 1": [
                    _delivery("KIZ Kabul 1", "Mehmet Kaya", {"Motor Grubu": 1}, {"Motor Grubu": 1}, "2026-05-01"),
                    _delivery("KIZ Kabul 2", "Zeynep Çelik", {"Kamera Sistemi": 1}, {"Kamera Sistemi": 1}, "2026-05-08"),
                ],
            }),
            (_contract("TB2-2026-005", "TB2", ["Zeynep Çelik"], status="Başlanmadı"), [
                SystemInfo(name="TB2 Sistem 1", components={"Güç Dağıtım Ünitesi": 1, "Kablo Seti": 1}),
            ], {
                "TB2 Sistem 1": [_delivery("TB2 Kabul 1", "", {"Güç Dağıtım Ünitesi": 1}, {"Güç Dağıtım Ünitesi": 0}, "2026-05-15")],
            }),
        ]
        contract_ids: dict[tuple[str, str, str], int] = {}
        for contract, systems, deliveries in contracts:
            contract_ids[(contract.platform, contract.no, contract.contract_type)] = store.write_contract(contract, systems, deliveries)
        main_id = contract_ids[(MAIN_PLATFORM, MAIN_CONTRACT_NO, MAIN_CONTRACT_TYPE)]
        sd_id = contract_ids[(MAIN_PLATFORM, "AKN-2026-001-SD-001", "SD-001")]
        store.db.conn.execute("UPDATE contracts SET parent_contract_id=?, parent_contract_no=? WHERE id=?", (main_id, MAIN_CONTRACT_NO, sd_id))
        store.db.conn.commit()

        store.save_contract_tags(MAIN_PLATFORM, MAIN_CONTRACT_NO, MAIN_CONTRACT_TYPE, ["Öncelikli", "Export Kontrol"])
        store.save_contract_tags(MAIN_PLATFORM, "AKN-2026-001-SD-001", "SD-001", ["Takipte"])
        store.save_contract_tags("KIZILELMA", "KIZ-2026-010", MAIN_CONTRACT_TYPE, ["Takipte"])

        expected_files: dict[int, bytes] = {}
        with TemporaryDirectory() as td:
            source_dir = Path(td)
            _add_blob_file(store, source_dir, expected_files, MAIN_PLATFORM, MAIN_CONTRACT_NO, MAIN_CONTRACT_TYPE, "AKN-2026-001-not.txt", "AKINCI manuel test notu\n".encode("utf-8"))
            _add_blob_file(store, source_dir, expected_files, MAIN_PLATFORM, MAIN_CONTRACT_NO, MAIN_CONTRACT_TYPE, "AKN-2026-001-imzali.pdf", b"%PDF-1.4\n% dummy signed contract\n%%EOF\n")
            _add_blob_file(store, source_dir, expected_files, MAIN_PLATFORM, "AKN-2026-001-SD-001", "SD-001", "AKN-SD-001-ek.xlsx", b"PK\x03\x04dummy-xlsx-manual-sts-bytes\n")
            _add_blob_file(store, source_dir, expected_files, "KIZILELMA", "KIZ-2026-010", MAIN_CONTRACT_TYPE, "KIZ-kabul.png", b"\x89PNG\r\n\x1a\ndummy-png-manual-sts-bytes\n")
            validate_manual_sts(store, expected_files, export_dir=source_dir)
        store.save()
    finally:
        store.db.close()
    return output


def validate_manual_sts(store: STSStore, expected_files: dict[int, bytes], export_dir: Path) -> None:
    conn = store.db.conn
    assert store.db.integrity_check() == ["ok"]
    assert store.db.foreign_key_check() == []
    expected_counts = {"platforms": 3, "users": 4, "components": 8, "contracts": 4, "systems": 5, "deliveries": 8, "contract_files": 4}
    for table, expected in expected_counts.items():
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == expected
    assert "delivery_user_id" not in {row[1] for row in conn.execute("PRAGMA table_info(systems)")}
    assert "delivery_user_id" in {row[1] for row in conn.execute("PRAGMA table_info(deliveries)")}
    assert "content_blob" in {row[1] for row in conn.execute("PRAGMA table_info(contract_files)")}
    assert conn.execute("SELECT COUNT(*) FROM contract_files WHERE length(content_blob) > 0").fetchone()[0] == 4
    file_rows = conn.execute("SELECT filename,file_ext,mime_type,size_bytes,content_blob,created_at FROM contract_files ORDER BY id").fetchall()
    assert all(row[0] and row[1] and row[2] and int(row[3] or 0) > 0 and bytes(row[4]) and row[5] for row in file_rows)
    assert {row[1] for row in file_rows} == {"txt", "pdf", "xlsx", "png"}
    assert conn.execute("SELECT COUNT(*) FROM system_components WHERE qty <= 0").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM delivery_components WHERE planned = 0 AND delivered = 0").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM delivery_components WHERE planned = 0 AND delivered > 0").fetchone()[0] >= 1
    assert conn.execute("SELECT parent_contract_id FROM contracts WHERE contract_no='AKN-2026-001-SD-001'").fetchone()[0] is not None

    listed = store.list_contract_files(MAIN_PLATFORM, MAIN_CONTRACT_NO, MAIN_CONTRACT_TYPE)
    assert len(listed) == 2 and all("content_blob" not in item for item in listed)
    for file_id, original_bytes in expected_files.items():
        filename, _mime_type, content = store.get_contract_file_bytes(file_id)
        assert content == original_bytes
        exported = export_dir / f"exported-{filename}"
        store.export_contract_file(file_id, exported)
        assert hashlib.sha256(exported.read_bytes()).digest() == hashlib.sha256(original_bytes).digest()

    _contract_info, _systems, deliveries = store.load_contract_structure(MAIN_PLATFORM, MAIN_CONTRACT_NO, contract_type=MAIN_CONTRACT_TYPE)
    users = {delivery.name: delivery.delivery_user for delivery in deliveries["AKINCI Sistem 1"]}
    assert users == {"AKN Kabul 1": "Ali Yılmaz", "AKN Kabul 2": "Ayşe Demir", "AKN Kabul 3": "Zeynep Çelik"}
    blank_delivery = deliveries["AKINCI Sistem 2"][0]
    assert blank_delivery.delivery_user == ""
    assert blank_delivery.planned == {"Kamera Sistemi": 1.0}
    special = next(delivery for delivery in deliveries["AKINCI Sistem 1"] if delivery.name == "AKN Kabul 3")
    assert special.planned == {"Aviyonik Birim": 0.0} and special.delivered == {"Aviyonik Birim": 1.0}

    cascade_contract = _contract("CASCADE-CHECK", "TB2", ["Zeynep Çelik"])
    cascade_id = store.write_contract(cascade_contract, [], {})
    source = export_dir / "cascade-check.txt"; source.write_bytes(b"cascade-check")
    cascade_file_id = store.add_contract_file("TB2", cascade_contract.no, source, cascade_contract.contract_type)
    assert conn.execute("SELECT COUNT(*) FROM contract_files WHERE id=?", (cascade_file_id,)).fetchone()[0] == 1
    assert store.delete_contract("TB2", cascade_contract.no)["deleted_rows"] == 1
    assert conn.execute("SELECT COUNT(*) FROM contracts WHERE id=?", (cascade_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM contract_files WHERE id=?", (cascade_file_id,)).fetchone()[0] == 0
    assert store.db.foreign_key_check() == []


if __name__ == "__main__":
    generated = create_manual_sts()
    print(f"ok: {generated}")
