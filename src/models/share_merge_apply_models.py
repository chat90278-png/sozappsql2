from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ShareMergeApplyStatus(str, Enum):
    MERGED = "MERGED"
    PARTIALLY_MERGED = "PARTIALLY_MERGED"
    NO_CHANGE = "NO_CHANGE"


@dataclass(frozen=True)
class ShareMergeApplyIssue:
    code: str
    message: str
    operation_id: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class ShareMergeBackupInfo:
    path: str
    size_bytes: int
    integrity_check: str = ""


@dataclass(frozen=True)
class AppliedMergeOperationResult:
    operation_id: str
    operation_kind: str
    entity_kind: str
    entity_uid: str
    status: str = "APPLIED"
    message: str = ""


@dataclass(frozen=True)
class ShareMergeApplyResult:
    share_package_id: str
    contract_merge_uid: str
    status: ShareMergeApplyStatus
    operations_requested: int
    operations_applied: int
    operations_skipped: int
    operations_failed: int
    applied_operation_ids: list[str] = field(default_factory=list)
    base_snapshot_hash: str = ""
    pre_apply_local_snapshot_hash: str = ""
    remote_snapshot_hash: str = ""
    post_apply_snapshot_hash: str = ""
    operations_hash: str = ""
    backup_path: str = ""
    contract_revision_before: int = 0
    contract_revision_after: int = 0
    registry_status: str = ""
    is_partial: bool = False
    success: bool = True
    warnings: list[str] = field(default_factory=list)
    backup: ShareMergeBackupInfo | None = None
    operation_results: list[AppliedMergeOperationResult] = field(default_factory=list)
