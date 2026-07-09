from __future__ import annotations

from typing import Any


def as_number(value: Any) -> float:
    try:
        if callable(value) or isinstance(value, (dict, list, tuple, set)):
            return 0.0
        return float(value or 0)
    except Exception:
        return 0.0


def component_display_keys(system: Any) -> list[str]:
    """Return canonical component names for a system without integer-id assumptions."""
    components = getattr(system, "components", None) or {}
    if not isinstance(components, dict):
        return []
    return [str(name) for name in components.keys()]


def system_component_projection(system: Any, deliveries: list[Any] | None = None) -> list[dict[str, float | str]]:
    """Build the system/component table model from canonical component names.

    Share packages rematerialize local integer ids, so UI projection must not key
    rows by component ids. The stable relation for share display/edit is the
    canonical component name loaded from the current database.
    """
    deliveries = list(deliveries or [])
    rows: list[dict[str, float | str]] = []
    components = getattr(system, "components", None) or {}
    notes = getattr(system, "component_notes", None) or {}
    for name in component_display_keys(system):
        qty = as_number(components.get(name, 0))
        delivered = sum(as_number((getattr(delivery, "delivered", None) or {}).get(name, 0)) for delivery in deliveries)
        rows.append({"component": name, "qty": qty, "delivered": delivered, "remaining": qty - delivered, "note": str(notes.get(name, "") or "")})
    return rows
