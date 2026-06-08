import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ui.dialogs.database_access import (
    TABLE_ACCESS,
    TABLE_INFO,
    contains_restricted_table_sql,
    visible_table_names,
)

all_tables = sorted(TABLE_INFO)
viewer_permissions = {"view_contracts"}
personnel_permissions = {"view_contracts", "open_sql_panel", "sql_read"}
manager_permissions = {"view_contracts", "sql_write"}
admin_permissions = {"view_contracts", "manage_staff", "sql_write"}

viewer_tables = set(visible_table_names(all_tables, viewer_permissions.__contains__))
assert "contracts" in viewer_tables
assert "contract_users" in viewer_tables
assert "systems" in viewer_tables
assert "staff" not in viewer_tables
assert "roles" not in viewer_tables
assert "role_permissions" not in viewer_tables
assert "permissions" not in viewer_tables
assert "meta" not in viewer_tables
assert "sqlite_sequence" not in viewer_tables

personnel_tables = set(visible_table_names(all_tables, personnel_permissions.__contains__))
assert "contracts" in personnel_tables
assert "staff" not in personnel_tables
assert "roles" not in personnel_tables

admin_tables = set(visible_table_names(all_tables, admin_permissions.__contains__))
assert {"staff", "roles", "role_permissions", "permissions", "activity_logs", "document_locks"} <= admin_tables
assert "meta" not in admin_tables
assert "sqlite_sequence" not in admin_tables

assert TABLE_ACCESS["contract_users"] == "view_contracts"
assert TABLE_ACCESS["staff"] == "manage_staff"
assert TABLE_ACCESS["roles"] == "manage_staff"
assert TABLE_ACCESS["meta"] is None
assert TABLE_ACCESS["sqlite_sequence"] is None

assert contains_restricted_table_sql("SELECT * FROM staff")
assert contains_restricted_table_sql('SELECT * FROM "roles"')
assert contains_restricted_table_sql("SELECT * FROM [role_permissions]")
assert contains_restricted_table_sql("SELECT * FROM permissions WHERE code='manage_staff'")
assert not contains_restricted_table_sql("SELECT * FROM contracts")
assert not contains_restricted_table_sql("SELECT * FROM contract_users")
assert not ("manage_staff" in personnel_permissions and "sql_write" in personnel_permissions)
assert not ("manage_staff" in manager_permissions and "sql_write" in manager_permissions)
assert "manage_staff" in admin_permissions and "sql_write" in admin_permissions

print("ok")
