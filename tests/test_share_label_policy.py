from src.share_permissions import CONTRACT_SCOPED_SHARE_PERMISSIONS, can_mutate_current_contract
from src.services.share_package_service import parse_share_metadata


def test_edit_share_does_not_grant_manage_labels_capability():
    metadata = parse_share_metadata({
        "share_mode": "true",
        "permission_mode": "edit",
        "source_contract_merge_uid": "contract-1",
    })
    assert "manage_labels" not in CONTRACT_SCOPED_SHARE_PERMISSIONS
    assert not can_mutate_current_contract(
        share_mode=True,
        permission_mode="edit",
        metadata=metadata,
        target_contract={"merge_uid": "contract-1"},
        operation="manage_labels",
    )
