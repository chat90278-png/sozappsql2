import hashlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.sts_store import STSStore
from src.ui.dialogs.schema_relationships import get_schema_relationships, relationship_text
from tools.create_manual_sts_latest import MAIN_CONTRACT_NO, MAIN_CONTRACT_TYPE, MAIN_PLATFORM, create_manual_sts

with TemporaryDirectory() as td:
    root = Path(td)
    path = create_manual_sts(root / "manual_latest_v2_test.sts")
    assert path.exists()
    store = STSStore(path)
    conn = store.db.conn
    assert "delivery_user_id" not in {row[1] for row in conn.execute("PRAGMA table_info(systems)")}
    assert "delivery_user_id" in {row[1] for row in conn.execute("PRAGMA table_info(deliveries)")}
    assert "content_blob" in {row[1] for row in conn.execute("PRAGMA table_info(contract_files)")}
    assert store.db.foreign_key_check() == []
    assert store.db.integrity_check() == ["ok"]

    contract, systems, deliveries = store.load_contract_structure(MAIN_PLATFORM, MAIN_CONTRACT_NO, contract_type=MAIN_CONTRACT_TYPE)
    assert contract.no == MAIN_CONTRACT_NO
    assert contract.users == ["Ali Yılmaz", "Ayşe Demir"]
    assert len(systems) == 2
    users = {delivery.name: delivery.delivery_user for delivery in deliveries["AKINCI Sistem 1"]}
    assert users == {"AKN Kabul 1": "Ali Yılmaz", "AKN Kabul 2": "Ayşe Demir", "AKN Kabul 3": "Zeynep Çelik"}
    assert deliveries["AKINCI Sistem 2"][0].delivery_user == ""
    assert store.load_contract_tags(MAIN_PLATFORM, MAIN_CONTRACT_NO, MAIN_CONTRACT_TYPE) == [
        {"name": "Export Kontrol", "color": "#2563eb", "kind": "contract"},
        {"name": "Öncelikli", "color": "#ef4444", "kind": "contract"},
    ]

    files = store.list_contract_files(MAIN_PLATFORM, MAIN_CONTRACT_NO, MAIN_CONTRACT_TYPE)
    assert len(files) == 2 and all("content_blob" not in item for item in files)
    filename, _mime_type, content = store.get_contract_file_bytes(files[0]["id"])
    assert content
    exported = root / filename
    store.export_contract_file(files[0]["id"], exported)
    assert hashlib.sha256(exported.read_bytes()).digest() == hashlib.sha256(content).digest()

    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    relationships = {relationship_text(item) for item in get_schema_relationships(conn, tables)}
    assert "contract_files.contract_id → contracts.id" in relationships
    assert "deliveries.delivery_user_id → users.id" in relationships
    assert "systems.delivery_user_id → users.id" not in relationships
    store.db.close()

print("ok")
