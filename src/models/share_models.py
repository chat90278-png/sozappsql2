from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SHARE_FORMAT_V1 = 1
SHARE_FORMAT_V2 = 2
SUPPORTED_SHARE_FORMATS = {SHARE_FORMAT_V1, SHARE_FORMAT_V2}

SHARE_STATUS_OPEN = "OPEN"
SHARE_STATUS_RETURNED = "RETURNED"
SHARE_STATUS_MERGED = "MERGED"
SHARE_STATUS_PARTIALLY_MERGED = "PARTIALLY_MERGED"
SHARE_STATUS_REJECTED = "REJECTED"
SHARE_STATUS_CANCELLED = "CANCELLED"
SHARE_PACKAGE_STATUSES = {
    SHARE_STATUS_OPEN,
    SHARE_STATUS_RETURNED,
    SHARE_STATUS_MERGED,
    SHARE_STATUS_PARTIALLY_MERGED,
    SHARE_STATUS_REJECTED,
    SHARE_STATUS_CANCELLED,
}


@dataclass(frozen=True)
class SharePackageMetadata:
    raw: dict[str, str]
    share_mode: bool = False
    format_version: int = SHARE_FORMAT_V1
    share_package_id: str = ""
    permission_mode: str = "view"
    source_sts_instance_id: str = ""
    source_schema_version: int = 0
    source_contract_id: int = 0
    source_contract_merge_uid: str = ""
    source_contract_no: str = ""
    base_revision: int = 0
    base_snapshot_sha256: str = ""
    snapshot_format_version: int = 0
    created_at: str = ""
    created_by_staff_id: int = 0
    created_by_username: str = ""
    created_by_full_name: str = ""
    document_count: int = 0
    document_bytes: int = 0


@dataclass(frozen=True)
class ShareBaseSnapshot:
    snapshot_format_version: int
    contract_merge_uid: str
    snapshot_json: str
    snapshot_sha256: str
    created_at: str


@dataclass(frozen=True)
class SharePackageValidationResult:
    is_share_package: bool
    format_version: int = 0
    is_supported: bool = False
    is_valid: bool = False
    supports_merge: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: SharePackageMetadata | None = None


@dataclass(frozen=True)
class SharePackageRegistryEntry:
    share_package_id: str
    contract_id: int
    contract_merge_uid: str
    source_contract_revision: int
    permission_mode: str
    share_format_version: int
    snapshot_format_version: int
    base_snapshot_sha256: str
    created_at: str
    created_by_staff_id: int = 0
    created_by_username: str = ""
    created_by_full_name: str = ""
    exported_filename: str = ""
    status: str = SHARE_STATUS_OPEN
    last_imported_at: str = ""
    last_imported_by_staff_id: int = 0
    last_remote_snapshot_sha256: str = ""
    merge_result_sha256: str = ""
    return_count: int = 0

    def as_db_values(self) -> dict[str, Any]:
        return dict(self.__dict__)
