# -*- coding: utf-8 -*-
from __future__ import annotations

import calendar
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from src.domain.flexible_date import parse_flexible_date, validate_flexible_date
from src.models.app_models import DeliveryInfo


PLANNED_DATE_LABEL = "Planlanan Kabul Tarihi"
ACTUAL_DATE_LABEL = "Gerçekleşen Kabul Tarihi"


def as_number(v) -> float:
    """DeliveryDialog'un kullandığı sayısal dönüşüm davranışını korur."""
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def fmt_num(v) -> str:
    """DeliveryDialog'daki miktar gösterim formatını korur."""
    try:
        f = float(v or 0)
        return str(int(f)) if f == int(f) else str(round(f, 2))
    except Exception:
        return str(v or "")


def add_months(d: date, months: int) -> date:
    """Ay ekler; hedef ayın son günü gerekiyorsa günü kırpar."""
    month = d.month - 1 + int(months or 0)
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def remaining_qty(planned: float, delivered: float) -> float:
    return max(as_number(planned) - as_number(delivered), 0)


def assignable_remaining(
    system_qty: float,
    assigned_elsewhere: float,
    current_planned: float,
) -> float:
    """system_total - (assigned_elsewhere + current_planned) ortak denklemi."""
    return as_number(system_qty) - (
        as_number(assigned_elsewhere) + as_number(current_planned)
    )


def distributable_target(system_qty: float, assigned_elsewhere: float) -> float:
    """Mevcut fill-all ve fill-remaining akışlarının ortak hedef miktarı."""
    return max(as_number(system_qty) - as_number(assigned_elsewhere), 0)


# Mevcut iki buton akışı aynı formülü kullanıyor; iki isim aynı fonksiyona yönlenir.
fill_all_target = distributable_target
fill_remaining_target = distributable_target


def _norm_status_text(status: str) -> str:
    txt = str(status or "").strip().lower()
    repl = {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
    }
    for source, target in repl.items():
        txt = txt.replace(source, target)
    return " ".join(txt.split())


def is_delivered_status(status: str) -> bool:
    return _norm_status_text(status) in {"teslim edildi", "tamamlandi"}


def planned_remaining_state(
    planned: Dict[str, float],
    delivered: Dict[str, float],
) -> Tuple[bool, List[str]]:
    active_components = [
        comp for comp, qty in planned.items() if max(as_number(qty), 0) > 0.0001
    ]
    remaining = [
        comp
        for comp in active_components
        if remaining_qty(planned.get(comp, 0), delivered.get(comp, 0)) > 0.0001
    ]
    return bool(active_components) and not remaining, remaining


def validate_quantities(
    component_keys,
    planned: Dict[str, float],
    delivered: Dict[str, float],
    system_qty_fn: Callable[[str], float],
    assigned_elsewhere_fn: Callable[[str], float],
) -> List[str]:
    errors: List[str] = []
    for comp in component_keys:
        pv = as_number(planned.get(comp, 0))
        dv = as_number(delivered.get(comp, 0))
        assigned_other = max(as_number(assigned_elsewhere_fn(comp)), 0)
        system_qty = max(as_number(system_qty_fn(comp)), 0)
        if pv + assigned_other > system_qty + 0.0001:
            errors.append(f"{comp}: tanımlanan toplam miktar sistem adedini aşamaz.")
        if dv > pv:
            errors.append(f"{comp}: teslim edilen, teslim edilecekten büyük olamaz.")
    return errors


