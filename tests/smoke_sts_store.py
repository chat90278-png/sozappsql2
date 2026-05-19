import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ComponentDef, ContractInfo, TagDef
from src.services.sts_store import STSStore

with TemporaryDirectory() as td:
    p = Path(td) / "smoke.sts"
    store = STSStore(p)

    store.create_platform("AKINCI")
    store.write_users([{"name": "Serhat", "yi_yd": "Yİ", "active": True, "note": ""}])
    store.write_components([ComponentDef(name="GÖVDE", platforms={"AKINCI": True})])

    ci = ContractInfo(no='K1', platform='AKINCI', user='Serhat', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    store.write_contract(ci, [], {})

    store.upsert_tag_def(TagDef(name="Deneme", color="#3B82F6"))

    defs = store.load_tag_defs(active_only=True)
    assert any(t.name == "Deneme" for t in defs)

    tags = store.load_tags(active_only=True)
    assert any(t.name == "Deneme" for t in tags)

    store.save_contract_tags("AKINCI", "K1", "Ana Sözleşme", ["Deneme"])
    ctags = store.load_contract_tags("AKINCI", "K1", "Ana Sözleşme")
    assert any((t.get("name") == "Deneme") for t in ctags)

    tag_map = store.all_contract_tags_map()
    assert ("AKINCI", "K1", "Ana Sözleşme") in tag_map
    assert "Deneme" in tag_map[("AKINCI", "K1", "Ana Sözleşme")]

    idx = store.build_contract_index()
    it = next(x for x in idx if x.get("platform") == "AKINCI" and x.get("no") == "K1")
    assert "Deneme" in list(it.get("tags") or [])

    store.delete_tag_def("Deneme")
    defs2 = store.load_tag_defs(active_only=False)
    assert not any(t.name == "Deneme" for t in defs2)

print("ok")
