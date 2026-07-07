
import uuid
from pathlib import Path

from src.domain.contract_snapshot import hash_contract_snapshot, normalize_contract_snapshot
from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_database import STSDatabase
from src.services.sts_store import STSStore


def make_contract(no="C-1"):
    return ContractInfo(no=no, platform="AKINCI", user="SSB", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="2026-01-01", t0_date="2026-01-02", t0_months=1, completion_date="2026-02-02", status="PLAN", note="n")


def test_sts_instance_id_stable(tmp_path):
    path = tmp_path / "a.sts"
    db = STSDatabase(path)
    first = db.conn.execute("SELECT value FROM sts_metadata WHERE key='sts_instance_id'").fetchone()[0]
    uuid.UUID(first)
    db.close()
    db = STSDatabase(path)
    second = db.conn.execute("SELECT value FROM sts_metadata WHERE key='sts_instance_id'").fetchone()[0]
    migrated = db.init_schema()
    third = db.conn.execute("SELECT value FROM sts_metadata WHERE key='sts_instance_id'").fetchone()[0]
    db.close()
    assert first == second == third


def test_merge_uid_backfill_and_new_entities(tmp_path):
    store = STSStore(tmp_path / "b.sts")
    ci = make_contract()
    sys = SystemInfo("SYS", {"C": 1})
    delivery = DeliveryInfo("DEL", "PLAN", "", "", {"C": 1}, {"C": 0})
    cid = store.write_contract(ci, [sys], {"SYS": [delivery]})
    tables = ["contracts", "systems", "deliveries"]
    values = {t: store.db.conn.execute(f"SELECT merge_uid FROM {t} LIMIT 1").fetchone()[0] for t in tables}
    folder = store.create_contract_file_folder("AKINCI", "C-1", "Ana Sözleşme", name="F")
    source = tmp_path / "x.txt"; source.write_text("hello")
    file_id = store.add_contract_file("AKINCI", "C-1", source, "Ana Sözleşme", folder_id=folder["id"])
    values["contract_file_folders"] = store.db.conn.execute("SELECT merge_uid FROM contract_file_folders WHERE id=?", (folder["id"],)).fetchone()[0]
    values["contract_files"] = store.db.conn.execute("SELECT merge_uid FROM contract_files WHERE id=?", (file_id,)).fetchone()[0]
    for v in values.values():
        uuid.UUID(v)
    store.db.init_schema()
    again = {t: store.db.conn.execute(f"SELECT merge_uid FROM {t} LIMIT 1").fetchone()[0] for t in values}
    assert values == again
    store.db.close()


def test_share_write_path_preserves_core_uids(tmp_path):
    src = STSStore(tmp_path / "src.sts")
    ci = make_contract(); ci.merge_uid = "contract-A"
    sys = SystemInfo("SYS", {"C": 1}, merge_uid="system-B")
    delivery = DeliveryInfo("DEL", "PLAN", "", "", {"C": 1}, {"C": 0}, merge_uid="delivery-C")
    src.write_contract(ci, [sys], {"SYS": [delivery]})
    loaded_ci, systems, deliveries = src.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    share = STSStore(tmp_path / "share.sts")
    loaded_ci.entry_start_row = loaded_ci.id = loaded_ci.contract_id = 0
    loaded_ci.platform_ids = []
    loaded_ci.platforms = []
    loaded_ci.platform_id = 0
    loaded_ci.primary_platform_id = 0
    share.write_contract(loaded_ci, systems, deliveries)
    assert share.db.conn.execute("SELECT merge_uid FROM contracts").fetchone()[0] == "contract-A"
    assert share.db.conn.execute("SELECT merge_uid FROM systems").fetchone()[0] == "system-B"
    assert share.db.conn.execute("SELECT merge_uid FROM deliveries").fetchone()[0] == "delivery-C"


def test_snapshot_deterministic_and_meaningful_changes():
    a = {"systems": [{"merge_uid": "b", "status": "X"}, {"merge_uid": "a", "status": "Y"}], "contract": {"note": "n", "status": "PLAN"}}
    b = {"contract": {"status": "PLAN", "note": "n"}, "systems": [{"status": "Y", "merge_uid": "a"}, {"status": "X", "merge_uid": "b"}]}
    assert hash_contract_snapshot(a) == hash_contract_snapshot(b)
    c = {"contract": {"status": "DONE", "note": "n"}, "systems": a["systems"]}
    assert hash_contract_snapshot(a) != hash_contract_snapshot(c)
    d = {"files": [{"merge_uid": "f", "sha256": "1"}]}
    e = {"files": [{"merge_uid": "f", "sha256": "2"}]}
    assert hash_contract_snapshot(d) != hash_contract_snapshot(e)


def test_revision_changes_only_on_meaningful_write(tmp_path):
    store = STSStore(tmp_path / "r.sts")
    ci = make_contract()
    store.write_contract(ci, [], {})
    rev1 = store.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (ci.id,)).fetchone()[0]
    store.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    rev_read = store.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (ci.id,)).fetchone()[0]
    store.write_contract(ci, [], {})
    rev_noop = store.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (ci.id,)).fetchone()[0]
    ci.note = "changed"
    store.write_contract(ci, [], {})
    rev_changed = store.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (ci.id,)).fetchone()[0]
    assert rev1 == 1
    assert rev_read == rev1
    assert rev_noop == rev1
    assert rev_changed == rev1 + 1
