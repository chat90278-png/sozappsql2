from __future__ import annotations

from datetime import date, datetime

import pytest

from src.domain.agenda.constants import (
    AgendaContractScopeCode,
    AgendaLifecycleType,
    AgendaPresentationProfileCode,
    AgendaSeverity,
)
from src.domain.agenda.keys import build_agenda_key
from src.domain.agenda.models import AgendaContext, AgendaPresentationProfile
from src.domain.agenda.providers.document_lock import DocumentLockAgendaProvider
from src.domain.agenda.source_models import (
    AgendaCalendarSource,
    AgendaSourceBundle,
    DocumentLockAgendaSource,
    ReturnedShareAgendaSource,
)
from src.models.share_models import SHARE_STATUS_RETURNED


NOW = datetime(2026, 7, 13, 10, 30, 0)


def _context(
    permissions=(),
    *,
    staff_id=7,
    role="personnel",
    profile_code=AgendaPresentationProfileCode.PERSONAL,
):
    permission_set = frozenset(permissions)
    profile = AgendaPresentationProfile(
        code=profile_code,
        display_name="Profile",
        description="Profile",
        permissions=permission_set,
    )
    return AgendaContext(
        now=NOW,
        today=date(2026, 7, 13),
        presentation_profile=profile,
        current_staff={"id": staff_id, "role": role, "permissions": permission_set},
        staff_id=staff_id,
        permissions=permission_set,
        contract_scope=AgendaContractScopeCode.RESPONSIBLE,
    )


def _source(
    *,
    contract_id=11,
    owner_id=7,
    owner_name="Ada Lovelace",
    device_name="WS-7",
    is_locked=True,
    locked_at="2026-07-13 09:15:00",
):
    return DocumentLockAgendaSource(
        contract_id=contract_id,
        contract_no=" C-11 ",
        contract_type=" Ana ",
        platform=" Platform A ",
        is_locked=is_locked,
        locked_by_staff_id=owner_id,
        locked_by_device_name=device_name,
        locked_by_full_name=owner_name,
        locked_at=locked_at,
        updated_at=" 2026-07-13 09:20:00 ",
    )


def test_document_lock_source_normalizes_values():
    source = _source(contract_id="11", owner_id="7", is_locked=1)
    assert source.contract_id == 11
    assert source.locked_by_staff_id == 7
    assert source.is_locked is True
    assert source.contract_no == "C-11"
    assert source.contract_type == "Ana"
    assert source.platform == "Platform A"
    assert source.locked_by_device_name == "WS-7"
    assert source.locked_by_full_name == "Ada Lovelace"
    assert source.updated_at == "2026-07-13 09:20:00"


@pytest.mark.parametrize("value", [0, -1, True, False, None, "bad"])
def test_document_lock_source_rejects_invalid_contract_id(value):
    with pytest.raises(ValueError):
        _source(contract_id=value)


@pytest.mark.parametrize("value", [0, -1, True, False, "bad"])
def test_document_lock_source_rejects_invalid_optional_owner_id(value):
    with pytest.raises(ValueError):
        _source(owner_id=value)


def test_document_lock_source_accepts_null_owner_and_false_lock():
    source = _source(owner_id=None, is_locked=0)
    assert source.locked_by_staff_id is None
    assert source.is_locked is False


def test_document_lock_source_rejects_empty_locked_at():
    with pytest.raises(ValueError, match="locked_at"):
        _source(locked_at="  ")


def test_source_bundle_snapshots_document_locks_and_preserves_existing_sources():
    locks = [_source()]
    calendar = AgendaCalendarSource(
        entity_type="contract",
        entity_id=11,
        contract_id=11,
    )
    share = ReturnedShareAgendaSource(
        registry_id=1,
        share_package_id="pkg-1",
        contract_id=11,
        status=SHARE_STATUS_RETURNED,
    )
    bundle = AgendaSourceBundle(
        calendar=[calendar],
        returned_shares=[share],
        document_locks=locks,
    )
    locks.clear()
    assert bundle.calendar == (calendar,)
    assert bundle.returned_shares == (share,)
    assert len(bundle.document_locks) == 1


def test_source_bundle_rejects_wrong_document_lock_type():
    with pytest.raises(TypeError, match="document_locks"):
        AgendaSourceBundle(document_locks=(object(),))


def test_provider_code_is_exact():
    assert DocumentLockAgendaProvider.code == "document_lock"


@pytest.mark.parametrize(
    "permissions,expected",
    [
        ((), False),
        (("view_contracts",), False),
        (("lock_documents",), False),
        (("unlock_own_documents",), True),
        (("unlock_all_documents",), True),
        (("unlock_own_documents", "unlock_all_documents"), True),
    ],
)
def test_provider_capability_is_permission_snapshot_only(permissions, expected):
    assert DocumentLockAgendaProvider().is_enabled(_context(permissions)) is expected


def test_role_name_alone_does_not_enable_provider():
    context = _context((), role="manager", profile_code=AgendaPresentationProfileCode.MANAGEMENT)
    assert DocumentLockAgendaProvider().is_enabled(context) is False


