import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo, TagDef
from src.services.sts_store import STSStore


def delivery(name, planned, delivered, delivery_user=""):
    return DeliveryInfo(
        name=name,
        status="PLAN",
        acceptance_date="",
        note="",
        planned=planned,
        delivered=delivered,
        delivery_user=delivery_user,
    )


with TemporaryDirectory() as td:
    path = Path(td) / "workflow.sts"
    store = STSStore(path)

    store.create_platform("AKINCI")
    store.create_platform("KIZILELMA")
    assert store.platform_names() == ["AKINCI", "KIZILELMA"]

    store.write_users([
        {"name": "Serhat", "yi_yd": "Yİ", "active": True, "note": ""},
        {"name": "Ayşe", "yi_yd": "YD", "active": True, "note": ""},
        {"name": "Mehmet", "yi_yd": "Yİ", "active": True, "note": ""},
    ])
    store.write_components([
        ComponentDef(name="GÖVDE", platforms={"AKINCI": True, "KIZILELMA": True}),
        ComponentDef(name="KANAT", platforms={"AKINCI": True, "KIZILELMA": True}),
        ComponentDef(name="MOTOR", platforms={"AKINCI": True, "KIZILELMA": False}),
        ComponentDef(name="AVİYONİK", platforms={"AKINCI": True, "KIZILELMA": True}),
        ComponentDef(name="SIFIR", platforms={"AKINCI": True, "KIZILELMA": False}),
    ])
    assert store.assigned_components("AKINCI") == ["AVİYONİK", "GÖVDE", "KANAT", "MOTOR", "SIFIR"]
    assert store.assigned_components("KIZILELMA") == ["AVİYONİK", "GÖVDE", "KANAT"]

    contract = ContractInfo(
        no="AKN-001",
        platform="AKINCI",
        user="Serhat",
        yi_yd="Yİ",
        contract_type="Ana Sözleşme",
        signature_date="2026-01-01",
        t0_date="2026-01-01",
        t0_months=12,
        completion_date="2026-12-31",
    )
    systems = [
        SystemInfo(name="Sistem-A", components={"GÖVDE": 2, "KANAT": 4, "SIFIR": 0}),
        SystemInfo(name="Sistem-B", components={"MOTOR": 1, "AVİYONİK": 3, "SIFIR": -1}),
    ]
    deliveries = {
        "Sistem-A": [
            delivery("A-Kabul-1", {"GÖVDE": 1, "KANAT": 2, "SIFIR": 0}, {"GÖVDE": 1, "KANAT": 1, "SIFIR": 0}, "Ayşe"),
            delivery("A-Kabul-2", {"GÖVDE": 1, "KANAT": 2}, {"GÖVDE": 0, "KANAT": 2}, "Mehmet"),
        ],
        "Sistem-B": [
            delivery("B-Kabul-1", {"MOTOR": 1, "SIFIR": 0}, {"MOTOR": 1, "AVİYONİK": 2, "SIFIR": 0}, "Serhat"),
            delivery("B-Kabul-2", {"AVİYONİK": 1}, {"AVİYONİK": 1}),
        ],
    }
    contract_id = store.write_contract(contract, systems, deliveries)
    store.upsert_tag_def(TagDef(name="Öncelikli", color="#ef4444"))
    store.save_contract_tags("AKINCI", "AKN-001", "Ana Sözleşme", ["Öncelikli"])

    conn = store.db.conn
    assert conn.execute("SELECT COUNT(*) FROM system_components WHERE qty <= 0").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM delivery_components WHERE planned = 0 AND delivered = 0").fetchone()[0] == 0
    delivered_only = conn.execute(
        """
        SELECT dc.planned, dc.delivered
        FROM delivery_components dc
        JOIN components c ON c.id = dc.component_id
        JOIN deliveries d ON d.id = dc.delivery_id
        WHERE d.name = 'B-Kabul-1' AND c.name = 'AVİYONİK'
        """
    ).fetchone()
    assert delivered_only[:] == (0.0, 2.0)
    assert conn.execute("SELECT COUNT(*) FROM systems WHERE delivery_user_id IS NOT NULL").fetchone()[0] == 0
    assert store.db.foreign_key_check() == []
    assert store.db.integrity_check() == ["ok"]

    store.db.close()
    store = STSStore(path)
    loaded_contract, loaded_systems, loaded_deliveries = store.load_contract_structure("AKINCI", "AKN-001")
    assert loaded_contract.platform == "AKINCI"
    assert loaded_contract.user == "Serhat"
    assert {item.name: item.components for item in loaded_systems} == {
        "Sistem-A": {"GÖVDE": 2.0, "KANAT": 4.0},
        "Sistem-B": {"MOTOR": 1.0, "AVİYONİK": 3.0},
    }
    assert len(loaded_deliveries["Sistem-A"]) == 2
    assert len(loaded_deliveries["Sistem-B"]) == 2
    loaded_a_users = {item.name: item.delivery_user for item in loaded_deliveries["Sistem-A"]}
    assert loaded_a_users == {"A-Kabul-1": "Ayşe", "A-Kabul-2": "Mehmet"}
    loaded_b1 = next(item for item in loaded_deliveries["Sistem-B"] if item.name == "B-Kabul-1")
    assert loaded_b1.delivery_user == "Serhat"
    assert loaded_b1.planned == {"MOTOR": 1.0, "AVİYONİK": 0.0}
    assert loaded_b1.delivered == {"MOTOR": 1.0, "AVİYONİK": 2.0}
    assert store.load_contract_tags("AKINCI", "AKN-001", "Ana Sözleşme") == [
        {"name": "Öncelikli", "color": "#ef4444", "kind": "contract"}
    ]

    conn = store.db.conn
    system_ids = [row[0] for row in conn.execute("SELECT id FROM systems WHERE contract_id=?", (contract_id,))]
    delivery_ids = [row[0] for row in conn.execute("SELECT id FROM deliveries WHERE contract_id=?", (contract_id,))]
    assert len(system_ids) == 2
    assert len(delivery_ids) == 4

    result = store.delete_contract("AKINCI", "AKN-001")
    assert result["deleted_rows"] == 1
    assert conn.execute("SELECT COUNT(*) FROM contracts WHERE id=?", (contract_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM systems WHERE contract_id=?", (contract_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM deliveries WHERE contract_id=?", (contract_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM contract_tags WHERE contract_id=?", (contract_id,)).fetchone()[0] == 0
    assert conn.execute(
        f"SELECT COUNT(*) FROM system_components WHERE system_id IN ({','.join('?' for _ in system_ids)})",
        system_ids,
    ).fetchone()[0] == 0
    assert conn.execute(
        f"SELECT COUNT(*) FROM delivery_components WHERE delivery_id IN ({','.join('?' for _ in delivery_ids)})",
        delivery_ids,
    ).fetchone()[0] == 0
    assert store.db.foreign_key_check() == []
    assert store.db.integrity_check() == ["ok"]
    store.db.close()

print("ok")
