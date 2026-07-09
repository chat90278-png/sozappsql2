from __future__ import annotations

import atexit
from pathlib import Path

from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_store import STSStore


ANALYSIS_SMOKE_FILENAME = "STS-S-VR-S-NEK---TBD---1__share-edit__2026-07-07_14-04.sts"


def _cleanup_source(path: Path) -> None:
    path.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _delivery(name: str, planned_acceptance_date: str) -> DeliveryInfo:
    planned = {"YKİ": 1, "YVT": 1, "Hava Aracı": 3}
    delivered = {key: 0 for key in planned}
    return DeliveryInfo(
        name=name,
        status="Başlanmadı",
        acceptance_date="",
        note="",
        planned=planned,
        delivered=delivered,
        delivery_user="KKK",
        planned_acceptance_date=planned_acceptance_date,
    )


def create_analysis_smoke_source(root: Path | str) -> Path:
    """Create the Tur 21 semantic smoke dataset using the current STS schema."""

    root_path = Path(root).resolve()
    output = root_path / ANALYSIS_SMOKE_FILENAME
    _cleanup_source(output)

    store = STSStore(output, actor="Analysis Test", source="Analysis Test")
    try:
        for platform in ("SİVRİSİNEK", "AKINCI"):
            store.create_platform(platform)
        store.write_users([
            {"name": "DENEME", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "DENEME1", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "DENEME2", "yi_yd": "Yİ", "active": True, "note": ""},
            {"name": "KKK", "yi_yd": "Yİ", "active": True, "note": ""},
        ])
        store.write_components([
            ComponentDef(name="Hava Aracı", unit="Adet", platforms={"SİVRİSİNEK": True}),
            ComponentDef(name="YKİ", unit="Adet", platforms={"SİVRİSİNEK": True}),
            ComponentDef(name="YVT", unit="Adet", platforms={"SİVRİSİNEK": True}),
        ])
        store.write_tags([
            {"name": "Deneme3", "color": "#8B5CF6", "kind": "contract"},
        ])

        contract = ContractInfo(
            no="SİVRİSİNEK - TBD - 1",
            platform="SİVRİSİNEK",
            user="DENEME",
            yi_yd="Yİ",
            contract_type="-",
            signature_date="TBD",
            t0_date="TBD",
            t0_months=0,
            completion_date="TBD",
            status="Başlanmadı",
            note="",
            users=["DENEME", "DENEME1", "DENEME2", "KKK"],
        )
        systems = [
            SystemInfo(
                name="Sistem 1",
                components={"YKİ": 1, "YVT": 1, "Hava Aracı": 3},
                status="Başlanmadı",
            )
        ]
        deliveries = {
            "Sistem 1": [
                _delivery("Teslimat 1", "2026-07-09"),
                _delivery("Teslimat 2", "TBD"),
            ]
        }
        store.write_contract(contract, systems, deliveries)
        store.save_contract_tags(
            "SİVRİSİNEK",
            "SİVRİSİNEK - TBD - 1",
            "-",
            ["Deneme3"],
        )
        store.save()
    finally:
        store.db.close()

    atexit.register(_cleanup_source, output)
    return output
