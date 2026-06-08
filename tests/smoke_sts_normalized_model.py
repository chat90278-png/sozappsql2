import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_database import STSDatabase
from src.services.sts_store import STSStore


def column_names(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


with TemporaryDirectory() as td:
    root = Path(td)
    store = STSStore(root / "normalized.sts")
    contract = ContractInfo(
        no="AKN-NORM-001",
        platform="AKINCI",
        user="Kullanıcı A, Kullanıcı B",
        users=["Kullanıcı A", "Kullanıcı B"],
        yi_yd="Yİ",
        contract_type="Ana Sözleşme",
        signature_date="",
        t0_date="",
        t0_months=0,
        completion_date="",
        status="Devam ediyor",
    )
    system = SystemInfo(name="Sistem 1", components={"Gövde Kit": 2})
    acceptance = DeliveryInfo(name="Kabul 1", status="", acceptance_date="", note="", planned={"Gövde Kit": 2}, delivered={"Gövde Kit": 1})
    store.write_contract(contract, [system], {system.name: [acceptance]})
    conn = store.db.conn

    contract_columns = column_names(conn, "contracts")
    assert "user_" "names" not in contract_columns
    assert "parent_contract_" "no" not in contract_columns
    delivery_columns = column_names(conn, "deliveries")
    assert "system_" "name" not in delivery_columns
    assert conn.execute("SELECT [notnull] FROM pragma_table_info('deliveries') WHERE name='system_id'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM contract_users").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM deliveries d JOIN systems s ON s.id=d.system_id WHERE s.name=?", (system.name,)).fetchone()[0] == 1
    loaded, loaded_systems, loaded_deliveries = store.load_contract_structure("AKINCI", contract.no, contract_type=contract.contract_type)
    assert loaded.users == ["Kullanıcı A", "Kullanıcı B"]
    assert list(loaded_deliveries) == ["Sistem 1"]
    assert store.db.foreign_key_check() == []
    assert store.db.integrity_check() == ["ok"]
    store.db.close()

    legacy_path = root / "legacy-normalized.sts"
    legacy = sqlite3.connect(legacy_path)
    legacy.execute("PRAGMA foreign_keys=OFF")
    legacy.execute("CREATE TABLE platforms(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL)")
    legacy.execute("CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,yi_yd TEXT DEFAULT 'Yİ',active INTEGER DEFAULT 1,note TEXT,created_at TEXT,updated_at TEXT)")
    legacy.execute(
        "CREATE TABLE contracts(id INTEGER PRIMARY KEY AUTOINCREMENT,platform_id INTEGER NOT NULL,user_id INTEGER,contract_no TEXT NOT NULL,"
        "user_" "names TEXT,parent_contract_" "no TEXT,contract_type TEXT)"
    )
    legacy.execute("CREATE TABLE systems(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,name TEXT NOT NULL,status TEXT,completion_date TEXT,acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT)")
    legacy.execute(
        "CREATE TABLE deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,system_id INTEGER,system_" "name TEXT NOT NULL,name TEXT NOT NULL)"
    )
    legacy.execute("INSERT INTO platforms(id,name) VALUES(1,'AKINCI')")
    legacy.execute("INSERT INTO users(id,name) VALUES(1,'Eski Kullanıcı')")
    legacy.execute(
        "INSERT INTO contracts(id,platform_id,user_id,contract_no,user_" "names,parent_contract_" "no,contract_type) VALUES(1,1,1,'LEG-001',?,NULL,'Ana Sözleşme')",
        ('["Eski Kullanıcı", "İkinci Kullanıcı"]',),
    )
    legacy.execute("INSERT INTO systems(id,contract_id,name) VALUES(1,1,'Legacy Sistem')")
    legacy.execute("INSERT INTO deliveries(id,contract_id,system_id,system_" "name,name) VALUES(1,1,NULL,'Legacy Sistem','Legacy Kabul')")
    legacy.commit()
    legacy.close()

    upgraded = STSDatabase(legacy_path)
    assert "user_" "names" not in column_names(upgraded.conn, "contracts")
    assert "parent_contract_" "no" not in column_names(upgraded.conn, "contracts")
    assert "user_id" not in column_names(upgraded.conn, "contracts")
    assert "system_" "name" not in column_names(upgraded.conn, "deliveries")
    assert upgraded.conn.execute("SELECT COUNT(*) FROM contract_users").fetchone()[0] == 2
    assert upgraded.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "8"
    assert upgraded.conn.execute("SELECT system_id FROM deliveries WHERE id=1").fetchone()[0] == 1
    assert upgraded.foreign_key_check() == []
    assert upgraded.integrity_check() == ["ok"]
    upgraded.close()

print("ok")
