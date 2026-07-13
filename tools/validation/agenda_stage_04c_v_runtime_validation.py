from __future__ import annotations
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE_COMMIT = "522e5d15bd103a881f7cf43dd24c7822dc90148f"
VALIDATOR_PATH = "tools/validation/agenda_stage_04c_v_runtime_validation.py"

source = subprocess.check_output(
    ["git", "show", f"{SOURCE_COMMIT}:{VALIDATOR_PATH}"],
    text=True,
    encoding="utf-8",
)

old_seed = '''bad=[ac(c,cid=C["a"],action=x)for x in("contract_created","system_updated","delivery_updated","bad")]+[ac(c,cid=C["a"],etype="system"),ac(c,cid=C["a"],eid=""),ac(c,cid=C["a"],eid="abc"),ac(c,cid=C["a"],eid=f"{C['a']}x"),ac(c,cid=C["a"],eid=f"0{C['a']}"),ac(c,cid=C["out"]),ac(c,cid=C["a"],rb="",ra="{}"),ac(c,cid=C["a"],rb="{bad",ra="{}"),ac(c,cid=C["a"],rb="[]",ra="{}"),ac(c,cid=C["a"],rb="{}",ra="1"),ac(c,cid=C["a"],before={"completion_date":" x "},after={"completion_date":"x"}),ac(c,cid=C["a"],before={"completion_date":{"a":1}},after={"completion_date":{"a":2}})]'''
new_seed = '''bad=[ac(c,cid=C["a"],action=x)for x in("contract_created","system_updated","delivery_updated","bad")]+[ac(c,cid=C["a"],etype="system"),ac(c,cid=C["a"],eid=""),ac(c,cid=C["a"],eid="abc"),ac(c,cid=C["a"],eid=f"{C['a']}x"),ac(c,cid=C["a"],eid=f"0{C['a']}"),ac(c,cid=C["out"]),ac(c,cid=C["a"],rb="",ra="{}"),ac(c,cid=C["a"],rb="{bad",ra="{}"),ac(c,cid=C["a"],rb="[]",ra="{}"),ac(c,cid=C["a"],rb="{}",ra="1")]
    L["equal"]=ac(c,cid=C["a"],before={"completion_date":" x "},after={"completion_date":"x"})
    L["nested"]=ac(c,cid=C["a"],before={"completion_date":{"a":1}},after={"completion_date":{"a":2}})
    L["status_in_update"]=ac(c,cid=C["a"],before={"completion_date":"same","acceptance_date":"same","status":"Açık"},after={"completion_date":"same","acceptance_date":"same","status":"Kapalı"})'''
old_need = 'need={L[x]for x in("up","sa","sb","new","7n","7","7o","inv","t1","t2")}'
new_need = 'need={L[x]for x in("up","sa","sb","equal","nested","status_in_update","new","7n","7","7o","inv","t1","t2")}'
old_fields = 'q({f for(l,f)in by if l==L["up"]}=={"completion_date","acceptance_date"}and{f for(l,f)in by if l==L["sa"]}=={"status"},"fields")'
new_fields = 'q({f for(l,f)in by if l==L["up"]}=={"completion_date","acceptance_date"}and{f for(l,f)in by if l==L["sa"]}=={"status"}and not any(l in {L["equal"],L["nested"],L["status_in_update"]}for(l,f)in by),"fields")'

for old, new, label in (
    (old_seed, new_seed, "seed boundary"),
    (old_need, new_need, "repository accepted set"),
    (old_fields, new_fields, "provider exclusions"),
):
    if source.count(old) != 1:
        raise RuntimeError(f"Unable to patch {label}: expected one exact match.")
    source = source.replace(old, new, 1)

with tempfile.TemporaryDirectory() as td:
    patched = Path(td) / "agenda_stage_04c_v_runtime_validation_patched.py"
    patched.write_text(source, encoding="utf-8")
    raise SystemExit(subprocess.call([sys.executable, str(patched), *sys.argv[1:]]))
