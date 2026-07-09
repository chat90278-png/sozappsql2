from src.models.app_models import DeliveryInfo, SystemInfo
from src.services.share_package_service import parse_share_metadata
from src.share_permissions import can_mutate_current_contract
from src.contract_projection import system_component_projection


def _meta(permission="edit", uid="contract-uid"):
    return parse_share_metadata({
        "share_mode": "true",
        "permission_mode": permission,
        "source_contract_merge_uid": uid,
    })


def _contract(uid="contract-uid"):
    return {"contract_no": "141414", "platform": "P", "merge_uid": uid}


def test_normal_unauthorized_sts_share_capability_does_not_bypass_roles():
    assert not can_mutate_current_contract(
        share_mode=False,
        permission_mode="edit",
        metadata=_meta(),
        target_contract=_contract(),
        operation="edit_contracts",
    )


def test_view_share_system_edit_denied():
    assert not can_mutate_current_contract(
        share_mode=True,
        permission_mode="view",
        metadata=_meta("view"),
        target_contract=_contract(),
        operation="edit_contracts",
    )


def test_edit_share_correct_contract_scoped_actions_allowed():
    for operation in ("edit_contracts", "manage_acceptances", "manage_terms", "manage_labels"):
        assert can_mutate_current_contract(
            share_mode=True,
            permission_mode="edit",
            metadata=_meta(),
            target_contract=_contract(),
            operation=operation,
        )


def test_edit_share_wrong_contract_and_create_delete_denied():
    assert not can_mutate_current_contract(
        share_mode=True,
        permission_mode="edit",
        metadata=_meta(uid="source-contract"),
        target_contract=_contract(uid="other-contract"),
        operation="edit_contracts",
    )
    for operation in ("create_contracts", "delete_contracts"):
        assert not can_mutate_current_contract(
            share_mode=True,
            permission_mode="edit",
            metadata=_meta(),
            target_contract=_contract(),
            operation=operation,
        )


def test_edit_share_does_not_gain_admin_staff_sql_or_global_management():
    for operation in ("manage_staff", "manage_roles", "open_sql_panel", "sql_write", "terminal_full_access", "manage_platforms", "manage_components"):
        assert not can_mutate_current_contract(
            share_mode=True,
            permission_mode="edit",
            metadata=_meta(),
            target_contract=_contract(),
            operation=operation,
        )


def test_share_permission_metadata_missing_or_malformed_fails_closed():
    for metadata in (None, {}, {"share_mode": "true", "permission_mode": "edit"}):
        assert not can_mutate_current_contract(
            share_mode=True,
            permission_mode="edit",
            metadata=metadata,
            target_contract=_contract(),
            operation="edit_contracts",
        )


def test_share_component_projection_uses_canonical_names_not_local_integer_ids():
    system = SystemInfo(
        name="Sistem 1",
        components={"Hava Aracı": 3, "YKİ": 2, "YVT": 2},
    )
    delivery = DeliveryInfo(
        name="Teslimat 1",
        status="PLAN",
        acceptance_date="",
        note="",
        planned={"Hava Aracı": 1, "YKİ": 1, "YVT": 1},
        delivered={"Hava Aracı": 1, "YKİ": 0, "YVT": 0},
    )
    rows = {row["component"]: row for row in system_component_projection(system, [delivery])}
    assert rows["Hava Aracı"]["qty"] == 3
    assert rows["YKİ"]["qty"] == 2
    assert rows["YVT"]["qty"] == 2
    assert rows["Hava Aracı"]["remaining"] == 2


def test_share_component_projection_keeps_second_system_values():
    system = SystemInfo(name="Sistem 2", components={"Hava Aracı": 2, "YKİ": 1, "YVT": 1})
    rows = {row["component"]: row for row in system_component_projection(system, [])}
    assert rows["Hava Aracı"]["qty"] == 2
    assert rows["YKİ"]["qty"] == 1
    assert rows["YVT"]["qty"] == 1
