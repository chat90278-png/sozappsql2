from __future__ import annotations

from collections.abc import Collection, Sequence

from src.domain.agenda.source_models import (
    AgendaCalendarSource,
    AgendaSourceBundle,
    ReturnedShareAgendaSource,
)
from src.models.share_models import SHARE_STATUS_RETURNED
from src.services.sts_database import STSDatabase


_ENTITY_RANK = {"contract": 0, "system": 1, "delivery": 2}


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed


def _normalize_contract_ids(values: Collection[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        contract_id = _positive_int(value, "contract_id")
        if contract_id in seen:
            continue
        seen.add(contract_id)
        result.append(contract_id)
    return sorted(result)


class AgendaSourceRepository:
    def __init__(self, db: STSDatabase):
        self.db = db
        self.conn = db.conn

    def list_personal_contract_ids(self, staff_id: int) -> frozenset[int]:
        normalized_staff_id = _positive_int(staff_id, "staff_id")
        rows = self.conn.execute(
            """
            SELECT DISTINCT cre.contract_id
            FROM contract_responsible_engineers AS cre
            JOIN staff AS s ON s.id = cre.staff_id
            WHERE cre.staff_id=?
              AND COALESCE(s.is_active,1)=1
            ORDER BY cre.contract_id
            """,
            (normalized_staff_id,),
        ).fetchall()
        return frozenset(int(row[0]) for row in rows)

    def list_all_contract_ids(self) -> frozenset[int]:
        rows = self.conn.execute(
            """
            SELECT id
            FROM contracts
            ORDER BY id
            """
        ).fetchall()
        return frozenset(int(row[0]) for row in rows if int(row[0]) > 0)

    def _platform_names_by_contract(self, ids: Sequence[int]) -> dict[int, tuple[str, ...]]:
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT x.contract_id,p.name
            FROM (
                SELECT cp.contract_id,cp.platform_id
                FROM contract_platforms AS cp
                WHERE cp.contract_id IN ({placeholders})
                UNION ALL
                SELECT c.id AS contract_id,c.platform_id
                FROM contracts AS c
                WHERE c.id IN ({placeholders})
                  AND c.platform_id IS NOT NULL
            ) AS x
            JOIN platforms AS p ON p.id=x.platform_id
            ORDER BY x.contract_id,LOWER(TRIM(p.name)),TRIM(p.name)
            """,
            [*ids, *ids],
        ).fetchall()

        result: dict[int, list[str]] = {}
        seen: dict[int, set[str]] = {}
        for row in rows:
            contract_id = int(row[0])
            name = str(row[1] or "").strip()
            if not name:
                continue
            normalized = name.casefold()
            if normalized in seen.setdefault(contract_id, set()):
                continue
            seen[contract_id].add(normalized)
            result.setdefault(contract_id, []).append(name)
        return {contract_id: tuple(names) for contract_id, names in result.items()}

    def list_calendar_sources(
        self,
        contract_ids: Collection[int],
    ) -> tuple[AgendaCalendarSource, ...]:
        ids = _normalize_contract_ids(contract_ids)
        return self._list_calendar_sources(ids, self._platform_names_by_contract(ids))

    def _list_calendar_sources(
        self,
        ids: Sequence[int],
        platforms_by_contract: dict[int, tuple[str, ...]],
    ) -> tuple[AgendaCalendarSource, ...]:
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)

        contract_rows = self.conn.execute(
            f"""
            SELECT c.id,c.platform_id,c.contract_no,c.contract_type,c.status,
                   c.completion_date,c.acceptance_date,c.note
            FROM contracts AS c
            WHERE c.id IN ({placeholders})
            """,
            list(ids),
        ).fetchall()

        system_rows = self.conn.execute(
            f"""
            SELECT s.id,s.contract_id,c.contract_no,c.contract_type,
                   COALESCE(p.name,''),s.name,s.status,s.completion_date,
                   s.acceptance_date,s.note
            FROM systems AS s
            JOIN contracts AS c ON c.id=s.contract_id
            LEFT JOIN platforms AS p ON p.id=COALESCE(s.platform_id,c.platform_id)
            WHERE s.contract_id IN ({placeholders})
            """,
            list(ids),
        ).fetchall()

        delivery_rows = self.conn.execute(
            f"""
            SELECT d.id,d.system_id,d.contract_id,c.contract_no,c.contract_type,
                   COALESCE(p.name,''),s.name,d.name,d.status,
                   d.acceptance_date,d.planned_acceptance_date,d.note
            FROM deliveries AS d
            JOIN systems AS s ON s.id=d.system_id
            JOIN contracts AS c ON c.id=d.contract_id
            LEFT JOIN platforms AS p ON p.id=COALESCE(s.platform_id,c.platform_id)
            WHERE d.contract_id IN ({placeholders})
            """,
            list(ids),
        ).fetchall()

        sources: list[AgendaCalendarSource] = []
        for row in contract_rows:
            contract_id = int(row[0])
            sources.append(
                AgendaCalendarSource(
                    entity_type="contract",
                    entity_id=contract_id,
                    contract_id=contract_id,
                    platform=" / ".join(platforms_by_contract.get(contract_id, ())),
                    contract_no=row[2],
                    contract_type=row[3],
                    status=row[4],
                    completion_date=row[5],
                    acceptance_date=row[6],
                    note=row[7],
                )
            )
        for row in system_rows:
            sources.append(
                AgendaCalendarSource(
                    entity_type="system",
                    entity_id=int(row[0]),
                    contract_id=int(row[1]),
                    system_id=int(row[0]),
                    contract_no=row[2],
                    contract_type=row[3],
                    platform=row[4],
                    system_name=row[5],
                    status=row[6],
                    completion_date=row[7],
                    acceptance_date=row[8],
                    note=row[9],
                )
            )
        for row in delivery_rows:
            sources.append(
                AgendaCalendarSource(
                    entity_type="delivery",
                    entity_id=int(row[0]),
                    contract_id=int(row[2]),
                    system_id=int(row[1]),
                    delivery_id=int(row[0]),
                    contract_no=row[3],
                    contract_type=row[4],
                    platform=row[5],
                    system_name=row[6],
                    delivery_name=row[7],
                    status=row[8],
                    acceptance_date=row[9],
                    planned_acceptance_date=row[10],
                    note=row[11],
                )
            )

        return tuple(
            sorted(
                sources,
                key=lambda source: (
                    _ENTITY_RANK[source.entity_type],
                    source.contract_no.casefold(),
                    source.system_name.casefold(),
                    source.delivery_name.casefold(),
                    source.entity_id,
                ),
            )
        )

    def list_returned_share_sources(
        self,
        contract_ids: Collection[int],
    ) -> tuple[ReturnedShareAgendaSource, ...]:
        ids = _normalize_contract_ids(contract_ids)
        return self._list_returned_share_sources(ids, self._platform_names_by_contract(ids))

    def _list_returned_share_sources(
        self,
        ids: Sequence[int],
        platforms_by_contract: dict[int, tuple[str, ...]],
    ) -> tuple[ReturnedShareAgendaSource, ...]:
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT sp.id,sp.share_package_id,sp.contract_id,sp.contract_merge_uid,
                   c.contract_no,c.contract_type,sp.status,
                   sp.source_contract_revision,sp.permission_mode,
                   sp.share_format_version,sp.snapshot_format_version,
                   sp.base_snapshot_sha256,sp.created_at,
                   NULLIF(sp.created_by_staff_id,0),sp.created_by_full_name,
                   sp.exported_filename,COALESCE(sp.last_imported_at,''),
                   NULLIF(sp.last_imported_by_staff_id,0),
                   sp.last_remote_snapshot_sha256,sp.return_count
            FROM share_packages AS sp
            JOIN contracts AS c ON c.id=sp.contract_id
            WHERE sp.contract_id IN ({placeholders})
              AND sp.status=?
            ORDER BY c.contract_no COLLATE NOCASE,
                     sp.share_package_id COLLATE NOCASE,
                     sp.id
            """,
            [*ids, SHARE_STATUS_RETURNED],
        ).fetchall()

        return tuple(
            ReturnedShareAgendaSource(
                registry_id=row[0],
                share_package_id=row[1],
                contract_id=row[2],
                contract_merge_uid=row[3],
                contract_no=row[4],
                contract_type=row[5],
                platform=" / ".join(platforms_by_contract.get(int(row[2]), ())),
                status=row[6],
                source_contract_revision=row[7],
                permission_mode=row[8],
                share_format_version=row[9],
                snapshot_format_version=row[10],
                base_snapshot_sha256=row[11],
                created_at=row[12],
                created_by_staff_id=row[13],
                created_by_full_name=row[14],
                exported_filename=row[15],
                last_imported_at=row[16],
                last_imported_by_staff_id=row[17],
                last_remote_snapshot_sha256=row[18],
                return_count=row[19],
            )
            for row in rows
        )

    def load_personal_sources(
        self,
        contract_ids: Collection[int],
    ) -> AgendaSourceBundle:
        ids = _normalize_contract_ids(contract_ids)
        if not ids:
            return AgendaSourceBundle()
        platforms_by_contract = self._platform_names_by_contract(ids)
        return AgendaSourceBundle(
            calendar=self._list_calendar_sources(ids, platforms_by_contract),
            returned_shares=self._list_returned_share_sources(ids, platforms_by_contract),
        )
