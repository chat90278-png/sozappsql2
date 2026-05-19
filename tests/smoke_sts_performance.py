import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ComponentDef, ContractInfo
from src.services.sts_store import STSStore

with TemporaryDirectory() as td:
    p = Path(td) / "perf.sts"
    s = STSStore(p)
    s.create_platform("AKINCI")
    s.write_users([{"name": "Serhat", "yi_yd": "Yİ", "active": True, "note": ""}], actor="admin")
    s.write_components([ComponentDef(name="GÖVDE", platforms={"AKINCI": True})], actor="admin")
    ci = ContractInfo(no="K1", platform="AKINCI", user="Serhat", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="", t0_date="", t0_months=0, completion_date="")
    s.write_contract(ci, [], {})

    st = s.performance_stats()
    assert "file_size_mb" in st
    assert "table_counts" in st
    assert st.get("total_records", 0) >= 1
    assert st.get("contract_count", 0) >= 1

    s.add_performance_log("platform_refresh", duration_ms=35, payload={"platform": "AKINCI"})
    logs = s.recent_performance_logs(limit=10)
    assert any(("platform_refresh" in str(x.get("payload_json") or "") or x.get("action") == "performance_measurement") for x in logs)

print("ok")
