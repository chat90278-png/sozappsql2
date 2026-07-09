from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from .analysis_models import NormalizedAnalysisData


def build_sample_data(today: date | None = None) -> NormalizedAnalysisData:
    base = today or date.today()
    upcoming_1 = (base + timedelta(days=12)).isoformat()
    upcoming_2 = (base + timedelta(days=38)).isoformat()
    past_1 = (base - timedelta(days=9)).isoformat()
    completed_date = (base - timedelta(days=18)).isoformat()

    platforms: List[Dict[str, Any]] = [
        {"id": 1, "name": "AKINCI", "display_name": "AKINCI", "is_active": True},
        {"id": 2, "name": "TB2", "display_name": "TB2", "is_active": True},
        {"id": 3, "name": "KIZILELMA", "display_name": "KIZILELMA", "is_active": True},
    ]
    users = [
        {"id": 1, "name": "KY Kullanıcı 1", "active": True, "yi_yd": "Yİ"},
        {"id": 2, "name": "KY Kullanıcı 2", "active": True, "yi_yd": "YD"},
    ]
    contracts = [
        {"id": 101, "platform": "AKINCI", "contract_no": "STS-2026-001", "contract_type": "Ana Sözleşme", "status": "Devam Ediyor", "completion_date": upcoming_1, "acceptance_date": "", "users": ["KY Kullanıcı 1"], "user": "KY Kullanıcı 1", "content": "Demo ana sözleşme", "is_main": True, "tags": ["aviyonik", "öncelikli"]},
        {"id": 102, "platform": "TB2", "contract_no": "STS-2026-002", "contract_type": "Ana Sözleşme", "status": "Tamamlandı", "completion_date": completed_date, "acceptance_date": completed_date, "users": ["KY Kullanıcı 2"], "user": "KY Kullanıcı 2", "content": "Demo tamamlanan sözleşme", "is_main": True, "tags": ["teslim edildi"]},
        {"id": 103, "platform": "KIZILELMA", "contract_no": "STS-2026-003", "contract_type": "Ana Sözleşme", "status": "Başlanmadı", "completion_date": past_1, "acceptance_date": "", "users": [], "user": "", "content": "Eksik kullanıcı demo kaydı", "is_main": True, "tags": []},
    ]
    systems = [
        {"id": 201, "contract_id": 101, "platform": "AKINCI", "contract_no": "STS-2026-001", "name": "Görev Bilgisayarı", "status": "Devam Ediyor", "completion_date": upcoming_1, "acceptance_date": ""},
        {"id": 202, "contract_id": 102, "platform": "TB2", "contract_no": "STS-2026-002", "name": "Kamera Sistemi", "status": "Tamamlandı", "completion_date": completed_date, "acceptance_date": completed_date},
        {"id": 203, "contract_id": 103, "platform": "KIZILELMA", "contract_no": "STS-2026-003", "name": "Uçuş Kontrol", "status": "Başlanmadı", "completion_date": upcoming_2, "acceptance_date": ""},
    ]
    components = [
        {"id": 301, "name": "Bileşen A", "version": "1.0", "unit": "Adet", "active": True},
        {"id": 302, "name": "Bileşen B", "version": "2.1", "unit": "Adet", "active": True},
        {"id": 303, "name": "Bileşen C", "version": "", "unit": "Adet", "active": True},
    ]
    acceptances = [
        {"id": 401, "contract_id": 101, "system_id": 201, "platform": "AKINCI", "contract_no": "STS-2026-001", "system_name": "Görev Bilgisayarı", "name": "Teslimat-1", "status": "Devam Ediyor", "acceptance_date": "", "planned_acceptance_date": upcoming_1, "planned_delivery_date": "", "completion_date": upcoming_1, "planned_total": 10.0, "delivered_total": 4.0},
        {"id": 402, "contract_id": 102, "system_id": 202, "platform": "TB2", "contract_no": "STS-2026-002", "system_name": "Kamera Sistemi", "name": "Teslimat-1", "status": "Tamamlandı", "acceptance_date": completed_date, "planned_acceptance_date": completed_date, "planned_delivery_date": "", "completion_date": completed_date, "planned_total": 6.0, "delivered_total": 6.0},
    ]
    tags = [
        {"id": 501, "name": "aviyonik", "color": "#3B82F6", "contract_count": 1},
        {"id": 502, "name": "öncelikli", "color": "#F97316", "contract_count": 1},
        {"id": 503, "name": "teslim edildi", "color": "#16A34A", "contract_count": 1},
    ]
    deadlines = [
        {"entity": "contract", "platform": "AKINCI", "contract_no": "STS-2026-001", "name": "Ana Sözleşme", "due_date": upcoming_1, "status": "Devam Ediyor"},
        {"entity": "system", "platform": "KIZILELMA", "contract_no": "STS-2026-003", "name": "Uçuş Kontrol", "due_date": upcoming_2, "status": "Başlanmadı"},
        {"entity": "contract", "platform": "KIZILELMA", "contract_no": "STS-2026-003", "name": "Ana Sözleşme", "due_date": past_1, "status": "Başlanmadı"},
    ]
    return {"contracts": contracts, "platforms": platforms, "acceptances": acceptances, "deadlines": deadlines, "systems": systems, "components": components, "users": users, "tags": tags}
