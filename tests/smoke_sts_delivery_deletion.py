import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_store import STSStore


def delivery(name, planned, delivered, status="Teslim Edildi", acceptance_date="2026-05-01"):
    return DeliveryInfo(name=name, status=status, acceptance_date=acceptance_date, note="", planned=planned, delivered=delivered)


with TemporaryDirectory() as td:
    store = STSStore(Path(td) / "delivery-delete.sts")
    store.create_platform("AKINCI")
    contract = ContractInfo(no="AKN-DELETE-001", platform="AKINCI", user="", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="", t0_date="", t0_months=0, completion_date="", status="Tamamlandı", acceptance_date="2026-05-02")
    system = SystemInfo(name="Sistem 1", components={"Gövde Kit": 2}, status="Teslim Edildi", acceptance_date="2026-05-02")
    kabul_1 = delivery("Kabul 1", {"Gövde Kit": 1}, {"Gövde Kit": 1}, acceptance_date="2026-05-01")
    kabul_2 = delivery("Kabul 2", {"Gövde Kit": 1}, {"Gövde Kit": 1}, acceptance_date="2026-05-02")
    store.write_contract(contract, [system], {system.name: [kabul_1, kabul_2]})

    conn = store.db.conn
    component_before = conn.execute("SELECT id,qty FROM system_components").fetchone()
    kabul_2_id = conn.execute("SELECT id FROM deliveries WHERE name='Kabul 2'").fetchone()[0]
    kabul_2_component_ids = [row[0] for row in conn.execute("SELECT id FROM delivery_components WHERE delivery_id=?", (kabul_2_id,))]

    # A forced failure after the delivery DELETE must rollback the whole write.
    conn.execute("CREATE TRIGGER fail_delivery_delete BEFORE DELETE ON deliveries BEGIN SELECT RAISE(ABORT, 'forced rollback'); END")
    conn.commit()
    try:
        store.write_contract(contract, [system], {system.name: [kabul_1]})
        raise AssertionError("forced delivery delete unexpectedly succeeded")
    except Exception as exc:
        assert "forced rollback" in str(exc)
    assert conn.execute("SELECT COUNT(*) FROM deliveries WHERE id=?", (kabul_2_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT id,qty FROM system_components").fetchone()[:] == component_before[:]
    conn.execute("DROP TRIGGER fail_delivery_delete")
    conn.commit()

    # Deleting Kabul 2 persists only the removed acceptance and its child rows.
    contract.status = "Devam ediyor"
    contract.acceptance_date = ""
    system.status = "Parçalı Teslimat"
    system.acceptance_date = ""
    store.write_contract(contract, [system], {system.name: [kabul_1]})
    assert conn.execute("SELECT COUNT(*) FROM deliveries WHERE id=?", (kabul_2_id,)).fetchone()[0] == 0
    assert all(conn.execute("SELECT COUNT(*) FROM delivery_components WHERE id=?", (item_id,)).fetchone()[0] == 0 for item_id in kabul_2_component_ids)
    assert conn.execute("SELECT id,qty FROM system_components").fetchone()[:] == component_before[:]
    delivered = conn.execute("SELECT SUM(dc.delivered) FROM delivery_components dc JOIN deliveries d ON d.id=dc.delivery_id WHERE d.system_name='Sistem 1'").fetchone()[0]
    assert delivered == 1
    assert component_before[1] - delivered == 1
    assert conn.execute("SELECT status,acceptance_date FROM systems WHERE name='Sistem 1'").fetchone()[:] == ("Parçalı Teslimat", "")
    assert conn.execute("SELECT status,acceptance_date FROM contracts WHERE contract_no=?", (contract.no,)).fetchone()[:] == ("Devam ediyor", "")

    log = conn.execute("SELECT actor,source,device_name,entity_type,entity_id,contract_no,message,before_json,after_json FROM activity_logs WHERE action='delivery_deleted' ORDER BY id DESC LIMIT 1").fetchone()
    assert log[0] == "Kullanıcı"
    assert log[1] == "Delivery Editor"
    assert log[2]
    assert log[3:7] == ("delivery", str(kabul_2_id), contract.no, "Teslimat silindi")
    before = json.loads(log[7])
    assert before["status"] == "Teslim Edildi"
    assert before["acceptance_date"] == "2026-05-02"
    assert before["components"] == {"Gövde Kit": {"planned": 1.0, "delivered": 1.0}}
    assert log[8] is None
    assert store.db.foreign_key_check() == []
    assert store.db.integrity_check() == ["ok"]
    store.db.close()

print("ok")
