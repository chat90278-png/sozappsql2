import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_database import STSDatabase, device_name, format_log_timestamp, now_iso
from src.services.sts_store import STSStore


with TemporaryDirectory() as td:
    root = Path(td)
    path = root / "audit.sts"
    store = STSStore(path)
    logs = store.list_logs(limit=10)
    assert logs == []
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", now_iso())
    assert format_log_timestamp("2026-06-01T05:53:06") == "2026-06-01 05:53:06"

    before_count = store.db.conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
    assert not store.db.add_sql_query_log("SELECT 1", duration_ms=1)
    assert not store.db.add_sql_query_log("PRAGMA table_info(activity_logs)", duration_ms=1)
    assert not store.db.add_sql_query_log("WITH data AS (SELECT 1) SELECT * FROM data", duration_ms=1)
    assert store.db.conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0] == before_count

    store.db.conn.execute("CREATE TABLE audit_sql_target(id INTEGER PRIMARY KEY, name TEXT)")
    store.db.conn.commit()
    assert store.db.add_sql_query_log("CREATE TABLE audit_sql_target(id INTEGER PRIMARY KEY, name TEXT)", duration_ms=3, affected_rows=0)
    sql_log = store.db.conn.execute("SELECT * FROM activity_logs WHERE action='sql_query_executed' ORDER BY id DESC LIMIT 1").fetchone()
    assert sql_log["actor"] == "Kimliği belirlenemedi"
    assert sql_log["source"] == "SQL Terminal"
    assert sql_log["device_name"] == device_name()
    payload = json.loads(sql_log["payload_json"])
    assert payload == {
        "operation": "CREATE",
        "duration_ms": 3,
        "changed": True,
        "affected_rows": 0,
    }
    assert "query_preview" not in payload

    for statement, operation in [
        ("INSERT INTO audit_sql_target(id,name) VALUES(1,'x')", "INSERT"),
        ("UPDATE audit_sql_target SET name='y' WHERE id=1", "UPDATE"),
        ("DELETE FROM audit_sql_target WHERE id=1", "DELETE"),
    ]:
        assert store.db.add_sql_query_log(statement, duration_ms=2, affected_rows=1)
        latest = store.db.conn.execute("SELECT payload_json FROM activity_logs WHERE action='sql_query_executed' ORDER BY id DESC LIMIT 1").fetchone()
        assert json.loads(latest[0])["operation"] == operation

    store.create_platform("AKINCI")
    contract = ContractInfo(no="AKN-AUDIT-001", platform="AKINCI", user="", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="", t0_date="", t0_months=0, completion_date="")
    store.write_contract(contract, [], {})
    contract.note = "Güncellendi"
    system = SystemInfo(name="Sistem-A", components={"GÖVDE": 1}, status="Başlanmadı")
    delivery = DeliveryInfo(name="Kabul 1", status="Başlanmadı", acceptance_date="", note="", planned={"GÖVDE": 1}, delivered={"GÖVDE": 0})
    store.write_contract(contract, [system], {"Sistem-A": [delivery]})
    system.components["GÖVDE"] = 2
    delivery.status = "Teslim Edildi"
    delivery.acceptance_date = "2026-06-01"
    store.write_contract(contract, [system], {"Sistem-A": [delivery]})
    store.save_contract_tags("AKINCI", contract.no, contract.contract_type, [])
    source_file = root / "audit.txt"
    source_file.write_text("audit", encoding="utf-8")
    document_id = store.add_contract_file("AKINCI", contract.no, source_file, contract.contract_type)
    assert store.delete_contract_file(document_id)
    store.delete_contract("AKINCI", contract.no)
    actions = {row[0] for row in store.db.conn.execute("SELECT action FROM activity_logs")}
    assert {
        "contract_created", "contract_updated", "system_created", "system_updated",
        "delivery_created", "delivery_updated", "document_added",
        "document_deleted", "contract_deleted",
    } <= actions
    assert {"contract_tags_updated", "system_component_updated", "delivery_status_changed"}.isdisjoint(actions)
    user_logs = store.db.conn.execute("SELECT actor,device_name FROM activity_logs WHERE action='contract_created'").fetchone()
    assert user_logs[:] == ("Kullanıcı", device_name())

    store.db.close()

    legacy_path = root / "legacy-audit.sts"
    legacy = sqlite3.connect(legacy_path)
    legacy.execute("CREATE TABLE activity_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,actor TEXT,action TEXT NOT NULL,entity_type TEXT,entity_id TEXT,entity_key TEXT,platform_id INTEGER,contract_no TEXT,message TEXT,before_json TEXT,after_json TEXT,payload_json TEXT)")
    legacy.execute("INSERT INTO activity_logs(created_at,actor,action) VALUES('2026-06-01T05:53:06','','legacy_action')")
    legacy.commit()
    legacy.close()

    upgraded = STSDatabase(legacy_path)
    columns = {row[1] for row in upgraded.conn.execute("PRAGMA table_info(activity_logs)")}
    assert {
        "source", "device_name", "occurred_at_utc", "category", "status",
        "operation_id", "actor_type", "actor_staff_id", "actor_admin_id",
        "actor_display_name", "session_id", "contract_id",
        "platform_name_snapshot", "contract_no_snapshot",
        "changed_fields_json", "technical_payload_json", "event_schema_version",
    } <= columns
    old = upgraded.conn.execute("SELECT created_at,actor,source,device_name FROM activity_logs WHERE action='legacy_action'").fetchone()
    assert old[:] == ("2026-06-01T05:53:06", "", None, None)
    migration = upgraded.conn.execute("SELECT 1 FROM activity_logs WHERE action='schema_migrated' LIMIT 1").fetchone()
    assert migration is None
    upgraded.close()

print("ok")
