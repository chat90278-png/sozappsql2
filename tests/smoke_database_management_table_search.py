import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ui.dialogs.database_management_filters import filter_table_metadata


tables = ["activity_logs", "contracts", "contract_files"]
assert filter_table_metadata(tables, "") == tables
assert filter_table_metadata(tables, "CONTRACT") == ["contracts", "contract_files"]
assert filter_table_metadata(tables, "İŞ", {"activity_logs": "İşlem geçmişi"}) == ["activity_logs"]
assert filter_table_metadata(tables, "zzzz") == []
print("ok")
