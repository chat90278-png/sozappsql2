from __future__ import annotations

from typing import Iterable


HIDDEN_SCHEMA_COLUMNS = {("systems", "delivery_user_id")}


FALLBACK_RELATIONSHIPS = [
    ("contracts", "platform_id", "platforms", "id"),
    ("contracts", "user_id", "users", "id"),
    ("contract_users", "contract_id", "contracts", "id"),
    ("contract_users", "user_id", "users", "id"),
    ("systems", "contract_id", "contracts", "id"),
    ("deliveries", "contract_id", "contracts", "id"),
    ("deliveries", "system_id", "systems", "id"),
    ("deliveries", "delivery_user_id", "users", "id"),
    ("system_components", "system_id", "systems", "id"),
    ("system_components", "component_id", "components", "id"),
    ("delivery_components", "delivery_id", "deliveries", "id"),
    ("delivery_components", "component_id", "components", "id"),
    ("contract_tags", "contract_id", "contracts", "id"),
    ("contract_tags", "tag_id", "tags", "id"),
    ("contract_file_folders", "contract_id", "contracts", "id"),
    ("contract_file_folders", "parent_id", "contract_file_folders", "id"),
    ("contract_files", "contract_id", "contracts", "id"),
    ("contract_files", "folder_id", "contract_file_folders", "id"),
    ("component_platforms", "component_id", "components", "id"),
    ("component_platforms", "platform_id", "platforms", "id"),
    ("activity_logs", "platform_id", "platforms", "id"),
]


RELATIONSHIP_GROUP_ORDER = (
    "contracts",
    "contract_users",
    "contract_file_folders",
    "contract_files",
    "deliveries",
    "delivery_components",
    "system_components",
    "contract_tags",
    "component_platforms",
    "activity_logs",
)


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


def compact_relationship_text(relationship: dict) -> str:
    return f"{relationship['source_column']} → {relationship['target_table']}.{relationship['target_column']}"


def group_relationships_by_source(relationships: Iterable[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for relationship in relationships:
        groups.setdefault(str(relationship["source_table"]), []).append(relationship)
    fallback_order = {relationship: index for index, relationship in enumerate(FALLBACK_RELATIONSHIPS)}
    for source_table, source_relationships in groups.items():
        source_relationships.sort(
            key=lambda relationship: (
                fallback_order.get(relationship_key(relationship), len(fallback_order)),
                relationship_key(relationship),
            )
        )
    group_order = {source_table: index for index, source_table in enumerate(RELATIONSHIP_GROUP_ORDER)}
    return dict(sorted(groups.items(), key=lambda item: (group_order.get(item[0], len(group_order)), item[0])))


def filter_relationship_groups(groups: dict[str, list[dict]], query: str) -> dict[str, list[dict]]:
    needle = str(query or "").strip().casefold()
    if not needle:
        return {source_table: list(relationships) for source_table, relationships in groups.items()}
    filtered: dict[str, list[dict]] = {}
    for source_table, relationships in groups.items():
        if needle in source_table.casefold():
            filtered[source_table] = list(relationships)
            continue
        matching = [
            relationship
            for relationship in relationships
            if any(
                needle in str(relationship[field]).casefold()
                for field in ("source_table", "source_column", "target_table", "target_column")
            )
        ]
        if matching:
            filtered[source_table] = matching
    return filtered


def get_table_columns(conn, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [
        {"name": str(row[1]), "type": str(row[2] or ""), "primary_key": bool(row[5])}
        for row in rows
        if (str(table), str(row[1])) not in HIDDEN_SCHEMA_COLUMNS
    ]


def get_primary_key_columns(conn, table: str) -> list[str]:
    return [column["name"] for column in get_table_columns(conn, table) if column["primary_key"]]


def get_schema_relationships(conn, tables: Iterable[str], include_fallback: bool = True) -> list[dict]:
    table_names = {str(table) for table in tables}
    columns_by_table = {table: {column["name"] for column in get_table_columns(conn, table)} for table in table_names}
    relationships: dict[tuple[str, str, str, str], dict] = {}
    for source_table in sorted(table_names):
        for row in conn.execute(f"PRAGMA foreign_key_list({source_table})").fetchall():
            if (source_table, str(row[3])) in HIDDEN_SCHEMA_COLUMNS:
                continue
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
