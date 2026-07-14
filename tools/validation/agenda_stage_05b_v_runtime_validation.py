from __future__ import annotations
import hashlib,json,os,platform,shutil,sqlite3,subprocess,sys,tempfile,traceback,xml.etree.ElementTree as ET
from pathlib import Path

B='e1ed9a66318e19178f132602d3114a97880fa27f'; C='b6fe76d06abab31d70e7b129f4efdbe5bbb07472'; F='b45d6f2e2b2948d1bbf9dcf1f83c8b04386a5c98'; M='2931fa267560397d4d849d6365acde504f376775'; BR='integration/gundemim-current-main-20260713'
TMP=['.github/workflows/agenda-stage-05b-v-runtime-validation.yml','tools/validation/agenda_stage_05b_v_runtime_validation.py']
TARGET='''test_activity_agenda_provider.py test_agenda_compact_widget.py test_agenda_context_factory.py test_agenda_current_main_composition.py test_agenda_deadline_stage.py test_agenda_detail_window.py test_agenda_keys.py test_agenda_lifecycle.py test_agenda_models.py test_agenda_presentation.py test_agenda_schema_v18_integration.py test_agenda_source_repository.py test_agenda_startup_upgrade_integration.py test_agenda_state_repository.py test_deadline_agenda_provider.py test_document_lock_agenda_provider.py test_main_page_agenda_integration.py test_personal_agenda_facade.py test_returned_share_agenda_provider.py test_staff_agenda_service.py test_sts_database_transactions.py test_sts_schema_upgrade.py test_sts_schema_upgrade_gate.py test_sts_schema_upgrade_orchestration.py test_unknown_date_agenda_provider.py test_analysis_qt_integration.py test_analysis_builder_qt.py test_contract_edit_timing_runtime_fix.py test_sd_edit_timing_runtime_fix.py test_contract_save_telemetry_runtime_fix.py test_delivery_schedule_slicer_runtime_fix.py'''.split()
PROTECTED='''app.py requirements.txt src/auth.py src/ui/main_window.py src/ui/main_page_final_window.py src/ui/widgets/contract_status_summary.py src/ui/widgets/corner_menu_layer.py src/ui/contract/contract_work_window.py src/workers/sts_load_worker.py'''.split()
R=Path.cwd(); E=R/'evidence'; BD=R/'_validation/baseline'; CD=R/'_validation/candidate'; failures=[]

def wt(n,s): E.mkdir(exist_ok=True); (E/n).write_text(s,encoding='utf-8')
def wj(n,x): wt(n,json.dumps(x,indent=2,ensure_ascii=False,default=str)+'\n')
def run(a,cwd=R,log=None,ok=True):
 p=subprocess.run([str(x) for x in a],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,errors='replace'); out=p.stdout or ''
 if log: wt(log,'$ '+' '.join(map(str,a))+'\n'+out)
 if ok and p.returncode: raise RuntimeError(f"{p.returncode}: {' '.join(map(str,a))}\n{out[-3000:]}")
 return p
def git(*a,cwd=R): return run(['git',*a],cwd).stdout.strip()
def gate(n,f):
 try: f(); print('[PASS]',n)
 except Exception as e: failures.append(f'{n}: {e}'); print('[FAIL]',n,e); traceback.print_exc()

def preflight():
 h=git('rev-parse','HEAD'); br=os.getenv('GITHUB_HEAD_REF') or git('branch','--show-current')
 assert br==BR and run(['git','merge-base','--is-ancestor',C,h],ok=False).returncode==0
 for s in [B,C,F,M]: git('cat-file','-e',s+'^{commit}')
 changed=git('diff','--name-only',C+'..'+h).splitlines(); assert sorted(changed)==sorted(TMP),changed
 refs={'bootstrap':h,'main':git('rev-parse','origin/main'),'feature':git('rev-parse','origin/feature/gundemim-agenda-system'),'merge_base':git('merge-base',B,C),'ahead':int(git('rev-list','--count',B+'..'+C)),'behind':int(git('rev-list','--count',C+'..'+B))}
 assert refs['main']==B and refs['feature']==F and refs['merge_base']==B and refs['ahead']==11 and refs['behind']==0
 wj('refs.json',refs); wt('preflight.txt',json.dumps(refs,indent=2)+'\npaths='+repr(changed))
 mt=run(['git','merge-tree',M,B,F]).stdout; wt('merge-tree.txt',mt); assert not any(x in mt for x in ['<<<<<<<','>>>>>>>','CONFLICT (','changed in both'])

def materialize():
 run(['git','worktree','prune'],ok=False); shutil.rmtree(R/'_validation',ignore_errors=True); (R/'_validation').mkdir()
 run(['git','worktree','add','--detach',BD,B]); run(['git','worktree','add','--detach',CD,C])
 assert not git('status','--porcelain',cwd=BD) and not git('status','--porcelain',cwd=CD)

