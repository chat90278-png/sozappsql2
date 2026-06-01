import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import DeliveryInfo
from src.ui.contract.delivery_user_display import delivery_user_text, delivery_users_text


def delivery(name, user=""):
    return DeliveryInfo(name=name, status="PLAN", acceptance_date="", note="", planned={}, delivered={}, delivery_user=user)


items = [delivery("Kabul 1", "Ali Yılmaz"), delivery("Kabul 2", "Ayşe Demir"), delivery("Kabul 3", "Ali Yılmaz")]
assert [delivery_user_text(item) for item in items] == ["Ali Yılmaz", "Ayşe Demir", "Ali Yılmaz"]
assert delivery_users_text(items) == "Ali Yılmaz, Ayşe Demir"
assert delivery_user_text(delivery("Kabul 4")) == "-"
assert delivery_users_text([delivery("Kabul 4"), delivery("Kabul 5", "  ")]) == "-"

print("ok")
