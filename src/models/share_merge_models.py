from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MergeChangeKind(str, Enum):
    UNCHANGED = "UNCHANGED"
    REMOTE_ONLY = "REMOTE_ONLY"
    LOCAL_ONLY = "LOCAL_ONLY"
    SAME_CHANGE = "SAME_CHANGE"
    CONFLICT = "CONFLICT"
    REMOTE_ADDED = "REMOTE_ADDED"
    LOCAL_ADDED = "LOCAL_ADDED"
    SAME_ADDITION = "SAME_ADDITION"
    ADD_ADD_CONFLICT = "ADD_ADD_CONFLICT"
    REMOTE_DELETED = "REMOTE_DELETED"
    LOCAL_DELETED = "LOCAL_DELETED"
    BOTH_DELETED = "BOTH_DELETED"
    REMOTE_UPDATED = "REMOTE_UPDATED"
    LOCAL_UPDATED = "LOCAL_UPDATED"
    SAME_UPDATE = "SAME_UPDATE"
    UPDATE_UPDATE_CONFLICT = "UPDATE_UPDATE_CONFLICT"
    REMOTE_DELETE_LOCAL_UPDATE_CONFLICT = "REMOTE_DELETE_LOCAL_UPDATE_CONFLICT"
    LOCAL_DELETE_REMOTE_UPDATE_CONFLICT = "LOCAL_DELETE_REMOTE_UPDATE_CONFLICT"


class MergeEntityKind(str, Enum):
    CONTRACT = "CONTRACT"
    SYSTEM = "SYSTEM"
    DELIVERY = "DELIVERY"
    DOCUMENT_FOLDER = "DOCUMENT_FOLDER"
    DOCUMENT_FILE = "DOCUMENT_FILE"
    PLATFORM_RELATION = "PLATFORM_RELATION"
    USER_RELATION = "USER_RELATION"
    RESPONSIBLE_ENGINEER_RELATION = "RESPONSIBLE_ENGINEER_RELATION"
    TAG_RELATION = "TAG_RELATION"


class MergeConflictType(str, Enum):
    FIELD_CONFLICT = "FIELD_CONFLICT"
    ADD_ADD_CONFLICT = "ADD_ADD_CONFLICT"
    REMOTE_DELETE_LOCAL_UPDATE = "REMOTE_DELETE_LOCAL_UPDATE"
    LOCAL_DELETE_REMOTE_UPDATE = "LOCAL_DELETE_REMOTE_UPDATE"
    UPDATE_UPDATE_CONFLICT = "UPDATE_UPDATE_CONFLICT"


SUMMARY_KEYS = (
    "unchanged_count",
    "remote_only_count",
    "local_only_count",
    "same_change_count",
    "conflict_count",
    "remote_added_count",
    "local_added_count",
    "remote_deleted_count",
    "local_deleted_count",
    "same_addition_count",
    "both_deleted_count",
    "add_add_conflict_count",
    "delete_update_conflict_count",
    "update_update_conflict_count",
)


@dataclass(frozen=True)
class MergeChange:
    entity_kind: MergeEntityKind
    entity_uid: str
    entity_label: str
    field_path: str
    field_name: str
    base_value: Any = None
    local_value: Any = None
    remote_value: Any = None
    base_present: bool = True
    local_present: bool = True
    remote_present: bool = True
    change_kind: MergeChangeKind = MergeChangeKind.UNCHANGED


@dataclass(frozen=True)
class MergeConflict:
    conflict_type: MergeConflictType
    entity_kind: MergeEntityKind
    entity_uid: str
    entity_label: str
    field_path: str = ""
    field_name: str = ""
    base_value: Any = None
    local_value: Any = None
    remote_value: Any = None
    base_present: bool = True
    local_present: bool = True
    remote_present: bool = True
    reason_code: str = ""


@dataclass(frozen=True)
class MergePlan:
    contract_merge_uid: str
    base_snapshot_hash: str
    local_snapshot_hash: str
    remote_snapshot_hash: str
    changes: list[MergeChange] = field(default_factory=list)
    conflicts: list[MergeConflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @property
    def has_remote_changes(self) -> bool:
        return any(c.change_kind in {MergeChangeKind.REMOTE_ONLY, MergeChangeKind.REMOTE_ADDED, MergeChangeKind.REMOTE_DELETED} for c in self.changes)

    @property
    def has_local_changes(self) -> bool:
        return any(c.change_kind in {MergeChangeKind.LOCAL_ONLY, MergeChangeKind.LOCAL_ADDED, MergeChangeKind.LOCAL_DELETED} for c in self.changes)

    @property
    def safe_remote_change_count(self) -> int:
        return sum(1 for c in self.changes if c.change_kind in {MergeChangeKind.REMOTE_ONLY, MergeChangeKind.REMOTE_ADDED, MergeChangeKind.REMOTE_DELETED, MergeChangeKind.SAME_CHANGE, MergeChangeKind.SAME_ADDITION})
