from __future__ import annotations

import re
from typing import Callable, Optional

TABLE_INFO = {
    "contracts": "Ana sözleşme ve SD kayıtları",
    "systems": "Sözleşmelere bağlı sistemler",
    "deliveries": "Teslimat kayıtları",
    "system_components": "Sistem bileşen adetleri",
    "delivery_components": "Teslimat bazlı plan/teslim",
    "contract_tags": "Sözleşme etiket bağlantıları",
    "contract_file_folders": "Sözleşme belge klasörleri",
    "contract_files": "Sözleşmeye gömülü belgeler",
    "contract_users": "Sözleşme kullanıcı ilişkileri",
    "users": "Kullanıcı / kurum tanımları",
    "tags": "Etiket tanımları",
    "platforms": "Platform adları ve logolar",
    "components": "Tanımlı bileşenler",
    "activity_logs": "İşlem geçmişi",
    "staff": "Personel giriş kayıtları",
    "document_locks": "Belge kilit durumu",
    "component_platforms": "Bileşen platform yetkileri",
    "meta": "Sistem meta verileri",
    "permissions": "Tanımlı yetki kodları",
    "role_permissions": "Rol-yetki eşleşmeleri",
    "roles": "Tanımlı roller",
    "sqlite_sequence": None,
}

TABLE_ACCESS = {
    "contracts": "view_contracts",
    "systems": "view_contracts",
    "deliveries": "view_contracts",
    "system_components": "view_contracts",
    "delivery_components": "view_contracts",
    "contract_tags": "view_contracts",
    "contract_file_folders": "view_contracts",
    "contract_files": "view_contracts",
    "contract_users": "view_contracts",
    "users": "view_contracts",
    "tags": "view_contracts",
    "platforms": "view_contracts",
    "components": "view_contracts",
    "component_platforms": "view_contracts",
    "staff": "manage_staff",
    "document_locks": "manage_staff",
    "activity_logs": "manage_staff",
    "roles": "manage_staff",
    "role_permissions": "manage_staff",
    "permissions": "manage_staff",
    "sqlite_sequence": None,
    "meta": None,
}

SQL_RESTRICTED_TABLES = {"staff", "roles", "role_permissions", "permissions"}


def table_required_permission(table: str) -> Optional[str]:
    return TABLE_ACCESS.get(str(table or ""), "manage_staff")


def can_access_table(table: str, has_permission: Callable[[str], bool]) -> bool:
    permission = table_required_permission(table)
    return bool(permission and has_permission(permission))


def visible_table_names(table_names: list[str], has_permission: Callable[[str], bool]) -> list[str]:
    return [table for table in table_names if can_access_table(table, has_permission)]


def contains_restricted_table_sql(sql: str) -> bool:
    text = str(sql or "")
    for table in SQL_RESTRICTED_TABLES:
        escaped = re.escape(table)
        pattern = rf"(?<![\w])(?:{escaped}|[`\"]{escaped}[`\"]|\[{escaped}\])(?![\w])"
        if re.search(pattern, text, flags=re.I):
            return True
    return False
