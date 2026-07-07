from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any


def _scalar(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        d = Decimal(str(value)).normalize()
        if d == d.to_integral():
            return int(d)
        return float(d)
    if isinstance(value, Decimal):
        d = value.normalize()
        return int(d) if d == d.to_integral() else float(d)
    return str(value)


def normalize_contract_snapshot(data: Any) -> Any:
    if isinstance(data, dict):
        normalized = {str(k): normalize_contract_snapshot(v) for k, v in data.items()}
        for key in ("systems", "deliveries", "folders", "files", "platforms", "users", "responsible_engineers", "tags"):
            if isinstance(normalized.get(key), list):
                normalized[key] = sorted(
                    normalized[key],
                    key=lambda item: (
                        str((item or {}).get("merge_uid") or (item or {}).get("stable_uid") or (item or {}).get("name") or (item or {}).get("key") or "").casefold(),
                        serialize_contract_snapshot(item),
                    ) if isinstance(item, dict) else str(item).casefold(),
                )
        return {k: normalized[k] for k in sorted(normalized)}
    if isinstance(data, (list, tuple)):
        return [normalize_contract_snapshot(v) for v in data]
    return _scalar(data)


def serialize_contract_snapshot(snapshot: Any) -> str:
    return json.dumps(normalize_contract_snapshot(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_contract_snapshot(snapshot: Any) -> str:
    return hashlib.sha256(serialize_contract_snapshot(snapshot).encode("utf-8")).hexdigest()


def build_contract_snapshot(conn, contract_id: int) -> dict:
    cid = int(contract_id or 0)
    contract = conn.execute("SELECT * FROM contracts WHERE id=?", (cid,)).fetchone()
    if not contract:
        return {}
    c = dict(contract)
    snap = {"contract": {k: c.get(k) for k in (
        "merge_uid", "contract_no", "yi_yd", "contract_type", "type_display", "link_type", "status",
        "signed_date", "t0_date", "t0_months", "completion_date", "acceptance_date", "content", "note", "is_main"
    )}}
    snap["platforms"] = [dict(r) for r in conn.execute(
        "SELECT p.name AS stable_uid,p.name,cp.sort_order,cp.is_primary FROM contract_platforms cp JOIN platforms p ON p.id=cp.platform_id WHERE cp.contract_id=?",
        (cid,),
    ).fetchall()]
    snap["users"] = [dict(r) for r in conn.execute(
        "SELECT u.name AS stable_uid,u.name,u.yi_yd FROM contract_users cu JOIN users u ON u.id=cu.user_id WHERE cu.contract_id=?",
        (cid,),
    ).fetchall()]
    snap["responsible_engineers"] = [dict(r) for r in conn.execute(
        "SELECT s.full_name AS stable_uid,s.full_name,cre.sort_order,cre.is_primary FROM contract_responsible_engineers cre JOIN staff s ON s.id=cre.staff_id WHERE cre.contract_id=?",
        (cid,),
    ).fetchall()]
    snap["tags"] = [dict(r) for r in conn.execute(
        "SELECT lower(t.name) AS stable_uid,t.name,t.color,t.kind FROM contract_tags ct JOIN tags t ON t.id=ct.tag_id WHERE ct.contract_id=?",
        (cid,),
    ).fetchall()]
    snap["systems"] = []
    system_uid = {}
    for r in conn.execute("SELECT * FROM systems WHERE contract_id=?", (cid,)).fetchall():
        s = dict(r); system_uid[int(s["id"])] = s.get("merge_uid") or ""
        comps = [dict(x) for x in conn.execute("SELECT c.name,sc.qty,sc.note FROM system_components sc JOIN components c ON c.id=sc.component_id WHERE sc.system_id=?", (s["id"],)).fetchall()]
        snap["systems"].append({"merge_uid": s.get("merge_uid"), "platform_id": s.get("platform_id"), "name": s.get("name"), "status": s.get("status"), "completion_date": s.get("completion_date"), "acceptance_date": s.get("acceptance_date"), "note": s.get("note"), "sort_order": s.get("sort_order"), "payload_json": s.get("payload_json"), "components": sorted(comps, key=lambda x: str(x.get("name") or "").casefold())})
    snap["deliveries"] = []
    for r in conn.execute("SELECT * FROM deliveries WHERE contract_id=?", (cid,)).fetchall():
        d = dict(r)
        comps = [dict(x) for x in conn.execute("SELECT c.name,dc.planned,dc.delivered FROM delivery_components dc JOIN components c ON c.id=dc.component_id WHERE dc.delivery_id=?", (d["id"],)).fetchall()]
        snap["deliveries"].append({"merge_uid": d.get("merge_uid"), "system_merge_uid": system_uid.get(int(d.get("system_id") or 0), ""), "name": d.get("name"), "status": d.get("status"), "planned_acceptance_date": d.get("planned_acceptance_date"), "acceptance_date": d.get("acceptance_date"), "note": d.get("note"), "sort_order": d.get("sort_order"), "payload_json": d.get("payload_json"), "delivery_user_id": d.get("delivery_user_id"), "components": sorted(comps, key=lambda x: str(x.get("name") or "").casefold())})
    folders = [dict(r) for r in conn.execute("SELECT id,merge_uid,parent_id,name FROM contract_file_folders WHERE contract_id=?", (cid,)).fetchall()]
    folder_uid = {int(f["id"]): f.get("merge_uid") or "" for f in folders}
    snap["folders"] = [{"merge_uid": f.get("merge_uid"), "parent_merge_uid": folder_uid.get(int(f.get("parent_id") or 0), ""), "name": f.get("name")} for f in folders]
    snap["files"] = [{"merge_uid": r["merge_uid"], "folder_merge_uid": folder_uid.get(int(r["folder_id"] or 0), ""), "filename": r["filename"], "file_ext": r["file_ext"], "mime_type": r["mime_type"], "size_bytes": r["size_bytes"], "sha256": r["sha256"], "note": r["note"]} for r in conn.execute("SELECT merge_uid,folder_id,filename,file_ext,mime_type,size_bytes,sha256,note FROM contract_files WHERE contract_id=?", (cid,)).fetchall()]
    return normalize_contract_snapshot(snap)
