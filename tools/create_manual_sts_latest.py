"""Create a fresh manual STS v2 database that exercises the latest schema."""
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


def _contract(no: str, platform: str, user: str, contract_type: str = "Ana Sözleşme") -> ContractInfo:
    return ContractInfo(
        no=no,
        platform=platform,
        user=user,
        yi_yd="Yİ",
        contract_type=contract_type,
        signature_date="2026-01-15",
        t0_date="2026-02-01",
        t0_months=12,
        completion_date="2027-02-01",
        status="DEVAM",
        note=f"{no} manuel test sözleşmesi",
    )


def _delivery(name: str, user: str, component: str, acceptance_date: str) -> DeliveryInfo:
    return DeliveryInfo(
        name=name,
        status="KABUL",
        acceptance_date=acceptance_date,
        note=f"{name} manuel test kabulü",
        delivery_user=user,
        planned={component: 1},
        delivered={component: 1},
    )


def create_manual_sts(output_path: Path | str = OUTPUT_PATH) -> Path:
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal"):
        Path(f"{output}{suffix}").unlink(missing_ok=True)

    store = STSStore(output, actor="Test", source="Test")
    try:
        for platform in ("AKINCI", "KIZILELMA", "TB2"):
            store.create_platform(platform)
        store.write_users([
            {"name": "Ali Yılmaz", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "Ayşe Demir", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "Mehmet Kaya", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "Zeynep Çelik", "yi_yd": "Yİ", "active": True, "note": ""},
        ])
        component_names = ("GÖVDE", "KANAT", "MOTOR", "AVİYONİK", "KAMERA", "RADAR", "VERİ LİNKİ", "YER İSTASYONU")
        store.write_components([
            ComponentDef(name=name, version="v1", platforms={"AKINCI": True, "KIZILELMA": True, "TB2": True})
            for name in component_names
        ])
        store.write_tags([
            {"name": "Öncelikli", "color": "#ef4444", "kind": "contract"},
            {"name": "İhracat", "color": "#3b82f6", "kind": "contract"},
            {"name": "Bakım", "color": "#22c55e", "kind": "contract"},
        ])

        contracts = [
            (_contract("AKN-2026-001", "AKINCI", "Ali Yılmaz"), [
                SystemInfo(name="AKINCI-01", components={"GÖVDE": 1, "KANAT": 2, "AVİYONİK": 1}),
                SystemInfo(name="AKINCI-02", components={"GÖVDE": 1, "MOTOR": 1, "RADAR": 1}),
            ], {
                "AKINCI-01": [_delivery("AKN-01-Kabul-1", "Ayşe Demir", "GÖVDE", "2026-03-01"), _delivery("AKN-01-Kabul-2", "Mehmet Kaya", "KANAT", "2026-03-15")],
                "AKINCI-02": [_delivery("AKN-02-Kabul-1", "Zeynep Çelik", "RADAR", "2026-04-01")],
            }),
            (_contract("KIZ-2026-001", "KIZILELMA", "Ayşe Demir"), [
                SystemInfo(name="KIZILELMA-01", components={"GÖVDE": 1, "MOTOR": 1, "KAMERA": 1}),
            ], {
                "KIZILELMA-01": [_delivery("KIZ-01-Kabul-1", "Ali Yılmaz", "MOTOR", "2026-04-10"), _delivery("KIZ-01-Kabul-2", "Zeynep Çelik", "KAMERA", "2026-04-20")],
            }),
            (_contract("TB2-2026-001", "TB2", "Mehmet Kaya"), [
                SystemInfo(name="TB2-01", components={"GÖVDE": 1, "KANAT": 2, "VERİ LİNKİ": 1}),
            ], {
                "TB2-01": [_delivery("TB2-01-Kabul-1", "Ali Yılmaz", "VERİ LİNKİ", "2026-05-01"), _delivery("TB2-01-Kabul-2", "Ayşe Demir", "KANAT", "2026-05-08")],
            }),
            (_contract("AKN-2026-002", "AKINCI", "Zeynep Çelik"), [
                SystemInfo(name="AKINCI-03", components={"YER İSTASYONU": 1, "AVİYONİK": 1}),
            ], {
                "AKINCI-03": [_delivery("AKN-03-Kabul-1", "Mehmet Kaya", "YER İSTASYONU", "2026-05-15")],
            }),
        ]
        for contract, systems, deliveries in contracts:
            store.write_contract(contract, systems, deliveries)

        store.save_contract_tags("AKINCI", "AKN-2026-001", "Ana Sözleşme", ["Öncelikli", "Bakım"])
        store.save_contract_tags("KIZILELMA", "KIZ-2026-001", "Ana Sözleşme", ["İhracat"])

        expected_files: dict[int, bytes] = {}
        with TemporaryDirectory() as td:
            source_dir = Path(td)
            fixtures = {
                "manuel-not.txt": "STS son schema manuel test belgesi\n".encode("utf-8"),
                "manuel-ek.pdf": b"%PDF-1.4\n% dummy manual STS PDF bytes\n%%EOF\n",
                "manuel-tablo.xlsx": b"PK\x03\x04dummy-xlsx-manual-sts-bytes\n",
            }
            for filename, content in fixtures.items():
                source = source_dir / filename
                source.write_bytes(content)
                file_id = store.add_contract_file("AKINCI", "AKN-2026-001", source, "Ana Sözleşme", note="Manuel test BLOB belgesi")
                expected_files[file_id] = content

            validate_manual_sts(store, expected_files, export_dir=source_dir)
        store.save()
    finally:
        store.db.close()
    return output


def validate_manual_sts(store: STSStore, expected_files: dict[int, bytes], export_dir: Path) -> None:
    conn = store.db.conn
    assert store.db.integrity_check() == ["ok"]
    assert store.db.foreign_key_check() == []
    expected_counts = {"platforms": 3, "users": 4, "components": 8, "contracts": 4, "systems": 5, "deliveries": 8, "contract_files": 3}
    for table, expected in expected_counts.items():
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] >= expected
    assert "delivery_user_id" not in {row[1] for row in conn.execute("PRAGMA table_info(systems)")}
    assert "delivery_user_id" in {row[1] for row in conn.execute("PRAGMA table_info(deliveries)")}
    assert conn.execute("SELECT COUNT(*) FROM contract_files WHERE length(content_blob) > 0").fetchone()[0] >= 3
    listed = store.list_contract_files("AKINCI", "AKN-2026-001", "Ana Sözleşme")
    assert len(listed) == 3
    assert all("content_blob" not in item for item in listed)
    for file_id, original_bytes in expected_files.items():
        filename, _mime_type, content = store.get_contract_file_bytes(file_id)
        assert content == original_bytes
        exported = export_dir / f"exported-{filename}"
        store.export_contract_file(file_id, exported)
        assert hashlib.sha256(exported.read_bytes()).digest() == hashlib.sha256(original_bytes).digest()
    _contract_info, _systems, deliveries = store.load_contract_structure("AKINCI", "AKN-2026-001", contract_type="Ana Sözleşme")
    users = {delivery.name: delivery.delivery_user for delivery in deliveries["AKINCI-01"]}
    assert users == {"AKN-01-Kabul-1": "Ayşe Demir", "AKN-01-Kabul-2": "Mehmet Kaya"}


if __name__ == "__main__":
    generated = create_manual_sts()
    print(f"ok: {generated}")
