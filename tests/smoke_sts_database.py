import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.sts_database import STSDatabase

with TemporaryDirectory() as td:
    p = Path(td) / 'v2.sts'
    db = STSDatabase(p)
    assert db.conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert db.conn.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal'
    assert db.conn.execute('PRAGMA synchronous').fetchone()[0] == 1
    assert db.conn.execute('PRAGMA cache_size').fetchone()[0] == -64000
    assert db.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == '4'

    expected_columns = {
        'component_platforms': {'component_id', 'platform_id'},
        'contracts': {'platform_id', 'user_id'},
        'systems': {'contract_id'},
        'system_components': {'system_id', 'component_id', 'qty', 'note'},
        'deliveries': {'contract_id', 'system_id', 'delivery_user_id'},
        'delivery_components': {'delivery_id', 'component_id', 'planned', 'delivered'},
        'contract_tags': {'contract_id', 'tag_id'},
        'contract_file_folders': {'contract_id', 'parent_id', 'name', 'created_at', 'updated_at'},
        'contract_files': {'contract_id', 'folder_id', 'filename', 'original_path', 'file_ext', 'mime_type', 'size_bytes', 'content_blob', 'note', 'created_at', 'updated_at'},
        'activity_logs': {'platform_id', 'entity_type', 'entity_id', 'source', 'device_name'},
    }
    for table, columns in expected_columns.items():
        actual = {r[1] for r in db.conn.execute(f'PRAGMA table_info({table})')}
        assert columns <= actual, (table, columns - actual)
    forbidden_columns = {
        'component_platforms': {'platform_name'}, 'contracts': {'platform', 'user_name'},
        'systems': {'delivery_user', 'delivery_user_id'}, 'system_components': {'component_name'},
        'delivery_components': {'component_name'}, 'contract_tags': {'tag_name'},
        'activity_logs': {'platform'},
    }
    for table, forbidden in forbidden_columns.items():
        actual = {r[1] for r in db.conn.execute(f'PRAGMA table_info({table})')}
        assert not (actual & forbidden), (table, actual & forbidden)

    expected_indexes = {
        'idx_contracts_platform_id', 'idx_contracts_platform_status', 'idx_contracts_completion_date',
        'idx_systems_contract_id', 'idx_systems_completion_date', 'idx_system_components_component_id',
        'idx_deliveries_contract_id', 'idx_deliveries_system_id', 'idx_deliveries_delivery_user_id', 'idx_deliveries_contract_system',
        'idx_deliveries_acceptance_date', 'idx_delivery_components_component_id', 'idx_contract_file_folders_contract_id', 'idx_contract_file_folders_parent_id', 'idx_contract_files_contract_id', 'idx_contract_files_folder_id', 'idx_logs_created_at',
        'idx_logs_action', 'idx_logs_entity', 'idx_document_locks_id',
    }
    actual_indexes = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert expected_indexes <= actual_indexes, expected_indexes - actual_indexes
    assert db.integrity_check() == ['ok']
    assert db.foreign_key_check() == []
    db.close()

    legacy_path = Path(td) / 'legacy-v2.sts'
    legacy = sqlite3.connect(legacy_path)
    legacy.execute('CREATE TABLE systems(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,name TEXT NOT NULL,status TEXT,completion_date TEXT,acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT)')
    legacy.execute('CREATE TABLE deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,system_id INTEGER,system_name TEXT NOT NULL,name TEXT NOT NULL,status TEXT,acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT)')
    legacy.execute('CREATE TABLE contract_files(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,filename TEXT NOT NULL,original_path TEXT,file_ext TEXT,mime_type TEXT,size_bytes INTEGER NOT NULL DEFAULT 0,content_blob BLOB NOT NULL,note TEXT,created_at TEXT,updated_at TEXT)')
    legacy.commit()
    legacy.close()

    upgraded = STSDatabase(legacy_path)
    assert 'delivery_user_id' not in {r[1] for r in upgraded.conn.execute('PRAGMA table_info(systems)')}
    assert 'delivery_user_id' in {r[1] for r in upgraded.conn.execute('PRAGMA table_info(deliveries)')}
    assert 'folder_id' in {r[1] for r in upgraded.conn.execute('PRAGMA table_info(contract_files)')}
    assert 'contract_file_folders' in {r[0] for r in upgraded.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    delivery_indexes = {r[1] for r in upgraded.conn.execute('PRAGMA index_list(deliveries)')}
    assert 'idx_deliveries_delivery_user_id' in delivery_indexes
    assert upgraded.foreign_key_check() == []
    assert upgraded.integrity_check() == ['ok']
    upgraded.close()

print('ok')
