from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

_EXACT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_TBD_RE = re.compile(r"^(\d{4})-(\d{2})-TBD$")
_YEAR_TBD_RE = re.compile(r"^(\d{4})-TBD-TBD$")

CALENDAR_COUNT_KEYS = ("geciken", "kritik", "tamamlandi", "belirsiz")


def calendar_date_kind(text: str) -> str:
    t = (text or "").strip()
    if not t or t == "-":
        return "na"
    if t == "TBD":
        return "fully_unknown"
    if _EXACT_RE.match(t):
        return "exact"
    if _MONTH_TBD_RE.match(t):
        return "month_unknown_day"
    if _YEAR_TBD_RE.match(t):
        return "year_only"
    return "na"


def parse_calendar_date(text: str) -> Optional[date]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        return datetime.strptime(t, "%Y-%m-%d").date()
    except ValueError:
        return None


def calendar_month_tbd_parts(text: str) -> Optional[Tuple[int, int]]:
    m = _MONTH_TBD_RE.match((text or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def calendar_year_tbd_part(text: str) -> Optional[int]:
    m = _YEAR_TBD_RE.match((text or "").strip())
    if not m:
        return None
    return int(m.group(1))


def calendar_effective_date_raw(item: dict) -> str:
    ctype = str(item.get("type") or "").lower()
    if "teslimat" in ctype:
        acc = str(item.get("acceptance_date") or "").strip()
        if acc and acc != "-":
            return acc
        return str(item.get("planned_acceptance_date") or "").strip()
    return str(item.get("completion_date") or "").strip()


def classify_calendar_event(item: dict, eff: Optional[date], today: date, date_kind: str = "exact") -> str:
    s = str(item.get("status") or "").lower()
    acc_raw = str(item.get("acceptance_date") or "").strip()
    if (acc_raw and acc_raw != "-") or "tamam" in s or "teslim" in s:
        return "tamamlandi"
    if date_kind != "exact" or eff is None:
        return "belirsiz"
    delta = (eff - today).days
    if delta < 0:
        return "geciken"
    if delta <= 60:
        return "kritik"
    return "normal"


def annotate_calendar_events(raw_items: List[dict], today: date) -> List[dict]:
    out: List[dict] = []
    for item in raw_items:
        raw = calendar_effective_date_raw(item)
        kind = calendar_date_kind(raw)
        if kind == "na":
            continue

        eff: Optional[date] = None
        eff_year: Optional[int] = None
        eff_month: Optional[int] = None

        if kind == "exact":
            eff = parse_calendar_date(raw)
            if eff is None:
                continue
            eff_year, eff_month = eff.year, eff.month
        elif kind == "month_unknown_day":
            parts = calendar_month_tbd_parts(raw)
            if parts is None:
                continue
            eff_year, eff_month = parts
        elif kind == "year_only":
            eff_year = calendar_year_tbd_part(raw)
            if eff_year is None:
                continue

        cls = classify_calendar_event(item, eff, today, kind)
        no = str(item.get("no") or "")
        ctype = str(item.get("type") or item.get("contract_type") or "")
        title = str(item.get("title") or item.get("content") or item.get("note") or "")
        if not title:
            title = f"{no} · {ctype}" if ctype else no
        out.append({
            "_eff_date": eff, "_cls": cls,
            "_date_kind": kind,
            "_eff_year": eff_year, "_eff_month": eff_month,
            "_eff_raw": raw,
            "row": int(item.get("row") or 0),
            "delivery_id": item.get("delivery_id"),
            "platform": str(item.get("platform") or ""),
            "no": no, "user": str(item.get("user") or ""),
            "type": ctype, "title": title,
            "system_label": str(item.get("system_label") or ""),
            "status": str(item.get("status") or ""),
            "acceptance_date": str(item.get("acceptance_date") or ""),
            "planned_acceptance_date": str(item.get("planned_acceptance_date") or ""),
            "completion_date": str(item.get("completion_date") or ""),
        })
    return out


def calendar_event_counts(events: List[dict], year: Optional[int] = None) -> Dict[str, int]:
    counts = {key: 0 for key in CALENDAR_COUNT_KEYS}
    for event in events:
        if year is not None:
            kind = event.get("_date_kind", "exact")
            if kind in {"exact", "month_unknown_day", "year_only"} and event.get("_eff_year") != year:
                continue
            # fully_unknown is year-independent and included in each year view.
        cls = event.get("_cls")
        if cls in counts:
            counts[cls] += 1
    return counts


def calendar_events_by_day(events: List[dict], year: int, month: int) -> Dict[int, str]:
    priority = {"geciken": 0, "kritik": 1, "normal": 2, "tamamlandi": 3, "belirsiz": 4}
    by_day: Dict[int, str] = {}
    by_rank: Dict[int, int] = {}
    for event in events:
        if event.get("_date_kind") != "exact":
            continue
        eff = event.get("_eff_date")
        if not eff or eff.year != year or eff.month != month:
            continue
        cls = event.get("_cls")
        if cls not in {"geciken", "kritik", "tamamlandi"}:
            continue
        rank = priority.get(cls, 99)
        day = eff.day
        if day not in by_rank or rank < by_rank[day]:
            by_rank[day] = rank
            by_day[day] = cls
    return by_day


def fetch_calendar_event_sources(conn: sqlite3.Connection, year_from: int, year_to: int, platform_filter: str = "") -> tuple[list, list]:
    yf = str(int(year_from))
    yt = str(int(year_to))
    pf = str(platform_filter or "")
    pc = "AND p.name = ?" if pf else ""

    c_params = [yf, yt, yf, yt]
    if pf:
        c_params.append(pf)
    c_rows = conn.execute(
        "SELECT c.id AS row_id, p.name AS platform,"
        " c.contract_no AS no, c.contract_type AS type,"
        " c.status, c.completion_date, c.acceptance_date,"
        " c.note AS content"
        " FROM contracts c"
        " JOIN contract_platforms cp ON cp.contract_id = c.id"
        " JOIN platforms p           ON p.id = cp.platform_id"
        " WHERE ("
        "   (c.completion_date IS NOT NULL AND c.completion_date != ''  AND ("
        "       SUBSTR(c.completion_date,1,4) BETWEEN ? AND ?"
        "       OR c.completion_date = 'TBD'"
        "       OR c.completion_date LIKE '%-TBD-TBD'"
        "       OR c.completion_date LIKE '%-TBD'))"
        "   OR"
        "   (c.acceptance_date IS NOT NULL AND c.acceptance_date != '' AND ("
        "       SUBSTR(c.acceptance_date,1,4) BETWEEN ? AND ?"
        "       OR c.acceptance_date = 'TBD'"
        "       OR c.acceptance_date LIKE '%-TBD-TBD'"
        "       OR c.acceptance_date LIKE '%-TBD'))"
        " ) " + pc +
        " ORDER BY p.name, c.contract_no",
        c_params,
    ).fetchall()

    contract_events = [
        {
            "row": int(r["row_id"]),
            "platform": str(r["platform"] or ""),
            "no": str(r["no"] or ""),
            "type": str(r["type"] or ""),
            # Bir sözleşme birden fazla platforma bağlıysa (contract_platforms,
            # "paylaşımlı sözleşme" özelliği), aynı sözleşme no'su her platform
            # için ayrı bir kayıt üretir — bu KASITLIDIR. Ama görsel olarak
            # ayırt edilebilmesi için başlığa platform adı açıkça eklenir;
            # aksi halde takvimde aynı sözleşme iki kez, birbirinden
            # ayrılamayan şekilde görünür.
            "title": (
                f"{r['no']} · {r['type']} ({r['platform']})"
                if str(r["platform"] or "") else f"{r['no']} · {r['type']}"
            ),
            "status": str(r["status"] or ""),
            "completion_date": str(r["completion_date"] or ""),
            "acceptance_date": str(r["acceptance_date"] or ""),
            "planned_acceptance_date": "",
            "content": str(r["content"] or ""),
            "user": "",
        }
        for r in c_rows
    ]

    s_params = [yf, yt]
    if pf:
        s_params.append(pf)
    s_rows = conn.execute(
        "SELECT c.id AS contract_row, p.name AS platform,"
        " c.contract_no AS no, s.name AS system_name,"
        " s.status, s.completion_date, s.acceptance_date"
        " FROM systems s"
        " JOIN contracts c   ON c.id = s.contract_id"
        # ÖNEMLİ: platform, sistemin KENDİ platform_id'sinden alınır — bir
        # sözleşme birden fazla platforma bağlıysa (contract_platforms) bile,
        # her sistem sadece TEK bir platforma ait olmalı. Eskiden bu JOIN
        # contract_platforms üzerinden yapılıyordu ve sözleşme 2 platforma
        # bağlıysa her sistem/teslimat 2 kez (bir platform + diğer platform
        # etiketiyle) üretiliyordu — adetler ve kayıtlar ikiye katlanıyordu.
        " JOIN platforms p   ON p.id = COALESCE(s.platform_id, c.platform_id)"
        " WHERE s.completion_date IS NOT NULL AND s.completion_date != '' AND ("
        "   SUBSTR(s.completion_date,1,4) BETWEEN ? AND ?"
        "   OR s.completion_date = 'TBD'"
        "   OR s.completion_date LIKE '%-TBD-TBD'"
        "   OR s.completion_date LIKE '%-TBD'"
        " ) " + pc +
        " ORDER BY p.name, c.contract_no, s.name",
        s_params,
    ).fetchall()

    d_params = [yf, yt, yf, yt]
    if pf:
        d_params.append(pf)
    d_rows = conn.execute(
        "SELECT c.id AS contract_row, d.id AS delivery_id, p.name AS platform,"
        " c.contract_no AS no,"
        " s.name AS system_name, d.name AS delivery_name,"
        " d.status, d.acceptance_date, d.planned_acceptance_date"
        " FROM deliveries d"
        " JOIN systems  s  ON s.id  = d.system_id"
        " JOIN contracts c ON c.id  = d.contract_id"
        # Aynı düzeltme: teslimat, bağlı olduğu sistemin platformunu miras alır.
        " JOIN platforms p ON p.id  = COALESCE(s.platform_id, c.platform_id)"
        " WHERE ("
        "   (d.acceptance_date IS NOT NULL AND d.acceptance_date != '' AND ("
        "       SUBSTR(d.acceptance_date,1,4) BETWEEN ? AND ?"
        "       OR d.acceptance_date = 'TBD'"
        "       OR d.acceptance_date LIKE '%-TBD-TBD'"
        "       OR d.acceptance_date LIKE '%-TBD'))"
        "   OR"
        "   (d.planned_acceptance_date IS NOT NULL AND d.planned_acceptance_date != '' AND ("
        "       SUBSTR(d.planned_acceptance_date,1,4) BETWEEN ? AND ?"
        "       OR d.planned_acceptance_date = 'TBD'"
        "       OR d.planned_acceptance_date LIKE '%-TBD-TBD'"
        "       OR d.planned_acceptance_date LIKE '%-TBD'))"
        " ) " + pc +
        " ORDER BY p.name, c.contract_no, s.name, d.sort_order, d.id",
        d_params,
    ).fetchall()

    system_events: list = []
    for r in s_rows:
        sname = str(r["system_name"] or "")
        no = str(r["no"] or "")
        platform = str(r["platform"] or "")
        # Başlığa platform adını ekle — aynı sözleşme no'su birden fazla
        # platformda görünebildiği için (paylaşımlı sözleşme), pill/kart
        # üzerinde hangi platforma ait olduğu HER ZAMAN net görünmeli.
        label = f"{no} · {sname}" if sname else no
        title = f"{label} ({platform})" if platform else label
        system_events.append({
            "row": int(r["contract_row"]),
            "platform": platform,
            "no": no, "type": "Sistem",
            "system_label": sname,
            "title": title,
            "status": str(r["status"] or ""),
            "completion_date": str(r["completion_date"] or ""),
            "acceptance_date": str(r["acceptance_date"] or ""),
            "planned_acceptance_date": "",
            "user": "",
        })
    for r in d_rows:
        sname = str(r["system_name"] or "")
        dname = str(r["delivery_name"] or "")
        no = str(r["no"] or "")
        platform = str(r["platform"] or "")
        label = f"{no} · {sname} / {dname}" if sname else f"{no} / {dname}"
        title = f"{label} ({platform})" if platform else label
        system_events.append({
            "row": int(r["contract_row"]),
            "delivery_id": int(r["delivery_id"]),
            "platform": platform,
            "no": no, "type": "Teslimat",
            "system_label": sname,
            "title": title,
            "status": str(r["status"] or ""),
            "completion_date": "",
            "acceptance_date": str(r["acceptance_date"] or ""),
            "planned_acceptance_date": str(r["planned_acceptance_date"] or ""),
            "user": "",
        })
    return contract_events, system_events


def build_calendar_summary_from_sources(contract_events: list, system_events: list, today: date, year: int) -> tuple[Dict[str, int], Dict[int, str], List[dict]]:
    all_raw = list(contract_events or []) + list(system_events or [])
    delivery_only = [r for r in all_raw if str(r.get("type") or "").lower() == "teslimat"]
    events = annotate_calendar_events(delivery_only, today)
    counts = calendar_event_counts(events, year=year)
    events_by_day = calendar_events_by_day(events, today.year, today.month)
    return counts, events_by_day, events
