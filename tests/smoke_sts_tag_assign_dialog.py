import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PySide6.QtWidgets import QApplication
except ModuleNotFoundError:
    print("skip: PySide6 not installed")
    raise SystemExit(0)

from app import TagAssignDialog
from src.models.app_models import ContractInfo, TagDef
from src.services.sts_store import STSStore

app = QApplication.instance() or QApplication([])

with TemporaryDirectory() as td:
    root = Path(td)
    store = STSStore(root / "tag-filter.sts")
    store.create_platform("AKINCI")
    for tag in [
        TagDef(name="Export Kontrol", color="#ef4444"),
        TagDef(name="Takipte", color="#22c55e"),
        TagDef(name="Öncelikli", color="#2563eb"),
    ]:
        store.upsert_tag_def(tag)
    contract = ContractInfo(no="AKN-TAGS-001", platform="AKINCI", contract_type="Ana Sözleşme")
    store.write_contract(contract, [], {})
    store.save_contract_tags("AKINCI", contract.no, contract.contract_type, ["Export Kontrol", "Öncelikli"])

    assigned = store.load_contract_tags("AKINCI", contract.no, contract.contract_type)
    dlg = TagAssignDialog(store, assigned)
    assert [tag.name for tag in dlg.available_tags] == ["Takipte"]
    assert all(tag.name not in {"Export Kontrol", "Öncelikli"} for tag in dlg.available_tags)
    dlg.close()

    # Newly assigned tags are filtered immediately on the next dialog open.
    store.save_contract_tags("AKINCI", contract.no, contract.contract_type, ["Export Kontrol", "Öncelikli", "Takipte"])
    all_assigned = store.load_contract_tags("AKINCI", contract.no, contract.contract_type)
    full = TagAssignDialog(store, all_assigned)
    assert full.available_tags == []
    assert full.save_btn.isEnabled() is False
    full.close()

    # Removed tags become assignable again because filtering uses current assignments.
    store.save_contract_tags("AKINCI", contract.no, contract.contract_type, ["Export Kontrol", "Takipte"])
    after_remove = store.load_contract_tags("AKINCI", contract.no, contract.contract_type)
    reopened = TagAssignDialog(store, after_remove)
    assert [tag.name for tag in reopened.available_tags] == ["Öncelikli"]
    reopened.close()

    # Store-level duplicate safety is preserved even if duplicate inputs are submitted.
    store.save_contract_tags("AKINCI", contract.no, contract.contract_type, ["Takipte", "Takipte", {"name": "Takipte"}])
    contract_id = store._find_contract_id("AKINCI", contract.no, contract.contract_type)
    assert store.db.conn.execute("SELECT COUNT(*) FROM contract_tags WHERE contract_id=?", (contract_id,)).fetchone()[0] == 1
    store.db.close()

print("ok")
