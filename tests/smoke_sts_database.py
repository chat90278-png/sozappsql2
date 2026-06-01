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
    assert db.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == '2'

    expected_columns = {
        'component_platforms': {'component_id', 'platform_id'},
        'contracts': {'platform_id', 'user_id'},
        'systems': {'contract_id', 'delivery_user_id'},
        'system_components': {'system_id', 'component_id', 'qty'},
        'deliveries': {'contract_id', 'system_id'},
        'delivery_components': {'delivery_id', 'component_id', 'planned', 'delivered'},
        'contract_tags': {'contract_id', 'tag_id'},
        'activity_logs': {'platform_id', 'entity_type', 'entity_id'},
    }
    for table, columns in expected_columns.items():
        actual = {r[1] for r in db.conn.execute(f'PRAGMA table_info({table})')}
        assert columns <= actual, (table, columns - actual)
    forbidden_columns = {
        'component_platforms': {'platform_name'}, 'contracts': {'platform', 'user_name'},
        'systems': {'delivery_user'}, 'system_components': {'component_name'},
        'delivery_components': {'component_name'}, 'contract_tags': {'tag_name'},
        'activity_logs': {'platform'},
    }
    for table, forbidden in forbidden_columns.items():
        actual = {r[1] for r in db.conn.execute(f'PRAGMA table_info({table})')}
        assert not (actual & forbidden), (table, actual & forbidden)

    expected_indexes = {
        'idx_contracts_platform_id', 'idx_contracts_platform_status', 'idx_contracts_completion_date',
        'idx_systems_contract_id', 'idx_systems_completion_date', 'idx_system_components_component_id',
        'idx_deliveries_contract_id', 'idx_deliveries_system_id', 'idx_deliveries_contract_system',
        'idx_deliveries_acceptance_date', 'idx_delivery_components_component_id', 'idx_logs_created_at',
        'idx_logs_action', 'idx_logs_entity',
    }
    actual_indexes = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert expected_indexes <= actual_indexes, expected_indexes - actual_indexes
    assert db.integrity_check() == ['ok']
    assert db.foreign_key_check() == []

print('ok')
