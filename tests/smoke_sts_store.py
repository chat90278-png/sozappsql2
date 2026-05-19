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
    store.create_platform("TB2")

    store.write_components([
        ComponentDef(name="GÖVDE", version="", unit="Adet", active=True, usage=1, platforms={"AKINCI": True, "TB2": False}),
        ComponentDef(name="MOTOR", version="", unit="Adet", active=True, usage=1, platforms={"AKINCI": True, "TB2": True}),
    ])

    akinci = store.assigned_components("AKINCI")
    assert "GÖVDE" in akinci and "MOTOR" in akinci

    tb2 = store.assigned_components("TB2")
    assert "MOTOR" in tb2
    assert "GÖVDE" not in tb2

    # no platforms mapping -> fallback should still be safe
    store.write_components([
        {"name": "GÖVDE", "version": "", "unit": "Adet", "active": True, "usage": 1, "platforms": {"AKINCI": True, "TB2": False}},
        {"name": "MOTOR", "version": "", "unit": "Adet", "active": True, "usage": 1, "platforms": {"AKINCI": True, "TB2": True}},
        {"name": "KANAT", "version": "", "unit": "Adet", "active": True, "usage": 1},
    ])
    unknown = store.assigned_components("BILINMEYEN_PLATFORM")
    assert isinstance(unknown, list)
    assert "KANAT" in unknown

    components = store.load_components()
    govde = next((c for c in components if c.name == "GÖVDE"), None)
    assert govde is not None
    assert bool(govde.platforms.get("AKINCI")) is True

    store.upsert_tag_def(TagDef(name="Yeni Etiket", color="#3B82F6"))
    tags = store.load_tags()
    assert any(t.name == "Yeni Etiket" for t in tags)

print("ok")
