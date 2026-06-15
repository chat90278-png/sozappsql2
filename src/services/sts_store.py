from __future__ import annotations
import json
import mimetypes
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.config.app_config import MAX_CONTRACT_FILE_SIZE_BYTES
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

    def _normalize_users(self, raw, fallback="") -> List[str]:
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

    def _user_display(self, users, fallback="") -> str:
        clean = self._normalize_users(list(users or []), fallback=fallback)
        if clean:
            return ", ".join(clean)
        return str(fallback or "").strip()

    def list_staff_for_engineer_selection(self) -> List[dict]:
        rows = self.db.conn.execute(
            "SELECT id, full_name, device_name, role_id, is_active FROM staff WHERE COALESCE(is_active,1)=1 ORDER BY full_name COLLATE NOCASE"
        ).fetchall()
        return [
            {"id": int(r[0]), "staff_id": int(r[0]), "full_name": str(r[1] or ""), "device_name": str(r[2] or ""), "role_id": r[3], "is_active": bool(r[4])}
            for r in rows
            if str(r[1] or "").strip()
        ]

    def get_contract_responsible_engineers(self, contract_id=None, platform=None, contract_no=None, contract_type="Ana Sözleşme") -> List[dict]:
        cid = int(contract_id or 0)
        if not cid and platform and contract_no:
            cid = int(self._resolve_contract_id(str(platform or ""), str(contract_no or ""), str(contract_type or "Ana Sözleşme")) or 0)
        if not cid:
            return []
        rows = self.db.conn.execute(
            """
            SELECT cre.staff_id, s.full_name, s.device_name, cre.sort_order, cre.is_primary
            FROM contract_responsible_engineers cre
            JOIN staff s ON s.id = cre.staff_id
            WHERE cre.contract_id=?
            ORDER BY cre.sort_order ASC, cre.is_primary DESC, s.full_name COLLATE NOCASE
            """,
            (cid,),
        ).fetchall()
        return [
            {"staff_id": int(r[0]), "id": int(r[0]), "full_name": str(r[1] or ""), "device_name": str(r[2] or ""), "sort_order": int(r[3] or 0), "is_primary": bool(r[4])}
            for r in rows
        ]

    def set_contract_responsible_engineers(self, contract_id: int, staff_ids: List[int]) -> None:
        cid = int(contract_id or 0)
        if not cid:
            return
        clean: List[int] = []
        seen = set()
        active_staff = {int(r[0]) for r in self.db.conn.execute("SELECT id FROM staff WHERE COALESCE(is_active,1)=1").fetchall()}
        for raw in staff_ids or []:
            try:
                sid = int(raw or 0)
            except Exception:
                sid = 0
            if sid and sid in active_staff and sid not in seen:
                seen.add(sid)
                clean.append(sid)
        self.db.conn.execute("DELETE FROM contract_responsible_engineers WHERE contract_id=?", (cid,))
        for order, sid in enumerate(clean):
            self.db.conn.execute(
                "INSERT INTO contract_responsible_engineers(contract_id, staff_id, sort_order, is_primary) VALUES(?,?,?,?)",
                (cid, sid, order, 1 if order == 0 else 0),
            )


    def _log(self, action: str, **kwargs):
        self.db.add_log(action=action, **kwargs)

    def list_logs(self, limit=500, action=None, entity_type=None, platform=None, contract_no=None, search=None):
        return self.db.list_logs(limit=limit, action=action, entity_type=entity_type, platform=platform, contract_no=contract_no, search=search)


    def _resolve_contract_id(self, platform: str, contract_no: str, contract_type: str = "Ana Sözleşme") -> int | None:
        row = self.db.conn.execute(
            """
            SELECT c.id FROM contracts c
            JOIN contract_platforms cp ON cp.contract_id = c.id
            JOIN platforms p ON p.id = cp.platform_id
            WHERE p.name=? AND c.contract_no=? AND c.contract_type=?
            """,
            (str(platform or ""), str(contract_no or ""), str(contract_type or "Ana Sözleşme")),
        ).fetchone()
        return int(row[0]) if row else None

    def document_lock_state(self, platform: str, contract_no: str, contract_type: str = "Ana Sözleşme") -> dict:
        cid = self._resolve_contract_id(platform, contract_no, contract_type)
        if cid is None:
            return {
                "contract_id": None,
                "is_locked": 0,
                "locked_by_staff_id": None,
                "locked_by_device_name": None,
                "locked_by_full_name": None,
                "locked_at": None,
                "updated_at": None,
            }
        return auth.get_document_lock_state(self.db.conn, cid)

    def lock_documents(self, platform: str, contract_no: str, current_staff, contract_type: str = "Ana Sözleşme") -> dict:
        cid = self._resolve_contract_id(platform, contract_no, contract_type)
        if cid is None:
            return {"contract_id": None, "is_locked": 0}
        state = auth.lock_documents(self.db.conn, cid, current_staff or {})
        self._log(
            "documents_locked",
            entity_type="document_lock",
            source="Document Manager",
            message="Belgeler kilitlendi",
            payload={"contract_id": cid, "locked_by_device_name": (current_staff or {}).get("device_name")},
            actor=str((current_staff or {}).get("full_name") or self.current_actor()),
        )
        return state

    def unlock_documents(self, platform: str, contract_no: str, actor=None, contract_type: str = "Ana Sözleşme") -> dict:
        cid = self._resolve_contract_id(platform, contract_no, contract_type)
        if cid is None:
            return {"contract_id": None, "is_locked": 0}
        state = auth.unlock_documents(self.db.conn, cid)
        self._log(
            "documents_unlocked",
            entity_type="document_lock",
            source="Document Manager",
            message="Belgeler kilidi açıldı",
            payload={"contract_id": cid},
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
        return [r[0] for r in self.db.conn.execute("SELECT name FROM platforms WHERE is_active=1 AND is_excluded=0 ORDER BY sort_order,name").fetchall()]

    def load_platforms(self):
        rows = self.db.conn.execute(
            """
            SELECT
                p.id,
                p.name,
                p.is_active,
                p.is_excluded,
                p.sort_order,
                COALESCE(SUM(CASE WHEN cp.enabled=1 THEN 1 ELSE 0 END), 0) AS comp_count
            FROM platforms p
            LEFT JOIN component_platforms cp ON cp.platform_id=p.id
            GROUP BY p.id,p.name,p.is_active,p.is_excluded,p.sort_order
            ORDER BY p.sort_order,p.name
            """
        ).fetchall()
        return [{"id": int(r[0]), "name": r[1], "is_active": bool(r[2]), "is_excluded": bool(r[3]), "sort_order": int(r[4] or 0), "comp_count": int(r[5] or 0)} for r in rows]

    def update_platform(self, old_name, new_name, is_active, is_excluded, sort_order=None, logo_source=None):
        old = str(old_name or "").strip()
        new = str(new_name or "").strip()
        if not old or not new:
            return
        ts = now_iso()
        if sort_order is None:
            self.db.conn.execute(
                "UPDATE platforms SET name=?,display_name=?,is_active=?,is_excluded=?,updated_at=? WHERE name=?",
                (new, new, 1 if is_active else 0, 1 if is_excluded else 0, ts, old),
            )
        else:
            self.db.conn.execute(
                "UPDATE platforms SET name=?,display_name=?,is_active=?,is_excluded=?,sort_order=?,updated_at=? WHERE name=?",
                (new, new, 1 if is_active else 0, 1 if is_excluded else 0, int(sort_order or 0), ts, old),
            )
        self.db.conn.commit()
        self._clear_id_cache("platform")
        self._log("platform_updated", entity_type="platform", entity_key=new, platform=new, message="Platform güncellendi", before={"name": old}, after={"name": new, "is_active": bool(is_active), "is_excluded": bool(is_excluded)})
        if logo_source:
            raw = Path(logo_source).read_bytes()
            ext = Path(logo_source).suffix.lower().lstrip('.')
            self.set_platform_logo_bytes(new, raw, ext=ext)

    def create_platform(self, name, logo_source=None):
        nm = str(name or "").strip()
        if not nm:
            return
        ts = now_iso()
        next_order = int(self.db.conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM platforms").fetchone()[0] or 0)
        self.db.conn.execute("INSERT OR IGNORE INTO platforms(name,display_name,sort_order,created_at,updated_at) VALUES(?,?,?,?,?)", (nm, nm, next_order, ts, ts))
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
        for r in self.db.conn.execute("SELECT id,name,version,unit,active,usage,note FROM components ORDER BY COALESCE(display_order, id), name"):
            plats={x[0]:bool(x[1]) for x in self.db.conn.execute("SELECT p.name,cp.enabled FROM component_platforms cp JOIN platforms p ON p.id=cp.platform_id WHERE cp.component_id=?",(r[0],))}
            comp = ComponentDef(name=r[1],version=r[2] or "",unit=r[3] or "Adet",active=bool(r[4]),usage=int(r[5] or 1),platforms=plats)
            comp.note = r[6] or ""
            out.append(comp)
        return out

    def load_components_full(self):
        rows = self.db.conn.execute("SELECT id,name,unit,active,note,display_order FROM components ORDER BY COALESCE(display_order, id), name").fetchall()
        out = []
        for r in rows:
            plats = {x[0]: bool(x[1]) for x in self.db.conn.execute("SELECT p.name,cp.enabled FROM component_platforms cp JOIN platforms p ON p.id=cp.platform_id WHERE cp.component_id=?", (r[0],))}
            out.append({"id": int(r[0]), "name": r[1], "unit": r[2] or "Adet", "active": bool(r[3]), "note": r[4] or "", "display_order": int(r[5]) if r[5] is not None else int(r[0]), "platforms": plats})
        return out

    def write_component(self, comp_dict, actor=None):
        payload = dict(comp_dict or {})
        old_name = str(payload.get("old_name") or payload.get("name") or "").strip()
        items = self.load_components_full()
        replaced = False
        for idx, item in enumerate(items):
            if str(item.get("name") or "") == old_name or (payload.get("id") and int(item.get("id") or 0) == int(payload.get("id") or 0)):
                merged = dict(item)
                merged.update(payload)
                merged.pop("old_name", None)
                items[idx] = merged
                replaced = True
                break
        if not replaced:
            payload.pop("old_name", None)
            items.append(payload)
        self.write_components(items, actor=actor or self.current_actor())

    def delete_component(self, name):
        nm = str(name or "").strip()
        if not nm:
            return
        self.db.conn.execute("DELETE FROM components WHERE name=?", (nm,))
        self.db.conn.commit()
        self._clear_id_cache("component")
        self._log("component_deleted", entity_type="component", entity_key=nm, message="Bileşen silindi")
    def write_components(self, components_payload, actor=None):
        ts = now_iso()
        before_components = {str(row["name"]): {"version": row["version"] or "", "unit": row["unit"] or "Adet", "active": bool(row["active"]), "usage": float(row["usage"] or 1), "note": row["note"] or ""} for row in self.db.conn.execute("SELECT name,version,unit,active,usage,note FROM components")}
        existing_orders = {str(row["name"]): int(row["display_order"]) for row in self.db.conn.execute("SELECT name,display_order FROM components WHERE display_order IS NOT NULL")}
        next_order = int(self.db.conn.execute("SELECT COALESCE(MAX(display_order), -1) + 1 FROM components").fetchone()[0] or 0)
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
            note = str((c.get("note") if isinstance(c, dict) else getattr(c, "note", "")) or "")
            raw_order = c.get("display_order") if isinstance(c, dict) else getattr(c, "display_order", None)
            if raw_order is None or str(raw_order).strip() == "":
                display_order = existing_orders.get(name)
            else:
                display_order = int(raw_order)
            if display_order is None:
                display_order = next_order
                next_order += 1
            platforms = dict((c.get("platforms") if isinstance(c, dict) else getattr(c, "platforms", {})) or {})
            normalized.append((name, version, unit, active, usage, note, display_order, platforms))
        self._clear_id_cache("component")
        with self.db.tx():
            keep = []
            for name, version, unit, active, usage, note, display_order, platforms in normalized:
                self.db.conn.execute("INSERT INTO components(name,version,unit,active,usage,note,display_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET version=excluded.version,unit=excluded.unit,active=excluded.active,usage=excluded.usage,note=excluded.note,display_order=excluded.display_order,updated_at=excluded.updated_at",(name,version,unit,active,usage,note,display_order,ts,ts))
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
        after_components = {name: {"version": version, "unit": unit, "active": bool(active), "usage": float(usage), "note": note} for name, version, unit, active, usage, note, _display_order, _platforms in normalized}
        for name in sorted(set(before_components) | set(after_components)):
            before_component, after_component = before_components.get(name), after_components.get(name)
            action = "component_created" if before_component is None else ("component_deleted" if after_component is None else ("component_updated" if before_component != after_component else ""))
            if action:
                self._log(action, entity_type="component", entity_key=name, source="Main UI", message={"component_created": "Bileşen eklendi", "component_updated": "Bileşen güncellendi", "component_deleted": "Bileşen silindi"}[action], before=before_component, after=after_component, actor=audit_actor)
        self._log("components_updated", entity_type="component", message="Bileşen listesi güncellendi", payload={"count": len(normalized)}, actor=audit_actor)


    def update_component_order(self, ordered_component_ids: list[int]) -> None:
        ts = now_iso()
        ids = [int(x) for x in (ordered_component_ids or []) if int(x or 0) > 0]
        with self.db.tx():
            for order, component_id in enumerate(ids):
                self.db.conn.execute(
                    "UPDATE components SET display_order=?, updated_at=? WHERE id=?",
                    (order, ts, component_id),
                )
        self._clear_id_cache("component")
        self._log("component_order_updated", entity_type="component", message="Bileşen sırası güncellendi", payload={"component_ids": ids})

    def update_platform_order(self, ordered_platform_ids: list[int]) -> None:
        ts = now_iso()
        ids = [int(x) for x in (ordered_platform_ids or []) if int(x or 0) > 0]
        with self.db.tx():
            for order, platform_id in enumerate(ids):
                self.db.conn.execute(
                    "UPDATE platforms SET sort_order=?, updated_at=? WHERE id=?",
                    (order, ts, platform_id),
                )
        self._clear_id_cache("platform")
        self._log("platform_order_updated", entity_type="platform", message="Platform sırası güncellendi", payload={"platform_ids": ids})


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
                ORDER BY COALESCE(c.display_order, c.id), c.name ASC
                """,
                (self.get_platform_id(p),),
            ).fetchall()
        if rows:
            return [str(r[0]) for r in rows if str(r[0] or "").strip()]
        fb = self.db.conn.execute(
            "SELECT DISTINCT name FROM components WHERE active = 1 ORDER BY COALESCE(display_order, id), name ASC"
        ).fetchall()
        return [str(r[0]) for r in fb if str(r[0] or "").strip()]


    # ---------- Sistem Tipi / Bileşen Paketi helpers ----------
    # STS dosyalarında sistem tipi paketleri mevcut meta tablosunda JSON olarak tutulur.
    # Şema değişikliği yapılmaz; meta tablosu yoksa kayıt işlemi kontrollü hata verir.
    _SYSTEM_TYPES_META_KEY = "system_types"

    def _system_type_meta_available(self) -> bool:
        row = self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
        ).fetchone()
        return bool(row)

    def _system_type_platform_key(self, platform: str = "") -> str:
        return str(platform or "").strip()

    def _load_system_types_payload(self) -> dict:
        if not self._system_type_meta_available():
            return {}
        row = self.db.conn.execute(
            "SELECT value FROM meta WHERE key=?",
            (self._SYSTEM_TYPES_META_KEY,),
        ).fetchone()
        if not row or not str(row[0] or "").strip():
            return {}
        try:
            payload = json.loads(str(row[0] or "{}"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_system_types_payload(self, payload: dict) -> None:
        if not self._system_type_meta_available():
            raise RuntimeError("Sistem tipi kaydedilemedi: meta tablosu bulunamadı.")
        self.db.conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
            (self._SYSTEM_TYPES_META_KEY, json.dumps(payload or {}, ensure_ascii=False)),
        )

    def _find_system_type_key(self, platform_bucket: dict, type_name: str) -> str | None:
        target = str(type_name or "").strip().casefold()
        if not target or not isinstance(platform_bucket, dict):
            return None
        for key in platform_bucket.keys():
            if str(key or "").strip().casefold() == target:
                return str(key)
        return None

    def _normalize_system_type_components(self, components) -> Dict[str, float]:
        source = (components or {}).items() if isinstance(components, dict) else [(c, 1) for c in (components or [])]
        out: Dict[str, float] = {}
        seen = set()
        for cname, qty in source:
            name = str(cname or "").strip()
            key = name.casefold()
            if not name or key in seen:
                continue
            try:
                amount = float(qty or 0)
            except Exception:
                amount = 0.0
            if amount <= 0:
                continue
            seen.add(key)
            out[name] = int(amount) if amount.is_integer() else amount
        return out

    def save_system_type(self, type_name: str, platform: str, components) -> int:
        type_name = str(type_name or "").strip()
        if not type_name:
            raise ValueError("Tip adı boş olamaz.")
        normalized_components = self._normalize_system_type_components(components)
        if not normalized_components:
            raise ValueError("Kaydedilecek bileşen yok.")

        payload = self._load_system_types_payload()
        platform_key = self._system_type_platform_key(platform)
        platform_bucket = payload.get(platform_key)
        if not isinstance(platform_bucket, dict):
            platform_bucket = {}
            payload[platform_key] = platform_bucket

        existing_key = self._find_system_type_key(platform_bucket, type_name)
        if existing_key and existing_key != type_name:
            platform_bucket.pop(existing_key, None)
        platform_bucket[type_name] = normalized_components

        with self.db.tx():
            self._write_system_types_payload(payload)
        return len(normalized_components)

    def list_system_type_names(self, platform: str = "") -> List[str]:
        payload = self._load_system_types_payload()
        platform_bucket = payload.get(self._system_type_platform_key(platform))
        if not isinstance(platform_bucket, dict):
            return []
        names = [str(name).strip() for name in platform_bucket.keys() if str(name or "").strip()]
        return sorted(names, key=lambda x: x.casefold())

    def get_system_type_component_quantities(self, type_name: str, platform: str = "") -> Dict[str, float]:
        payload = self._load_system_types_payload()
        platform_bucket = payload.get(self._system_type_platform_key(platform))
        if not isinstance(platform_bucket, dict):
            return {}
        type_key = self._find_system_type_key(platform_bucket, type_name)
        if not type_key:
            return {}
        raw_components = platform_bucket.get(type_key)
        if not isinstance(raw_components, dict):
            return {}
        return self._normalize_system_type_components(raw_components)

    def get_system_type_components(self, type_name: str, platform: str = "") -> List[str]:
        return list(self.get_system_type_component_quantities(type_name, platform).keys())

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
        if size > MAX_CONTRACT_FILE_SIZE_BYTES:
            raise ValueError("Dosya boyutu 120 MB üstünde olamaz.")
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

        # Tüm alt klasör id'lerini recursive topla (kendisi dahil)
        def collect_all_ids(fid):
            ids = [int(fid)]
            children = self.db.conn.execute(
                "SELECT id FROM contract_file_folders WHERE parent_id=?",
                (int(fid),),
            ).fetchall()
            for child in children:
                ids.extend(collect_all_ids(int(child[0])))
            return ids

        all_folder_ids = collect_all_ids(int(folder_id))
        subfolder_count = len(all_folder_ids) - 1  # kendisi hariç alt klasör sayısı

        if all_folder_ids:
            placeholders = ",".join("?" for _ in all_folder_ids)
            file_count = self.db.conn.execute(
                f"SELECT COUNT(*) FROM contract_files WHERE folder_id IN ({placeholders})",
                all_folder_ids,
            ).fetchone()[0]
        else:
            file_count = 0

        with self.db.tx():
            if all_folder_ids:
                placeholders = ",".join("?" for _ in all_folder_ids)
                self.db.conn.execute(
                    f"DELETE FROM contract_files WHERE folder_id IN ({placeholders})",
                    all_folder_ids,
                )
                self.db.conn.execute(
                    f"DELETE FROM contract_file_folders WHERE id IN ({placeholders})",
                    all_folder_ids,
                )

        self._log(
            "document_folder_deleted",
            entity_type="document_folder",
            entity_id=int(folder_id),
            source="Document Manager",
            message=f"Belge klasörü silindi ({file_count} dosya, {subfolder_count} alt klasör etkilendi)",
            before={
                "name": before.get("name"),
                "parent_id": before.get("parent_id"),
                "file_count": file_count,
                "subfolder_count": subfolder_count,
            },
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

    def move_contract_file(self, file_id: int, target_folder_id):
        """Dosyayı hedef klasöre taşı. target_folder_id=None köke taşır."""
        row = self.db.conn.execute(
            "SELECT id,contract_id,folder_id,filename FROM contract_files WHERE id=?",
            (int(file_id),),
        ).fetchone()
        if not row:
            raise ValueError("Dosya bulunamadı.")
        file_data = dict(row)
        contract_id = int(file_data["contract_id"])

        real_target = None
        if target_folder_id not in (None, "", 0):
            real_target = self._validate_contract_folder_id(contract_id, target_folder_id)

        ts = now_iso()
        with self.db.tx():
            self.db.conn.execute(
                "UPDATE contract_files SET folder_id=?, updated_at=? WHERE id=?",
                (real_target, ts, int(file_id)),
            )
        self._log(
            "document_moved",
            entity_type="document",
            entity_id=int(file_id),
            source="Document Manager",
            message="Belge taşındı",
            before={"folder_id": file_data.get("folder_id")},
            after={"folder_id": real_target},
        )
        return True

    def move_contract_file_folder(self, folder_id: int, target_parent_id):
        """Klasörü hedef parent altına taşı. target_parent_id=None köke taşır."""
        row = self.db.conn.execute(
            "SELECT id,contract_id,parent_id,name FROM contract_file_folders WHERE id=?",
            (int(folder_id),),
        ).fetchone()
        if not row:
            raise ValueError("Klasör bulunamadı.")
        folder_data = dict(row)
        contract_id = int(folder_data["contract_id"])

        real_parent = None
        if target_parent_id not in (None, "", 0):
            real_parent = self._validate_contract_folder_id(contract_id, target_parent_id)

        # Klasörün kendi alt ağacına taşınmasını engelle
        if real_parent is not None:
            def is_descendant(fid, anc_id):
                r = self.db.conn.execute(
                    "SELECT parent_id FROM contract_file_folders WHERE id=?", (int(fid),)
                ).fetchone()
                if not r:
                    return False
                pid = r[0]
                if pid is None:
                    return False
                if int(pid) == int(anc_id):
                    return True
                return is_descendant(int(pid), anc_id)
            if int(real_parent) == int(folder_id) or is_descendant(real_parent, folder_id):
                raise ValueError("Klasör kendi alt klasörüne taşınamaz.")

        # Aynı seviyede aynı isim var mı?
        if self._folder_name_exists(contract_id, real_parent, str(folder_data["name"]), exclude_id=int(folder_id)):
            raise ValueError("Hedef klasörde aynı adda bir klasör zaten var.")

        ts = now_iso()
        with self.db.tx():
            self.db.conn.execute(
                "UPDATE contract_file_folders SET parent_id=?, updated_at=? WHERE id=?",
                (real_parent, ts, int(folder_id)),
            )
        self._log(
            "document_folder_moved",
            entity_type="document_folder",
            entity_id=int(folder_id),
            source="Document Manager",
            message="Belge klasörü taşındı",
            before={"parent_id": folder_data.get("parent_id")},
            after={"parent_id": real_parent},
        )
        return True

    def _contract_users(self, contract_id: int) -> List[str]:
        rows = self.db.conn.execute(
            """
            SELECT u.name
            FROM contract_users cu
            JOIN users u ON u.id=cu.user_id
            WHERE cu.contract_id=?
            ORDER BY u.name
            """,
            (int(contract_id),),
        ).fetchall()
        return [str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()]

    def _replace_contract_users(self, contract_id: int, users: List[str]) -> None:
        self.db.conn.execute("DELETE FROM contract_users WHERE contract_id=?", (int(contract_id),))
        for name in users:
            user_id = self.get_user_id(name, create=True)
            if user_id:
                self.db.conn.execute(
                    "INSERT OR IGNORE INTO contract_users(contract_id,user_id) VALUES(?,?)",
                    (int(contract_id), int(user_id)),
                )


    def get_contract_platforms(self, contract_id):
        rows = self.db.conn.execute(
            """
            SELECT cp.platform_id, p.name AS platform_name, cp.sort_order, cp.is_primary
            FROM contract_platforms cp
            JOIN platforms p ON p.id=cp.platform_id
            WHERE cp.contract_id=?
            ORDER BY cp.sort_order ASC, p.name ASC
            """,
            (int(contract_id),),
        ).fetchall()
        if not rows:
            rows = self.db.conn.execute(
                """
                SELECT c.platform_id, p.name AS platform_name, 0 AS sort_order, 1 AS is_primary
                FROM contracts c JOIN platforms p ON p.id=c.platform_id
                WHERE c.id=? AND c.platform_id IS NOT NULL
                """,
                (int(contract_id),),
            ).fetchall()
        return [{"platform_id": int(r[0]), "platform_name": str(r[1] or ""), "sort_order": int(r[2] or 0), "is_primary": bool(r[3])} for r in rows]

    def get_contract_platform_ids(self, contract_id):
        return [int(item["platform_id"]) for item in self.get_contract_platforms(contract_id)]

    def get_primary_contract_platform(self, contract_id):
        rows = self.get_contract_platforms(contract_id)
        for item in rows:
            if item.get("is_primary"):
                return {"platform_id": int(item["platform_id"]), "platform_name": item["platform_name"]}
        row = self.db.conn.execute("SELECT c.platform_id,p.name FROM contracts c LEFT JOIN platforms p ON p.id=c.platform_id WHERE c.id=?", (int(contract_id),)).fetchone()
        if row and row[0] is not None:
            return {"platform_id": int(row[0]), "platform_name": str(row[1] or "")}
        if rows:
            return {"platform_id": int(rows[0]["platform_id"]), "platform_name": rows[0]["platform_name"]}
        return None

    def set_contract_platforms(self, contract_id, platform_ids, primary_platform_id=None):
        cleaned = []
        seen = set()
        for raw in platform_ids or []:
            if raw is None:
                continue
            pid = int(raw)
            if pid not in seen:
                seen.add(pid); cleaned.append(pid)
        if not cleaned:
            raise ValueError("En az bir platform seçilmelidir.")
        primary = int(primary_platform_id or cleaned[0])
        if primary not in cleaned:
            primary = cleaned[0]
        existing = set(int(r[0]) for r in self.db.conn.execute("SELECT platform_id FROM contract_platforms WHERE contract_id=?", (int(contract_id),)))
        for removed in existing - set(cleaned):
            count = self.db.conn.execute("SELECT COUNT(*) FROM systems WHERE contract_id=? AND platform_id=?", (int(contract_id), int(removed))).fetchone()[0]
            if int(count or 0) > 0:
                raise ValueError("Bu platform altında kayıtlı sistemler olduğu için sözleşmeden kaldırılamaz.")
        self.db.conn.execute("UPDATE contracts SET platform_id=? WHERE id=?", (primary, int(contract_id)))
        for order, pid in enumerate(cleaned):
            self.db.conn.execute(
                """
                INSERT INTO contract_platforms(contract_id,platform_id,sort_order,is_primary)
                VALUES(?,?,?,?)
                ON CONFLICT(contract_id,platform_id) DO UPDATE SET sort_order=excluded.sort_order,is_primary=excluded.is_primary
                """,
                (int(contract_id), pid, order, 1 if pid == primary else 0),
            )
        q = ",".join("?" for _ in cleaned)
        self.db.conn.execute(f"DELETE FROM contract_platforms WHERE contract_id=? AND platform_id NOT IN ({q})", [int(contract_id), *cleaned])

    def add_contract_platform(self, contract_id, platform_id, is_primary=False):
        ids = self.get_contract_platform_ids(contract_id)
        if int(platform_id) not in ids:
            ids.append(int(platform_id))
        self.set_contract_platforms(contract_id, ids, int(platform_id) if is_primary else None)

    def remove_contract_platform(self, contract_id, platform_id):
        ids = self.get_contract_platform_ids(contract_id)
        if len(ids) <= 1:
            raise ValueError("Sözleşmede en az bir platform kalmalıdır.")
        if int(platform_id) not in ids:
            return
        count = self.db.conn.execute("SELECT COUNT(*) FROM systems WHERE contract_id=? AND platform_id=?", (int(contract_id), int(platform_id))).fetchone()[0]
        if int(count or 0) > 0:
            raise ValueError("Bu platform altında kayıtlı sistemler olduğu için sözleşmeden kaldırılamaz.")
        remaining = [pid for pid in ids if pid != int(platform_id)]
        primary = self.get_primary_contract_platform(contract_id)
        self.set_contract_platforms(contract_id, remaining, remaining[0] if primary and int(primary["platform_id"]) == int(platform_id) else None)

    def list_systems(self, contract_id, platform_id=None):
        if platform_id is None:
            rows = self.db.conn.execute("SELECT * FROM systems WHERE contract_id=? ORDER BY sort_order,id", (int(contract_id),)).fetchall()
        else:
            rows = self.db.conn.execute("SELECT * FROM systems WHERE contract_id=? AND platform_id=? ORDER BY sort_order,id", (int(contract_id), int(platform_id))).fetchall()
        return [dict(r) for r in rows]

    def list_main_contracts(self, platform, tags_map=None):
        rows=[]; tags_map = tags_map or self.all_contract_tags_map()
        for r in self.db.conn.execute("SELECT c.*,p.name AS platform FROM contracts c JOIN contract_platforms cp ON cp.contract_id=c.id JOIN platforms p ON p.id=cp.platform_id WHERE cp.platform_id=? ORDER BY c.id",(self.get_platform_id(platform),)):
            tags=tags_map.get((r['platform'],r['contract_no'],r['contract_type']),[])
            users = self._contract_users(int(r["id"]))
            user_display = self._user_display(users)
            search_text = str(r["search_text"] or "")
            if users and not search_text:
                search_text = " ".join(users)
            rows.append({
                "id":r["id"],"row":r["id"],"platform":r["platform"],
                "no":r["contract_no"],"contract_no":r["contract_no"],
                "user":user_display,"users":users,
                "type":r["contract_type"],"contract_type":r["contract_type"],
                "type_display":r["type_display"],"link":r["link_type"],"status":r["status"],
                "completion_date":r["completion_date"],"acceptance_date":r["acceptance_date"],"planned_acceptance_date":"","content":r["content"] or r["note"] or "",
                "is_main":bool(r["is_main"]),"tags":list(tags),"search":search_text
            })
        return rows
    def build_contract_index(self, progress_cb=None):
        out=[]; tags=self.all_contract_tags_map()
        for p in self.platform_names(): out.extend(self.list_main_contracts(p,tags_map=tags))
        return out
    def find_main_contract_info(self, platform, contract_no):
        r=self.db.conn.execute("SELECT c.*,p.name AS platform FROM contracts c JOIN contract_platforms cp ON cp.contract_id=c.id JOIN platforms p ON p.id=cp.platform_id WHERE cp.platform_id=? AND c.contract_no=? AND c.is_main=1 LIMIT 1",(self.get_platform_id(platform),contract_no)).fetchone()
        if not r:
            return None
        out = dict(r)
        users = self._contract_users(int(out["id"]))
        out.update({"row": out["id"], "block_start": out["id"], "block_end": out["id"], "user": self._user_display(users), "users": users, "type": out.get("contract_type") or ""})
        return out
    def next_sd_code(self, platform, contract_no):
        c=self.db.conn.execute("SELECT COUNT(*) FROM contracts c JOIN contract_platforms cp ON cp.contract_id=c.id WHERE cp.platform_id=? AND c.contract_no=?",(self.get_platform_id(platform),contract_no)).fetchone()[0]
        return f"SD-{int(c)+1:03d}"

    def _contract_platform_ids_from_info(self, ci) -> list[int]:
        selected_platform_ids: list[int] = []
        for raw in list(getattr(ci, "platform_ids", None) or []):
            try:
                pid = int(raw or 0)
            except Exception:
                pid = 0
            if pid and pid not in selected_platform_ids:
                selected_platform_ids.append(pid)
        if not selected_platform_ids:
            for item in list(getattr(ci, "platforms", None) or []):
                if isinstance(item, dict):
                    pid = int(item.get("platform_id") or item.get("id") or 0)
                    name = str(item.get("platform_name") or item.get("name") or "").strip()
                else:
                    pid = 0
                    name = str(item or "").strip()
                if not pid and name:
                    pid = self.get_platform_id(name, create=True) or 0
                if pid and pid not in selected_platform_ids:
                    selected_platform_ids.append(pid)
        if not selected_platform_ids:
            selected_platform_ids = [
                self.get_platform_id(name, create=True)
                for name in list(getattr(ci, "platform_names", None) or [])
                if str(name or "").strip()
            ]
            selected_platform_ids = [int(pid) for pid in selected_platform_ids if pid is not None]
        if not selected_platform_ids and str(getattr(ci, "platform", "") or "").strip():
            pid = self.get_platform_id(getattr(ci, "platform", ""), create=True)
            if pid is not None:
                selected_platform_ids.append(int(pid))
        return selected_platform_ids

    def write_contract(self, ci, systems, deliveries, old_contract_no=None, old_start_row=None):
        ts=now_iso(); ctype=ci.contract_type
        selected_platform_ids = self._contract_platform_ids_from_info(ci)
        platform_id = int(selected_platform_ids[0]) if selected_platform_ids else self.get_platform_id(ci.platform, create=True)
        if not platform_id:
            raise ValueError("Lütfen en az bir platform seçiniz.")
        users = self._normalize_users(getattr(ci, "users", None), getattr(ci, "user", ""))
        if not users:
            users = self._normalize_users([], getattr(ci, "user", ""))
        user_display = self._user_display(users, getattr(ci, "user", ""))
        responsible_engineer_id = int(getattr(ci, "responsible_engineer_id", 0) or 0)
        if not responsible_engineer_id:
            responsible_ids = list(getattr(ci, "responsible_engineer_ids", []) or [])
            responsible_engineer_id = int(responsible_ids[0] or 0) if responsible_ids else 0
        responsible_engineer_name = str(getattr(ci, "responsible_engineer_name", "") or "").strip()
        if responsible_engineer_id and not responsible_engineer_name:
            row_name = self.db.conn.execute("SELECT full_name FROM staff WHERE id=?", (responsible_engineer_id,)).fetchone()
            responsible_engineer_name = str(row_name[0] or "").strip() if row_name else ""
        search_text = " ".join([str(ci.platform or ""), str(ci.no or ""), str(ctype or ""), str(ci.note or ""), user_display, " ".join(users), responsible_engineer_name]).strip()
        ci.user = user_display; ci.users = users
        ci.responsible_engineer_id = responsible_engineer_id
        ci.responsible_engineer_name = responsible_engineer_name
        row = None
        if int(getattr(ci, "entry_start_row", 0) or 0):
            row = self.db.conn.execute("SELECT id,status,note,completion_date,acceptance_date FROM contracts WHERE id=?", (int(getattr(ci, "entry_start_row", 0) or 0),)).fetchone()
        if not row:
            row=self.db.conn.execute("SELECT id,status,note,completion_date,acceptance_date FROM contracts WHERE platform_id=? AND contract_no=? AND contract_type=?",(platform_id,ci.no,ctype)).fetchone()
        before_contract = {"status": row[1] or "", "note": row[2] or "", "completion_date": row[3] or "", "acceptance_date": row[4] or ""} if row else None
        old_systems = {}
        old_deliveries = {}
        if row:
            for old_system in self.db.conn.execute("SELECT id,name,status,completion_date,acceptance_date FROM systems WHERE contract_id=?", (row[0],)):
                components = {item[0]: float(item[1] or 0) for item in self.db.conn.execute("SELECT c.name,sc.qty FROM system_components sc JOIN components c ON c.id=sc.component_id WHERE sc.system_id=?", (old_system[0],))}
                old_systems[str(old_system[1])] = {"status": old_system[2] or "", "completion_date": old_system[3] or "", "acceptance_date": old_system[4] or "", "components": components}
            for old_delivery in self.db.conn.execute("SELECT d.id,s.name AS delivery_system,d.name,d.status,d.planned_acceptance_date,d.acceptance_date,d.note FROM deliveries d JOIN systems s ON s.id=d.system_id WHERE d.contract_id=?", (row[0],)):
                components = {item[0]: {"planned": float(item[1] or 0), "delivered": float(item[2] or 0)} for item in self.db.conn.execute("SELECT c.name,dc.planned,dc.delivered FROM delivery_components dc JOIN components c ON c.id=dc.component_id WHERE dc.delivery_id=?", (old_delivery[0],))}
                old_deliveries[(str(old_delivery[1]), str(old_delivery[2]))] = {"id": int(old_delivery[0]), "status": old_delivery[3] or "", "planned_acceptance_date": old_delivery[4] or "", "acceptance_date": old_delivery[5] or "", "note": old_delivery[6] or "", "components": components}
        with self.db.tx():
            if row:
                cid=row[0]
                self.db.conn.execute("UPDATE contracts SET yi_yd=?,status=?,signed_date=?,t0_date=?,t0_months=?,completion_date=?,acceptance_date=?,note=?,content=?,search_text=?,responsible_engineer_id=?,updated_at=? WHERE id=?",(ci.yi_yd,ci.status,ci.signature_date,ci.t0_date,int(ci.t0_months or 0),ci.completion_date,ci.acceptance_date,ci.note,ci.note,search_text,responsible_engineer_id or None,ts,cid))
            else:
                cursor = self.db.conn.execute("INSERT INTO contracts(platform_id,contract_no,yi_yd,contract_type,type_display,link_type,status,signed_date,t0_date,t0_months,completion_date,acceptance_date,content,note,is_main,search_text,responsible_engineer_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(platform_id,ci.no,ci.yi_yd,ctype,ctype,"",ci.status,ci.signature_date,ci.t0_date,int(ci.t0_months or 0),ci.completion_date,ci.acceptance_date,ci.note,ci.note,1 if self._normalize_label(ctype)==self._normalize_label('Ana Sözleşme') else 0,search_text,responsible_engineer_id or None,ts,ts))
                cid=cursor.lastrowid
            self._replace_contract_users(int(cid), users)
            self.set_contract_platforms(int(cid), selected_platform_ids or [platform_id], primary_platform_id=platform_id)
            self.set_contract_responsible_engineers(int(cid), [responsible_engineer_id] if responsible_engineer_id else [])

            existing_systems = {str(item[1]): int(item[0]) for item in self.db.conn.execute("SELECT id,name FROM systems WHERE contract_id=? AND COALESCE(platform_id, ?) = ?", (cid, platform_id, platform_id))}
            desired_system_labels = {str(system.name) for system in (systems or [])}
            # Remove deliveries first so deleted acceptances cascade only to their own delivery_components.
            desired_delivery_keys = {(str(sys_name), str(delivery.name)) for sys_name, items in (deliveries or {}).items() for delivery in (items or [])}
            for delivery_row in self.db.conn.execute("SELECT d.id,s.name AS delivery_system,d.name FROM deliveries d JOIN systems s ON s.id=d.system_id WHERE d.contract_id=? AND COALESCE(s.platform_id, ?) = ?", (cid, platform_id, platform_id)).fetchall():
                if (str(delivery_row[1]), str(delivery_row[2])) not in desired_delivery_keys:
                    self.db.conn.execute("DELETE FROM deliveries WHERE id=?", (delivery_row[0],))

            system_ids = {}
            for i,system in enumerate(systems or []):
                payload=json.dumps({"t0_date":system.t0_date,"t0_months":system.t0_months})
                sid=existing_systems.get(str(system.name))
                if sid is None:
                    self.db.conn.execute("INSERT INTO systems(contract_id,platform_id,name,status,completion_date,acceptance_date,note,sort_order,payload_json) VALUES(?,?,?,?,?,?,?,?,?)",(cid,platform_id,system.name,system.status,system.completion_date,system.acceptance_date,"",i,payload))
                    sid=self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    self.db.conn.execute("UPDATE systems SET platform_id=?,name=?,status=?,completion_date=?,acceptance_date=?,sort_order=?,payload_json=? WHERE id=?",(platform_id,system.name,system.status,system.completion_date,system.acceptance_date,i,payload,sid))
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
                if name not in desired_system_labels:
                    self.db.conn.execute("DELETE FROM systems WHERE id=?", (sid,))

            existing_deliveries = {(str(item[1]), str(item[2])): int(item[0]) for item in self.db.conn.execute("SELECT d.id,s.name AS delivery_system,d.name FROM deliveries d JOIN systems s ON s.id=d.system_id WHERE d.contract_id=? AND COALESCE(s.platform_id, ?) = ?", (cid, platform_id, platform_id))}
            for sys_name, dlist in (deliveries or {}).items():
                for i,delivery in enumerate(dlist or []):
                    delivery_user_id = self.get_user_id(getattr(delivery, "delivery_user", ""), create=True)
                    payload=json.dumps({"t0_date":delivery.t0_date,"t0_months":delivery.t0_months,"completion_date":delivery.completion_date})
                    did=existing_deliveries.get((str(sys_name), str(delivery.name)))
                    if did is None:
                        self.db.conn.execute("INSERT INTO deliveries(contract_id,system_id,delivery_user_id,name,status,planned_acceptance_date,acceptance_date,note,sort_order,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)",(cid,system_ids.get(sys_name),delivery_user_id,delivery.name,delivery.status,getattr(delivery,"planned_acceptance_date","") or "",delivery.acceptance_date,delivery.note,i,payload))
                        did=self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    else:
                        self.db.conn.execute("UPDATE deliveries SET system_id=?,delivery_user_id=?,name=?,status=?,planned_acceptance_date=?,acceptance_date=?,note=?,sort_order=?,payload_json=? WHERE id=?",(system_ids.get(sys_name),delivery_user_id,delivery.name,delivery.status,getattr(delivery,"planned_acceptance_date","") or "",delivery.acceptance_date,delivery.note,i,payload,did))
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
        ci.entry_start_row = int(cid or 0)
        setattr(ci, "id", int(cid or 0))
        setattr(ci, "contract_id", int(cid or 0))
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
        new_deliveries = {(str(system_label), str(delivery.name)): {"status": str(delivery.status or ""), "planned_acceptance_date": str(getattr(delivery, "planned_acceptance_date", "") or ""), "acceptance_date": str(delivery.acceptance_date or ""), "note": str(delivery.note or ""), "components": {name: {"planned": float((delivery.planned or {}).get(name, 0) or 0), "delivered": float((delivery.delivered or {}).get(name, 0) or 0)} for name in set((delivery.planned or {})) | set((delivery.delivered or {})) if float((delivery.planned or {}).get(name, 0) or 0) > 0 or float((delivery.delivered or {}).get(name, 0) or 0) > 0}} for system_label, items in (deliveries or {}).items() for delivery in (items or [])}
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

    def load_contract_structure(self, platform, contract_no=None, start_row=None, contract_type=None, platform_id=None):
        # Backward compatible call style remains: load_contract_structure(platform_name, contract_no, ...).
        # New multi-platform detail context passes platform_id so filtering never depends on display names.
        if contract_no is None:
            contract_no = platform
        if contract_type is None and start_row is not None and not str(start_row).isdigit():
            contract_type = str(start_row)
            start_row = None
        active_platform_id = int(platform_id or 0)
        if not active_platform_id:
            active_platform_id = int(self.get_platform_id(platform, create=False) or 0)
        r = None
        if start_row is not None and str(start_row).isdigit():
            r = self.db.conn.execute("SELECT c.*,p.name AS platform FROM contracts c JOIN platforms p ON p.id=c.platform_id WHERE c.id=? LIMIT 1", (int(start_row),)).fetchone()
        if not r and contract_type:
            r = self.db.conn.execute("SELECT c.*,p.name AS platform FROM contracts c JOIN contract_platforms cp ON cp.contract_id=c.id JOIN platforms p ON p.id=cp.platform_id WHERE cp.platform_id=? AND c.contract_no=? AND c.contract_type=? ORDER BY c.id LIMIT 1",(active_platform_id,contract_no,contract_type)).fetchone()
        if not r:
            r=self.db.conn.execute("SELECT c.*,p.name AS platform FROM contracts c JOIN contract_platforms cp ON cp.contract_id=c.id JOIN platforms p ON p.id=cp.platform_id WHERE cp.platform_id=? AND c.contract_no=? ORDER BY c.id LIMIT 1",(active_platform_id,contract_no)).fetchone()
        if not r: raise ValueError("contract not found")
        users = self._contract_users(int(r["id"]))
        user_display = self._user_display(users)
        platform_rows = self.get_contract_platforms(int(r['id']))
        active_name_row = self.db.conn.execute("SELECT name FROM platforms WHERE id=?", (active_platform_id,)).fetchone()
        active_platform_name = str((active_name_row[0] if active_name_row else r['platform']) or "")
        responsible_engineer_id = int(r['responsible_engineer_id'] or 0) if 'responsible_engineer_id' in r.keys() else 0
        responsible_engineer_name = ""
        if responsible_engineer_id:
            staff_row = self.db.conn.execute("SELECT full_name FROM staff WHERE id=?", (responsible_engineer_id,)).fetchone()
            responsible_engineer_name = str(staff_row[0] or "").strip() if staff_row else ""
        ci=ContractInfo(no=r['contract_no'],platform=active_platform_name,user=user_display,yi_yd=r['yi_yd'] or "Yİ",contract_type=r['contract_type'] or "",signature_date=r['signed_date'] or "",t0_date=r['t0_date'] or "",t0_months=int(r['t0_months'] or 0),completion_date=r['completion_date'] or "",status=r['status'] or "PLAN",note=r['note'] or "",acceptance_date=r['acceptance_date'] or "",entry_start_row=int(r['id']),id=int(r['id']),contract_id=int(r['id']),users=users, platform_id=active_platform_id or int(r['platform_id'] or 0), primary_platform_id=int(r['platform_id'] or 0), primary_platform=r['platform'] or '', platforms=platform_rows, platform_names=[x['platform_name'] for x in platform_rows], platform_ids=[int(x['platform_id']) for x in platform_rows], responsible_engineer_id=responsible_engineer_id, responsible_engineer_name=responsible_engineer_name)
        responsible_engineers = ([{"staff_id": responsible_engineer_id, "id": responsible_engineer_id, "full_name": responsible_engineer_name}] if responsible_engineer_id else self.get_contract_responsible_engineers(contract_id=int(r['id'])))
        if responsible_engineers and not responsible_engineer_id:
            responsible_engineer_id = int(responsible_engineers[0]["staff_id"])
            responsible_engineer_name = str(responsible_engineers[0].get("full_name") or "")
            ci.responsible_engineer_id = responsible_engineer_id
            ci.responsible_engineer_name = responsible_engineer_name
        setattr(ci, "responsible_engineers", responsible_engineers[:1])
        setattr(ci, "responsible_engineer_ids", [int(x["staff_id"]) for x in responsible_engineers[:1]])
        systems=[]; deliveries={}
        active_platform_id = active_platform_id or int(r['platform_id'] or 0)
        for s in self.db.conn.execute("SELECT * FROM systems WHERE contract_id=? AND COALESCE(platform_id, ?) = ? ORDER BY sort_order,id",(r['id'], active_platform_id, active_platform_id)):
            component_rows=self.db.conn.execute("SELECT c.name,sc.qty,sc.note FROM system_components sc JOIN components c ON c.id=sc.component_id WHERE sc.system_id=?",(s['id'],)).fetchall()
            comps={x[0]:float(x[1] or 0) for x in component_rows}
            component_notes={x[0]:str(x[2] or "") for x in component_rows if str(x[2] or "")}
            payload=json.loads(s['payload_json'] or "{}")
            si=SystemInfo(name=s['name'],components=comps,component_notes=component_notes,t0_date=payload.get('t0_date',''),t0_months=int(payload.get('t0_months',0) or 0),completion_date=s['completion_date'] or "",status=s['status'] or "Başlanmadı",acceptance_date=s['acceptance_date'] or "")
            systems.append(si)
        for d in self.db.conn.execute("SELECT d.*,s.name AS delivery_system,u.name AS delivery_user FROM deliveries d JOIN systems s ON s.id=d.system_id LEFT JOIN users u ON u.id=d.delivery_user_id WHERE d.contract_id=? AND COALESCE(s.platform_id, ?) = ? ORDER BY s.name,d.sort_order,d.id",(r['id'], active_platform_id, active_platform_id)):
            payload=json.loads(d['payload_json'] or "{}")
            rows=self.db.conn.execute("SELECT c.name,dc.planned,dc.delivered FROM delivery_components dc JOIN components c ON c.id=dc.component_id WHERE dc.delivery_id=?",(d['id'],)).fetchall()
            planned={x[0]:float(x[1] or 0) for x in rows}; delivered={x[0]:float(x[2] or 0) for x in rows}
            di=DeliveryInfo(name=d['name'],status=d['status'] or "",acceptance_date=d['acceptance_date'] or "",note=d['note'] or "",planned_acceptance_date=d['planned_acceptance_date'] or "",planned=planned,delivered=delivered,t0_date=payload.get('t0_date',''),t0_months=int(payload.get('t0_months',0) or 0),completion_date=payload.get('completion_date',''),delivery_user=d['delivery_user'] or "")
            deliveries.setdefault(d['delivery_system'],[]).append(di)
        return ci, systems, deliveries

    def delete_contract(self, platform, contract_no, start_row=None, actor=None, progress_cb=None):
        row=self.db.conn.execute("SELECT id FROM contracts WHERE platform_id=? AND contract_no=? ORDER BY id LIMIT 1",(self.get_platform_id(platform),contract_no)).fetchone()
        if not row: return {"platform":platform,"contract_no":contract_no,"start_row":0,"end_row":0,"deleted_rows":0}
        cid=row[0]
        before = self.db.conn.execute("SELECT contract_no,contract_type,status,completion_date,acceptance_date FROM contracts WHERE id=?", (cid,)).fetchone()
        self.db.conn.execute("DELETE FROM contracts WHERE id=?",(cid,)); self.db.conn.commit()
        self._log("contract_deleted", entity_type="contract", entity_id=cid, platform=str(platform or ""), contract_no=str(contract_no or ""), source="Contract Detail", message="Sözleşme silindi", before=dict(before) if before else None, actor=actor or self.current_actor())
        return {"platform":platform,"contract_no":contract_no,"start_row":cid,"end_row":cid,"deleted_rows":1}
