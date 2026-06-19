"""Service package compatibility helpers."""
from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _arg_value(
    args: tuple,
    kwargs: dict,
    names: tuple[str, ...],
    index: int | None = None,
    default: str = "",
):
    for name in names:
        if name in kwargs and kwargs.get(name) not in (None, ""):
            return kwargs.get(name)
    if index is not None and len(args) > index and args[index] not in (None, ""):
        return args[index]
    return default


def _patch_sts_store() -> None:
    try:
        from .sts_database import now_iso
        from .sts_store import STSStore
    except Exception:
        return

    if hasattr(STSStore, "update_linked_sd_contract_numbers"):
        return

    def update_linked_sd_contract_numbers(self, *args, **kwargs) -> int:
        """Update linked SD contract numbers after a main contract number change.

        Some UI flows call this method after editing a contract number. Older
        SQLite-backed stores did not define it, so the whole update failed with
        AttributeError. The signature is intentionally flexible for backward
        compatibility with older dialogs/workers.
        """
        platform = _clean_text(
            _arg_value(args, kwargs, ("platform", "platform_name"), 0)
        )
        old_no = _clean_text(
            _arg_value(
                args,
                kwargs,
                ("old_no", "old_contract_no", "old_contract_number", "source_contract_no"),
                1,
            )
        )
        new_no = _clean_text(
            _arg_value(
                args,
                kwargs,
                ("new_no", "new_contract_no", "new_contract_number", "target_contract_no"),
                2,
            )
        )
        parent_id = (
            kwargs.get("contract_id")
            or kwargs.get("parent_contract_id")
            or kwargs.get("main_contract_id")
        )

        if not old_no or not new_no or old_no == new_no:
            return 0

        conn = getattr(getattr(self, "db", None), "conn", None)
        if conn is None:
            return 0

        def int_or_none(value):
            try:
                number = int(value or 0)
            except Exception:
                return None
            return number if number > 0 else None

        parent_id_int = int_or_none(parent_id)
        if parent_id_int is None and platform:
            try:
                resolver = getattr(self, "_resolve_contract_id", None)
                if callable(resolver):
                    parent_id_int = int_or_none(resolver(platform, old_no, "Ana Sözleşme"))
                    if parent_id_int is None:
                        parent_id_int = int_or_none(resolver(platform, new_no, "Ana Sözleşme"))
            except Exception:
                parent_id_int = None

        params: list[object] = [f"%{old_no}%", "%değiş%", "SD", "%değiş%"]
        where = [
            "c.contract_no LIKE ?",
            "(LOWER(COALESCE(c.contract_type,'')) LIKE ? "
            "OR UPPER(COALESCE(c.contract_type,'')) = ? "
            "OR LOWER(COALESCE(c.link_type,'')) LIKE ?)",
        ]

        if parent_id_int is not None:
            where.append("c.parent_contract_id=?")
            params.append(parent_id_int)
        elif platform:
            where.append(
                "EXISTS ("
                "SELECT 1 FROM contract_platforms cp "
                "JOIN platforms p ON p.id=cp.platform_id "
                "WHERE cp.contract_id=c.id AND p.name=?"
                ")"
            )
            params.append(platform)

        rows = conn.execute(
            f"SELECT c.id, c.contract_no FROM contracts c WHERE {' AND '.join(where)}",
            params,
        ).fetchall()

        changed = 0
        ts = now_iso()
        with conn:
            for row in rows:
                cid = int(row[0])
                current_no = _clean_text(row[1])
                replacement = current_no.replace(old_no, new_no)
                if not replacement or replacement == current_no:
                    continue

                duplicate = conn.execute(
                    """
                    SELECT 1
                    FROM contracts other
                    WHERE other.id<>?
                      AND other.contract_no=?
                      AND COALESCE(other.contract_type,'')=COALESCE((SELECT contract_type FROM contracts WHERE id=?),'')
                      AND EXISTS (
                          SELECT 1 FROM contract_platforms a
                          JOIN contract_platforms b ON b.platform_id=a.platform_id
                          WHERE a.contract_id=other.id AND b.contract_id=?
                      )
                    LIMIT 1
                    """,
                    (cid, replacement, cid, cid),
                ).fetchone()
                if duplicate:
                    continue

                conn.execute(
                    "UPDATE contracts SET contract_no=?, updated_at=? WHERE id=?",
                    (replacement, ts, cid),
                )
                changed += 1

        if changed:
            try:
                log = getattr(self, "_log", None)
                if callable(log):
                    log(
                        "linked_sd_contract_numbers_updated",
                        entity_type="contract",
                        entity_id=parent_id_int,
                        platform=platform,
                        contract_no=new_no,
                        message="Bağlı SD sözleşme numaraları güncellendi",
                        payload={"old_no": old_no, "new_no": new_no, "changed": changed},
                        actor=getattr(self, "current_actor", lambda: "Kullanıcı")(),
                    )
            except Exception:
                pass
        return changed

    STSStore.update_linked_sd_contract_numbers = update_linked_sd_contract_numbers


_patch_sts_store()
