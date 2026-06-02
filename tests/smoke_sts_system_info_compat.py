import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import SystemInfo


# Keep the pre-note positional constructor contract intact for legacy callers.
system = SystemInfo("Sistem-A", {"GÖVDE": 1}, "2026-01-01", 12, "2026-12-31", "Başlanmadı", "")
assert system.t0_date == "2026-01-01"
assert system.t0_months == 12
assert system.completion_date == "2026-12-31"
assert system.component_notes == {}

system.component_notes["GÖVDE"] = "Kontrol edildi"
assert system.component_notes == {"GÖVDE": "Kontrol edildi"}

print("ok")
