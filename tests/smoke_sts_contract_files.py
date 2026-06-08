import hashlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ContractInfo
from src.services.sts_store import STSStore


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expect_value_error(call, expected_message: str):
    try:
        call()
    except ValueError as exc:
        assert str(exc) == expected_message, str(exc)
    else:
        raise AssertionError(f"ValueError bekleniyordu: {expected_message}")


with TemporaryDirectory() as td:
    root = Path(td)
    store = STSStore(root / "contract-files.sts")
    store.create_platform("AKINCI")
    store.write_users([{"name": "Ali Yılmaz", "yi_yd": "Yİ", "active": True, "note": ""}])
    contract = ContractInfo(no="AKN-FILES-001", platform="AKINCI", user="Ali Yılmaz", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="", t0_date="", t0_months=0, completion_date="")
    store.write_contract(contract, [], {})

    source = root / "sozlesme-notu.txt"
    source.write_bytes("STS gömülü belge smoke testi\n".encode("utf-8"))
    original_hash = sha256(source)

    file_id = store.add_contract_file("AKINCI", contract.no, source, contract.contract_type, note="Test belgesi")
    assert sha256(source) == original_hash

    listed = store.list_contract_files("AKINCI", contract.no, contract.contract_type)
    assert len(listed) == 1
    assert listed[0]["id"] == file_id
    assert listed[0]["filename"] == source.name
    assert listed[0]["file_ext"] == "txt"
    assert listed[0]["mime_type"] == "text/plain"
    assert listed[0]["size_bytes"] == source.stat().st_size
    assert listed[0]["note"] == "Test belgesi"
    expect_value_error(
        lambda: store.add_contract_file("AKINCI", contract.no, source, contract.contract_type),
        "Bu belge zaten ekli.",
    )
    assert len(store.list_contract_files("AKINCI", contract.no, contract.contract_type)) == 1
    assert "content_blob" not in listed[0]
    assert "original_path" not in listed[0]

    # BLOB işlemlerinin original_path erişimine bağlı olmadığını kanıtlamak için kaynak dosyayı test içinde geçici olarak yeniden adlandır.
    hidden_source = root / "kaynak-gecici-olarak-tasindi.txt"
    source.rename(hidden_source)
    filename, mime_type, content = store.get_contract_file_bytes(file_id)
    assert filename == source.name
    assert mime_type == "text/plain"
    assert hashlib.sha256(content).hexdigest() == original_hash

    exported = root / "disari-aktarilan.txt"
    result = store.export_contract_file(file_id, exported)
    assert result["target_path"] == str(exported)
    assert sha256(exported) == original_hash
    hidden_source.rename(source)
    assert sha256(source) == original_hash

    assert store.delete_contract_file(file_id) is True
    assert store.list_contract_files("AKINCI", contract.no, contract.contract_type) == []
    assert source.exists()
    assert sha256(source) == original_hash

    cascade_file_id = store.add_contract_file("AKINCI", contract.no, source, contract.contract_type)
    assert cascade_file_id
    assert store.db.database_stats()["table_counts"]["contract_files"] == 1
    assert len(store.db.preview_table("contract_files")) == 1
    assert store.delete_contract("AKINCI", contract.no)["deleted_rows"] == 1
    assert store.db.conn.execute("SELECT COUNT(*) FROM contract_files").fetchone()[0] == 0
    assert source.exists()
    assert sha256(source) == original_hash

    # Boyut ve uzantı kontrolleri sözleşme bulunabildiği sırada denenir.
    second = ContractInfo(no="AKN-FILES-002", platform="AKINCI", user="Ali Yılmaz", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="", t0_date="", t0_months=0, completion_date="")
    store.write_contract(second, [], {})

    root_folder = store.create_contract_file_folder("AKINCI", second.no, second.contract_type)
    assert root_folder["name"] == "Yeni Klasör"
    duplicate_named = store.create_contract_file_folder("AKINCI", second.no, second.contract_type)
    assert duplicate_named["name"] == "Yeni Klasör (2)"
    child_folder = store.create_contract_file_folder("AKINCI", second.no, second.contract_type, parent_id=root_folder["id"], name="Alt")
    renamed = store.rename_contract_file_folder(child_folder["id"], "Teknik")
    assert renamed["path"] == "Yeni Klasör/Teknik"
    expect_value_error(lambda: store.rename_contract_file_folder(child_folder["id"], ""), "Klasör adı boş olamaz.")
    expect_value_error(lambda: store.rename_contract_file_folder(child_folder["id"], "bad/name"), r'Klasör adında / \ : * ? " < > | karakterleri kullanılamaz.')
    folder_source = root / "foldered.txt"
    folder_source.write_text("foldered", encoding="utf-8")
    folder_file_id = store.add_contract_file("AKINCI", second.no, folder_source, second.contract_type, folder_id=child_folder["id"])
    foldered = [item for item in store.list_contract_files("AKINCI", second.no, second.contract_type) if item["id"] == folder_file_id][0]
    assert foldered["folder_id"] == child_folder["id"]
    assert foldered["folder_path"] == "Yeni Klasör/Teknik"
    folder_actions = {row[0] for row in store.db.conn.execute("SELECT action FROM activity_logs WHERE entity_type='document_folder'")}
    assert {"document_folder_created", "document_folder_renamed"} <= folder_actions

    too_large = root / "buyuk.txt"
    with too_large.open("wb") as stream:
        stream.truncate(50 * 1024 * 1024 + 1)
    expect_value_error(
        lambda: store.add_contract_file("AKINCI", second.no, too_large, second.contract_type),
        "Dosya boyutu 50 MB üstünde olamaz.",
    )
    risky = root / "calistirma.exe"
    risky.write_bytes(b"not executable")
    expect_value_error(
        lambda: store.add_contract_file("AKINCI", second.no, risky, second.contract_type),
        "Bu dosya türü desteklenmiyor.",
    )
    assert store.db.foreign_key_check() == []
    assert store.db.integrity_check() == ["ok"]
    store.db.close()

print("ok")