def env_req():
 b=(BD/'requirements.txt').read_bytes(); c=(CD/'requirements.txt').read_bytes(); x={'equal':b==c,'baseline_sha256':hashlib.sha256(b).hexdigest(),'candidate_sha256':hashlib.sha256(c).hexdigest()}; wj('requirements-parity.json',x); assert b==c
 import pytest,PySide6; from PySide6.QtCore import qVersion
 wt('environment.txt',f'platform={platform.platform()}\narchitecture={platform.architecture()}\npython={sys.version}\npip={run([sys.executable,"-m","pip","--version"]).stdout.strip()}\npytest={pytest.__version__}\nPySide6={PySide6.__version__}\nQt={qVersion()}\n')

def static():
 d=(CD/'src/services/sts_database.py').read_text(encoding='utf-8'); u=(CD/'src/services/sts_schema_upgrade.py').read_text(encoding='utf-8'); g=(CD/'src/services/sts_schema_upgrade_gate.py').read_text(encoding='utf-8'); q=(CD/'src/ui/main_page_analysis_window.py').read_text(encoding='utf-8')
 x={'schema18':'CURRENT_SCHEMA_VERSION = 18' in d,'helper_owner':d.count('def ensure_staff_agenda_state_schema')==1 and 'def ensure_staff_agenda_state_schema' not in u,'no_patch':'_sts_database_module' not in u,'migration':'v17_to_v18_staff_agenda_state' in u,'fingerprint':'FINGERPRINT_MAX_VERSION = 18' in g,'registry':'"agenda:detail"' in q and 'open_or_raise_tool_window' in q and 'close_tool_window("agenda:detail")' in q,'idempotency':q.count('qt_obj_alive(widget)')>=2 and 'qt_obj_alive(timer)' in q}; wj('static-invariants.json',x); assert all(x.values()),x

def suites():
 run([sys.executable,'-m','compileall','-q','src','tests'],BD,'baseline-compile.txt'); run([sys.executable,'-m','compileall','-q','src','tests'],CD,'candidate-compile.txt')
 run([sys.executable,'-m','pytest','-q',f'--junitxml={E/"baseline-full.xml"}'],BD,'baseline-full.log')
 paths=[str(Path('tests')/x) for x in TARGET]; miss=[x for x in paths if not (CD/x).exists()]; assert not miss,miss
 run([sys.executable,'-m','pytest','-q',*paths,f'--junitxml={E/"candidate-targeted.xml"}'],CD,'candidate-targeted.log')
 a=run([sys.executable,'tests/smoke_sts_agenda_schema.py'],CD,'agenda-schema-smoke.txt').stdout; assert 'agenda_schema=PASS' in a and 'schema_version=18' in a
 a=run([sys.executable,'tests/smoke_sts_database.py'],CD,'database-smoke.txt').stdout; assert a.strip().endswith('ok')
 run([sys.executable,'-m','pytest','-q',f'--junitxml={E/"candidate-full.xml"}'],CD,'candidate-full.log')

def contract(p):
 con=sqlite3.connect(p); out={'version':int(con.execute("select value from meta where key='schema_version'").fetchone()[0]),'columns':[r[1] for r in con.execute('pragma table_info(staff_agenda_state)')],'pk':[r[1] for r in sorted([r for r in con.execute('pragma table_info(staff_agenda_state)') if r[5]],key=lambda r:r[5])],'fk':[tuple(r) for r in con.execute('pragma foreign_key_list(staff_agenda_state)')],'indexes':{r[0]:[z[2] for z in con.execute(f'pragma index_info("{r[0]}")')] for r in con.execute("select name from sqlite_master where type='index' and name like 'idx_staff_agenda_state_%'")},'integrity':con.execute('pragma integrity_check').fetchone()[0],'fk_check':[tuple(r) for r in con.execute('pragma foreign_key_check')]}; con.close(); return out

