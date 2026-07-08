from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ShareHistoryRecord:
    id: int
    share_package_id: str
    contract_id: int
    contract_merge_uid: str
    source_contract_revision: int
    permission_mode: str
    share_format_version: int
    snapshot_format_version: int
    base_snapshot_sha256: str
    created_at: str
    created_by_staff_id: int | None = None
    created_by_username: str = ""
    created_by_full_name: str = ""
    exported_filename: str = ""
    status: str = ""
    last_imported_at: str = ""
    last_imported_by_staff_id: int | None = None
    last_remote_snapshot_sha256: str = ""
    merge_result_sha256: str = ""
    return_count: int = 0


class _ShareHistoryStore(Protocol):
    def list_contract_share_packages(self, contract_merge_uid: str, status: str | None = None) -> list[dict]: ...


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed or None


def _record_from_row(row: dict[str, Any]) -> ShareHistoryRecord:
    return ShareHistoryRecord(
        id=int(row.get("id") or 0),
        share_package_id=str(row.get("share_package_id") or ""),
        contract_id=int(row.get("contract_id") or 0),
        contract_merge_uid=str(row.get("contract_merge_uid") or ""),
        source_contract_revision=int(row.get("source_contract_revision") or 0),
        permission_mode=str(row.get("permission_mode") or ""),
        share_format_version=int(row.get("share_format_version") or 0),
        snapshot_format_version=int(row.get("snapshot_format_version") or 0),
        base_snapshot_sha256=str(row.get("base_snapshot_sha256") or ""),
        created_at=str(row.get("created_at") or ""),
        created_by_staff_id=_int_or_none(row.get("created_by_staff_id")),
        created_by_username=str(row.get("created_by_username") or ""),
        created_by_full_name=str(row.get("created_by_full_name") or ""),
        exported_filename=str(row.get("exported_filename") or ""),
        status=str(row.get("status") or ""),
        last_imported_at=str(row.get("last_imported_at") or ""),
        last_imported_by_staff_id=_int_or_none(row.get("last_imported_by_staff_id")),
        last_remote_snapshot_sha256=str(row.get("last_remote_snapshot_sha256") or ""),
        merge_result_sha256=str(row.get("merge_result_sha256") or ""),
        return_count=int(row.get("return_count") or 0),
    )


def list_contract_share_history(store: _ShareHistoryStore, contract_merge_uid: str) -> list[ShareHistoryRecord]:
    """Return read-only share package history for one stable contract merge UID."""
    uid = str(contract_merge_uid or "").strip()
    if not uid:
        return []
    rows = store.list_contract_share_packages(uid)
    records = [_record_from_row(dict(row)) for row in rows]
    return sorted(records, key=lambda r: (r.created_at or "", r.share_package_id or ""), reverse=True)
