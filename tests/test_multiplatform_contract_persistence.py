from __future__ import annotations

import copy

from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.services.multiplatform_contract_persistence import (
    install_multiplatform_contract_persistence_fix,
)
from src.services.sts_store import STSStore


def _contract_info(
    *,
    platform: str,
    platform_id: int,
    primary_platform_id: int,
    platform_ids: list[int],
    platform_names: list[str],
) -> ContractInfo:
    return ContractInfo(
        no="MP-001",
        platform=platform,
        user="DENEME",
        yi_yd="Yİ",
        contract_type="Ana Sözleşme",
        signature_date="2026-07-01",
        t0_date="2026-07-01",
        t0_months=12,
        completion_date="2027-07-01",
        platform_id=platform_id,
        primary_platform_id=primary_platform_id,
        platform_ids=list(platform_ids),
        platform_names=list(platform_names),
        platforms=[
            {
                "platform_id": pid,
                "platform_name": name,
                "is_primary": pid == primary_platform_id,
            }
            for pid, name in zip(platform_ids, platform_names)
        ],
    )


def _system_and_delivery(qty: float, delivered: float):
    system = SystemInfo(
        name="Sistem 1",
        components={"Hava Aracı": qty},
    )
    delivery = DeliveryInfo(
        name="Teslimat 1",
        status="Teslim Edildi" if delivered == qty else "Başlanmadı",
        acceptance_date="2026-07-08" if delivered else "",
        note="",
        planned={"Hava Aracı": qty},
        delivered={"Hava Aracı": delivered},
    )
    return [system], {system.name: [delivery]}


def test_multi_platform_writes_are_isolated_by_active_platform(tmp_path):
    install_multiplatform_contract_persistence_fix()
    store = STSStore(tmp_path / "multi-platform.sts")
    try:
        store.create_platform("SİVRİSİNEK")
        store.create_platform("AKINCI")
        siv_id = int(store.get_platform_id("SİVRİSİNEK") or 0)
        akin_id = int(store.get_platform_id("AKINCI") or 0)

        ci = _contract_info(
            platform="SİVRİSİNEK",
            platform_id=siv_id,
            primary_platform_id=siv_id,
            platform_ids=[siv_id, akin_id],
            platform_names=["SİVRİSİNEK", "AKINCI"],
        )
        systems, deliveries = _system_and_delivery(6, 6)
        contract_id = store.write_contract(ci, systems, deliveries)

        akin_ci, akin_systems, akin_deliveries = store.load_contract_structure(
            "AKINCI",
            contract_no=ci.no,
            start_row=contract_id,
            contract_type=ci.contract_type,
            platform_id=akin_id,
        )
        assert akin_systems == []
        assert akin_deliveries == {}

        akin_systems, akin_deliveries = _system_and_delivery(2, 0)
        store.write_contract(akin_ci, akin_systems, akin_deliveries)

        _, siv_systems, siv_deliveries = store.load_contract_structure(
            "SİVRİSİNEK",
            contract_no=ci.no,
            start_row=contract_id,
            contract_type=ci.contract_type,
            platform_id=siv_id,
        )
        _, reloaded_akin_systems, reloaded_akin_deliveries = store.load_contract_structure(
            "AKINCI",
            contract_no=ci.no,
            start_row=contract_id,
            contract_type=ci.contract_type,
            platform_id=akin_id,
        )

        assert siv_systems[0].components == {"Hava Aracı": 6.0}
        assert siv_deliveries["Sistem 1"][0].delivered == {"Hava Aracı": 6.0}
        assert reloaded_akin_systems[0].components == {"Hava Aracı": 2.0}
        assert reloaded_akin_deliveries["Sistem 1"][0].delivered == {"Hava Aracı": 0.0}
        assert store.get_primary_contract_platform(contract_id) == {
            "platform_id": siv_id,
            "platform_name": "SİVRİSİNEK",
        }
    finally:
        store.db.close()


def test_new_linked_platform_does_not_clone_current_platform_structure(tmp_path):
    install_multiplatform_contract_persistence_fix()
    store = STSStore(tmp_path / "linked-platform.sts")
    try:
        store.create_platform("SİVRİSİNEK")
        store.create_platform("AKINCI")
        siv_id = int(store.get_platform_id("SİVRİSİNEK") or 0)
        akin_id = int(store.get_platform_id("AKINCI") or 0)

        ci = _contract_info(
            platform="SİVRİSİNEK",
            platform_id=siv_id,
            primary_platform_id=siv_id,
            platform_ids=[siv_id],
            platform_names=["SİVRİSİNEK"],
        )
        systems, deliveries = _system_and_delivery(6, 6)
        contract_id = store.write_contract(ci, systems, deliveries)

        ci.platform_ids = [siv_id, akin_id]
        ci.platform_names = ["SİVRİSİNEK", "AKINCI"]
        ci.platforms = [
            {"platform_id": siv_id, "platform_name": "SİVRİSİNEK", "is_primary": True},
            {"platform_id": akin_id, "platform_name": "AKINCI", "is_primary": False},
        ]
        store.write_contract(ci, systems, deliveries)

        # ContractWorkWindow.edit_contract_info currently performs this extra
        # compatibility write for each newly linked platform. platform_id still
        # identifies the current tab; the new platform must stay empty.
        extra_ci = copy.copy(ci)
        extra_ci.platform = "AKINCI"
        extra_ci.entry_start_row = 0
        store.write_contract(extra_ci, systems, deliveries)

        _, siv_systems, _ = store.load_contract_structure(
            "SİVRİSİNEK",
            contract_no=ci.no,
            start_row=contract_id,
            contract_type=ci.contract_type,
            platform_id=siv_id,
        )
        _, akin_systems, akin_deliveries = store.load_contract_structure(
            "AKINCI",
            contract_no=ci.no,
            start_row=contract_id,
            contract_type=ci.contract_type,
            platform_id=akin_id,
        )

        assert siv_systems[0].components == {"Hava Aracı": 6.0}
        assert akin_systems == []
        assert akin_deliveries == {}
        assert store.db.conn.execute(
            "SELECT COUNT(*) FROM contracts WHERE contract_no=? AND contract_type=?",
            (ci.no, ci.contract_type),
        ).fetchone()[0] == 1
    finally:
        store.db.close()