def schema():
 old=list(sys.path); cwd=Path.cwd(); os.chdir(CD); sys.path.insert(0,str(CD))
 try:
  from src.services.sts_database import STSDatabase,STSMigrationError,ensure_staff_agenda_state_schema,AGENDA_STATE_COLUMNS
  from src.services.sts_schema_upgrade import upgrade_sts_file
  from src.services.sts_schema_upgrade_gate import validate_versioned_schema_fingerprint
  t=Path(tempfile.mkdtemp(dir=R/'_validation')); p=t/'fresh.sts'; d=STSDatabase(p); d.close(); x={'fresh':contract(p)}; assert x['fresh']['version']==18 and tuple(x['fresh']['columns'])==tuple(AGENDA_STATE_COLUMNS) and x['fresh']['pk']==['staff_id','agenda_key'] and x['fresh']['integrity']=='ok' and not x['fresh']['fk_check']; validate_versioned_schema_fingerprint(p,18)
  c=sqlite3.connect(':memory:'); c.execute('create table staff(id integer primary key)'); c.execute('begin'); first=ensure_staff_agenda_state_schema(c); assert c.in_transaction and ensure_staff_agenda_state_schema(c)==() and c.in_transaction; c.rollback(); c.close(); x['helper_transaction']={'created':first,'preserved':True}
  c=sqlite3.connect(':memory:'); c.execute('create table staff(id integer primary key)'); c.execute('create table staff_agenda_state(staff_id integer,agenda_key text)')
  try: ensure_staff_agenda_state_schema(c); raise AssertionError('malformed accepted')
  except RuntimeError as e: assert not c.execute("select name from sqlite_master where type='index' and name like 'idx_staff_agenda_state_%'").fetchall(); x['malformed']=str(e)
  c.close(); v=t/'v17.sts'; shutil.copy2(p,v); c=sqlite3.connect(v); c.execute('drop index idx_staff_agenda_state_staff'); c.execute('drop index idx_staff_agenda_state_snoozed'); c.execute('drop table staff_agenda_state'); c.execute("update meta set value='17' where key='schema_version'"); c.commit(); c.close(); validate_versioned_schema_fingerprint(v,17); r=upgrade_sts_file(v); assert r.applied_migrations==('v17_to_v18_staff_agenda_state',) and contract(r.backup_path)['version']==17; validate_versioned_schema_fingerprint(v,18); x['v17_to_v18']={'applied':r.applied_migrations,'backup':str(r.backup_path),'final':contract(v)}
  before=list((t/'yedekler').glob('*')); r=upgrade_sts_file(p); assert r.status=='current' and not r.applied_migrations and before==list((t/'yedekler').glob('*')); x['current']='noop'
  f=t/'v19.sts'; shutil.copy2(p,f); c=sqlite3.connect(f); c.execute("update meta set value='19' where key='schema_version'"); c.commit(); c.close(); h=hashlib.sha256(f.read_bytes()).hexdigest()
  try: upgrade_sts_file(f); raise AssertionError('future accepted')
  except STSMigrationError as e: assert hashlib.sha256(f.read_bytes()).hexdigest()==h; x['future']=str(e)
  cases={}
  for n in ['missing_table','missing_index','wrong_index_order','forbidden_table']:
   z=t/(n+'.sts'); shutil.copy2(p,z); c=sqlite3.connect(z)
   if n=='missing_table': c.execute('drop index idx_staff_agenda_state_staff'); c.execute('drop index idx_staff_agenda_state_snoozed'); c.execute('drop table staff_agenda_state')
   if n=='missing_index': c.execute('drop index idx_staff_agenda_state_staff')
   if n=='wrong_index_order': c.execute('drop index idx_staff_agenda_state_snoozed'); c.execute('create index idx_staff_agenda_state_snoozed on staff_agenda_state(snoozed_until,staff_id)')
   if n=='forbidden_table': c.execute('create table agenda_items(id integer primary key)')
   c.commit(); c.close()
   try: validate_versioned_schema_fingerprint(z,18); raise AssertionError(n+' accepted')
   except STSMigrationError as e: cases[n]=getattr(e,'technical_detail',str(e))
  x['drift']=cases; wj('schema-runtime.json',x)
 finally: os.chdir(cwd); sys.path[:]=old

