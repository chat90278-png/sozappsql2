from __future__ import annotations

from functools import wraps
from typing import Iterable

from src.services.sts_store import STSStore

_PATCH_FLAG = "_multiplatform_contract_persistence_patch_installed"
_ORIGINAL_WRITE_ATTR = "_multiplatform_contract_original_write_contract"


def _clean_platform_ids(values: Iterable[object]) -> list[int]:
    cleaned: list[int] = []
    seen: set[int] = set()
    for raw in values or []:
        try:
            platform_id = int(raw or 0)
        except (TypeError, ValueError):
            platform_id = 0
        if platform_id and platform_id not in seen:
            seen.add(platform_id)
            cleaned.append(platform_id)
    return cleaned


def _existing_contract_row(store: STSStore, ci, platform_ids: list[int]) -> tuple[int, int]:
    """Return ``(contract_id, persisted_primary_platform_id)`` when available."""
    contract_id = int(
        getattr(ci, "entry_start_row", 0)
        or getattr(ci, "contract_id", 0)
        or getattr(ci, "id", 0)
        or 0
    )
    if contract_id:
        row = store.db.conn.execute(
            "SELECT id, platform_id FROM contracts WHERE id=? LIMIT 1",
            (contract_id,),
        ).fetchone()
        if row:
            return int(row[0]), int(row[1] or 0)

    contract_no = str(getattr(ci, "no", "") or "").strip()
    contract_type = str(getattr(ci, "contract_type", "") or "").strip()
    if not contract_no or not contract_type or not platform_ids:
        return 0, 0

    placeholders = ",".join("?" for _ in platform_ids)
    try:
        row = store.db.conn.execute(
            f"""
            SELECT DISTINCT c.id, c.platform_id
            FROM contracts c
            JOIN contract_platforms cp ON cp.contract_id=c.id
            WHERE cp.platform_id IN ({placeholders})
              AND c.contract_no=?
              AND c.contract_type=?
            ORDER BY c.id
            LIMIT 1
            """,
            [*platform_ids, contract_no, contract_type],
        ).fetchone()
    except Exception:
        row = None

    if not row:
        for platform_id in platform_ids:
            row = store.db.conn.execute(
                """
                SELECT id, platform_id
                FROM contracts
                WHERE platform_id=? AND contract_no=? AND contract_type=?
                ORDER BY id
                LIMIT 1
                """,
                (platform_id, contract_no, contract_type),
            ).fetchone()
            if row:
                break

    return (int(row[0]), int(row[1] or 0)) if row else (0, 0)


def install_multiplatform_contract_persistence_fix() -> None:
    """Make ``STSStore.write_contract`` write systems to the active platform.

    A contract may be linked to several platforms, while its systems and deliveries
    are platform-scoped. The existing writer chooses the first linked platform as
    its write target. This adapter keeps linked-platform/primary-platform semantics
    intact, but temporarily puts ``ci.platform_id`` first for the platform-scoped
    system and delivery upsert performed by that writer.
    """
    if getattr(STSStore, _PATCH_FLAG, False):
        return

    original_write_contract = STSStore.write_contract
    setattr(STSStore, _ORIGINAL_WRITE_ATTR, original_write_contract)

    def _write_contract_for_active_platform_in_transaction(
        self: STSStore,
        ci,
        systems,
        deliveries,
        old_contract_no=None,
        old_start_row=None,
    ):
        selected_platform_ids = _clean_platform_ids(
            self._contract_platform_ids_from_info(ci)
        )

        try:
            active_platform_id = int(getattr(ci, "platform_id", 0) or 0)
        except (TypeError, ValueError):
            active_platform_id = 0

        if not active_platform_id:
            platform_name = str(getattr(ci, "platform", "") or "").strip()
            if platform_name:
                active_platform_id = int(
                    self.get_platform_id(platform_name, create=True) or 0
                )

        if active_platform_id and active_platform_id not in selected_platform_ids:
            selected_platform_ids.append(active_platform_id)
        if not active_platform_id and selected_platform_ids:
            active_platform_id = selected_platform_ids[0]

        if not selected_platform_ids or not active_platform_id:
            return original_write_contract(
                self,
                ci,
                systems,
                deliveries,
                old_contract_no=old_contract_no,
                old_start_row=old_start_row,
            )

        existing_contract_id, persisted_primary_platform_id = _existing_contract_row(
            self,
            ci,
            selected_platform_ids,
        )
        if existing_contract_id:
            ci.entry_start_row = existing_contract_id

        try:
            requested_primary_platform_id = int(
                getattr(ci, "primary_platform_id", 0) or 0
            )
        except (TypeError, ValueError):
            requested_primary_platform_id = 0

        if persisted_primary_platform_id in selected_platform_ids:
            primary_platform_id = persisted_primary_platform_id
        elif requested_primary_platform_id in selected_platform_ids:
            primary_platform_id = requested_primary_platform_id
        else:
            primary_platform_id = selected_platform_ids[0]

        write_platform_ids = [active_platform_id] + [
            platform_id
            for platform_id in selected_platform_ids
            if platform_id != active_platform_id
        ]
        original_platform_ids = list(getattr(ci, "platform_ids", []) or [])
        ci.platform_ids = write_platform_ids
        ci.platform_id = active_platform_id

        try:
            contract_id = original_write_contract(
                self,
                ci,
                systems,
                deliveries,
                old_contract_no=old_contract_no,
                old_start_row=old_start_row,
            )
        finally:
            ci.platform_ids = original_platform_ids

        if contract_id:
            with self.db.tx():
                self.set_contract_platforms(
                    int(contract_id),
                    selected_platform_ids,
                    primary_platform_id=primary_platform_id,
                )

            platform_rows = self.get_contract_platforms(int(contract_id))
            ci.platforms = platform_rows
            ci.platform_names = [
                str(item.get("platform_name") or "") for item in platform_rows
            ]
            ci.platform_ids = [
                int(item.get("platform_id") or 0)
                for item in platform_rows
                if int(item.get("platform_id") or 0)
            ]
            ci.primary_platform_id = primary_platform_id
            primary_row = next(
                (
                    item
                    for item in platform_rows
                    if int(item.get("platform_id") or 0) == primary_platform_id
                ),
                None,
            )
            if primary_row:
                ci.primary_platform = str(primary_row.get("platform_name") or "")

        return contract_id

    @wraps(original_write_contract)
    def write_contract_for_active_platform(
        self: STSStore,
        ci,
        systems,
        deliveries,
        old_contract_no=None,
        old_start_row=None,
    ):
        # Platform ID creation may start an implicit SQLite transaction before
        # the Activity History writer enters its own db.tx() scope. Own the
        # complete adapter transaction so nested savepoints cannot leave a
        # write lock behind, while caller-owned batch transactions remain in
        # control when one is already active.
        with self.db.tx():
            return _write_contract_for_active_platform_in_transaction(
                self,
                ci,
                systems,
                deliveries,
                old_contract_no=old_contract_no,
                old_start_row=old_start_row,
            )

    STSStore.write_contract = write_contract_for_active_platform
    setattr(STSStore, _PATCH_FLAG, True)
