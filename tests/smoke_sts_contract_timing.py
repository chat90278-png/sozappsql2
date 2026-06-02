import sys
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.contract_timing import contract_timing, is_completed_status
from src.models.app_models import ContractInfo
from src.services.sts_store import STSStore


today = date(2026, 6, 2)
assert contract_timing(today + timedelta(days=91), status="Devam ediyor", today=today) == ("91 gün", 91, "devam_ediyor")
assert contract_timing(today - timedelta(days=5), status="Devam ediyor", today=today) == ("-5 gün", -5, "devam_ediyor")
assert contract_timing("2026-04-01", "2026-03-28", "Tamamlandı", today=today) == ("4 gün erken teslim edildi", -4, "erken_teslim")
assert contract_timing("2026-04-01", "2026-04-01", "Teslim Edildi", today=today) == ("Termin gününde teslim edildi", 0, "zamaninda_teslim")
assert contract_timing("2026-04-01", "2026-04-05", "teslim edildi", today=today) == ("4 gün gecikmeli teslim edildi", 4, "gecikmeli_teslim")
assert contract_timing("2026-04-01", "", "TAMAMLANDI", today=today) == ("Teslim tarihi yok", None, "teslim_tarihi_yok")
assert is_completed_status("Teslim Edildi")
assert is_completed_status("TESLİM EDİLDİ")
assert is_completed_status("teslim edildi")
assert is_completed_status("TAMAMLANDI")
assert is_completed_status("Tamamlandı")

with TemporaryDirectory() as td:
    store = STSStore(Path(td) / "contract-timing.sts")
    store.create_platform("KIZILELMA")
    contract = ContractInfo(
        no="KIZ-2026-010",
        platform="KIZILELMA",
        user="",
        yi_yd="Yİ",
        contract_type="Ana Sözleşme",
        signature_date="",
        t0_date="",
        t0_months=0,
        completion_date="2026-04-01",
        acceptance_date="2026-03-28",
        status="Tamamlandı",
    )
    store.write_contract(contract, [], {})
    item = store.list_main_contracts("KIZILELMA")[0]
    assert item["acceptance_date"] == "2026-03-28"
    store.db.close()

print("ok")