def test_own_permission_matching_stable_staff_id_builds_item():
    item = DocumentLockAgendaProvider().build(
        _context({"unlock_own_documents"}),
        AgendaSourceBundle(document_locks=(_source(owner_id=7),)),
    )[0]
    assert item.reason_text == "OWN_LOCK"
    assert item.description == "Belgeler sizin tarafınızdan kilitlendi."


def test_own_permission_different_staff_id_builds_nothing():
    result = DocumentLockAgendaProvider().build(
        _context({"unlock_own_documents"}, staff_id=7),
        AgendaSourceBundle(document_locks=(_source(owner_id=8),)),
    )
    assert result == ()


def test_same_name_and_device_do_not_count_as_own_without_staff_id_match():
    result = DocumentLockAgendaProvider().build(
        _context({"unlock_own_documents"}, staff_id=7),
        AgendaSourceBundle(
            document_locks=(
                _source(owner_id=8, owner_name="personnel", device_name="personnel"),
            )
        ),
    )
    assert result == ()


def test_null_owner_is_hidden_from_own_only_user():
    result = DocumentLockAgendaProvider().build(
        _context({"unlock_own_documents"}),
        AgendaSourceBundle(document_locks=(_source(owner_id=None),)),
    )
    assert result == ()


def test_null_owner_is_visible_to_unlock_all_user():
    item = DocumentLockAgendaProvider().build(
        _context({"unlock_all_documents"}),
        AgendaSourceBundle(document_locks=(_source(owner_id=None, owner_name=""),)),
    )[0]
    assert item.detail_payload["owner_relation"] == "UNKNOWN"
    assert item.reason_text == "OTHER_LOCK"
    assert item.description == "Belgeler başka bir personel tarafından kilitlendi."


def test_unlock_all_sees_other_owner():
    item = DocumentLockAgendaProvider().build(
        _context({"unlock_all_documents"}, staff_id=7),
        AgendaSourceBundle(document_locks=(_source(owner_id=8, owner_name="Grace Hopper"),)),
    )[0]
    assert item.detail_payload["owner_relation"] == "OTHER"
    assert item.description == "Belgeler Grace Hopper tarafından kilitlendi."


def test_both_permissions_emit_item_once():
    items = DocumentLockAgendaProvider().build(
        _context({"unlock_own_documents", "unlock_all_documents"}),
        AgendaSourceBundle(document_locks=(_source(),)),
    )
    assert len(items) == 1


def test_item_contract_is_exact():
    source = _source()
    item = DocumentLockAgendaProvider().build(
        _context({"unlock_own_documents", "unlock_all_documents"}),
        AgendaSourceBundle(document_locks=(source,)),
    )[0]
    assert item.key == build_agenda_key(
        provider_code="document_lock",
        entity_type="contract",
        entity_id=11,
    )
    assert item.provider_code == "document_lock"
    assert item.kind == "document_lock"
    assert item.lifecycle_type == AgendaLifecycleType.CONDITION
    assert item.priority == 800
    assert item.severity == AgendaSeverity.ATTENTION
    assert item.version == "LOCKED:7:2026-07-13 09:15:00"
    assert item.presentation_scope == AgendaPresentationProfileCode.PERSONAL
    assert item.contract_id == 11
    assert item.platform == "Platform A"
    assert item.contract_no == "C-11"
    assert item.contract_type == "Ana"
    assert item.actor_staff_id == 7
    assert item.actor_name == "Ada Lovelace"
    assert item.event_at == "2026-07-13 09:15:00"
    assert item.effective_date == "2026-07-13 09:15:00"
    assert item.reason_code == "DOCUMENT_LOCKED"
    assert item.reason_text == "OWN_LOCK"
    assert item.action_hints == ("open_contract",)
    assert item.supports_snooze is True
    assert dict(item.detail_payload) == {
        "source_type": "document_lock",
        "contract_id": 11,
        "is_locked": True,
        "locked_by_staff_id": 7,
        "locked_by_device_name": "WS-7",
        "locked_by_full_name": "Ada Lovelace",
        "locked_at": "2026-07-13 09:15:00",
        "updated_at": "2026-07-13 09:20:00",
        "owner_relation": "OWN",
        "can_unlock_own": True,
        "can_unlock_all": True,
    }


def test_title_fallback_when_contract_number_empty():
    source = DocumentLockAgendaSource(
        contract_id=11,
        locked_by_staff_id=7,
        locked_at="2026-07-13 09:15:00",
    )
    item = DocumentLockAgendaProvider().build(
        _context({"unlock_own_documents"}),
        AgendaSourceBundle(document_locks=(source,)),
    )[0]
    assert item.title == "Sözleşme belgeleri kilitli"


def test_inactive_source_and_empty_bundle_produce_no_items():
    provider = DocumentLockAgendaProvider()
    context = _context({"unlock_all_documents"})
    assert provider.build(context, AgendaSourceBundle()) == ()
    assert provider.build(
        context,
        AgendaSourceBundle(document_locks=(_source(is_locked=False),)),
    ) == ()


def test_build_does_not_mutate_context_or_source():
    context = _context({"unlock_all_documents"})
    source = _source(owner_id=8)
    before_permissions = context.permissions
    before_source = source
    DocumentLockAgendaProvider().build(
        context,
        AgendaSourceBundle(document_locks=(source,)),
    )
    assert context.permissions == before_permissions
    assert source == before_source
