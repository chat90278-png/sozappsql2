import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.sts_database import STSDatabase
from src.ui.dialogs.schema_relationships import (
    compact_relationship_text,
    filter_relationship_groups,
    get_schema_relationships,
    get_table_columns,
    group_relationships_by_source,
    relationship_text,
)


with TemporaryDirectory() as td:
    db = STSDatabase(Path(td) / "relationships.sts")
    tables = [row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    relationships = get_schema_relationships(db.conn, tables)
    texts = {relationship_text(relationship) for relationship in relationships}
    assert "contracts.platform_id → platforms.id" in texts
    assert "contracts." + "user_id → users.id" not in texts
    assert "contract_users.contract_id → contracts.id" in texts
    assert "contract_users.user_id → users.id" in texts
    assert "deliveries.delivery_user_id → users.id" in texts
    assert "systems.delivery_user_id → users.id" not in texts
    assert "delivery_components.component_id → components.id" in texts
    assert "contract_file_folders.contract_id → contracts.id" in texts
    assert "contract_file_folders.parent_id → contract_file_folders.id" in texts
    assert "contract_files.contract_id → contracts.id" in texts
    assert "contract_files.folder_id → contract_file_folders.id" in texts
    groups = group_relationships_by_source(relationships)
    assert len(groups["deliveries"]) == 3
    assert {compact_relationship_text(item) for item in groups["deliveries"]} == {
        "contract_id → contracts.id",
        "system_id → systems.id",
        "delivery_user_id → users.id",
    }
    assert compact_relationship_text(next(item for item in groups["deliveries"] if item["source_column"] == "delivery_user_id")) == "delivery_user_id → users.id"
    user_groups = filter_relationship_groups(groups, "user")
    assert {relationship_text(item) for items in user_groups.values() for item in items} == {
        "contract_users.contract_id → contracts.id",
        "contract_users.user_id → users.id",
        "deliveries.delivery_user_id → users.id",
    }
    component_groups = filter_relationship_groups(groups, "component")
    assert {"component_platforms", "system_components", "delivery_components"}.issubset(component_groups)
    assert all("component" in relationship_text(item) for items in component_groups.values() for item in items)
    delivery_user = next(item for item in relationships if relationship_text(item) == "deliveries.delivery_user_id → users.id")
    assert delivery_user["source_table"] == "deliveries"
    assert delivery_user["source_column"] == "delivery_user_id"
    assert delivery_user["target_table"] == "users"
    assert delivery_user["target_column"] == "id"
    assert delivery_user["on_delete"] == "SET NULL"
    assert delivery_user["on_update"] == "NO ACTION"
    db.close()

    legacy_path = Path(td) / "fallback.sts"
    legacy = sqlite3.connect(legacy_path)
    legacy.execute("CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
    legacy.execute("CREATE TABLE deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_user_id INTEGER)")
    legacy.execute("CREATE TABLE systems(id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_user_id INTEGER, FOREIGN KEY(delivery_user_id) REFERENCES users(id))")
    legacy.execute("CREATE TABLE contracts(id INTEGER PRIMARY KEY AUTOINCREMENT)")
    legacy.execute("CREATE TABLE contract_files(id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER)")
    fallback_relationships = get_schema_relationships(legacy, ["users", "deliveries", "systems", "contracts", "contract_files"])
    assert "delivery_user_id" not in {column["name"] for column in get_table_columns(legacy, "systems")}
    assert "systems.delivery_user_id → users.id" not in {relationship_text(item) for item in fallback_relationships}
    fallback = next(item for item in fallback_relationships if relationship_text(item) == "deliveries.delivery_user_id → users.id")
    assert fallback["fallback"] is True
    contract_file_fallback = next(item for item in fallback_relationships if relationship_text(item) == "contract_files.contract_id → contracts.id")
    assert contract_file_fallback["fallback"] is True
    legacy.close()

print("ok")