def validate_status_rules(
    status,
    acceptance_date_text,
    planned_acc_text,
    planned,
    delivered,
) -> List[str]:
    """DeliveryDialog.save içindeki tarih ve durum kurallarını Qt'siz uygular."""
    errors: List[str] = []
    plan_acc_text = str(planned_acc_text or "").strip()
    acc_text = str(acceptance_date_text or "").strip()

    if not plan_acc_text or plan_acc_text == "-":
        errors.append(
            f"{PLANNED_DATE_LABEL} zorunludur. Kesin tarih yazabilir veya belirsizse "
            "TBD / YYYY-MM-TBD / YYYY-TBD-TBD kullanabilirsiniz."
        )
    else:
        ok, message = validate_flexible_date(plan_acc_text, allow_empty=False)
        if not ok:
            errors.append(f"{PLANNED_DATE_LABEL}: {message}")

    ok, message = validate_flexible_date(acc_text, allow_empty=True)
    if not ok:
        errors.append(f"{ACTUAL_DATE_LABEL}: {message}")

    acc_date = parse_flexible_date(acc_text)
    delivered_status = is_delivered_status(status)
    if ok and acc_text and not acc_date and delivered_status:
        errors.append(
            f"Tamamlanan kayıtta {ACTUAL_DATE_LABEL} kesin YYYY-MM-DD olmalıdır. "
            "TBD kabul edilmez."
        )
    if acc_date and acc_date > date.today():
        errors.append(f"{ACTUAL_DATE_LABEL} bugünden ileri olamaz.")

    all_delivered, remaining_components = planned_remaining_state(planned, delivered)
    if delivered_status:
        if not acc_text:
            errors.append(
                f"Durum tamamlandı/teslim edildi olduğunda {ACTUAL_DATE_LABEL} zorunludur."
            )
        if remaining_components:
            errors.append(
                "Durum 'Teslim Edildi' olduğunda bu teslimattaki tüm bileşenlerin kalan değeri 0 olmalıdır.\n\n"
                "Eksik kalan bileşenler:\n• " + "\n• ".join(remaining_components)
            )
    elif all_delivered:
        errors.append(
            "Bu teslimatta tüm bileşenlerin kalanı 0. Kaydetmeden önce Durum alanını 'Teslim Edildi' yapın."
        )

    return errors


def _normalize_identifier(value: object) -> str:
    txt = str(value or "").strip().lower()
    repl = {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
    }
    for source, target in repl.items():
        txt = txt.replace(source, target)
    return txt


def validate_unit_tracking(
    comp: str,
    planned_qty: float,
    units: list,
) -> Optional[str]:
    pv = as_number(planned_qty)
    if pv != int(pv):
        return f"Bu bileşende teslim edilecek adet tam sayı olmalıdır.\n({comp})"

    counts: Dict[str, int] = {}
    for unit in units or []:
        ident = _normalize_identifier((unit or {}).get("identifier", ""))
        if ident:
            counts[ident] = counts.get(ident, 0) + 1
    if any(count > 1 for count in counts.values()):
        return f"{comp}: Aynı kuyruk no / seri no iki kez girilemez. Lütfen düzeltin."
    return None


def split_evenly(available_qty: float, count: int) -> List[float]:
    """AutoAcceptDialog'un mevcut divisible/qty-per-card davranışını korur."""
    count = int(count or 0)
    if count <= 0:
        return []
    available = max(as_number(available_qty), 0)
    divisible = float(available).is_integer() and int(available) % count == 0
    planned = available / count if divisible else 0.0
    return [planned for _ in range(count)]


def build_delivery_info(
    name: str,
    status: str,
    acceptance_date: str,
    note: str,
    planned: Dict[str, float],
    delivered: Dict[str, float],
    t0_date: str = "",
    t0_months: int = 0,
    completion_date: str = "",
    delivery_user: str = "",
    planned_acceptance_date: str = "",
    component_units: Optional[Dict[str, list]] = None,
    merge_uid: str = "",
) -> DeliveryInfo:
    """DeliveryInfo'nun mevcut 13 alanını ortak bir noktadan doldurur."""
    return DeliveryInfo(
        name=name,
        status=status,
        acceptance_date=acceptance_date,
        note=note,
        planned=planned,
        delivered=delivered,
        t0_date=t0_date,
        t0_months=t0_months,
        completion_date=completion_date,
        delivery_user=delivery_user,
        planned_acceptance_date=planned_acceptance_date,
        component_units={} if component_units is None else component_units,
        merge_uid=merge_uid,
    )
