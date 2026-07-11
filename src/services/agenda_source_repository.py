from __future__ import annotations

from collections.abc import Collection

from src.domain.agenda.source_models import AgendaCalendarSource
from src.services.sts_database import STSDatabase


_ENTITY_RANK = {"contract": 0, "system": 1, "delivery": 2}


def _positive_int(value: object, field_name: str) -> int:
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

    def list_calendar_sources(
        self,
        contract_ids: Collection[int],
    ) -> tuple[AgendaCalendarSource, ...]:
        ids = _normalize_contract_ids(contract_ids)
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
            ids,
        ).fetchall()

        platform_rows = self.conn.execute(
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

        platforms_by_contract: dict[int, list[str]] = {}
        seen_platforms: dict[int, set[str]] = {}
        for row in platform_rows:
            contract_id = int(row[0])
            name = str(row[1] or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen_platforms.setdefault(contract_id, set()):
                continue
            seen_platforms[contract_id].add(key)
            platforms_by_contract.setdefault(contract_id, []).append(name)

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
            ids,
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
            ids,
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
