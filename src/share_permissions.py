from __future__ import annotations

from typing import Any

from src.models.share_models import SharePackageMetadata

CONTRACT_SCOPED_SHARE_PERMISSIONS = frozenset({
    "edit_contracts",
    "manage_acceptances",
    "manage_terms",
    "lock_documents",
    "unlock_own_documents",
})


def _text(value: Any) -> str:
    return str(value or "").strip()


def contract_merge_uid(contract: Any) -> str:
    if contract is None:
        return ""
    if isinstance(contract, dict):
        return _text(contract.get("merge_uid") or contract.get("contract_merge_uid"))
    return _text(getattr(contract, "merge_uid", "") or getattr(contract, "contract_merge_uid", ""))


def metadata_from_mapping(raw: Any) -> SharePackageMetadata | None:
    if isinstance(raw, SharePackageMetadata):
        return raw
    if not isinstance(raw, dict):
        return None
    try:
        from src.services.share_package_service import parse_share_metadata
        return parse_share_metadata({str(k): str(v or "") for k, v in raw.items()})
    except Exception:
        return None


def can_mutate_current_contract(*, share_mode: bool, permission_mode: str, metadata: SharePackageMetadata | dict | None, target_contract: Any, operation: str) -> bool:
    """Return whether a share runtime grants a scoped mutation capability.

    This helper is intentionally fail-closed: malformed/missing share metadata,
    view shares, wrong-contract targets, and non-contract/global operations all
    return False. Normal STS authorization is handled by callers before/after
    this share-specific capability check.
    """
    if not share_mode:
        return False
    if _text(permission_mode).lower() != "edit":
        return False
    if _text(operation) not in CONTRACT_SCOPED_SHARE_PERMISSIONS:
        return False
    meta = metadata_from_mapping(metadata)
    if meta is None or not bool(meta.share_mode):
        return False
    if _text(meta.permission_mode).lower() != "edit":
        return False
    source_uid = _text(meta.source_contract_merge_uid)
    target_uid = contract_merge_uid(target_contract)
    if not source_uid or not target_uid:
        return False
    return source_uid == target_uid
