from __future__ import annotations

from typing import Iterable


FALLBACK_RELATIONSHIPS = [
    ("contracts", "platform_id", "platforms", "id"),
    ("contracts", "user_id", "users", "id"),
    ("systems", "contract_id", "contracts", "id"),
    ("systems", "delivery_user_id", "users", "id"),
    ("deliveries", "contract_id", "contracts", "id"),
    ("deliveries", "system_id", "systems", "id"),
    ("deliveries", "delivery_user_id", "users", "id"),
    ("system_components", "system_id", "systems", "id"),
    ("system_components", "component_id", "components", "id"),
    ("delivery_components", "delivery_id", "deliveries", "id"),
    ("delivery_components", "component_id", "components", "id"),
    ("contract_tags", "contract_id", "contracts", "id"),
    ("contract_tags", "tag_id", "tags", "id"),
    ("component_platforms", "component_id", "components", "id"),
    ("component_platforms", "platform_id", "platforms", "id"),
    ("activity_logs", "platform_id", "platforms", "id"),
]


def relationship_key(relationship: dict) -> tuple[str, str, str, str]:
    return (
        str(relationship["source_table"]),
        str(relationship["source_column"]),
        str(relationship["target_table"]),
        str(relationship["target_column"]),
    )


def relationship_text(relationship: dict) -> str:
    return (
        f"{relationship['source_table']}.{relationship['source_column']}"
        f" → {relationship['target_table']}.{relationship['target_column']}"
    )


def get_table_columns(conn, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [
        {"name": str(row[1]), "type": str(row[2] or ""), "primary_key": bool(row[5])}
        for row in rows
    ]


def get_primary_key_columns(conn, table: str) -> list[str]:
    return [column["name"] for column in get_table_columns(conn, table) if column["primary_key"]]


def get_schema_relationships(conn, tables: Iterable[str], include_fallback: bool = True) -> list[dict]:
    table_names = {str(table) for table in tables}
    columns_by_table = {table: {column["name"] for column in get_table_columns(conn, table)} for table in table_names}
    relationships: dict[tuple[str, str, str, str], dict] = {}
    for source_table in sorted(table_names):
        for row in conn.execute(f"PRAGMA foreign_key_list({source_table})").fetchall():
            relationship = {
                "source_table": source_table,
                "source_column": str(row[3]),
                "target_table": str(row[2]),
                "target_column": str(row[4]),
                "on_update": str(row[5] or "NO ACTION"),
                "on_delete": str(row[6] or "NO ACTION"),
                "fallback": False,
            }
            relationships[relationship_key(relationship)] = relationship
    if include_fallback:
        for source_table, source_column, target_table, target_column in FALLBACK_RELATIONSHIPS:
            if source_table not in table_names or target_table not in table_names:
                continue
            if source_column not in columns_by_table[source_table] or target_column not in columns_by_table[target_table]:
                continue
            relationship = {
                "source_table": source_table,
                "source_column": source_column,
                "target_table": target_table,
                "target_column": target_column,
                "on_update": "NO ACTION",
                "on_delete": "NO ACTION",
                "fallback": True,
            }
            relationships.setdefault(relationship_key(relationship), relationship)
    return sorted(relationships.values(), key=relationship_key)
