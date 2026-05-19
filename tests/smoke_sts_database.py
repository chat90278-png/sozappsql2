import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pathlib import Path
from tempfile import TemporaryDirectory
from src.services.sts_database import STSDatabase
with TemporaryDirectory() as td:
 p=Path(td)/'a.sts'; db=STSDatabase(p); db.conn.execute("INSERT INTO platforms(name) VALUES('P1')"); db.conn.execute("INSERT INTO users(name) VALUES('U1')"); db.conn.execute("INSERT INTO components(name) VALUES('C1')"); db.conn.execute("INSERT INTO tags(name) VALUES('T1')"); db.conn.execute("INSERT INTO contracts(platform,contract_no,contract_type,is_main) VALUES('P1','K1','Ana Sözleşme',1)"); cid=db.conn.execute('SELECT id FROM contracts').fetchone()[0]; db.conn.execute("INSERT INTO systems(contract_id,name) VALUES(?,?)",(cid,'S1')); sid=db.conn.execute('SELECT id FROM systems').fetchone()[0]; db.conn.execute("INSERT INTO system_components(system_id,component_name,qty) VALUES(?,?,?)",(sid,'C1',1)); db.conn.execute("INSERT INTO deliveries(contract_id,system_name,name) VALUES(?,?,?)",(cid,'S1','D1')); did=db.conn.execute('SELECT id FROM deliveries').fetchone()[0]; db.conn.execute("INSERT INTO delivery_components(delivery_id,component_name,planned,delivered) VALUES(?,?,?,?)",(did,'C1',1,1)); db.conn.commit(); assert db.conn.execute('SELECT COUNT(*) FROM contracts').fetchone()[0]==1; db.conn.execute('DELETE FROM contracts WHERE id=?',(cid,)); db.conn.commit(); assert db.conn.execute('SELECT COUNT(*) FROM systems').fetchone()[0]==0
print('ok')
