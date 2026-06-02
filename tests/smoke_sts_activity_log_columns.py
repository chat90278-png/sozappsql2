import ast
from pathlib import Path

source = Path("src/ui/dialogs/activity_logs.py").read_text(encoding="utf-8")
tree = ast.parse(source)
expected_headers = [
    "ID", "Tarih", "İşlem Yapan", "İşlem Kaynağı", "Bilgisayar", "İşlem", "Kayıt Türü",
    "Kayıt ID", "Kayıt Anahtarı", "Platform ID", "Sözleşme No", "Mesaj", "Önce", "Sonra", "Detay",
]
headers = None
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setHorizontalHeaderLabels":
        values = ast.literal_eval(node.args[0])
        if values and values[0] == "ID":
            headers = values
            break
assert headers == expected_headers
assert "self.table = QTableWidget(0, 15)" in source
for key in ("source", "device_name", "entity_id", "entity_key", "platform_id", "before_json", "after_json", "payload_json"):
    assert f'log.get("{key}")' in source
print("ok")
