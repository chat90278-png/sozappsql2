from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from src.domain.agenda.constants import (
    AgendaLifecycleType,
    AgendaPresentationProfileCode,
    AgendaSeverity,
)
from src.domain.agenda.lifecycle import AgendaLifecycleEngine
from src.domain.agenda.models import AgendaContext, AgendaItemState, AgendaPresentationProfile
from src.domain.agenda.providers.returned_share import ReturnedShareAgendaProvider
from src.domain.agenda.source_models import AgendaSourceBundle, ReturnedShareAgendaSource
from src.models.share_models import SHARE_STATUS_MERGED, SHARE_STATUS_RETURNED


NOW = datetime(2026, 7, 12, 12, 0, 0)


def _context() -> AgendaContext:
    profile = AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Personal",
        description="Personal",
        permissions=frozenset({"view_contracts"}),
    )
    return AgendaContext(
        now=NOW,
        today=date(2026, 7, 12),
        presentation_profile=profile,
        staff_id=7,
        permissions=frozenset({"view_contracts"}),
    )


def _source(**overrides) -> ReturnedShareAgendaSource:
    values = {
        "registry_id": 41,
        "share_package_id": "pkg-stable-001",
        "contract_id": 9,
        "contract_merge_uid": "contract-merge-uid",
        "contract_no": "C-9",
        "contract_type": "Ana",
        "platform": "Alpha / Zulu",
        "status": SHARE_STATUS_RETURNED,
        "source_contract_revision": 4,
        "permission_mode": "edit",
        "share_format_version": 2,
        "snapshot_format_version": 1,
        "base_snapshot_sha256": "abc123",
        "created_at": "2026-07-10 09:00:00",
        "created_by_staff_id": 5,
        "created_by_full_name": "Gönderen Personel",
        "exported_filename": "C-9-share.sts",
        "last_imported_at": "2026-07-12 10:00:00",
        "last_imported_by_staff_id": 7,
        "last_remote_snapshot_sha256": "remote456",
        "return_count": 2,
    }
    values.update(overrides)
    return ReturnedShareAgendaSource(**values)


def _build(source: ReturnedShareAgendaSource | None = None):
    bundle = AgendaSourceBundle(returned_shares=(source or _source(),))
    return ReturnedShareAgendaProvider().build(_context(), bundle)


def test_returned_share_builds_condition_item():
    item = _build()[0]
    assert item.kind == "returned_share"
    assert item.lifecycle_type == AgendaLifecycleType.CONDITION
    assert item.title == "C-9 paylaşımı geri döndü"
    assert item.description == "Birleştirme için bekliyor."


def test_non_returned_status_is_skipped():
    assert _build(_source(status=SHARE_STATUS_MERGED)) == ()


def test_key_uses_stable_share_package_id():
    item = _build()[0]
    assert item.key == "returned_share:share_package:pkg-stable-001"
    assert "41" not in item.key


def test_key_does_not_change_when_display_fields_change():
    first = _build()[0]
    second = _build(
        _source(
            contract_no="CHANGED",
            contract_type="Alt",
            platform="Different",
            exported_filename="renamed.sts",
        )
    )[0]
    assert first.key == second.key


def test_version_uses_revision_and_base_hash():
    assert _build()[0].version == "RETURNED:4:abc123"


def test_version_ignores_filename_platform_and_return_count():
    first = _build()[0]
    second = _build(
        _source(exported_filename="other.sts", platform="Other", return_count=99)
    )[0]
    assert first.version == second.version


def test_priority_and_severity():
    item = _build()[0]
    assert item.priority == 850
    assert item.severity == AgendaSeverity.ATTENTION


def test_item_supports_snooze():
    assert _build()[0].supports_snooze is True


def test_item_uses_personal_profile():
    assert _build()[0].presentation_scope == AgendaPresentationProfileCode.PERSONAL


def test_item_carries_contract_identity():
    item = _build()[0]
    assert item.contract_id == 9
    assert item.contract_no == "C-9"
    assert item.contract_type == "Ana"
    assert item.platform == "Alpha / Zulu"
    assert item.system_id is None and item.delivery_id is None


def test_payload_contains_registry_fields():
    payload = _build()[0].detail_payload
    assert payload == {
        "source_type": "share_package",
        "registry_id": 41,
        "share_package_id": "pkg-stable-001",
        "contract_merge_uid": "contract-merge-uid",
        "status": "RETURNED",
        "source_contract_revision": 4,
        "permission_mode": "edit",
        "share_format_version": 2,
        "snapshot_format_version": 1,
        "base_snapshot_sha256": "abc123",
        "created_at": "2026-07-10 09:00:00",
        "created_by_staff_id": 5,
        "created_by_full_name": "Gönderen Personel",
        "exported_filename": "C-9-share.sts",
        "last_imported_at": "2026-07-12 10:00:00",
        "last_imported_by_staff_id": 7,
        "last_remote_snapshot_sha256": "remote456",
        "return_count": 2,
    }


def test_action_hints_only_open_contract():
    assert _build()[0].action_hints == ("open_contract",)


def test_provider_reads_only_returned_share_bundle():
    empty = AgendaSourceBundle()
    assert ReturnedShareAgendaProvider().build(_context(), empty) == ()


def test_seen_returned_share_remains_visible_through_lifecycle():
    item = _build()[0]
    state = AgendaItemState(staff_id=7, agenda_key=item.key, seen_version=item.version)
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert decision.visible is True
    assert decision.is_seen is True
    assert decision.is_new is False


def test_snoozed_returned_share_is_hidden():
    item = _build()[0]
    state = AgendaItemState(
        staff_id=7,
        agenda_key=item.key,
        snoozed_until="2026-07-13 12:00:00",
        snoozed_version=item.version,
        snoozed_severity="ATTENTION",
    )
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert decision.visible is False
    assert decision.reason == "snoozed"


def test_version_change_resurfaces_as_new():
    old_item = _build()[0]
    new_item = _build(replace(_source(), source_contract_revision=5))[0]
    state = AgendaItemState(staff_id=7, agenda_key=old_item.key, seen_version=old_item.version)
    decision = AgendaLifecycleEngine().evaluate(new_item, state, NOW)
    assert new_item.key == old_item.key
    assert new_item.version != old_item.version
    assert decision.visible is True
    assert decision.is_new is True
