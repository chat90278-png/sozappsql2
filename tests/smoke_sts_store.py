import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ComponentDef, TagDef
from src.services.sts_store import STSStore

with TemporaryDirectory() as td:
    p = Path(td) / "smoke.sts"
    store = STSStore(p)

    store.create_platform("AKINCI")

    store.write_users([
        {"name": "Serhat", "yi_yd": "Yİ", "active": True, "note": ""}
    ])
    users = store.load_users(active_only=False)
    assert any(u.get("name") == "Serhat" for u in users)

    store.write_components([
        ComponentDef(
            name="GÖVDE",
            version="",
            unit="Adet",
            active=True,
            usage=1,
            platforms={"AKINCI": True},
        )
    ])
    components = store.load_components()
    govde = next((c for c in components if c.name == "GÖVDE"), None)
    assert govde is not None
    assert bool(govde.platforms.get("AKINCI")) is True

    store.upsert_tag_def(TagDef(name="Yeni Etiket", color="#3B82F6"))
    tags = store.load_tags()
    assert any(t.name == "Yeni Etiket" for t in tags)

    snap_tags, snap_map = store.load_tag_snapshot()
    assert isinstance(snap_tags, list)
    assert isinstance(snap_map, dict)

print("ok")
