from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.models.share_merge_models import MergeChangeKind, MergeConflictType, MergeEntityKind


class MergeDecisionKind(str, Enum):
    LOCAL_KEEP = "LOCAL_KEEP"
    REMOTE_USE = "REMOTE_USE"
    NO_ACTION = "NO_ACTION"
    SKIP = "SKIP"
    DOCUMENT_KEEP_BOTH = "DOCUMENT_KEEP_BOTH"


class MergeDecisionSource(str, Enum):
    DEFAULT = "DEFAULT"
    USER = "USER"
    POLICY = "POLICY"
    SYSTEM = "SYSTEM"


class MergeDecisionTargetType(str, Enum):
    FIELD = "FIELD"
    ENTITY = "ENTITY"


class MergeOperationKind(str, Enum):
    SET_CONTRACT_FIELD = "SET_CONTRACT_FIELD"
    ADD_SYSTEM = "ADD_SYSTEM"
    DELETE_SYSTEM = "DELETE_SYSTEM"
    SET_SYSTEM_FIELD = "SET_SYSTEM_FIELD"
    SET_SYSTEM_COMPONENT = "SET_SYSTEM_COMPONENT"
    SET_SYSTEM_COMPONENT_NOTE = "SET_SYSTEM_COMPONENT_NOTE"
    ADD_DELIVERY = "ADD_DELIVERY"
    DELETE_DELIVERY = "DELETE_DELIVERY"
    SET_DELIVERY_FIELD = "SET_DELIVERY_FIELD"
    SET_DELIVERY_COMPONENT_FIELD = "SET_DELIVERY_COMPONENT_FIELD"
    ADD_DOCUMENT_FOLDER = "ADD_DOCUMENT_FOLDER"
    DELETE_DOCUMENT_FOLDER = "DELETE_DOCUMENT_FOLDER"
    SET_DOCUMENT_FOLDER_FIELD = "SET_DOCUMENT_FOLDER_FIELD"
    ADD_DOCUMENT_FILE = "ADD_DOCUMENT_FILE"
    DELETE_DOCUMENT_FILE = "DELETE_DOCUMENT_FILE"
    SET_DOCUMENT_FILE_FIELD = "SET_DOCUMENT_FILE_FIELD"
    REPLACE_DOCUMENT_FILE_CONTENT = "REPLACE_DOCUMENT_FILE_CONTENT"
    KEEP_BOTH_DOCUMENT_FILE = "KEEP_BOTH_DOCUMENT_FILE"
    ADD_PLATFORM_RELATION = "ADD_PLATFORM_RELATION"
    DELETE_PLATFORM_RELATION = "DELETE_PLATFORM_RELATION"
    SET_PLATFORM_RELATION_FIELD = "SET_PLATFORM_RELATION_FIELD"
    ADD_USER_RELATION = "ADD_USER_RELATION"
    DELETE_USER_RELATION = "DELETE_USER_RELATION"
    SET_USER_RELATION_FIELD = "SET_USER_RELATION_FIELD"
    ADD_RESPONSIBLE_ENGINEER_RELATION = "ADD_RESPONSIBLE_ENGINEER_RELATION"
    DELETE_RESPONSIBLE_ENGINEER_RELATION = "DELETE_RESPONSIBLE_ENGINEER_RELATION"
    SET_RESPONSIBLE_ENGINEER_RELATION_FIELD = "SET_RESPONSIBLE_ENGINEER_RELATION_FIELD"
    ADD_TAG_RELATION = "ADD_TAG_RELATION"
    DELETE_TAG_RELATION = "DELETE_TAG_RELATION"
    SET_TAG_RELATION_FIELD = "SET_TAG_RELATION_FIELD"


@dataclass(frozen=True)
class MergeDecisionTarget:
    target_id: str
    target_type: MergeDecisionTargetType
    entity_kind: MergeEntityKind
    entity_uid: str
    change_kind: MergeChangeKind
    field_path: str = ""
    field_name: str = ""
    conflict_type: MergeConflictType | None = None


@dataclass(frozen=True)
class MergeDecision:
    target_id: str
    decision: MergeDecisionKind
    source: MergeDecisionSource = MergeDecisionSource.USER

    def to_dict(self) -> dict[str, str]:
        return {"target_id": self.target_id, "decision": self.decision.value, "source": self.source.value}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "MergeDecision":
        return MergeDecision(
            target_id=str(data.get("target_id") or ""),
            decision=MergeDecisionKind(str(data.get("decision") or "")),
            source=MergeDecisionSource(str(data.get("source") or MergeDecisionSource.USER.value)),
        )


@dataclass(frozen=True)
class ResolutionItem:
    target: MergeDecisionTarget
    entity_label: str
    base_value: Any = None
    local_value: Any = None
    remote_value: Any = None
    base_present: bool = True
    local_present: bool = True
    remote_present: bool = True
    default_decision: MergeDecisionKind = MergeDecisionKind.NO_ACTION
    allowed_decisions: tuple[MergeDecisionKind, ...] = ()
    requires_user_decision: bool = False
    is_conflict: bool = False
    reason_code: str = ""


@dataclass(frozen=True)
class MergeOperation:
    operation_id: str
    operation_kind: MergeOperationKind
    entity_kind: MergeEntityKind
    entity_uid: str
    entity_label: str
    source_target_id: str
    field_path: str = ""
    field_name: str = ""
    value: Any = None
    value_present: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MergeResolutionIssue:
    code: str
    message: str
    target_ids: tuple[str, ...] = ()
    severity: str = "ERROR"


@dataclass(frozen=True)
class ResolvedMergePlan:
    contract_merge_uid: str
    base_snapshot_hash: str
    local_snapshot_hash: str
    remote_snapshot_hash: str
    resolution_items: list[ResolutionItem] = field(default_factory=list)
    decisions: list[MergeDecision] = field(default_factory=list)
    operations: list[MergeOperation] = field(default_factory=list)
    issues: list[MergeResolutionIssue] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    operations_hash: str = ""

    @property
    def has_unresolved_conflicts(self) -> bool:
        return any(i.code == "UNRESOLVED_CONFLICT" for i in self.issues)

    @property
    def has_structural_issues(self) -> bool:
        return any(i.code != "UNRESOLVED_CONFLICT" and i.severity == "ERROR" for i in self.issues)

    @property
    def is_partial(self) -> bool:
        return self.has_unresolved_conflicts or any(d.decision == MergeDecisionKind.SKIP for d in self.decisions)

    @property
    def fully_resolved(self) -> bool:
        return not self.has_unresolved_conflicts and not self.has_structural_issues
