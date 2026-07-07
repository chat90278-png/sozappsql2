from __future__ import annotations

from typing import Dict, List, Optional


def filter_table_metadata(tables: List[str], query: str, descriptions: Optional[Dict[str, str]] = None) -> List[str]:
    """Return table names matching *query* without touching Qt widgets or SQLite."""
    normalized_query = (query or "").strip().casefold()
    if not normalized_query:
        return list(tables)
    descriptions = descriptions or {}
    return [
        table
        for table in tables
        if normalized_query in table.casefold()
        or normalized_query in str(descriptions.get(table) or "").casefold()
    ]
