from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .analysis_models import NormalizedAnalysisData
from .analysis_sample_data import build_sample_data
from .analysis_settings import NORMALIZED_DATA_KEYS


def _empty() -> NormalizedAnalysisData:
    return {key: [] for key in NORMALIZED_DATA_KEYS}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not _text(value):
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in {"0", "false", "hayır", "hayir", "no"}


def _row(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


class AnalysisDataLoader:
    """Read-only analiz veri yükleyici.

    Öncelik sırası: .sts/SQLite mode=ro, contract_index benzeri liste, sample veri.
    Çıktı her zaman sabit normalize anahtarları içerir.
    """

    def __init__(self, source: Any = None, contract_index: Optional[Iterable[Mapping[str, Any]]] = None, use_sample: bool = True):
        self.source = source
        self.contract_index = list(contract_index or [])
        self.use_sample = bool(use_sample)
        self.errors: List[str] = []

    def load(self) -> NormalizedAnalysisData:
        data = _empty()
        path = self._path_from_source()
        if path and path.exists():
            try:
                data = self._from_sqlite(path)
            except Exception as exc:
                self.errors.append(f"sqlite:{exc}")
                data = _empty()
        if not self._has_data(data):
            rows = self.contract_index or self._index_from_source()
            if rows:
                try:
                    data = self._from_contract_index(rows)
                except Exception as exc:
                    self.errors.append(f"contract_index:{exc}")
                    data = _empty()
        if not self._has_data(data) and self.use_sample:
            data = build_sample_data()
        data = self._ensure(data)
        data["_meta"] = [{"errors": list(self.errors), "source": self._source_label(path, data)}]
        return data

    def _path_from_source(self) -> Optional[Path]:
        if isinstance(self.source, (str, Path)):
            return Path(self.source)
        for attr in ("path", "db_path", "database_path"):
            value = getattr(self.source, attr, None)
            if value:
                return Path(value)
        store = getattr(self.source, "store", None)
        value = getattr(store, "path", None) if store is not None else None
        return Path(value) if value else None

    def _index_from_source(self) -> List[Mapping[str, Any]]:
        for attr in ("contract_index", "contracts", "index"):
            value = getattr(self.source, attr, None)
            if isinstance(value, list):
                return value
        return []

    @staticmethod
    def _ensure(data: NormalizedAnalysisData) -> NormalizedAnalysisData:
        out = {key: list(data.get(key, [])) for key in NORMALIZED_DATA_KEYS}
        if "_meta" in data:
            out["_meta"] = list(data.get("_meta", []))
        return out

    @staticmethod
    def _has_data(data: NormalizedAnalysisData) -> bool:
        return bool(data.get("contracts") or data.get("platforms") or data.get("acceptances"))

    def _source_label(self, path: Optional[Path], data: NormalizedAnalysisData) -> str:
        if path and data.get("contracts"):
            return "sqlite_read_only"
        if self.contract_index or self._index_from_source():
            return "contract_index"
        return "sample" if self.use_sample else "empty"

    @staticmethod
    def _table(conn: sqlite3.Connection, name: str) -> bool:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    def _cols(self, conn: sqlite3.Connection, name: str) -> set[str]:
        if not self._table(conn, name):
            return set()
        return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{name}")')}

    def _from_sqlite(self, path: Path) -> NormalizedAnalysisData:
        conn = _readonly_connect(path)
        try:
            data = _empty()
            data["platforms"] = self._read_platforms(conn)
            data["users"] = self._read_users(conn)
            data["components"] = self._read_components(conn)
            data["contracts"] = self._read_contracts(conn)
            data["systems"] = self._read_systems(conn, data["contracts"])
            data["acceptances"] = self._read_acceptances(conn, data["contracts"], data["systems"])
            data["tags"] = self._read_tags(conn)
            self._attach_tags(conn, data["contracts"])
            data["deadlines"] = self._deadlines(data)
            data["health_items"] = self._health(data)
            return data
        finally:
            conn.close()

    def _read_platforms(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        if not self._table(conn, "platforms"):
            return []
        cols = self._cols(conn, "platforms")
        display = "display_name" if "display_name" in cols else "name"
        active = "is_active" if "is_active" in cols else "1"
        order = "sort_order,name" if "sort_order" in cols else "name"
        rows = conn.execute(f"SELECT id,name,{display} AS display_name,{active} AS is_active FROM platforms ORDER BY {order}").fetchall()
        return [{"id": r["id"], "name": _text(r["name"]), "display_name": _text(r["display_name"]) or _text(r["name"]), "is_active": _bool(r["is_active"])} for r in rows if _text(r["name"])]

    def _read_users(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        if not self._table(conn, "users"):
            return []
        cols = self._cols(conn, "users")
        yi = "yi_yd" if "yi_yd" in cols else "'Yİ'"
        active = "active" if "active" in cols else "1"
        return [{"id": r["id"], "name": _text(r["name"]), "yi_yd": _text(r["yi_yd"]), "active": _bool(r["active"])} for r in conn.execute(f"SELECT id,name,{yi} AS yi_yd,{active} AS active FROM users ORDER BY name") if _text(r["name"])]

    def _read_components(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        if not self._table(conn, "components"):
            return []
        cols = self._cols(conn, "components")
        version = "version" if "version" in cols else "''"
        unit = "unit" if "unit" in cols else "'Adet'"
        active = "active" if "active" in cols else "1"
        return [{"id": r["id"], "name": _text(r["name"]), "version": _text(r["version"]), "unit": _text(r["unit"]) or "Adet", "active": _bool(r["active"])} for r in conn.execute(f"SELECT id,name,{version} AS version,{unit} AS unit,{active} AS active FROM components ORDER BY name") if _text(r["name"])]

    def _read_contracts(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        if not self._table(conn, "contracts"):
            return []
        cols = self._cols(conn, "contracts")
        sql = "SELECT c.*,p.name AS platform_name FROM contracts c LEFT JOIN platforms p ON p.id=c.platform_id ORDER BY c.id" if "platform_id" in cols and self._table(conn, "platforms") else "SELECT c.* FROM contracts c ORDER BY c.id"
        user_map = self._contract_users(conn)
        out = []
        for raw_row in conn.execute(sql).fetchall():
            r = _row(raw_row)
            cid = int(r.get("id") or 0)
            users = user_map.get(cid, [])
            fallback_user = _text(r.get("user_name") or r.get("user"))
            if not users and fallback_user:
                users = [fallback_user]
            out.append({"id": r.get("id"), "platform": _text(r.get("platform_name") or r.get("platform") or r.get("platform_id")), "contract_no": _text(r.get("contract_no") or r.get("no")), "contract_type": _text(r.get("contract_type") or r.get("type")), "type_display": _text(r.get("type_display") or r.get("contract_type") or r.get("type")), "status": _text(r.get("status")), "signed_date": _text(r.get("signed_date")), "t0_date": _text(r.get("t0_date")), "t0_months": int(r.get("t0_months") or 0) if str(r.get("t0_months") or "").isdigit() else 0, "completion_date": _text(r.get("completion_date")), "acceptance_date": _text(r.get("acceptance_date")), "content": _text(r.get("content") or r.get("note")), "is_main": _bool(r.get("is_main"), True), "users": users, "user": ", ".join(users), "tags": []})
        return out

    def _contract_users(self, conn: sqlite3.Connection) -> Dict[int, List[str]]:
        if not (self._table(conn, "contract_users") and self._table(conn, "users")):
            return {}
        out: Dict[int, List[str]] = {}
        try:
            rows = conn.execute("SELECT cu.contract_id,u.name FROM contract_users cu JOIN users u ON u.id=cu.user_id ORDER BY u.name").fetchall()
        except sqlite3.DatabaseError:
            return {}
        for contract_id, name in rows:
            if _text(name):
                out.setdefault(int(contract_id or 0), []).append(_text(name))
        return out

    @staticmethod
    def _contract_by_id(contracts: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        return {int(item.get("id") or 0): item for item in contracts if item.get("id") is not None}

    def _read_systems(self, conn: sqlite3.Connection, contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self._table(conn, "systems"):
            return []
        contract_map = self._contract_by_id(contracts)
        out = []
        for raw_row in conn.execute("SELECT * FROM systems ORDER BY contract_id,sort_order,id").fetchall():
            r = _row(raw_row)
            contract = contract_map.get(int(r.get("contract_id") or 0), {})
            payload = _json(r.get("payload_json"))
            out.append({"id": r.get("id"), "contract_id": r.get("contract_id"), "platform": contract.get("platform", ""), "contract_no": contract.get("contract_no", ""), "name": _text(r.get("name")), "status": _text(r.get("status")), "completion_date": _text(r.get("completion_date")), "acceptance_date": _text(r.get("acceptance_date")), "t0_date": _text(payload.get("t0_date")), "t0_months": int(payload.get("t0_months") or 0) if str(payload.get("t0_months") or "").isdigit() else 0})
        return out

    def _read_acceptances(self, conn: sqlite3.Connection, contracts: List[Dict[str, Any]], systems: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self._table(conn, "deliveries"):
            return []
        contract_map = self._contract_by_id(contracts)
        system_map = {int(item.get("id") or 0): item for item in systems if item.get("id") is not None}
        totals = self._delivery_totals(conn)
        out = []
        for raw_row in conn.execute("SELECT * FROM deliveries ORDER BY contract_id,sort_order,id").fetchall():
            r = _row(raw_row)
            contract = contract_map.get(int(r.get("contract_id") or 0), {})
            system = system_map.get(int(r.get("system_id") or 0), {})
            payload = _json(r.get("payload_json"))
            total = totals.get(int(r.get("id") or 0), {})
            out.append({"id": r.get("id"), "contract_id": r.get("contract_id"), "system_id": r.get("system_id"), "platform": contract.get("platform", ""), "contract_no": contract.get("contract_no", ""), "system_name": system.get("name") or _text(r.get("system_name")), "name": _text(r.get("name")), "status": _text(r.get("status")), "acceptance_date": _text(r.get("acceptance_date")), "completion_date": _text(payload.get("completion_date")), "planned_total": total.get("planned_total", 0.0), "delivered_total": total.get("delivered_total", 0.0)})
        return out

    def _delivery_totals(self, conn: sqlite3.Connection) -> Dict[int, Dict[str, float]]:
        if not self._table(conn, "delivery_components"):
            return {}
        cols = self._cols(conn, "delivery_components")
        if not {"delivery_id", "planned", "delivered"}.issubset(cols):
            return {}
        rows = conn.execute("SELECT delivery_id,SUM(COALESCE(planned,0)) AS planned_total,SUM(COALESCE(delivered,0)) AS delivered_total FROM delivery_components GROUP BY delivery_id").fetchall()
        return {int(r["delivery_id"] or 0): {"planned_total": _float(r["planned_total"]), "delivered_total": _float(r["delivered_total"])} for r in rows}

    def _read_tags(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        if not self._table(conn, "tags"):
            return []
        cols = self._cols(conn, "tags")
        color = "color" if "color" in cols else "'#3B82F6'"
        return [{"id": r["id"], "name": _text(r["name"]), "color": _text(r["color"]) or "#3B82F6", "contract_count": 0} for r in conn.execute(f"SELECT id,name,{color} AS color FROM tags ORDER BY name") if _text(r["name"])]

    def _attach_tags(self, conn: sqlite3.Connection, contracts: List[Dict[str, Any]]) -> None:
        if not (self._table(conn, "contract_tags") and contracts):
            return
        cols = self._cols(conn, "contract_tags")
        by_id = {int(item.get("id") or 0): item for item in contracts if item.get("id") is not None}
        try:
            rows = conn.execute("SELECT ct.contract_id,t.name FROM contract_tags ct JOIN tags t ON t.id=ct.tag_id ORDER BY t.name").fetchall() if "tag_id" in cols and self._table(conn, "tags") else conn.execute("SELECT contract_id,tag_name FROM contract_tags ORDER BY tag_name").fetchall() if "tag_name" in cols else []
        except sqlite3.DatabaseError:
            rows = []
        for contract_id, tag_name in rows:
            target = by_id.get(int(contract_id or 0))
            if target is not None and _text(tag_name):
                target.setdefault("tags", []).append(_text(tag_name))

    def _deadlines(self, data: NormalizedAnalysisData) -> List[Dict[str, Any]]:
        rows = []
        for source_key, entity, name_key in (("contracts", "contract", "contract_type"), ("systems", "system", "name"), ("acceptances", "acceptance", "name")):
            for item in data.get(source_key, []):
                due = _text(item.get("completion_date"))
                if due:
                    rows.append({"entity": entity, "platform": item.get("platform", ""), "contract_no": item.get("contract_no", ""), "name": item.get(name_key) or entity, "due_date": due, "status": item.get("status", "")})
        return rows

    def _health(self, data: NormalizedAnalysisData) -> List[Dict[str, Any]]:
        out = []
        systems_by_contract: Dict[Any, int] = {}
        for system in data.get("systems", []):
            systems_by_contract[system.get("contract_id")] = systems_by_contract.get(system.get("contract_id"), 0) + 1
        for contract in data.get("contracts", []):
            platform = _text(contract.get("platform")); no = _text(contract.get("contract_no"))
            for field, label in (("platform", "Eksik platform bilgisi"), ("contract_no", "Eksik sözleşme numarası"), ("status", "Eksik durum bilgisi"), ("completion_date", "Eksik termin tarihi"), ("user", "Eksik kullanıcı bilgisi")):
                if not _text(contract.get(field)):
                    out.append({"entity": "contract", "platform": platform, "contract_no": no, "field": field, "label": label})
            if not contract.get("tags"):
                out.append({"entity": "contract", "platform": platform, "contract_no": no, "field": "tags", "label": "Etiketsiz kayıt"})
            if contract.get("id") is not None and systems_by_contract.get(contract.get("id"), 0) == 0:
                out.append({"entity": "contract", "platform": platform, "contract_no": no, "field": "systems", "label": "Sistem kaydı yok"})
        return out

    def _from_contract_index(self, rows: Iterable[Mapping[str, Any]]) -> NormalizedAnalysisData:
        data = _empty()
        platforms: Dict[str, Dict[str, Any]] = {}
        tag_counts: Dict[str, int] = {}
        for idx, raw_item in enumerate(rows, start=1):
            item = dict(raw_item)
            platform = _text(item.get("platform"))
            tags = [_text(t.get("name") if isinstance(t, dict) else t) for t in list(item.get("tags") or [])]
            tags = [tag for tag in tags if tag]
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if platform:
                platforms.setdefault(platform, {"id": None, "name": platform, "display_name": platform, "is_active": True})
            data["contracts"].append({"id": item.get("id") or item.get("row") or idx, "platform": platform, "contract_no": _text(item.get("contract_no") or item.get("no")), "contract_type": _text(item.get("contract_type") or item.get("type")), "type_display": _text(item.get("type_display") or item.get("type")), "status": _text(item.get("status")), "completion_date": _text(item.get("completion_date")), "acceptance_date": _text(item.get("acceptance_date")), "content": _text(item.get("content")), "is_main": _bool(item.get("is_main"), True), "users": list(item.get("users") or ([_text(item.get("user"))] if _text(item.get("user")) else [])), "user": _text(item.get("user")), "tags": tags})
        data["platforms"] = list(platforms.values())
        data["tags"] = [{"id": None, "name": name, "color": "#3B82F6", "contract_count": count} for name, count in sorted(tag_counts.items())]
        data["deadlines"] = self._deadlines(data)
        data["health_items"] = self._health(data)
        return data


def load_analysis_data(source: Any = None, contract_index: Optional[Iterable[Mapping[str, Any]]] = None, use_sample: bool = True) -> NormalizedAnalysisData:
    return AnalysisDataLoader(source=source, contract_index=contract_index, use_sample=use_sample).load()
