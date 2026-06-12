import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.sts_store import STSStore


with TemporaryDirectory() as td:
    store = STSStore(Path(td) / "system_types.sts")

    assert store.list_system_type_names("AKINCI") == []
    assert store.get_system_type_components("Standart Tip", "AKINCI") == []
    assert store.get_system_type_component_quantities("Standart Tip", "AKINCI") == {}

    assert store.save_system_type("Standart Tip", "AKINCI", ["Gövde Kit", "Aviyonik Birim"]) == 2
    assert store.list_system_type_names("AKINCI") == ["Standart Tip"]
    assert store.list_system_type_names("TB2") == []
    assert store.get_system_type_components("standart tip", "AKINCI") == ["Gövde Kit", "Aviyonik Birim"]
    assert store.get_system_type_component_quantities("Standart Tip", "AKINCI") == {
        "Gövde Kit": 1,
        "Aviyonik Birim": 1,
    }

    assert store.save_system_type("Standart Tip", "AKINCI", {"Gövde Kit": 3, "Aviyonik Birim": 2, "Boş": 0}) == 2
    assert store.get_system_type_component_quantities("Standart Tip", "AKINCI") == {
        "Gövde Kit": 3,
        "Aviyonik Birim": 2,
    }

    raw = store.db.conn.execute("SELECT value FROM meta WHERE key='system_types'").fetchone()[0]
    assert json.loads(raw) == {"AKINCI": {"Standart Tip": {"Gövde Kit": 3, "Aviyonik Birim": 2}}}

    store.db.conn.execute("UPDATE meta SET value='{' WHERE key='system_types'")
    store.db.conn.commit()
    assert store.list_system_type_names("AKINCI") == []
    assert store.get_system_type_component_quantities("Standart Tip", "AKINCI") == {}

print("ok")
