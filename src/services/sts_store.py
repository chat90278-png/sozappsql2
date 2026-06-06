from __future__ import annotations
import json
import mimetypes
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo, TagDef
from src.services.sts_database import STSDatabase, now_iso
from src import auth


class STSStore:
    def __init__(self, path: Path | str, actor: str = "Kullanıcı", source: str = "Main UI"):
        self.path = Path(path)
        self.actor = str(actor or "Kullanıcı")
        self.source = str(source or "Main UI")
        self.db = STSDatabase(self.path, source=self.source)
        self._id_cache = {"platform": {}, "component": {}, "user": {}, "tag": {}}

    def current_actor(self) -> str: return self.actor
    def save(self): self.db.conn.commit()
    def reload_from_disk(self):
        self.db.close(); self.db = STSDatabase(self.path, source=self.source)
        self._clear_id_cache()
    @contextmanager
    def batch_save(self):
        with self.db.tx():
            yield
    def flush_pending_styles(self): return 0
    def rebuild_platform_headers(self, *args, **kwargs): return None
    def style_platform_rows(self, *args, **kwargs): return None
    def _normalize_label(self, text: str) -> str: return " ".join(str(text or "").casefold().split())
    def all_sheet_names(self): return self.platform_names()

    def _clear_id_cache(self, kind=None):
        if kind:
            self._id_cache[kind].clear()
        else:
            for cache in self._id_cache.values():
                cache.clear()

    def _get_named_id(self, kind, table, name, create=False):
        clean = str(name or "").strip()
        if not clean:
            return None
        cache = self._id_cache[kind]
        if clean in cache:
            return cache[clean]
        row = self.db.conn.execute(f"SELECT id FROM {table} WHERE name=?", (clean,)).fetchone()
        if not row and create:
            ts = now_iso()
            self.db.conn.execute(f"INSERT INTO {table}(name,created_at,updated_at) VALUES(?,?,?)", (clean, ts, ts))
            row = self.db.conn.execute(f"SELECT id FROM {table} WHERE name=?", (clean,)).fetchone()
        value = int(row[0]) if row else None
        if value is not None:
            cache[clean] = value
        return value

    def get_platform_id(self, name, create=False):
        return self._get_named_id("platform", "platforms", name, create=create)

    def get_component_id(self, name, create=False):
        return self._get_named_id("component", "components", name, create=create)

    def get_user_id(self, name, create=False):
        return self._get_named_id("user", "users", name, create=create)

    def get_tag_id(self, name, create=False):
        return self._get_named_id("tag", "tags", name, create=create)

    def _decode_user_names(self, raw, fallback="") -> List[str]:
        values: List[str] = []
        if isinstance(raw, list):
            values = [str(x or "").strip() for x in raw]
        elif raw is not None:
            txt = str(raw).strip()
            if txt:
                try:
                    parsed = json.loads(txt)
                    if isinstance(parsed, list):
                        values = [str(x or "").strip() for x in parsed]
                    else:
                        values = [x.strip() for x in txt.split(",")]
                except Exception:
                    values = [x.strip() for x in txt.split(",")]
        if not values:
            f = str(fallback or "").strip()
            values = [f] if f else []
        out: List[str] = []
        seen = set()
        for v in values:
            if not v:
                continue
            k = self._normalize_label(v)
            if k in seen:
                continue
            seen.add(k)
            out.append(v)
        return out

    def _encode_user_names(self, users) -> str:
        clean = self._decode_user_names(list(users or []))
        return json.dumps(clean, ensure_ascii=False)

    def _user_display(self, users, fallback="") -> str:
        clean = self._decode_user_names(list(users or []), fallback=fallback)
        if clean:
            return ", ".join(clean)
        return str(fallback or "").strip()


    def _log(self, action: str, **kwargs):
        self.db.add_log(action=action, **kwargs)

    def list_logs(self, limit=500, action=None, entity_type=None, platform=None, contract_no=None, search=None):
        return self.db.list_logs(limit=limit, action=action, entity_type=entity_type, platform=platform, contract_no=contract_no, search=search)


    def document_lock_state(self):
        return auth.get_document_lock_state(self.db.conn)

    def lock_documents(self, current_staff):
        state = auth.lock_documents(self.db.conn, current_staff or {})
        self._log(
            "documents_locked",
            entity_type="document_lock",
            source="Document Manager",
            message="Belgeler kilitlendi",
            payload={"locked_by_staff_id": (current_staff or {}).get("id"), "locked_by_device_name": (current_staff or {}).get("device_name")},
            actor=str((current_staff or {}).get("full_name") or self.current_actor()),
        )
        return state

    def unlock_documents(self, actor=None):
        state = auth.unlock_documents(self.db.conn)
        self._log(
            "documents_unlocked",
            entity_type="document_lock",
            source="Document Manager",
            message="Belgeler kilidi açıldı",
            actor=str(actor or self.current_actor()),
        )
        return state

    def supports_activity_logs(self):
        return True



    def performance_stats(self):
        return self.db.performance_stats()

    def recent_performance_logs(self, limit=100):
        return self.db.recent_performance_logs(limit=limit)

    def add_performance_log(self, metric, duration_ms=None, duration_sec=None, payload=None):
        return self.db.add_performance_log(metric, duration_ms=duration_ms, duration_sec=duration_sec, payload=payload)

    def supports_performance_tracking(self):
        return True

    def database_stats(self):
        return self.db.database_stats()

    def integrity_check(self):
        return self.db.integrity_check()

    def foreign_key_check(self):
        return self.db.foreign_key_check()

    def vacuum(self):
        res = self.db.vacuum()
        self._log("database_vacuum_completed", entity_type="database", source="Database Manager", payload=res)
        return res

    def optimize(self):
        res = self.db.optimize()
        self._log("database_optimize_completed", entity_type="database", source="Database Manager", payload=res)
        return res

    def backup_database(self, target_path):
        res = self.db.backup_to(target_path)
        self._log("database_backup_created", entity_type="database", source="Database Manager", message="Veritabanı yedeği oluşturuldu", payload=res)
        return res

    def supports_database_management(self):
        return True

    def preview_table(self, table_name, limit=100):
        return self.db.preview_table(table_name, limit)

    def export_to_excel(self, output_path, options=None, progress_cb=None):
        import time
        t0 = time.time()
        from src.services.sts_excel_exporter import export_sts_to_excel
        try:
            result = export_sts_to_excel(self.db, output_path, options=options, progress_cb=progress_cb)
            payload = dict(result or {})
            payload["options"] = options or {}
            self._log("excel_exported", entity_type="export", message="Excel dosyası oluşturuldu", payload=payload, actor=self.current_actor())
            return result
        except Exception as exc:
            self._log("excel_export_failed", entity_type="export", message="Excel dışa aktarma hatası", payload={"output_path": str(output_path), "error": str(exc), "duration_sec": round(time.time()-t0,3), "options": options or {}}, actor=self.current_actor())
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
        self._clear_id_cache("platform")
        self._log("platform_created", entity_type="platform", entity_key=nm, platform=nm, message=f"Platform oluşturuldu: {nm}")
        if logo_source:
            raw = Path(logo_source).read_bytes()
            ext = Path(logo_source).suffix.lower().lstrip('.')
            self.set_platform_logo_bytes(nm, raw, ext=ext)

    def delete_platform(self, name):
        nm = str(name or "").strip()
        self.db.conn.execute("DELETE FROM platforms WHERE name=?", (nm,)); self.db.conn.commit()
        self._clear_id_cache("platform")
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
        before_users = {str(row["name"]): {"yi_yd": row["yi_yd"] or "Yİ", "active": bool(row["active"]), "note": row["note"] or ""} for row in self.db.conn.execute("SELECT name,yi_yd,active,note FROM users")}
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
            keep = []
            for row in rows:
                self.db.conn.execute("INSERT INTO users(name,yi_yd,active,note,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET yi_yd=excluded.yi_yd,active=excluded.active,note=excluded.note,updated_at=excluded.updated_at", row)
                keep.append(row[0])
            if keep:
                marks = ",".join("?" for _ in keep)
                self.db.conn.execute(f"DELETE FROM users WHERE name NOT IN ({marks})", keep)
            else:
                self.db.conn.execute("DELETE FROM users")
        self._clear_id_cache("user")
        audit_actor = actor or self.current_actor()
        after_users = {name: {"yi_yd": yi_yd, "active": bool(active), "note": note} for name, yi_yd, active, note, _created, _updated in rows}
        for name in sorted(set(before_users) | set(after_users)):
            before_user, after_user = before_users.get(name), after_users.get(name)
            action = "user_created" if before_user is None else ("user_deleted" if after_user is None else ("user_updated" if before_user != after_user else ""))
            if action:
                self._log(action, entity_type="user", entity_key=name, source="Main UI", message={"user_created": "Kullanıcı eklendi", "user_updated": "Kullanıcı güncellendi", "user_deleted": "Kullanıcı silindi"}[action], before=before_user, after=after_user, actor=audit_actor)
        self._log("users_updated", entity_type="user", message="Kullanıcı listesi güncellendi", payload={"count": len(rows)}, actor=audit_actor)

    def load_components(self):
        out=[]
        for r in self.db.conn.execute("SELECT id,name,version,unit,active,usage FROM components ORDER BY name"):
            plats={x[0]:bool(x[1]) for x in self.db.conn.execute("SELECT p.name,cp.enabled FROM component_platforms cp JOIN platforms p ON p.id=cp.platform_id WHERE cp.component_id=?",(r[0],))}
            out.append(ComponentDef(name=r[1],version=r[2] or "",unit=r[3] or "Adet",active=bool(r[4]),usage=int(r[5] or 1),platforms=plats))
        return out
    def write_components(self, components_payload, actor=None):
        ts = now_iso()
        before_components = {str(row["name"]): {"version": row["version"] or "", "unit": row["unit"] or "Adet", "active": bool(row["active"]), "usage": float(row["usage"] or 1)} for row in self.db.conn.execute("SELECT name,version,unit,active,usage FROM components")}
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
        self._clear_id_cache("component")
        with self.db.tx():
            keep = []
            for name, version, unit, active, usage, platforms in normalized:
                self.db.conn.execute("INSERT INTO components(name,version,unit,active,usage,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET version=excluded.version,unit=excluded.unit,active=excluded.active,usage=excluded.usage,updated_at=excluded.updated_at",(name,version,unit,active,usage,ts,ts))
                cid = self.get_component_id(name)
                keep.append(cid)
                self.db.conn.execute("DELETE FROM component_platforms WHERE component_id=?", (cid,))
                for platform, enabled in platforms.items():
                    pid = self.get_platform_id(platform)
                    if pid is not None:
                        self.db.conn.execute("INSERT INTO component_platforms(component_id,platform_id,enabled) VALUES(?,?,?)", (cid, pid, 1 if bool(enabled) else 0))
            if keep:
                marks = ",".join("?" for _ in keep)
                self.db.conn.execute(f"DELETE FROM components WHERE id NOT IN ({marks})", keep)
            else:
                self.db.conn.execute("DELETE FROM components")
        self._clear_id_cache("component")
        audit_actor = actor or self.current_actor()
        after_components = {name: {"version": version, "unit": unit, "active": bool(active), "usage": float(usage)} for name, version, unit, active, usage, _platforms in normalized}
        for name in sorted(set(before_components) | set(after_components)):
            before_component, after_component = before_components.get(name), after_components.get(name)
            action = "component_created" if before_component is None else ("component_deleted" if after_component is None else ("component_updated" if before_component != after_component else ""))
            if action:
                self._log(action, entity_type="component", entity_key=name, source="Main UI", message={"component_created": "Bileşen eklendi", "component_updated": "Bileşen güncellendi", "component_deleted": "Bileşen silindi"}[action], before=before_component, after=after_component, actor=audit_actor)
        self._log("components_updated", entity_type="component", message="Bileşen listesi güncellendi", payload={"count": len(normalized)}, actor=audit_actor)


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
                  AND cp.platform_id = ?
                  AND cp.enabled = 1
                ORDER BY c.name ASC
                """,
                (self.get_platform_id(p),),
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
        keep = []
        with self.db.tx():
            seen = set()
            for t in list(tags or []):
                name = self._tag_name_of(t)
                if not name:
                    continue
                key = self._normalize_label(name)
                if key in seen:
                    continue
                seen.add(key); keep.append(name)
                color = str((t.get("color") if isinstance(t, dict) else getattr(t, "color", "#3B82F6")) or "#3B82F6")
                kind = str((t.get("kind") if isinstance(t, dict) else getattr(t, "kind", "contract")) or "contract")
                self.db.conn.execute("INSERT INTO tags(name,color,kind,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET color=excluded.color,kind=excluded.kind,updated_at=excluded.updated_at", (name, color, kind, ts, ts))
            if keep:
                marks = ",".join("?" for _ in keep)
                self.db.conn.execute(f"DELETE FROM tags WHERE name NOT IN ({marks})", keep)
            else:
                self.db.conn.execute("DELETE FROM tags")
        self._clear_id_cache("tag")

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
        self._clear_id_cache("tag")
        self._log("tag_upserted", entity_type="tag", entity_key=name, message="Etiket güncellendi", actor=getattr(self, "current_actor", lambda: "Sistem")())

    def delete_tag_def(self, tag_or_name):
        nm = self._tag_name_of(tag_or_name)
        if not nm:
            return
        with self.db.tx():
            self.db.conn.execute("DELETE FROM tags WHERE name=?", (nm,))
        self._clear_id_cache("tag")
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
            "SELECT p.name,c.contract_no,c.contract_type,t.name FROM contract_tags ct JOIN contracts c ON c.id=ct.contract_id JOIN platforms p ON p.id=c.platform_id JOIN tags t ON t.id=ct.tag_id ORDER BY p.name,c.contract_no,c.contract_type,t.name"
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
                "SELECT id FROM contracts WHERE platform_id=? AND contract_no=? AND contract_type=? ORDER BY id LIMIT 1",
                (self.get_platform_id(p), no, ct),
            ).fetchone()
        if not row:
            row = self.db.conn.execute(
                "SELECT id FROM contracts WHERE platform_id=? AND contract_no=? ORDER BY id LIMIT 1",
                (self.get_platform_id(p), no),
            ).fetchone()
        return int(row[0]) if row else 0

    def load_contract_tags(self, platform, contract_no, contract_type):
        cid = self._find_contract_id(platform, contract_no, contract_type)
        if not cid:
            return []
        rows = self.db.conn.execute(
            "SELECT t.name, t.color, t.kind FROM contract_tags ct JOIN tags t ON t.id=ct.tag_id WHERE ct.contract_id=? ORDER BY t.name",
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
                self.db.conn.execute("INSERT OR IGNORE INTO contract_tags(contract_id,tag_id) VALUES(?,?)", (cid, self.get_tag_id(nm)))
        self._log("contract_tags_updated", entity_type="contract", entity_id=cid, platform=str(platform or ""), contract_no=str(contract_no or ""), source="Tag Manager", message="Sözleşme etiketleri güncellendi", payload={"count": len(names)}, actor=actor or self.current_actor())


    def _folder_path_from_rows(self, folder_id, rows_by_id: dict[int, dict]) -> str:
        if not folder_id:
            return ""
        parts = []
        current = rows_by_id.get(int(folder_id))
        guard = 0
        while current and guard < 100:
            parts.append(str(current.get("name") or ""))
            parent_id = current.get("parent_id")
            current = rows_by_id.get(int(parent_id)) if parent_id else None
            guard += 1
        return "/".join(reversed([part for part in parts if part]))

    def _contract_folder_rows(self, contract_id: int) -> list[dict]:
        rows = self.db.conn.execute(
            "SELECT id,contract_id,parent_id,name,created_at,updated_at FROM contract_file_folders WHERE contract_id=? ORDER BY parent_id,name COLLATE NOCASE,id",
            (int(contract_id),),
        ).fetchall()
        data = [dict(row) for row in rows]
        by_id = {int(row["id"]): row for row in data}
        for row in data:
            row["path"] = self._folder_path_from_rows(row.get("id"), by_id)
        return data

    def list_contract_file_folders(self, platform, contract_no, contract_type=None):
        cid = self._find_contract_id(platform, contract_no, contract_type)
        if not cid:
            return []
        return self._contract_folder_rows(cid)

    def _normalize_folder_name(self, name: str) -> str:
        clean = str(name or "").strip()
        if not clean:
            raise ValueError("Klasör adı boş olamaz.")
        if any(ch in clean for ch in '/\\:*?"<>|'):
            raise ValueError("Klasör adında / \\ : * ? \" < > | karakterleri kullanılamaz.")
        return clean

    def _validate_contract_folder_id(self, contract_id: int, folder_id):
        if folder_id in (None, "", 0):
            return None
        row = self.db.conn.execute(
            "SELECT id FROM contract_file_folders WHERE id=? AND contract_id=?",
            (int(folder_id), int(contract_id)),
        ).fetchone()
        if not row:
            raise ValueError("Belge klasörü bulunamadı.")
        return int(row[0])

    def _folder_name_exists(self, contract_id: int, parent_id, name: str, exclude_id=None) -> bool:
        params = [int(contract_id), str(name)]
        sql = "SELECT id FROM contract_file_folders WHERE contract_id=? AND name=? AND "
        if parent_id in (None, "", 0):
            sql += "parent_id IS NULL"
        else:
            sql += "parent_id=?"
            params.append(int(parent_id))
        if exclude_id:
            sql += " AND id<>?"
            params.append(int(exclude_id))
        sql += " LIMIT 1"
        return self.db.conn.execute(sql, params).fetchone() is not None

    def _unique_folder_name(self, contract_id: int, parent_id, base_name: str = "Yeni Klasör") -> str:
        base = self._normalize_folder_name(base_name)
        if not self._folder_name_exists(contract_id, parent_id, base):
            return base
        index = 2
        while True:
            candidate = f"{base} ({index})"
            if not self._folder_name_exists(contract_id, parent_id, candidate):
                return candidate
            index += 1

    def create_contract_file_folder(self, platform, contract_no, contract_type=None, parent_id=None, name="Yeni Klasör"):
        cid = self._find_contract_id(platform, contract_no, contract_type)
        if not cid:
            raise ValueError("Sözleşme bulunamadı. Önce sözleşmeyi kaydedin.")
        parent_id = self._validate_contract_folder_id(cid, parent_id)
        folder_name = self._unique_folder_name(cid, parent_id, name or "Yeni Klasör")
        ts = now_iso()
        with self.db.tx():
            self.db.conn.execute(
                "INSERT INTO contract_file_folders(contract_id,parent_id,name,created_at,updated_at) VALUES(?,?,?,?,?)",
                (cid, parent_id, folder_name, ts, ts),
            )
            folder_id = int(self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        folders = {int(row["id"]): row for row in self._contract_folder_rows(cid)}
        folder_path = self._folder_path_from_rows(folder_id, folders)
        self._log(
            "document_folder_created",
            entity_type="document_folder",
            entity_id=folder_id,
            contract_no=str(contract_no or ""),
            source="Document Manager",
            message="Belge klasörü oluşturuldu",
            payload={"name": folder_name, "parent_id": parent_id, "path": folder_path},
        )
        return {"id": folder_id, "contract_id": cid, "parent_id": parent_id, "name": folder_name, "path": folder_path, "created_at": ts, "updated_at": ts}

    def rename_contract_file_folder(self, folder_id, new_name: str):
        row = self.db.conn.execute(
            "SELECT id,contract_id,parent_id,name,created_at,updated_at FROM contract_file_folders WHERE id=?",
            (int(folder_id),),
        ).fetchone()
        if not row:
            raise ValueError("Belge klasörü bulunamadı.")
        before = dict(row)
        clean = self._normalize_folder_name(new_name)
        if clean == str(before.get("name") or ""):
            return {**before, "path": self._folder_path_from_rows(int(folder_id), {int(r["id"]): r for r in self._contract_folder_rows(int(before["contract_id"]))})}
        if self._folder_name_exists(int(before["contract_id"]), before.get("parent_id"), clean, exclude_id=int(folder_id)):
            raise ValueError("Aynı seviyede bu klasör adı zaten var.")
        ts = now_iso()
        with self.db.tx():
            self.db.conn.execute("UPDATE contract_file_folders SET name=?,updated_at=? WHERE id=?", (clean, ts, int(folder_id)))
        folders = {int(r["id"]): r for r in self._contract_folder_rows(int(before["contract_id"]))}
        after = {**before, "name": clean, "updated_at": ts, "path": self._folder_path_from_rows(int(folder_id), folders)}
        self._log(
            "document_folder_renamed",
            entity_type="document_folder",
            entity_id=int(folder_id),
            source="Document Manager",
            message="Belge klasörü yeniden adlandırıldı",
            before={"name": before.get("name"), "parent_id": before.get("parent_id")},
            after={"name": clean, "parent_id": before.get("parent_id"), "path": after.get("path")},
        )
        return after

    def list_contract_files(self, platform, contract_no, contract_type=None):
        cid = self._find_contract_id(platform, contract_no, contract_type)
        if not cid:
            return []
        folder_rows = self._contract_folder_rows(cid)
        folders = {int(row["id"]): row for row in folder_rows}
        rows = self.db.conn.execute(
            "SELECT id,folder_id,filename,file_ext,mime_type,size_bytes,created_at,note FROM contract_files WHERE contract_id=? ORDER BY folder_id,filename COLLATE NOCASE,created_at,id",
            (cid,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["folder_path"] = self._folder_path_from_rows(item.get("folder_id"), folders)
            out.append(item)
        return out

    def add_contract_file(self, platform, contract_no, file_path, contract_type=None, note="", folder_id=None):
        cid = self._find_contract_id(platform, contract_no, contract_type)
        if not cid:
            raise ValueError("Sözleşme bulunamadı. Önce sözleşmeyi kaydedin.")
        folder_id = self._validate_contract_folder_id(cid, folder_id)
        source = Path(file_path)
        if not source.exists():
            raise ValueError("Dosya seçilemedi veya bulunamadı.")
        if source.is_dir():
            raise ValueError("Klasör yüklenemez, lütfen dosya seçin.")
        if not source.is_file():
            raise ValueError("Lütfen geçerli bir dosya seçin.")
        if not os.access(source, os.R_OK):
            raise ValueError("Dosya okunamıyor.")
        ext = source.suffix.lower().lstrip(".")
        allowed = {"pdf", "doc", "docx", "xls", "xlsx", "xlsm", "ppt", "pptx", "png", "jpg", "jpeg", "txt"}
        blocked = {"exe", "bat", "cmd", "ps1", "sh", "msi", "dll", "com", "scr", "vbs", "js"}
        if ext in blocked or ext not in allowed:
            raise ValueError("Bu dosya türü desteklenmiyor.")
        size = source.stat().st_size
        if size > 25 * 1024 * 1024:
            raise ValueError("Dosya boyutu 25 MB üstünde olamaz.")
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise ValueError(f"Dosya okunamıyor: {exc}") from exc
        try:
            stored_path = str(source.resolve())
        except OSError:
            stored_path = str(source)
        duplicate = self.db.conn.execute(
            """
            SELECT id FROM contract_files
            WHERE contract_id=? AND filename=?
              AND (original_path=? OR (size_bytes=? AND content_blob=?))
            LIMIT 1
            """,
            (cid, source.name, stored_path, len(content), content),
        ).fetchone()
        if duplicate:
            raise ValueError("Bu belge zaten ekli.")
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        ts = now_iso()
        with self.db.tx():
            self.db.conn.execute(
                "INSERT INTO contract_files(contract_id,folder_id,filename,original_path,file_ext,mime_type,size_bytes,content_blob,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cid, folder_id, source.name, stored_path, ext, mime_type, len(content), content, str(note or ""), ts, ts),
            )
            file_id = int(self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        self._log(
            "document_added",
            entity_type="document",
            entity_id=file_id,
            contract_no=str(contract_no or ""),
            source="Document Manager",
            message="Belge eklendi",
            payload={"filename": source.name, "folder_id": folder_id, "size_bytes": len(content), "mime_type": mime_type, "extension": ext},
        )
        return file_id

    def get_contract_file_bytes(self, file_id):
        row = self.db.conn.execute("SELECT filename,mime_type,content_blob FROM contract_files WHERE id=?", (int(file_id),)).fetchone()
        if not row:
            raise ValueError("Belge bulunamadı.")
        return str(row[0]), str(row[1] or "application/octet-stream"), bytes(row[2])

    def export_contract_file(self, file_id, target_path):
        filename, mime_type, content = self.get_contract_file_bytes(file_id)
        target = Path(target_path)
        target.write_bytes(content)
        return {"filename": filename, "mime_type": mime_type, "target_path": str(target), "size_bytes": len(content)}

    def delete_contract_file_folder(self, folder_id):
        row = self.db.conn.execute(
            "SELECT id,contract_id,parent_id,name FROM contract_file_folders WHERE id=?",
            (int(folder_id),),
        ).fetchone()
        if not row:
            raise ValueError("Klasör bulunamadı.")
        before = dict(row)
        # Klasör altındaki dosya sayısını kontrol et (alt klasörler dahil, CASCADE siler)
        file_count = self.db.conn.execute(
            "SELECT COUNT(*) FROM contract_files WHERE folder_id IN "
            "(WITH RECURSIVE sub(id) AS (SELECT ? UNION ALL SELECT f.id FROM contract_file_folders f JOIN sub ON f.parent_id=sub.id) SELECT id FROM sub)",
            (int(folder_id),),
        ).fetchone()[0]
        with self.db.tx():
            self.db.conn.execute("DELETE FROM contract_file_folders WHERE id=?", (int(folder_id),))
        self._log(
            "document_folder_deleted",
            entity_type="document_folder",
            entity_id=int(folder_id),
            source="Document Manager",
            message=f"Belge klasörü silindi ({file_count} dosya etkilendi)",
            before={"name": before.get("name"), "parent_id": before.get("parent_id"), "file_count": file_count},
        )
        return True

    def delete_contract_file(self, file_id):
        before = self.db.conn.execute("SELECT id,contract_id,folder_id,filename,size_bytes,note FROM contract_files WHERE id=?", (int(file_id),)).fetchone()
        with self.db.tx():
            cursor = self.db.conn.execute("DELETE FROM contract_files WHERE id=?", (int(file_id),))
        deleted = bool(cursor.rowcount)
        if deleted:
            self._log("document_deleted", entity_type="document", entity_id=int(file_id), source="Document Manager", message="Belge silindi", before=dict(before) if before else None)
        return deleted

    def list_main_contracts(self, platform, tags_map=None):
        rows=[]; tags_map = tags_map or self.all_contract_tags_map()
        for r in self.db.conn.execute("SELECT c.*,p.name AS platform,u.name AS user_name FROM contracts c JOIN platforms p ON p.id=c.platform_id LEFT JOIN users u ON u.id=c.user_id WHERE c.platform_id=? ORDER BY c.id",(self.get_platform_id(platform),)):
            tags=tags_map.get((r['platform'],r['contract_no'],r['contract_type']),[])
            users = self._decode_user_names(r["user_names"], r["user_name"] or "")
            user_display = self._user_display(users, r["user_name"] or "")
            search_text = str(r["search_text"] or "")
            if users and not search_text:
                search_text = " ".join(users)
            rows.append({
                "id":r["id"],"row":r["id"],"platform":r["platform"],
                "no":r["contract_no"],"contract_no":r["contract_no"],
                "user":user_display,"users":users,
                "type":r["contract_type"],"contract_type":r["contract_type"],
                "type_display":r["type_display"],"link":r["link_type"],"status":r["status"],
                "completion_date":r["completion_date"],"acceptance_date":r["acceptance_date"],"content":r["content"] or r["note"] or "",
                "is_main":bool(r["is_main"]),"tags":list(tags),"search":search_text
            })
        return rows
    def build_contract_index(self, progress_cb=None):
        out=[]; tags=self.all_contract_tags_map()
        for p in self.platform_names(): out.extend(self.list_main_contracts(p,tags_map=tags))
        return out
    def find_main_contract_info(self, platform, contract_no):
        r=self.db.conn.execute("SELECT c.*,p.name AS platform,u.name AS user_name FROM contracts c JOIN platforms p ON p.id=c.platform_id LEFT JOIN users u ON u.id=c.user_id WHERE c.platform_id=? AND c.contract_no=? AND c.is_main=1 LIMIT 1",(self.get_platform_id(platform),contract_no)).fetchone()
        if not r:
            return None
        out = dict(r)
        users = self._decode_user_names(out.get("user_names"), out.get("user_name") or "")
        out.update({"row": out["id"], "block_start": out["id"], "block_end": out["id"], "user": self._user_display(users, out.get("user_name") or ""), "type": out.get("contract_type") or ""})
        return out
    def next_sd_code(self, platform, contract_no):
        c=self.db.conn.execute("SELECT COUNT(*) FROM contracts WHERE platform_id=? AND contract_no=?",(self.get_platform_id(platform),contract_no)).fetchone()[0]
        return f"SD-{int(c)+1:03d}"

    def write_contract(self, ci, systems, deliveries, old_contract_no=None, old_start_row=None):
        ts=now_iso(); ctype=ci.contract_type
        platform_id = self.get_platform_id(ci.platform, create=True)
        users = self._decode_user_names(getattr(ci, "users", None), getattr(ci, "user", ""))
        if not users:
            users = self._decode_user_names([], getattr(ci, "user", ""))
        user_display = self._user_display(users, getattr(ci, "user", ""))
        user_id = self.get_user_id(users[0], create=True) if users else None
        user_names_json = self._encode_user_names(users)
        search_text = " ".join([str(ci.platform or ""), str(ci.no or ""), str(ctype or ""), str(ci.note or ""), user_display, " ".join(users)]).strip()
        ci.user = user_display; ci.users = users
        row=self.db.conn.execute("SELECT id,status,note,completion_date,acceptance_date FROM contracts WHERE platform_id=? AND contract_no=? AND contract_type=?",(platform_id,ci.no,ctype)).fetchone()
        before_contract = {"status": row[1] or "", "note": row[2] or "", "completion_date": row[3] or "", "acceptance_date": row[4] or ""} if row else None
        old_systems = {}
        old_deliveries = {}
        if row:
            for old_system in self.db.conn.execute("SELECT id,name,status,completion_date,acceptance_date FROM systems WHERE contract_id=?", (row[0],)):
                components = {item[0]: float(item[1] or 0) for item in self.db.conn.execute("SELECT c.name,sc.qty FROM system_components sc JOIN components c ON c.id=sc.component_id WHERE sc.system_id=?", (old_system[0],))}
                old_systems[str(old_system[1])] = {"status": old_system[2] or "", "completion_date": old_system[3] or "", "acceptance_date": old_system[4] or "", "components": components}
            for old_delivery in self.db.conn.execute("SELECT id,system_name,name,status,acceptance_date,note FROM deliveries WHERE contract_id=?", (row[0],)):
                components = {item[0]: {"planned": float(item[1] or 0), "delivered": float(item[2] or 0)} for item in self.db.conn.execute("SELECT c.name,dc.planned,dc.delivered FROM delivery_components dc JOIN components c ON c.id=dc.component_id WHERE dc.delivery_id=?", (old_delivery[0],))}
                old_deliveries[(str(old_delivery[1]), str(old_delivery[2]))] = {"id": int(old_delivery[0]), "status": old_delivery[3] or "", "acceptance_date": old_delivery[4] or "", "note": old_delivery[5] or "", "components": components}
        with self.db.tx():
            if row:
                cid=row[0]
                self.db.conn.execute("UPDATE contracts SET user_id=?,user_names=?,yi_yd=?,status=?,signed_date=?,t0_date=?,t0_months=?,completion_date=?,acceptance_date=?,note=?,content=?,search_text=?,updated_at=? WHERE id=?",(user_id,user_names_json,ci.yi_yd,ci.status,ci.signature_date,ci.t0_date,int(ci.t0_months or 0),ci.completion_date,ci.acceptance_date,ci.note,ci.note,search_text,ts,cid))
            else:
                self.db.conn.execute("INSERT INTO contracts(platform_id,user_id,contract_no,user_names,yi_yd,contract_type,type_display,link_type,status,signed_date,t0_date,t0_months,completion_date,acceptance_date,content,note,is_main,parent_contract_no,search_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(platform_id,user_id,ci.no,user_names_json,ci.yi_yd,ctype,ctype,"",ci.status,ci.signature_date,ci.t0_date,int(ci.t0_months or 0),ci.completion_date,ci.acceptance_date,ci.note,ci.note,1 if self._normalize_label(ctype)==self._normalize_label('Ana Sözleşme') else 0,ci.sd_anchor_no,search_text,ts,ts))
                cid=self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            existing_systems = {str(item[1]): int(item[0]) for item in self.db.conn.execute("SELECT id,name FROM systems WHERE contract_id=?", (cid,))}
            desired_system_names = {str(system.name) for system in (systems or [])}
            # Remove deliveries first so deleted acceptances cascade only to their own delivery_components.
            desired_delivery_keys = {(str(sys_name), str(delivery.name)) for sys_name, items in (deliveries or {}).items() for delivery in (items or [])}
            for delivery_row in self.db.conn.execute("SELECT id,system_name,name FROM deliveries WHERE contract_id=?", (cid,)).fetchall():
                if (str(delivery_row[1]), str(delivery_row[2])) not in desired_delivery_keys:
                    self.db.conn.execute("DELETE FROM deliveries WHERE id=?", (delivery_row[0],))

            system_ids = {}
            for i,system in enumerate(systems or []):
                payload=json.dumps({"t0_date":system.t0_date,"t0_months":system.t0_months})
                sid=existing_systems.get(str(system.name))
                if sid is None:
                    self.db.conn.execute("INSERT INTO systems(contract_id,name,status,completion_date,acceptance_date,note,sort_order,payload_json) VALUES(?,?,?,?,?,?,?,?)",(cid,system.name,system.status,system.completion_date,system.acceptance_date,"",i,payload))
                    sid=self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    self.db.conn.execute("UPDATE systems SET name=?,status=?,completion_date=?,acceptance_date=?,sort_order=?,payload_json=? WHERE id=?",(system.name,system.status,system.completion_date,system.acceptance_date,i,payload,sid))
                system_ids[system.name]=sid
                existing_components = {int(item[0]): int(item[1]) for item in self.db.conn.execute("SELECT component_id,id FROM system_components WHERE system_id=?", (sid,))}
                desired_component_ids = set()
                for cname, qty in (system.components or {}).items():
                    value=float(qty or 0)
                    if value <= 0:
                        continue
                    component_id=self.get_component_id(cname,create=True); desired_component_ids.add(component_id)
                    note=str((getattr(system, "component_notes", {}) or {}).get(cname, "") or "")
                    if component_id in existing_components:
                        self.db.conn.execute("UPDATE system_components SET qty=?,note=? WHERE id=?", (value,note,existing_components[component_id]))
                    else:
                        self.db.conn.execute("INSERT INTO system_components(system_id,component_id,qty,note) VALUES(?,?,?,?)",(sid,component_id,value,note))
                for component_id, system_component_id in existing_components.items():
                    if component_id not in desired_component_ids:
                        self.db.conn.execute("DELETE FROM system_components WHERE id=?", (system_component_id,))
            for name, sid in existing_systems.items():
                if name not in desired_system_names:
                    self.db.conn.execute("DELETE FROM systems WHERE id=?", (sid,))

            existing_deliveries = {(str(item[1]), str(item[2])): int(item[0]) for item in self.db.conn.execute("SELECT id,system_name,name FROM deliveries WHERE contract_id=?", (cid,))}
            for sys_name, dlist in (deliveries or {}).items():
                for i,delivery in enumerate(dlist or []):
                    delivery_user_id = self.get_user_id(getattr(delivery, "delivery_user", ""), create=True)
                    payload=json.dumps({"t0_date":delivery.t0_date,"t0_months":delivery.t0_months,"completion_date":delivery.completion_date})
                    did=existing_deliveries.get((str(sys_name), str(delivery.name)))
                    if did is None:
                        self.db.conn.execute("INSERT INTO deliveries(contract_id,system_id,delivery_user_id,system_name,name,status,acceptance_date,note,sort_order,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)",(cid,system_ids.get(sys_name),delivery_user_id,sys_name,delivery.name,delivery.status,delivery.acceptance_date,delivery.note,i,payload))
                        did=self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    else:
                        self.db.conn.execute("UPDATE deliveries SET system_id=?,delivery_user_id=?,system_name=?,name=?,status=?,acceptance_date=?,note=?,sort_order=?,payload_json=? WHERE id=?",(system_ids.get(sys_name),delivery_user_id,sys_name,delivery.name,delivery.status,delivery.acceptance_date,delivery.note,i,payload,did))
                    existing_components = {int(item[0]): int(item[1]) for item in self.db.conn.execute("SELECT component_id,id FROM delivery_components WHERE delivery_id=?", (did,))}
                    desired_component_ids = set()
                    names=set((delivery.planned or {})) | set((delivery.delivered or {}))
                    for cname in names:
                        planned=float((delivery.planned or {}).get(cname,0) or 0); delivered=float((delivery.delivered or {}).get(cname,0) or 0)
                        if planned <= 0 and delivered <= 0:
                            continue
                        component_id=self.get_component_id(cname,create=True); desired_component_ids.add(component_id)
                        if component_id in existing_components:
                            self.db.conn.execute("UPDATE delivery_components SET planned=?,delivered=? WHERE id=?",(planned,delivered,existing_components[component_id]))
                        else:
                            self.db.conn.execute("INSERT INTO delivery_components(delivery_id,component_id,planned,delivered) VALUES(?,?,?,?)",(did,component_id,planned,delivered))
                    for component_id, delivery_component_id in existing_components.items():
                        if component_id not in desired_component_ids:
                            self.db.conn.execute("DELETE FROM delivery_components WHERE id=?", (delivery_component_id,))
        after_contract = {"status": str(ci.status or ""), "note": str(ci.note or ""), "completion_date": str(ci.completion_date or ""), "acceptance_date": str(ci.acceptance_date or "")}
        self._log("contract_updated" if row else "contract_created", entity_type="contract", entity_id=cid, platform=str(ci.platform or ""), contract_no=str(ci.no or ""), source="Contract Detail", message="Sözleşme ana bilgileri güncellendi" if row else "Sözleşme oluşturuldu", before=before_contract, after=after_contract, payload={"system_count":len(systems or []),"delivery_count":sum(len(v or []) for v in (deliveries or {}).values()),"component_count":sum(len((x.components or {})) for x in (systems or []))}, actor=self.current_actor())
        if before_contract and before_contract.get("status") != after_contract.get("status"):
            self._log("contract_status_changed", entity_type="contract", entity_id=cid, platform=str(ci.platform or ""), contract_no=str(ci.no or ""), source="Contract Detail", message="Sözleşme durumu güncellendi", before={"status": before_contract.get("status")}, after={"status": after_contract.get("status")}, actor=self.current_actor())
        new_systems = {str(system.name): {"status": str(system.status or ""), "completion_date": str(system.completion_date or ""), "acceptance_date": str(system.acceptance_date or ""), "components": {str(name): float(qty or 0) for name, qty in (system.components or {}).items() if float(qty or 0) > 0}} for system in (systems or [])}
        for name in sorted(set(new_systems) | set(old_systems)):
            before_system, after_system = old_systems.get(name), new_systems.get(name)
            if before_system is None:
                self._log("system_created", entity_type="system", entity_key=name, contract_no=str(ci.no or ""), source="System Editor", message="Sistem eklendi", after=after_system)
            elif after_system is None:
                self._log("system_deleted", entity_type="system", entity_key=name, contract_no=str(ci.no or ""), source="System Editor", message="Sistem silindi", before=before_system)
            elif before_system != after_system:
                self._log("system_updated", entity_type="system", entity_key=name, contract_no=str(ci.no or ""), source="System Editor", message="Sistem güncellendi", before=before_system, after=after_system)
                if before_system.get("components") != after_system.get("components"):
                    self._log("system_component_updated", entity_type="system", entity_key=name, contract_no=str(ci.no or ""), source="System Editor", message="Sistem bileşenleri güncellendi", before={"components": before_system.get("components")}, after={"components": after_system.get("components")})
        new_deliveries = {(str(system_name), str(delivery.name)): {"status": str(delivery.status or ""), "acceptance_date": str(delivery.acceptance_date or ""), "note": str(delivery.note or ""), "components": {name: {"planned": float((delivery.planned or {}).get(name, 0) or 0), "delivered": float((delivery.delivered or {}).get(name, 0) or 0)} for name in set((delivery.planned or {})) | set((delivery.delivered or {})) if float((delivery.planned or {}).get(name, 0) or 0) > 0 or float((delivery.delivered or {}).get(name, 0) or 0) > 0}} for system_name, items in (deliveries or {}).items() for delivery in (items or [])}
        for key in sorted(set(new_deliveries) | set(old_deliveries)):
            before_delivery, after_delivery = old_deliveries.get(key), new_deliveries.get(key)
            before_compare = {name: value for name, value in (before_delivery or {}).items() if name != "id"}
            entity_key = f"{key[0]} / {key[1]}"
            if before_delivery is None:
                self._log("delivery_created", entity_type="delivery", entity_key=entity_key, contract_no=str(ci.no or ""), source="Delivery Editor", message="Teslimat eklendi", after=after_delivery)
            elif after_delivery is None:
                self._log("delivery_deleted", entity_type="delivery", entity_id=before_delivery.get("id"), entity_key=entity_key, contract_no=str(ci.no or ""), source="Delivery Editor", message="Teslimat silindi", before=before_delivery)
            elif before_compare != after_delivery:
                self._log("delivery_updated", entity_type="delivery", entity_key=entity_key, contract_no=str(ci.no or ""), source="Delivery Editor", message="Teslimat güncellendi", before=before_compare, after=after_delivery)
                if before_compare.get("status") != after_delivery.get("status"):
                    self._log("delivery_status_changed", entity_type="delivery", entity_key=entity_key, contract_no=str(ci.no or ""), source="Delivery Editor", message="Teslimat durumu güncellendi", before={"status": before_compare.get("status")}, after={"status": after_delivery.get("status")})
        return cid

    def load_contract_structure(self, platform, contract_no, start_row=None, contract_type=None):
        if contract_type is None and start_row is not None and not str(start_row).isdigit():
            contract_type = str(start_row)
            start_row = None
        r = None
        if start_row is not None and str(start_row).isdigit():
            r = self.db.conn.execute("SELECT c.*,p.name AS platform,u.name AS user_name FROM contracts c JOIN platforms p ON p.id=c.platform_id LEFT JOIN users u ON u.id=c.user_id WHERE c.id=? LIMIT 1", (int(start_row),)).fetchone()
        if not r and contract_type:
            r = self.db.conn.execute("SELECT c.*,p.name AS platform,u.name AS user_name FROM contracts c JOIN platforms p ON p.id=c.platform_id LEFT JOIN users u ON u.id=c.user_id WHERE c.platform_id=? AND c.contract_no=? AND c.contract_type=? ORDER BY c.id LIMIT 1",(self.get_platform_id(platform),contract_no,contract_type)).fetchone()
        if not r:
            r=self.db.conn.execute("SELECT c.*,p.name AS platform,u.name AS user_name FROM contracts c JOIN platforms p ON p.id=c.platform_id LEFT JOIN users u ON u.id=c.user_id WHERE c.platform_id=? AND c.contract_no=? ORDER BY c.id LIMIT 1",(self.get_platform_id(platform),contract_no)).fetchone()
        if not r: raise ValueError("contract not found")
        users = self._decode_user_names(r["user_names"], r["user_name"] or "")
        user_display = self._user_display(users, r["user_name"] or "")
        ci=ContractInfo(no=r['contract_no'],platform=r['platform'],user=user_display,yi_yd=r['yi_yd'] or "Yİ",contract_type=r['contract_type'] or "",signature_date=r['signed_date'] or "",t0_date=r['t0_date'] or "",t0_months=int(r['t0_months'] or 0),completion_date=r['completion_date'] or "",status=r['status'] or "PLAN",note=r['note'] or "",acceptance_date=r['acceptance_date'] or "",entry_start_row=int(r['id']),users=users)
        systems=[]; deliveries={}
        for s in self.db.conn.execute("SELECT * FROM systems WHERE contract_id=? ORDER BY sort_order,id",(r['id'],)):
            component_rows=self.db.conn.execute("SELECT c.name,sc.qty,sc.note FROM system_components sc JOIN components c ON c.id=sc.component_id WHERE sc.system_id=?",(s['id'],)).fetchall()
            comps={x[0]:float(x[1] or 0) for x in component_rows}
            component_notes={x[0]:str(x[2] or "") for x in component_rows if str(x[2] or "")}
            payload=json.loads(s['payload_json'] or "{}")
            si=SystemInfo(name=s['name'],components=comps,component_notes=component_notes,t0_date=payload.get('t0_date',''),t0_months=int(payload.get('t0_months',0) or 0),completion_date=s['completion_date'] or "",status=s['status'] or "Başlanmadı",acceptance_date=s['acceptance_date'] or "")
            systems.append(si)
        for d in self.db.conn.execute("SELECT d.*,u.name AS delivery_user FROM deliveries d LEFT JOIN users u ON u.id=d.delivery_user_id WHERE d.contract_id=? ORDER BY d.system_name,d.sort_order,d.id",(r['id'],)):
            payload=json.loads(d['payload_json'] or "{}")
            rows=self.db.conn.execute("SELECT c.name,dc.planned,dc.delivered FROM delivery_components dc JOIN components c ON c.id=dc.component_id WHERE dc.delivery_id=?",(d['id'],)).fetchall()
            planned={x[0]:float(x[1] or 0) for x in rows}; delivered={x[0]:float(x[2] or 0) for x in rows}
            di=DeliveryInfo(name=d['name'],status=d['status'] or "",acceptance_date=d['acceptance_date'] or "",note=d['note'] or "",planned=planned,delivered=delivered,t0_date=payload.get('t0_date',''),t0_months=int(payload.get('t0_months',0) or 0),completion_date=payload.get('completion_date',''),delivery_user=d['delivery_user'] or "")
            deliveries.setdefault(d['system_name'],[]).append(di)
        return ci, systems, deliveries

    def delete_contract(self, platform, contract_no, start_row=None, actor=None, progress_cb=None):
        row=self.db.conn.execute("SELECT id FROM contracts WHERE platform_id=? AND contract_no=? ORDER BY id LIMIT 1",(self.get_platform_id(platform),contract_no)).fetchone()
        if not row: return {"platform":platform,"contract_no":contract_no,"start_row":0,"end_row":0,"deleted_rows":0}
        cid=row[0]
        before = self.db.conn.execute("SELECT contract_no,contract_type,status,completion_date,acceptance_date FROM contracts WHERE id=?", (cid,)).fetchone()
        self.db.conn.execute("DELETE FROM contracts WHERE id=?",(cid,)); self.db.conn.commit()
        self._log("contract_deleted", entity_type="contract", entity_id=cid, platform=str(platform or ""), contract_no=str(contract_no or ""), source="Contract Detail", message="Sözleşme silindi", before=dict(before) if before else None, actor=actor or self.current_actor())
        return {"platform":platform,"contract_no":contract_no,"start_row":cid,"end_row":cid,"deleted_rows":1}
