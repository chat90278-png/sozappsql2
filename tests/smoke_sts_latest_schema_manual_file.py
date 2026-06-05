import hashlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.sts_store import STSStore
from src.ui.dialogs.schema_relationships import get_schema_relationships, relationship_text
from tools.create_manual_sts_latest import create_manual_sts

EXPECTED_COLUMNS = {
    "platforms": ["id", "name", "display_name", "is_active", "is_excluded", "logo_blob", "logo_ext", "logo_mime", "logo_updated_at", "sort_order", "created_at", "updated_at"],
    "users": ["id", "name", "yi_yd", "active", "note", "created_at", "updated_at"],
    "components": ["id", "name", "version", "unit", "active", "usage", "payload_json", "created_at", "updated_at"],
    "component_platforms": ["id", "component_id", "platform_id", "enabled"],
    "contracts": ["id", "platform_id", "user_id", "contract_no", "user_names", "yi_yd", "contract_type", "type_display", "link_type", "status", "signed_date", "t0_date", "t0_months", "completion_date", "acceptance_date", "content", "note", "is_main", "parent_contract_id", "parent_contract_no", "search_text", "payload_json", "created_at", "updated_at"],
    "systems": ["id", "contract_id", "name", "status", "completion_date", "acceptance_date", "note", "sort_order", "payload_json"],
    "system_components": ["id", "system_id", "component_id", "qty", "note"],
    "deliveries": ["id", "contract_id", "system_id", "delivery_user_id", "system_name", "name", "status", "acceptance_date", "note", "sort_order", "payload_json"],
    "delivery_components": ["id", "delivery_id", "component_id", "planned", "delivered"],
    "tags": ["id", "name", "color", "kind", "created_at", "updated_at"],
    "contract_tags": ["id", "contract_id", "tag_id"],
    "contract_file_folders": ["id", "contract_id", "parent_id", "name", "created_at", "updated_at"],
    "contract_files": ["id", "contract_id", "folder_id", "filename", "original_path", "file_ext", "mime_type", "size_bytes", "content_blob", "note", "created_at", "updated_at"],
    "activity_logs": ["id", "created_at", "actor", "source", "device_name", "action", "entity_type", "entity_id", "entity_key", "platform_id", "contract_no", "message", "before_json", "after_json", "payload_json"],
}

with TemporaryDirectory() as td:
    root = Path(td)
    path = create_manual_sts(root / "manual_latest_v2_test.sts")
    store = STSStore(path)
    conn = store.db.conn

    for table, expected in EXPECTED_COLUMNS.items():
        assert [row[1] for row in conn.execute(f"PRAGMA table_info({table})")] == expected
    assert "delivery_user_id" not in EXPECTED_COLUMNS["systems"]
    assert "delivery_user_id" in EXPECTED_COLUMNS["deliveries"]
    assert "content_blob" in EXPECTED_COLUMNS["contract_files"]

    stats = store.database_stats()
    assert stats["table_counts"]["contract_files"] == 3
    assert len(store.preview_table("contract_files")) == 3

    source = root / "silme-akisi.txt"
    source_bytes = "BLOB ekleme, okuma, dışa aktarma ve silme testi\n".encode("utf-8")
    source.write_bytes(source_bytes)
    original_hash = hashlib.sha256(source_bytes).digest()
    file_id = store.add_contract_file("AKINCI", "AKN-2026-002", source, "Ana Sözleşme", note="Silme akışı")
    source.unlink()
    filename, mime_type, content = store.get_contract_file_bytes(file_id)
    assert filename == "silme-akisi.txt"
    assert mime_type == "text/plain"
    assert hashlib.sha256(content).digest() == original_hash
    exported = root / "exported.txt"
    store.export_contract_file(file_id, exported)
    assert hashlib.sha256(exported.read_bytes()).digest() == original_hash
    assert store.delete_contract_file(file_id) is True
    assert conn.execute("SELECT COUNT(*) FROM contract_files WHERE id=?", (file_id,)).fetchone()[0] == 0

    cascade_source = root / "cascade.txt"
    cascade_source.write_text("cascade", encoding="utf-8")
    cascade_id = store.add_contract_file("AKINCI", "AKN-2026-002", cascade_source, "Ana Sözleşme")
    contract_id = store._find_contract_id("AKINCI", "AKN-2026-002", "Ana Sözleşme")
    assert store.delete_contract("AKINCI", "AKN-2026-002")["deleted_rows"] == 1
    assert conn.execute("SELECT COUNT(*) FROM contract_files WHERE id=?", (cascade_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM contract_files WHERE contract_id=?", (contract_id,)).fetchone()[0] == 0

    tables = list(EXPECTED_COLUMNS)
    relationships = {relationship_text(item) for item in get_schema_relationships(conn, tables)}
    assert "contract_files.contract_id → contracts.id" in relationships
    assert "deliveries.delivery_user_id → users.id" in relationships
    assert "systems.delivery_user_id → users.id" not in relationships
    assert store.db.foreign_key_check() == []
    assert store.db.integrity_check() == ["ok"]
    store.db.close()

print("ok")
