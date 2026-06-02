from __future__ import annotations

from typing import Iterable


EPSILON = 0.0001


def _number(value) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def acceptance_coverage_issues(systems: Iterable[object], deliveries: dict[str, list[object]]) -> list[dict]:
    """Return save-blocking acceptance allocation and delivered quantity issues.

    Allocation uses planned quantities so ongoing partial deliveries remain savable.
    Delivered quantities are checked separately against the system contract quantity.
    Removed deliveries are naturally excluded because the editor removes them from
    the deliveries mapping before save validation runs.
    """
    issues: list[dict] = []
    for system in systems or []:
        system_name = str(getattr(system, "name", "") or "")
        system_deliveries = list((deliveries or {}).get(system_name, []) or [])
        for delivery in system_deliveries:
            for component, raw_delivered_qty in (getattr(delivery, "delivered", {}) or {}).items():
                planned_qty = _number((getattr(delivery, "planned", {}) or {}).get(component, 0))
                delivered_qty = _number(raw_delivered_qty)
                if delivered_qty - planned_qty > EPSILON:
                    issues.append({
                        "kind": "delivery_over_planned",
                        "system": system_name,
                        "delivery": str(getattr(delivery, "name", "") or ""),
                        "component": str(component),
                        "planned_qty": planned_qty,
                        "delivered_qty": delivered_qty,
                        "qty": delivered_qty - planned_qty,
                    })
        for component, raw_contract_qty in (getattr(system, "components", {}) or {}).items():
            contract_qty = _number(raw_contract_qty)
            if contract_qty <= EPSILON:
                continue
            planned_qty = sum(_number((getattr(delivery, "planned", {}) or {}).get(component, 0)) for delivery in system_deliveries)
            delivered_qty = sum(_number((getattr(delivery, "delivered", {}) or {}).get(component, 0)) for delivery in system_deliveries)
            if planned_qty - contract_qty > EPSILON:
                issues.append({
                    "kind": "over_assigned",
                    "system": system_name,
                    "component": str(component),
                    "contract_qty": contract_qty,
                    "planned_qty": planned_qty,
                    "delivered_qty": delivered_qty,
                    "qty": planned_qty - contract_qty,
                })
            if contract_qty - planned_qty > EPSILON:
                issues.append({
                    "kind": "unassigned",
                    "system": system_name,
                    "component": str(component),
                    "contract_qty": contract_qty,
                    "planned_qty": planned_qty,
                    "delivered_qty": delivered_qty,
                    "qty": contract_qty - planned_qty,
                })
            if delivered_qty - contract_qty > EPSILON:
                issues.append({
                    "kind": "over_delivered",
                    "system": system_name,
                    "component": str(component),
                    "contract_qty": contract_qty,
                    "planned_qty": planned_qty,
                    "delivered_qty": delivered_qty,
                    "qty": delivered_qty - contract_qty,
                })
    return issues
