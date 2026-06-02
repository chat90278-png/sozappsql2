import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.delivery_coverage import acceptance_coverage_issues
from src.models.app_models import DeliveryInfo, SystemInfo


def delivery(name, planned, delivered):
    return DeliveryInfo(name=name, status="Başlanmadı", acceptance_date="", note="", planned=planned, delivered=delivered)


system = SystemInfo(name="Sistem 1 - Uçuş Bilgisayarı", components={"Gövde Kit": 2, "Aviyonik Birim": 4, "Yazılım Paketi": 1})
kabul_1 = delivery("Kabul 1", {"Gövde Kit": 1, "Aviyonik Birim": 2, "Yazılım Paketi": 1}, {"Gövde Kit": 1, "Aviyonik Birim": 1, "Yazılım Paketi": 0})
kabul_2 = delivery("Kabul 2", {"Gövde Kit": 1, "Aviyonik Birim": 2}, {"Gövde Kit": 1, "Aviyonik Birim": 2})

# Partial delivery remains savable while all system quantities are assigned to acceptances.
assert acceptance_coverage_issues([system], {system.name: [kabul_1, kabul_2]}) == []

# Removing Kabul 2 excludes it from validation and exposes the now-unassigned quantities.
issues = acceptance_coverage_issues([system], {system.name: [kabul_1]})
assert [(item["kind"], item["component"], item["qty"]) for item in issues] == [
    ("unassigned", "Gövde Kit", 1.0),
    ("unassigned", "Aviyonik Birim", 2.0),
]
assert all(item["system"] == system.name for item in issues)
assert system.components == {"Gövde Kit": 2, "Aviyonik Birim": 4, "Yazılım Paketi": 1}

# Reassigning the removed acceptance quantities permits save again without changing the system quantities.
replacement = delivery("Kabul 3", {"Gövde Kit": 1, "Aviyonik Birim": 2}, {"Gövde Kit": 0, "Aviyonik Birim": 0})
assert acceptance_coverage_issues([system], {system.name: [kabul_1, replacement]}) == []
assert system.components == {"Gövde Kit": 2, "Aviyonik Birim": 4, "Yazılım Paketi": 1}

# Delivered quantities above the system contract quantity are blocked separately.
over_delivery = delivery("Hatalı Kabul", {"Gövde Kit": 2, "Aviyonik Birim": 4, "Yazılım Paketi": 1}, {"Gövde Kit": 3, "Aviyonik Birim": 4, "Yazılım Paketi": 1})
issues = acceptance_coverage_issues([system], {system.name: [over_delivery]})
assert [(item["kind"], item["component"], item.get("contract_qty"), item["delivered_qty"]) for item in issues] == [
    ("delivery_over_planned", "Gövde Kit", None, 3.0),
    ("over_delivered", "Gövde Kit", 2.0, 3.0),
]

# Assigned acceptance quantities above the system quantity are also blocked.
over_assignment = delivery("Fazla Atama", {"Gövde Kit": 3, "Aviyonik Birim": 4, "Yazılım Paketi": 1}, {"Gövde Kit": 0})
issues = acceptance_coverage_issues([system], {system.name: [over_assignment]})
assert [(item["kind"], item["component"], item["planned_qty"]) for item in issues] == [
    ("over_assigned", "Gövde Kit", 3.0),
]

print("ok")
