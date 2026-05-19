from __future__ import annotations
import json
import mimetypes
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo, TagDef
from src.services.sts_database import STSDatabase, now_iso


class STSStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.db = STSDatabase(self.path)

    def current_actor(self) -> str: return "Sistem"
    def save(self): self.db.conn.commit()
    def reload_from_disk(self): self.db.close(); self.db = STSDatabase(self.path)
    @contextmanager
    def batch_save(self):
        with self.db.tx():
            yield
    def flush_pending_styles(self): return 0
    def rebuild_platform_headers(self, *args, **kwargs): return None
    def style_platform_rows(self, *args, **kwargs): return None
    def _normalize_label(self, text: str) -> str: return " ".join(str(text or "").casefold().split())
    def all_sheet_names(self): return self.platform_names()


    def _log(self, action: str, **kwargs):
        self.db.add_log(action=action, **kwargs)

    def list_logs(self, limit=500, action=None, entity_type=None, platform=None, contract_no=None, search=None):
        return self.db.list_logs(limit=limit, action=action, entity_type=entity_type, platform=platform, contract_no=contract_no, search=search)

    def supports_activity_logs(self):
        return True

    def export_to_excel(self, output_path, progress_cb=None):
        import time
        t0 = time.time()
        from src.services.sts_excel_exporter import export_sts_to_excel
        try:
            result = export_sts_to_excel(self.db, output_path, progress_cb=progress_cb)
            self._log("excel_exported", entity_type="export", message="Excel dosyası oluşturuldu", payload=result, actor=self.current_actor())
            return result
        except Exception as exc:
            self._log("excel_export_failed", entity_type="export", message="Excel dışa aktarma hatası", payload={"output_path": str(output_path), "error": str(exc), "duration_sec": round(time.time()-t0,3)}, actor=self.current_actor())
            raise

    def platform_names(self):
        return [r[0] for r in self.db.conn.execute("SELECT name FROM platforms WHERE is_active=1 ORDER BY sort_order,name").fetchall()]
    def create_platform(self, name, logo_source=None):
        nm = str(name or "").strip()
        if not nm:
            return
        ts = now_iso()
        self.db.conn.execute("INSERT OR IGNORE INTO platforms(name,display_name,created_at,updated_at) VALUES(?,?,?,?)", (nm, nm, ts, ts))
        self.db.conn.commit()
        self._log("platform_created", entity_type="platform", entity_key=nm, platform=nm, message=f"Platform oluşturuldu: {nm}")
        if logo_source:
            raw = Path(logo_source).read_bytes()
            ext = Path(logo_source).suffix.lower().lstrip('.')
            self.set_platform_logo_bytes(nm, raw, ext=ext)

    def delete_platform(self, name):
        nm = str(name or "").strip()
        self.db.conn.execute("DELETE FROM platforms WHERE name=?", (nm,)); self.db.conn.commit()
        self._log("platform_deleted", entity_type="platform", entity_key=nm, platform=nm, message=f"Platform silindi: {nm}")
    def load_excluded_platforms(self):
        return [r[0] for r in self.db.conn.execute("SELECT name FROM platforms WHERE is_excluded=1").fetchall()]
    def save_excluded_platforms(self, excluded):
        ex = set(excluded or [])
        for p in self.platform_names() + list(ex):
            self.db.conn.execute("UPDATE platforms SET is_excluded=? WHERE name=?", (1 if p in ex else 0, p))
        self.db.conn.commit()
        self._log("platform_exclusions_updated", entity_type="platform", message="Platform dışlamaları güncellendi", payload={"excluded": sorted(list(ex))})
    def get_platform_logo_bytes(self, platform):
        r=self.db.conn.execute("SELECT logo_blob FROM platforms WHERE name=?",(platform,)).fetchone(); return r[0] if r else None
    def set_platform_logo_bytes(self, platform, data, ext=None):
        raw = bytes(data or b"")
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Logo dosyası 2 MB üstünde olamaz.")
        extv = str(ext or "").lower().strip().lstrip('.')
        if extv and extv not in {"png", "jpg", "jpeg", "bmp", "webp", "svg"}:
            extv = ""
        mime = mimetypes.types_map.get(f".{extv}", "application/octet-stream") if extv else "application/octet-stream"
        ts = now_iso()
        self.db.conn.execute("UPDATE platforms SET logo_blob=?,logo_ext=?,logo_mime=?,logo_updated_at=?,updated_at=? WHERE name=?", (raw, extv or None, mime, ts, ts, platform))
        self.db.conn.commit()
        self._log("platform_logo_updated", entity_type="platform", entity_key=str(platform or ""), platform=str(platform or ""), message="Platform logosu güncellendi", payload={"ext": extv, "size": len(raw)})

    def load_users(self, active_only=True):
        q="SELECT name,yi_yd,active,note FROM users"+(" WHERE active=1" if active_only else "")+" ORDER BY name"
        return [{"name":r[0],"yi_yd":r[1] or "Yİ","active":bool(r[2]),"note":r[3] or ""} for r in self.db.conn.execute(q)]
    def write_users(self, users_payload, actor=None):
        ts = now_iso()
        rows = []
        seen = set()
        for u in list(users_payload or []):
            name = str((u.get("name") if isinstance(u, dict) else getattr(u, "name", "")) or "").strip()
            if not name:
                continue
            key = self._normalize_label(name)
            if key in seen:
                continue
            seen.add(key)
            yi_yd = str((u.get("yi_yd") if isinstance(u, dict) else getattr(u, "yi_yd", "Yİ")) or "Yİ").strip().upper()
            yi_yd = "YD" if yi_yd == "YD" else "Yİ"
            active_val = (u.get("active") if isinstance(u, dict) else getattr(u, "active", True))
            active = 1 if bool(active_val) else 0
            note = str((u.get("note") if isinstance(u, dict) else getattr(u, "note", "")) or "")
            rows.append((name, yi_yd, active, note, ts, ts))
        with self.db.tx():
            self.db.conn.execute("DELETE FROM users")
            for row in rows:
                self.db.conn.execute("INSERT INTO users(name,yi_yd,active,note,created_at,updated_at) VALUES(?,?,?,?,?,?)", row)
        self._log("users_updated", entity_type="user", message="Kullanıcı listesi güncellendi", payload={"count": len(rows)}, actor=actor or self.current_actor())

    def load_components(self):
        out=[]
        for r in self.db.conn.execute("SELECT id,name,version,unit,active,usage FROM components ORDER BY name"):
            plats={x[0]:bool(x[1]) for x in self.db.conn.execute("SELECT platform_name,enabled FROM component_platforms WHERE component_id=?",(r[0],))}
            out.append(ComponentDef(name=r[1],version=r[2] or "",unit=r[3] or "Adet",active=bool(r[4]),usage=int(r[5] or 1),platforms=plats))
        return out
    def write_components(self, components_payload, actor=None):
        ts = now_iso()
        normalized = []
        seen = set()
        for c in list(components_payload or []):
            name = str((c.get("name") if isinstance(c, dict) else getattr(c, "name", "")) or "").strip()
            if not name:
                continue
            key = self._normalize_label(name)
            if key in seen:
                continue
            seen.add(key)
            version = str((c.get("version") if isinstance(c, dict) else getattr(c, "version", "")) or "")
            unit = str((c.get("unit") if isinstance(c, dict) else getattr(c, "unit", "Adet")) or "Adet")
            active = 1 if bool((c.get("active") if isinstance(c, dict) else getattr(c, "active", True))) else 0
            usage = float((c.get("usage") if isinstance(c, dict) else getattr(c, "usage", 1)) or 1)
            platforms = dict((c.get("platforms") if isinstance(c, dict) else getattr(c, "platforms", {})) or {})
            normalized.append((name, version, unit, active, usage, platforms))
        with self.db.tx():
            self.db.conn.execute("DELETE FROM component_platforms")
            self.db.conn.execute("DELETE FROM components")
            for name, version, unit, active, usage, platforms in normalized:
                self.db.conn.execute("INSERT INTO components(name,version,unit,active,usage,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(name,version,unit,active,usage,ts,ts))
                cid = self.db.conn.execute("SELECT id FROM components WHERE name=?", (name,)).fetchone()[0]
                for p, en in platforms.items():
                    if not str(p).strip():
                        continue
                    self.db.conn.execute("INSERT INTO component_platforms(component_id,platform_name,enabled) VALUES(?,?,?)", (cid, str(p).strip(), 1 if bool(en) else 0))
        self._log("components_updated", entity_type="component", message="Bileşen listesi güncellendi", payload={"count": len(normalized)}, actor=actor or self.current_actor())


    def assigned_components(self, platform: str) -> List[str]:
        p = str(platform or "").strip()
        rows = []
        if p:
            rows = self.db.conn.execute(
                """
                SELECT DISTINCT c.name
                FROM components c
                JOIN component_platforms cp ON cp.component_id = c.id
                WHERE c.active = 1
                  AND cp.platform_name = ?
                  AND cp.enabled = 1
                ORDER BY c.name ASC
                """,
                (p,),
            ).fetchall()
        if rows:
            return [str(r[0]) for r in rows if str(r[0] or "").strip()]
        fb = self.db.conn.execute(
            "SELECT DISTINCT name FROM components WHERE active = 1 ORDER BY name ASC"
        ).fetchall()
        return [str(r[0]) for r in fb if str(r[0] or "").strip()]

    def _tag_name_of(self, tag) -> str:
        if isinstance(tag, str):
            return str(tag).strip()
        if isinstance(tag, dict):
            return str(tag.get("name") or "").strip()
        return str(getattr(tag, "name", "") or "").strip()

    def load_tags(self, active_only: bool = True):
        rows = self.db.conn.execute(
            "SELECT DISTINCT name, color, kind FROM tags WHERE COALESCE(name, '') <> '' ORDER BY name"
        ).fetchall()
        out: List[TagDef] = []
        for r in rows:
            out.append(TagDef(name=str(r[0]).strip(), color=str(r[1] or "#3B82F6").strip() or "#3B82F6", note="", active=True))
        return out

    def load_tag_defs(self, active_only: bool = True):
        return self.load_tags(active_only=active_only)

    def write_tags(self, tags, actor=None):
        ts = now_iso()
        with self.db.tx():
            self.db.conn.execute("DELETE FROM tags")
            seen = set()
            for t in list(tags or []):
                name = self._tag_name_of(t)
                if not name:
                    continue
                key = self._normalize_label(name)
                if key in seen:
                    continue
                seen.add(key)
                color = str((t.get("color") if isinstance(t, dict) else getattr(t, "color", "#3B82F6")) or "#3B82F6")
                kind = str((t.get("kind") if isinstance(t, dict) else getattr(t, "kind", "contract")) or "contract")
                self.db.conn.execute(
                    "INSERT INTO tags(name,color,kind,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (name, color, kind, ts, ts),
                )

    write_tag_defs = write_tags

    def upsert_tag_def(self, tag):
        ts = now_iso()
        name = self._tag_name_of(tag)
        if not name:
            return
        color = str((tag.get("color") if isinstance(tag, dict) else getattr(tag, "color", "#3B82F6")) or "#3B82F6")
        kind = str((tag.get("kind") if isinstance(tag, dict) else getattr(tag, "kind", "contract")) or "contract")
        row = self.db.conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        with self.db.tx():
            if row:
                self.db.conn.execute("UPDATE tags SET color=?, kind=?, updated_at=? WHERE id=?", (color, kind, ts, row[0]))
            else:
                self.db.conn.execute("INSERT INTO tags(name,color,kind,created_at,updated_at) VALUES(?,?,?,?,?)", (name, color, kind, ts, ts))
        self._log("tag_upserted", entity_type="tag", entity_key=name, message="Etiket güncellendi", actor=getattr(self, "current_actor", lambda: "Sistem")())

    def delete_tag_def(self, tag_or_name):
        nm = self._tag_name_of(tag_or_name)
        if not nm:
            return
        with self.db.tx():
            self.db.conn.execute("DELETE FROM tags WHERE name=?", (nm,))
            self.db.conn.execute("DELETE FROM contract_tags WHERE tag_name=?", (nm,))
        self._log("tag_deleted", entity_type="tag", entity_key=nm, message="Etiket silindi")

    def load_tag_snapshot(self):
        return self.load_tag_defs(active_only=False), self.all_contract_tags_map()

    def write_tag_snapshot(self, tags, assignments_by_key, actor=None):
        self.write_tags(tags, actor=actor)
        for key, vals in (assignments_by_key or {}).items():
            p, no, ctype = key if isinstance(key, tuple) else key.split("|")
            self.save_contract_tags(p, no, ctype, vals or [], actor=actor)
        self._log("tag_snapshot_updated", entity_type="tag", message="Etiket snapshot güncellendi", actor=actor or self.current_actor())

    def all_contract_tags_map(self):
        out = {}
        rows = self.db.conn.execute(
            "SELECT c.platform,c.contract_no,c.contract_type,t.tag_name FROM contract_tags t JOIN contracts c ON c.id=t.contract_id ORDER BY c.platform,c.contract_no,c.contract_type,t.tag_name"
        ).fetchall()
        for r in rows:
            out.setdefault((str(r[0] or ""), str(r[1] or ""), str(r[2] or "")), []).append(str(r[3] or ""))
        return out

    def _find_contract_id(self, platform, contract_no, contract_type):
        p = str(platform or "").strip()
        no = str(contract_no or "").strip()
        ct = str(contract_type or "").strip()
        row = None
        if ct:
            row = self.db.conn.execute(
                "SELECT id FROM contracts WHERE platform=? AND contract_no=? AND contract_type=? ORDER BY id LIMIT 1",
                (p, no, ct),
            ).fetchone()
        if not row:
            row = self.db.conn.execute(
                "SELECT id FROM contracts WHERE platform=? AND contract_no=? ORDER BY id LIMIT 1",
                (p, no),
            ).fetchone()
        return int(row[0]) if row else 0

    def load_contract_tags(self, platform, contract_no, contract_type):
        cid = self._find_contract_id(platform, contract_no, contract_type)
        if not cid:
            return []
        rows = self.db.conn.execute(
            "SELECT ct.tag_name, t.color, t.kind FROM contract_tags ct LEFT JOIN tags t ON t.name=ct.tag_name WHERE ct.contract_id=? ORDER BY ct.tag_name",
            (cid,),
        ).fetchall()
        out = []
        for r in rows:
            name = str(r[0] or "").strip()
            if not name:
                continue
            out.append({"name": name, "color": str(r[1] or "#3B82F6"), "kind": str(r[2] or "contract")})
        return out

    def save_contract_tags(self, platform, contract_no, contract_type, tags, actor=None):
        cid = self._find_contract_id(platform, contract_no, contract_type)
        if not cid:
            return
        names = []
        seen = set()
        for t in list(tags or []):
            nm = self._tag_name_of(t)
            if not nm:
                continue
            key = self._normalize_label(nm)
            if key in seen:
                continue
            seen.add(key)
            names.append((nm, t))
        ts = now_iso()
        with self.db.tx():
            self.db.conn.execute("DELETE FROM contract_tags WHERE contract_id=?", (cid,))
            for nm, t in names:
                row = self.db.conn.execute("SELECT id FROM tags WHERE name=?", (nm,)).fetchone()
                if not row:
                    color = str((t.get("color") if isinstance(t, dict) else getattr(t, "color", "#3B82F6")) or "#3B82F6")
                    kind = str((t.get("kind") if isinstance(t, dict) else getattr(t, "kind", "contract")) or "contract")
                    self.db.conn.execute("INSERT INTO tags(name,color,kind,created_at,updated_at) VALUES(?,?,?,?,?)", (nm, color, kind, ts, ts))
                self.db.conn.execute("INSERT OR IGNORE INTO contract_tags(contract_id,tag_name) VALUES(?,?)", (cid, nm))
        self._log("contract_tags_updated", entity_type="contract", entity_id=cid, platform=str(platform or ""), contract_no=str(contract_no or ""), message="Sözleşme etiketleri güncellendi", payload={"count": len(names)}, actor=actor or self.current_actor())

    def list_main_contracts(self, platform, tags_map=None):
        rows=[]; tags_map = tags_map or self.all_contract_tags_map()
        for r in self.db.conn.execute("SELECT * FROM contracts WHERE platform=? ORDER BY id",(platform,)):
            tags=tags_map.get((r['platform'],r['contract_no'],r['contract_type']),[])
            rows.append({"id":r["id"],"row":r["id"],"platform":r["platform"],"no":r["contract_no"],"user":r["user_name"],"type":r["contract_type"],"type_display":r["type_display"],"link":r["link_type"],"status":r["status"],"completion_date":r["completion_date"],"content":r["content"] or r["note"] or "","is_main":bool(r["is_main"]),"tags":list(tags),"search":r["search_text"] or ""})
        return rows
    def build_contract_index(self, progress_cb=None):
        out=[]; tags=self.all_contract_tags_map()
        for p in self.platform_names(): out.extend(self.list_main_contracts(p,tags_map=tags))
        return out
    def find_main_contract_info(self, platform, contract_no):
        r=self.db.conn.execute("SELECT * FROM contracts WHERE platform=? AND contract_no=? AND is_main=1 LIMIT 1",(platform,contract_no)).fetchone()
        return dict(r) if r else None
    def next_sd_code(self, platform, contract_no):
        c=self.db.conn.execute("SELECT COUNT(*) FROM contracts WHERE platform=? AND contract_no=?",(platform,contract_no)).fetchone()[0]
        return f"SD-{int(c)+1:03d}"

    def write_contract(self, ci, systems, deliveries, old_contract_no=None, old_start_row=None):
        ts=now_iso(); ctype=ci.contract_type
        row=self.db.conn.execute("SELECT id FROM contracts WHERE platform=? AND contract_no=? AND contract_type=?",(ci.platform,ci.no,ctype)).fetchone()
        with self.db.tx():
            if row:
                cid=row[0]
                self.db.conn.execute("UPDATE contracts SET user_name=?,yi_yd=?,status=?,signed_date=?,t0_date=?,t0_months=?,completion_date=?,acceptance_date=?,note=?,content=?,updated_at=? WHERE id=?",(ci.user,ci.yi_yd,ci.status,ci.signature_date,ci.t0_date,int(ci.t0_months or 0),ci.completion_date,ci.acceptance_date,ci.note,ci.note,ts,cid))
                self.db.conn.execute("DELETE FROM systems WHERE contract_id=?",(cid,)); self.db.conn.execute("DELETE FROM deliveries WHERE contract_id=?",(cid,))
            else:
                self.db.conn.execute("INSERT INTO contracts(platform,contract_no,user_name,yi_yd,contract_type,type_display,link_type,status,signed_date,t0_date,t0_months,completion_date,acceptance_date,content,note,is_main,parent_contract_no,search_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ci.platform,ci.no,ci.user,ci.yi_yd,ctype,ctype,"",ci.status,ci.signature_date,ci.t0_date,int(ci.t0_months or 0),ci.completion_date,ci.acceptance_date,ci.note,ci.note,1 if self._normalize_label(ctype)==self._normalize_label('Ana Sözleşme') else 0,ci.sd_anchor_no,"",ts,ts))
                cid=self.db.conn.execute("SELECT id FROM contracts WHERE platform=? AND contract_no=? AND contract_type=?",(ci.platform,ci.no,ctype)).fetchone()[0]
            existing_tags=[r[0] for r in self.db.conn.execute("SELECT tag_name FROM contract_tags WHERE contract_id=?",(cid,))]
            for i,s in enumerate(systems or []):
                self.db.conn.execute("INSERT INTO systems(contract_id,name,status,completion_date,acceptance_date,note,sort_order,payload_json) VALUES(?,?,?,?,?,?,?,?)",(cid,s.name,s.status,s.completion_date,s.acceptance_date,"",i,json.dumps({"t0_date":s.t0_date,"t0_months":s.t0_months})))
                sid=self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                for cname,qty in (s.components or {}).items(): self.db.conn.execute("INSERT INTO system_components(system_id,component_name,qty) VALUES(?,?,?)",(sid,cname,float(qty or 0)))
            for sys_name, dlist in (deliveries or {}).items():
                for i,d in enumerate(dlist or []):
                    self.db.conn.execute("INSERT INTO deliveries(contract_id,system_name,name,status,acceptance_date,note,sort_order,payload_json) VALUES(?,?,?,?,?,?,?,?)",(cid,sys_name,d.name,d.status,d.acceptance_date,d.note,i,json.dumps({"t0_date":d.t0_date,"t0_months":d.t0_months,"completion_date":d.completion_date})))
                    did=self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    for cname,p in (d.planned or {}).items():
                        self.db.conn.execute("INSERT INTO delivery_components(delivery_id,component_name,planned,delivered) VALUES(?,?,?,?)",(did,cname,float(p or 0),float((d.delivered or {}).get(cname,0) or 0)))
            self.db.conn.execute("DELETE FROM contract_tags WHERE contract_id=?",(cid,))
            for t in existing_tags: self.db.conn.execute("INSERT INTO contract_tags(contract_id,tag_name) VALUES(?,?)",(cid,t))
        self._log("contract_updated" if row else "contract_created", entity_type="contract", entity_id=cid, platform=str(ci.platform or ""), contract_no=str(ci.no or ""), payload={"system_count": len(systems or []), "delivery_count": sum(len(v or []) for v in (deliveries or {}).values()), "component_count": sum(len((x.components or {})) for x in (systems or []))}, actor=self.current_actor())
        return cid

    def load_contract_structure(self, platform, contract_no, start_row=None):
        r=self.db.conn.execute("SELECT * FROM contracts WHERE platform=? AND contract_no=? ORDER BY id LIMIT 1",(platform,contract_no)).fetchone()
        if not r: raise ValueError("contract not found")
        ci=ContractInfo(no=r['contract_no'],platform=r['platform'],user=r['user_name'] or "",yi_yd=r['yi_yd'] or "Yİ",contract_type=r['contract_type'] or "",signature_date=r['signed_date'] or "",t0_date=r['t0_date'] or "",t0_months=int(r['t0_months'] or 0),completion_date=r['completion_date'] or "",status=r['status'] or "PLAN",note=r['note'] or "",acceptance_date=r['acceptance_date'] or "",entry_start_row=int(r['id']))
        systems=[]; deliveries={}
        for s in self.db.conn.execute("SELECT * FROM systems WHERE contract_id=? ORDER BY sort_order,id",(r['id'],)):
            comps={x[0]:float(x[1] or 0) for x in self.db.conn.execute("SELECT component_name,qty FROM system_components WHERE system_id=?",(s['id'],))}
            payload=json.loads(s['payload_json'] or "{}")
            si=SystemInfo(name=s['name'],components=comps,t0_date=payload.get('t0_date',''),t0_months=int(payload.get('t0_months',0) or 0),completion_date=s['completion_date'] or "",status=s['status'] or "Başlanmadı",acceptance_date=s['acceptance_date'] or "")
            systems.append(si)
        for d in self.db.conn.execute("SELECT * FROM deliveries WHERE contract_id=? ORDER BY system_name,sort_order,id",(r['id'],)):
            payload=json.loads(d['payload_json'] or "{}")
            rows=self.db.conn.execute("SELECT component_name,planned,delivered FROM delivery_components WHERE delivery_id=?",(d['id'],)).fetchall()
            planned={x[0]:float(x[1] or 0) for x in rows}; delivered={x[0]:float(x[2] or 0) for x in rows}
            di=DeliveryInfo(name=d['name'],status=d['status'] or "",acceptance_date=d['acceptance_date'] or "",note=d['note'] or "",planned=planned,delivered=delivered,t0_date=payload.get('t0_date',''),t0_months=int(payload.get('t0_months',0) or 0),completion_date=payload.get('completion_date',''))
            deliveries.setdefault(d['system_name'],[]).append(di)
        return ci, systems, deliveries

    def delete_contract(self, platform, contract_no, start_row=None, actor=None, progress_cb=None):
        row=self.db.conn.execute("SELECT id FROM contracts WHERE platform=? AND contract_no=? ORDER BY id LIMIT 1",(platform,contract_no)).fetchone()
        if not row: return {"platform":platform,"contract_no":contract_no,"start_row":0,"end_row":0,"deleted_rows":0}
        cid=row[0]; self.db.conn.execute("DELETE FROM contracts WHERE id=?",(cid,)); self.db.conn.commit()
        self._log("contract_deleted", entity_type="contract", entity_id=cid, platform=str(platform or ""), contract_no=str(contract_no or ""), actor=actor or self.current_actor())
        return {"platform":platform,"contract_no":contract_no,"start_row":cid,"end_row":cid,"deleted_rows":1}