def qt():
 old=list(sys.path); cwd=Path.cwd(); os.chdir(CD); sys.path.insert(0,str(CD)); os.environ['QT_QPA_PLATFORM']='offscreen'
 try:
  from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QHBoxLayout
  from src.ui.main_page_analysis_window import MainWindow
  from src.ui.main_window import qt_obj_alive
  app=QApplication.instance() or QApplication([])
  class H(MainWindow):
   def __init__(s):
    QMainWindow.__init__(s); s._agenda_facade=s._agenda_bound_db=s._agenda_snapshot=s._agenda_detail_window=s._agenda_refresh_timer=None; s.current_staff=object(); s.contract_index=[]; s.allowed=True; s.reg={}; s.calls=s.refreshes=0; s.opened=[]; card=QWidget(s); lay=QHBoxLayout(card); cal=QWidget(card); lay.addWidget(cal); s.setCentralWidget(card); s._cal_widget=cal; s.upcoming_scroll=None
   def is_sts_mode(s): return True
   def has_permission(s,n): return s.allowed and n=='view_contracts'
   def refresh_agenda(s,*a,**k): s.refreshes+=1
   def open_contract_item(s,i): s.opened.append(i)
   def open_or_raise_tool_window(s,k,t,f):
    o=s.reg.get(k)
    if not qt_obj_alive(o): s.calls+=1; o=f(); s.reg[k]=o
    o.show(); return o
   def close_tool_window(s,k):
    o=s.reg.pop(k,None)
    if qt_obj_alive(o): o.close(); o.deleteLater(); app.processEvents()
  h=H(); h._install_contract_status_widget(); sw=h.contract_status_widget; h._install_contract_status_widget(); assert h.contract_status_widget is sw; h._install_personal_agenda_widget(); aw=h.agenda_compact_widget; tm=h._agenda_refresh_timer; h._install_personal_agenda_widget(); assert h.agenda_compact_widget is aw and h._agenda_refresh_timer is tm; lay=h._cal_widget.parentWidget().layout(); order=[lay.itemAt(i).widget() for i in range(lay.count())]; assert order.count(sw)==order.count(aw)==order.count(h._cal_widget)==1 and order.index(sw)<order.index(aw)<order.index(h._cal_widget); tm.timeout.emit(); assert h.refreshes==1
  h._open_agenda_details(); d=h._agenda_detail_window; h._open_agenda_details(); assert h._agenda_detail_window is d and h.calls==1; h.close_tool_window('agenda:detail'); h._agenda_detail_window=None; h._open_agenda_details(); assert h._agenda_detail_window is not d and h.calls==2; h.allowed=False; assert not h._sync_agenda_permission_visibility() and 'agenda:detail' not in h.reg and h._agenda_detail_window is None; h.contract_index=[{'id':1,'contract_no':'DUP'},{'id':2,'contract_no':'DUP'}]; h._open_agenda_contract(2); assert h.opened[-1]['id']==2
  wj('qt-runtime.json',{'widget_install':{'status_reused':True,'agenda_reused':True,'timer_reused':True,'single_signal_effect':1,'order':[type(w).__name__ for w in order]},'registry':{'key':'agenda:detail','first_reused':True,'reopen_factory_calls':2,'permission_loss_closed':True},'navigation':{'id':2,'duplicate_safe':True}}); h.close(); app.processEvents()
 finally: os.chdir(cwd); sys.path[:]=old

def js(p):
 cases=ET.parse(p).getroot().findall('.//testcase'); nodes=[]; fail=[]; err=[]; skip=[]
 for c in cases:
  n=c.attrib.get('classname','')+'::'+c.attrib.get('name',''); nodes.append(n)
  if c.find('failure') is not None: fail.append(n)
  if c.find('error') is not None: err.append(n)
  if c.find('skipped') is not None: skip.append(n)
 return {'tests':len(cases),'nodes':sorted(set(nodes)),'failures':fail,'errors':err,'skipped':skip}
def diff():
 b=js(E/'baseline-full.xml'); c=js(E/'candidate-full.xml'); t=js(E/'candidate-targeted.xml'); x={'baseline':b,'candidate':c,'targeted':t,'candidate_only':sorted(set(c['nodes'])-set(b['nodes'])),'baseline_only':sorted(set(b['nodes'])-set(c['nodes']))}; wj('junit-differential.json',x); wt('junit-differential.txt',f"baseline={b['tests']} candidate={c['tests']} targeted={t['tests']}\nbaseline_only={x['baseline_only']}\ncandidate_only={x['candidate_only']}\n"); assert not (b['failures']+b['errors']+b['skipped']+c['failures']+c['errors']+c['skipped']+t['failures']+t['errors']+t['skipped']+x['baseline_only'])
def parity():
 x={p:{'baseline':git('rev-parse',B+':'+p),'candidate':git('rev-parse',C+':'+p)} for p in PROTECTED}; [v.update(equal=v['baseline']==v['candidate']) for v in x.values()]; wj('protected-source-parity.json',x); assert all(v['equal'] for v in x.values())

def main():
 for n,f in [('preflight',preflight),('materialization',materialize),('environment/requirements',env_req),('static',static),('compile/tests/smokes',suites),('schema runtime',schema),('Qt runtime',qt),('JUnit differential',diff),('protected parity',parity)]: gate(n,f)
 wt('decision.txt',('PASS' if not failures else 'FAIL')+'\n'+'\n'.join(failures)); wj('pr-state.json',{'number':os.getenv('PR_NUMBER'),'title':'TEMP VALIDATION: Agenda Stage 5B-V','base':'main','head':BR,'run_id':os.getenv('GITHUB_RUN_ID'),'job':os.getenv('GITHUB_JOB')}); return 1 if failures else 0
if __name__=='__main__': raise SystemExit(main())
