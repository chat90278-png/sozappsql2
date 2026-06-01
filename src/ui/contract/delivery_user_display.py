from __future__ import annotations


def delivery_user_text(delivery) -> str:
    return str(getattr(delivery, "delivery_user", "") or "").strip() or "-"


def delivery_users_text(deliveries) -> str:
    names = []
    seen = set()
    for delivery in deliveries or []:
        name = str(getattr(delivery, "delivery_user", "") or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return ", ".join(names) or "-"
