from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


class LocalCacheDB:
    """Offline/yerel indeks cache.

    Amaç:
    - Excel'den okunan ana sözleşme listesini SQLite üzerinde tutmak
    - Listeleme/filtreleme/sıralama sorgularını Excel yerine DB'den yapmak
    - Detay kaydında sadece değişen kaydı Excel'e yazıp DB'yi eşitlemek
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA temp_store=MEMORY;

            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                no TEXT NOT NULL,
                user TEXT,
                type TEXT,
                type_display TEXT,
                status TEXT,
                completion_date TEXT,
                content TEXT,
                row_no INTEGER,
                search_norm TEXT,
                day_num INTEGER,
                tags_str TEXT,
                UNIQUE(platform, no, type)
            );

            CREATE INDEX IF NOT EXISTS idx_contracts_platform ON contracts(platform);
            CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
            CREATE INDEX IF NOT EXISTS idx_contracts_completion ON contracts(completion_date);
            CREATE INDEX IF NOT EXISTS idx_contracts_search ON contracts(search_norm);
            """
        )
        self.conn.commit()

    def replace_contracts(self, rows: Iterable[dict]) -> None:
        self.conn.execute("DELETE FROM contracts")
        self.conn.executemany(
            """
            INSERT INTO contracts (
                platform, no, user, type, type_display,
                status, completion_date, content, row_no,
                search_norm, day_num, tags_str
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(r.get("platform", "") or ""),
                    str(r.get("no", "") or ""),
                    str(r.get("user", "") or ""),
                    str(r.get("type", "") or ""),
                    str(r.get("type_display", "") or ""),
                    str(r.get("status", "") or ""),
                    str(r.get("completion_date", "") or ""),
                    str(r.get("content", "") or ""),
                    int(r.get("row", 0) or 0),
                    str(r.get("search", "") or "").lower(),
                    int(r.get("_day_num", 0) or 0) if r.get("_day_num") is not None else None,
                    ", ".join(list(r.get("tags", []) or [])),
                )
                for r in rows
            ],
        )
        self.conn.commit()

    def query_contracts(
        self,
        platform: str,
        search_text: str = "",
        status: str = "",
        sort_mode: str = "default",
        limit: Optional[int] = None,
    ) -> List[sqlite3.Row]:
        where = ["platform = ?"]
        params: List[object] = [platform]

        s = str(search_text or "").strip().lower()
        if s:
            where.append("search_norm LIKE ?")
            params.append(f"%{s}%")

        if status:
            where.append("status = ?")
            params.append(status)

        order = "row_no ASC"
        if sort_mode == "no_asc":
            order = "no ASC"
        elif sort_mode == "no_desc":
            order = "no DESC"
        elif sort_mode == "date_asc":
            order = "completion_date ASC"
        elif sort_mode == "date_desc":
            order = "completion_date DESC"
        elif sort_mode == "days_asc":
            order = "day_num ASC"
        elif sort_mode == "days_desc":
            order = "day_num DESC"

        sql = f"SELECT * FROM contracts WHERE {' AND '.join(where)} ORDER BY {order}"
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(int(limit))

        return list(self.conn.execute(sql, params))

    def close(self) -> None:
        self.conn.close()
