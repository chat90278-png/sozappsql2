from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,platform,subprocess,sys,tempfile,traceback
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
S="04C-V"; B="c52c59ca15756ca0accd0a3910a1e20b9c66c4ea"; P="e1bfe4014b05c0e694cb1012198bf0134e8cfc77"; A="90aad699cdbe95b3e3dd692ec7046095785f21c5"; MB="2931fa267560397d4d849d6365acde504f376775"; N=datetime(2026,7,13,12); T={".github/workflows/agenda-stage-04c-v-runtime-validation.yml","tools/validation/agenda_stage_04c_v_runtime_validation.py"}
PT={"docs/agenda/AGENDA_STAGE_04C_CONTRACT_ACTIVITY_PROVIDER.md","src/domain/agenda/__init__.py","src/domain/agenda/activity.py","src/domain/agenda/providers/__init__.py","src/domain/agenda/providers/activity.py","src/domain/agenda/source_models.py","src/services/agenda_source_repository.py","src/services/staff_agenda_service.py","tests/test_activity_agenda_provider.py","tests/test_agenda_source_repository.py","tests/test_personal_agenda_facade.py","tests/test_staff_agenda_service.py"}
TF=["tests/test_agenda_source_repository.py","tests/test_activity_agenda_provider.py","tests/test_staff_agenda_service.py","tests/test_personal_agenda_facade.py","tests/test_agenda_context_factory.py","tests/test_agenda_lifecycle.py","tests/test_agenda_models.py","tests/test_deadline_agenda_provider.py","tests/test_unknown_date_agenda_provider.py","tests/test_returned_share_agenda_provider.py","tests/test_document_lock_agenda_provider.py"]
def q(x,m):
 if not x: raise AssertionError(m)
def d(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True,default=str)+"\n",encoding="utf8")
def r(c,w,l=None,e=None):
 z=os.environ.copy();z.update(e or {});o=subprocess.run(c,cwd=w,env=z,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,errors="replace")
 if l:l.write_text("$ "+subprocess.list2cmdline(c)+f"\nabsolute_exit={o.returncode}\n\n"+o.stdout,encoding="utf8")
 return o
def g(w,*a): o=r(["git",*a],w);q(o.returncode==0,o.stdout);return o.stdout.strip()
def ps(w,a,b):return sorted(x.replace("\\","/") for x in g(w,"diff","--name-only",a,b).splitlines() if x)
def sh(p):b=p.read_bytes();return {"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def ju(p):
 R=ET.parse(p).getroot();C=list(R.iter("testcase"));f=sum(c.find("failure")is not None for c in C);e=sum(c.find("error")is not None for c in C);s=sum(c.find("skipped")is not None for c in C)
 return {"valid":True,"tests":len(C),"passed":len(C)-f-e-s,"failures":f,"errors":e,"skipped":s,"duration":sum(float(c.get("time")or 0)for c in C),"nodes":sorted({f"{c.get('classname','')}::{c.get('name','')}"for c in C if c.find("failure")is not None or c.find("error")is not None})}
def hm(f):
 s=importlib.util.spec_from_file_location("_h",f/"tests/test_agenda_source_repository.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class SS:
 def __init__(s,x):
  s.x=x;s.p=[];s.a=0;s.l=[];s.pc=0;o=x._platform_names_by_contract
  def cp(i):s.pc+=1;return o(i)
  x._platform_names_by_contract=cp
 def list_personal_contract_ids(s,i):s.p.append(i);return s.x.list_personal_contract_ids(i)
 def list_all_contract_ids(s):s.a+=1;return s.x.list_all_contract_ids()
 def load_personal_sources(s,i,*,activity_since=None):s.l.append({"ids":sorted(i),"since":str(activity_since)});return s.x.load_personal_sources(i,activity_since=activity_since)
class ST:
 def __init__(s,x):s.x=x;s.c=defaultdict(list)
 def z(s,n,*a,**k):s.c[n].append({"args":list(a),"kwargs":k});return getattr(s.x,n)(*a,**k)
 def get_states(s,*a,**k):return s.z("get_states",*a,**k)
 def touch_presented(s,*a,**k):return s.z("touch_presented",*a,**k)
 def mark_seen(s,*a,**k):return s.z("mark_seen",*a,**k)
 def snooze(s,*a,**k):return s.z("snooze",*a,**k)
 def clear_snooze(s,*a,**k):return s.z("clear_snooze",*a,**k)
class PP:
 def __init__(s,p):s.p=p;s.code=p.code;s.e=s.b=0
 def is_enabled(s,c):s.e+=1;return s.p.is_enabled(c)
 def build(s,c,x):s.b+=1;return s.p.build(c,x)
def ses(i,role,perms,n,dev):return {"id":i,"role":role,"role_name":role,"full_name":n,"device_name":dev,"is_active":1,"permissions":frozenset(perms)}
def ac(c,**k):
 cid=k.pop("cid");action=k.pop("action","contract_updated");at=k.pop("at","2026-07-13 10:00:00");etype=k.pop("etype","contract");eid=k.pop("eid",None);before=k.pop("before",{"completion_date":"old"});after=k.pop("after",{"completion_date":"new"});rb=k.pop("rb",None);ra=k.pop("ra",None)
 bj=rb if rb is not None else json.dumps(before,ensure_ascii=False);aj=ra if ra is not None else json.dumps(after,ensure_ascii=False)
 return int(c.execute("INSERT INTO activity_logs(created_at,actor,source,device_name,action,entity_type,entity_id,contract_no,message,before_json,after_json,payload_json)VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(at,k.pop("actor","Actor"),k.pop("source","Runtime"),k.pop("device","DEVICE"),action,etype,str(cid)if eid is None else eid,k.pop("contract_no",None),k.pop("message","message"),bj,aj,k.pop("payload",None))).lastrowid)
def rt(f,o):
 os.chdir(f);sys.path.insert(0,str(f))
 from PySide6 import __version__ as pv
 from PySide6.QtCore import Qt
 from PySide6.QtWidgets import QApplication,QPushButton,QToolButton
 from src import auth
 from src.domain.agenda.constants import AgendaLifecycleType,AgendaPresentationProfileCode,AgendaSeverity
 from src.domain.agenda.lifecycle import AgendaLifecycleEngine
 from src.domain.agenda.models import AgendaItemState,AgendaResult
 from src.domain.agenda.presentation import project_agenda_result
 from src.domain.agenda.providers import ActivityAgendaProvider,DeadlineAgendaProvider,ReturnedShareAgendaProvider,DocumentLockAgendaProvider,UnknownDateAgendaProvider
 from src.domain.agenda.source_models import AgendaSourceBundle
 from src.services.agenda_context_factory import PersonalAgendaContextFactory
 from src.services.agenda_source_repository import AgendaSourceRepository
 from src.services.agenda_state_repository import AgendaStateRepository
 from src.services.personal_agenda_facade import PersonalAgendaFacade,AgendaInteractionError
 from src.services.staff_agenda_service import StaffAgendaService
 from src.services.sts_database import STSDatabase,CURRENT_SCHEMA_VERSION
 from src.ui.agenda_compact_widget import AgendaCompactWidget
 from src.ui.agenda_detail_window import AgendaDetailWindow
 H=hm(f);E={}
 with tempfile.TemporaryDirectory()as td:
  db=STSDatabase(Path(td)/"v.sts",source=S);c=db.conn
  try:
   q(CURRENT_SCHEMA_VERSION==18,"schema");I=H._seed(db)
   with db.tx():
    c.execute("UPDATE contracts SET contract_no='DUP' WHERE id IN (?,?)",(I["c1"],I["c2"]));roles={x["name"]:int(x["id"])for x in c.execute("select id,name from roles")}
    c.execute("insert into roles(name,display_name,is_system)values('custom_activity','Custom',0)");roles["custom_activity"]=int(c.execute("select id from roles where name='custom_activity'").fetchone()[0])
    X={}
    for k,ro,n,de in(("m","manager","Manager","mdev"),("v","viewer","Viewer","vdev"),("x","custom_activity","Custom","xdev")):X[k]=int(c.execute("insert into staff(device_name,full_name,password_hash,role,role_id,is_active)values(?,?,?,?,?,1)",(de,n,"x",ro,roles.get(ro))).lastrowid)
    def nc(no,date,p=I["p1"]):
     return int(c.execute("insert into contracts(platform_id,contract_no,contract_type,status,completion_date,merge_uid,revision)values(?,?,?,?,?,?,1)",(p,no,"Ana","Açık",date,"m-"+no)).lastrowid)
    C={"a":I["c1"],"b":I["c2"],"u":nc("UNKNOWN","TBD"),"s":nc("SHARE","2026-07-20",I["p2"]),"l":nc("LOCK","2026-07-25"),"out":nc("OUT","2026-07-30",I["p2"])}
    c.execute("update contracts set completion_date='2026-07-12'where id=?",(C["a"],));c.execute("insert into contract_responsible_engineers(contract_id,staff_id,is_primary)values(?,?,1)",(C["u"],I["staff1"]));c.execute("insert into contract_responsible_engineers(contract_id,staff_id,is_primary)values(?,?,1)",(C["b"],X["x"]))
    for z,p in((C["u"],I["p1"]),(C["s"],I["p2"]),(C["l"],I["p1"]),(C["out"],I["p2"])):c.execute("insert or ignore into contract_platforms(contract_id,platform_id,sort_order,is_primary)values(?,?,0,1)",(z,p))
    H._insert_share(db,contract_id=C["s"],package_id="pkg-v",staff_id=I["staff1"]);H._insert_lock(db,contract_id=C["l"],staff_id=I["staff1"])
    c.execute("insert into staff_agenda_state(staff_id,agenda_key,seen_at,seen_version,created_at,updated_at)values(?,?,?,?,?,?)",(I["staff1"],"collision:seed","2026-07-01","V1","2026-07-01","2026-07-01"))
    L={};L["up"]=ac(c,cid=C["a"],before={"completion_date":"2026-07-20","acceptance_date":None,"status":"Açık","note":"old"},after={"completion_date":"2026-07-21","acceptance_date":"2026-08-01","status":"Kapalı","note":"new"},actor="S1",device="d1")
    L["sa"]=ac(c,cid=C["a"],action="contract_status_changed",at="2026-07-13 10:05:00",before={"status":"Açık"},after={"status":"Kapalı"},actor="S1",device="d1");L["sb"]=ac(c,cid=C["b"],action="contract_status_changed",at="2026-07-13 10:06:00",before={"status":"Açık"},after={"status":"Kapalı"})
    bad=[ac(c,cid=C["a"],action=x)for x in("contract_created","system_updated","delivery_updated","bad")]+[ac(c,cid=C["a"],etype="system"),ac(c,cid=C["a"],eid=""),ac(c,cid=C["a"],eid="abc"),ac(c,cid=C["a"],eid=f"{C['a']}x"),ac(c,cid=C["a"],eid=f"0{C['a']}"),ac(c,cid=C["out"]),ac(c,cid=C["a"],rb="",ra="{}"),ac(c,cid=C["a"],rb="{bad",ra="{}"),ac(c,cid=C["a"],rb="[]",ra="{}"),ac(c,cid=C["a"],rb="{}",ra="1"),ac(c,cid=C["a"],before={"completion_date":" x "},after={"completion_date":"x"}),ac(c,cid=C["a"],before={"completion_date":{"a":1}},after={"completion_date":{"a":2}})]
    L["old"]=ac(c,cid=C["a"],at="2026-07-05 11:59:59");L["cut"]=ac(c,cid=C["a"],at="2026-07-05 12:00:00");L["new"]=ac(c,cid=C["a"],at="2026-07-05 12:00:01");L["7n"]=ac(c,cid=C["a"],at="2026-07-06 12:00:01");L["7"]=ac(c,cid=C["a"],at="2026-07-06 12:00:00");L["7o"]=ac(c,cid=C["a"],at="2026-07-05 18:00:00");L["inv"]=ac(c,cid=C["a"],at="not-a-time");L["t1"]=ac(c,cid=C["a"],at="2026-07-12 08:00:00");L["t2"]=ac(c,cid=C["a"],at="2026-07-12 08:00:00")
   cut=N-timedelta(days=8);R=AgendaSourceRepository(db);src=R.list_activity_sources([C["a"],C["b"]],activity_since=cut);got={x.log_id for x in src};need={L[x]for x in("up","sa","sb","new","7n","7","7o","inv","t1","t2")}
   q(need<=got and not(set(bad)|{L["old"],L["cut"]})&got,"repository filter");q({x.contract_id for x in src if x.log_id in(L["sa"],L["sb"])}=={C["a"],C["b"]},"identity");q([x.log_id for x in src if x.created_at=="2026-07-12 08:00:00"]==[L["t2"],L["t1"]],"order")
   q([x.log_id for x in R.list_activity_sources([C["a"],C["b"]],activity_since=" 2026-07-05 12:00:00 ")]==[x.log_id for x in src],"string cutoff")
   et=[];c.set_trace_callback(et.append);q(R.list_activity_sources([])==(),"empty");c.set_trace_callback(None);q(not et,"empty query")
   tr=[];bc=c.total_changes;bt=c.in_transaction;c.set_trace_callback(tr.append);du=R.list_activity_sources([C["a"],C["a"]],activity_since=cut);c.set_trace_callback(None);aq=[x for x in tr if"FROM activity_logs AS l"in x]
   q(c.total_changes==bc and c.in_transaction==bt and all(x.lstrip().upper().startswith("SELECT")for x in tr)and len(aq)==1 and" staff "not in aq[0].lower(),"readonly")
   RB=AgendaSourceRepository(db);pc=[0];op=RB._platform_names_by_contract
   def cp(i):pc[0]+=1;return op(i)
   RB._platform_names_by_contract=cp;bu=RB.load_personal_sources([C["a"],C["s"],C["l"]],activity_since=cut);q(all((bu.calendar,bu.returned_shares,bu.document_locks,bu.activities))and pc[0]==1,"bundle")
   RE={"status":"PASS","accepted":sorted(got),"skipped":sorted(set(bad)|{L["old"],L["cut"]}),"order":[[x.created_at,x.log_id]for x in src],"empty_queries":len(et),"activity_queries":len(aq),"total_changes":[bc,c.total_changes],"transaction":[bt,c.in_transaction],"platform":pc[0],"bundle":{"calendar":len(bu.calendar),"returned":len(bu.returned_shares),"locks":len(bu.document_locks),"activities":len(bu.activities)}};d(o/"repository-runtime.json",RE);d(o/"sql-trace-summary.json",{"trace":tr})
   F=PersonalAgendaContextFactory(now_provider=lambda:N);person=ses(I["staff1"],"personnel",{"view_contracts"},"S1","d1");ctx=F.build(person,now=N,personal_contract_ids=[C["a"],C["b"]]);AP=ActivityAgendaProvider();it=AP.build(ctx,AgendaSourceBundle(activities=tuple(src)));by={(x.detail_payload["log_id"],x.detail_payload["field_name"]):x for x in it}
   q({f for(l,f)in by if l==L["up"]}=={"completion_date","acceptance_date"}and{f for(l,f)in by if l==L["sa"]}=={"status"},"fields")
   for(l,f),x in by.items():q(x.key==f"activity:activity_log:{l}:{f}"and x.version==f"ACTIVITY:{l}:{f}:{x.event_at}"and x.lifecycle_type==AgendaLifecycleType.EVENT and x.priority==450 and x.severity==AgendaSeverity.INFO and x.actor_staff_id is None and not x.supports_snooze and x.action_hints==("open_contract",)and x.detail_payload["actor_identity_verified"]is False,"item")
   q(any(x.detail_payload["log_id"]==L["sa"]and x.actor_name=="S1"for x in it),"self filter");PE={"status":"PASS","keys":[x.key for x in it],"update_fields":sorted(f for(l,f)in by if l==L["up"]),"actor_visible":True};d(o/"activity-projection.json",PE)
   def sv(ss,ov=()):
    sr=SS(AgendaSourceRepository(db));st=ST(AgendaStateRepository(db));pp=[PP(x)for x in(DeadlineAgendaProvider(),ReturnedShareAgendaProvider(),DocumentLockAgendaProvider(),UnknownDateAgendaProvider(),ActivityAgendaProvider())];cx=F.build(ss,now=N,personal_contract_ids=ov);rr=StaffAgendaService(db,state_repository=st,source_repository=sr,providers=pp).build(cx,touch_presented=False);cl={"source":{"personal":sr.p,"all":sr.a,"loads":sr.l,"platform":sr.pc},"state":dict(st.c),"providers":{p.code:{"is_enabled":p.e,"build":p.b}for p in pp}};return cx,rr,cl
   mgr=ses(X["m"],"manager",{"view_contracts","edit_contracts","unlock_all_documents"},"Manager","mdev");view=ses(X["v"],"viewer",{"view_contracts"},"Viewer","vdev");custom=ses(X["x"],"custom_activity",{"view_contracts"},"Custom","xdev");M={}
   for n,s,o2 in(("personnel",person,()),("manager",mgr,()),("viewer",view,()),("custom",custom,()),("override",person,{C["b"]})):
    cx,rr,cl=sv(s,o2);M[n]={"profile":cx.presentation_profile.code.value,"scope":cx.contract_scope.value,"permissions":sorted(cx.permissions),"resolved":cl["source"]["loads"][0]["ids"]if cl["source"]["loads"]else[],"activity":[x.key for x in rr.items if x.kind=="activity"],"calls":cl}
   q(any(x.kind=="activity"for x in sv(view)[1])and not any(x.kind in("returned_share","document_lock")for x in sv(view)[1]),"viewer");z=dict(custom);z["permissions"]=frozenset();_,zr,zc=sv(z);q(not zr.items and not zc["source"]["loads"]and not zc["state"],"no view");q(not sv(person,{C["b"]})[2]["source"]["personal"]and sv(person,{C["b"]})[2]["source"]["all"]==0,"override");d(o/"profile-permission-scope.json",{"status":"PASS","matrix":M})
   eng=AgendaLifecycleEngine();recent=by[(L["sa"],"status")];si=lambda lid:next(x for x in it if x.detail_payload["log_id"]==lid and x.detail_payload["field_name"]=="completion_date");i7n,i7,io,iv=map(si,(L["7n"],L["7"],L["7o"],L["inv"]))
   q(eng.evaluate(recent,None,N).reason=="event_new"and eng.evaluate(i7n,None,N).visible and eng.evaluate(i7,None,N).reason=="event_unseen_ttl_expired"and eng.evaluate(io,None,N).reason=="event_unseen_ttl_expired"and eng.evaluate(iv,None,N).reason=="event_timestamp_invalid","ttl")
   AR=AgendaStateRepository(db);FA=PersonalAgendaFacade(db,context_factory=F,agenda_service=StaffAgendaService(db,state_repository=AR),state_repository=AR);sb=[dict(x)for x in c.execute("select * from staff_agenda_state order by staff_id,agenda_key")];FA.mark_seen(person,recent,seen_at=N-timedelta(hours=1));sn=FA.load(person,now=N,touch_presented=False);q(recent.key not in sn.new_keys and any(x.key==recent.key for x in sn.all_items),"seen")
   s23=AgendaItemState(staff_id=I["staff1"],agenda_key=recent.key,seen_at="2026-07-12 12:00:01",seen_version=recent.version);s24=AgendaItemState(staff_id=I["staff1"],agenda_key=recent.key,seen_at="2026-07-12 12:00:00",seen_version=recent.version);so=AgendaItemState(staff_id=I["staff1"],agenda_key=io.key,seen_at="2026-07-13 11:00:00",seen_version=io.version);sbad=AgendaItemState(staff_id=I["staff1"],agenda_key=recent.key,seen_at="bad",seen_version=recent.version)
   q(eng.evaluate(recent,s23,N).visible and eng.evaluate(recent,s24,N).reason=="event_seen_ttl_expired"and eng.evaluate(io,so,N).visible and eng.evaluate(recent,sbad,N).reason=="event_seen_timestamp_invalid","state ttl");AR.dismiss_event(I["staff1"],i7n.key,i7n.version,N);q(eng.evaluate(i7n,AR.get_states(I["staff1"],[i7n.key])[i7n.key],N).reason=="dismissed","dismiss")
   be=c.total_changes;err=""
   try:FA.snooze(person,recent,until=N+timedelta(days=1),now=N)
   except AgendaInteractionError as x:err=str(x)
   q(err and c.total_changes==be,"snooze");sa=[dict(x)for x in c.execute("select * from staff_agenda_state order by staff_id,agenda_key")];LE={"status":"PASS","new":"event_new","seven_new":eng.evaluate(i7n,None,N).reason,"seven_exact":eng.evaluate(i7,None,N).reason,"old_seen":eng.evaluate(io,so,N).reason,"invalid_seen":eng.evaluate(recent,sbad,N).reason,"snooze_error":err};d(o/"event-lifecycle.json",LE);d(o/"state-before-after.json",{"before":sb,"after":sa})
   auth.create_system_admin(c,"root","pw");ad=auth.build_system_admin_session(auth.verify_system_admin_login(c,"root","pw"),"sys");q(ad["admin_id"]==I["staff1"],"collision");cb=dict(c.execute("select * from staff_agenda_state where staff_id=?and agenda_key='collision:seed'",(I["staff1"],)).fetchone());SM={}
   for n,s,ov in(("normal",ad,()),("injected",{**ad,"permissions":{"view_contracts"}},()),("override",{**ad,"permissions":{"view_contracts"}},{C["a"]})):
    cx,rr,cl=sv(s,ov);q(cx.presentation_profile.code==AgendaPresentationProfileCode.SYSTEM and cx.staff_id is None and not rr.items and not cl["source"]["loads"]and not cl["state"]and all(v=={"is_enabled":0,"build":0}for v in cl["providers"].values()),"system");SM[n]=cl
   ee=[];SF=PersonalAgendaFacade(db,context_factory=F)
   for op in("mark_seen","snooze","clear_snooze"):
    try:
     if op=="mark_seen":SF.mark_seen({**ad,"permissions":{"view_contracts"}},recent)
     elif op=="snooze":SF.snooze({**ad,"permissions":{"view_contracts"}},recent,until=N+timedelta(days=1),now=N)
     else:SF.clear_snooze({**ad,"permissions":{"view_contracts"}},recent)
    except AgendaInteractionError as x:ee.append([op,str(x)])
   q(len(ee)==3 and cb==dict(c.execute("select * from staff_agenda_state where staff_id=?and agenda_key='collision:seed'",(I["staff1"],)).fetchone()),"system interactions");SY={"status":"PASS","session":ad,"matrix":SM,"errors":ee,"collision":True};d(o/"system-admin.json",SY)
   _,mr,mc=sv(mgr);K=[(x.kind,x.priority,x.key)for x in mr.items];q(any(a=="unknown_date"and b==500 for a,b,_ in K)and any(a=="activity"and b==450 for a,b,_ in K)and len({x.key for x in mr.items})==len(mr.items)and len(mc["source"]["loads"])==1 and mc["source"]["platform"]==1,"coexist");CO={"status":"PASS","items":K,"load":1,"platform":1};d(o/"coexistence-priority.json",CO)
   app=QApplication.instance()or QApplication([]);one=AgendaResult(profile=ctx.presentation_profile,items=(recent,),new_count=1,active_count=1,counts_by_kind={"activity":1},new_keys=frozenset({recent.key}),states_by_key={},snoozed_count=0,filtered_count=0);shot=project_agenda_result(one,compact_limit=5,detail_limit=5);cw=AgendaCompactWidget();co=[];cw.open_contract_requested.connect(co.append);cw.set_snapshot(shot);app.processEvents();b1=cw.findChild(QToolButton,"agendaCompactOpenContract");q(len(cw._rows)==1 and cw._rows[0].property("agendaKey")==recent.key and b1,"compact");b1.click();dw=AgendaDetailWindow();do=[];dw.open_contract_requested.connect(do.append);dw.set_snapshot(shot);dw.show();cw.show();app.processEvents();b2=dw.findChild(QPushButton,"agendaDetailOpenContract");q(len(dw._rows)==1 and b2 and dw.findChild(QToolButton,"agendaDetailSnooze")is None and bool(dw.windowFlags()&Qt.Tool),"detail");b2.click();app.processEvents();q(co==[recent.contract_id]and do==[recent.contract_id],"signals");png=[]
   try:
    p1=o/"activity-compact.png";p2=o/"activity-detail.png"
    if cw.grab().save(str(p1))and dw.grab().save(str(p2)):png=[p1.name,p2.name]
   except Exception:pass
   QT={"status":"PASS","PySide6":pv,"rows":[len(cw._rows),len(dw._rows)],"signals":[co,do],"pngs":png};d(o/"qt-presentation.json",QT);cw.close();dw.close()
   E={"repository_runtime":RE,"activity_projection":PE,"profile_permission_scope":{"status":"PASS"},"event_lifecycle":LE,"system_admin":SY,"coexistence_priority":CO,"qt_presentation":QT};d(o/"runtime-evidence.json",E);return E,{"PySide6":pv}
  finally:db.close()
def main():
 a=argparse.ArgumentParser();a.add_argument("--baseline",required=True);a.add_argument("--feature",required=True);a.add_argument("--evidence",required=True);x=a.parse_args();b=Path(x.baseline).resolve();f=Path(x.feature).resolve();o=Path(x.evidence).resolve();o.mkdir(parents=True,exist_ok=True);ev={"QT_QPA_PLATFORM":"offscreen","PYTHONUTF8":"1","PYTHONHASHSEED":"0"};er=[];h=g(f,"rev-parse","HEAD");(o/"git-status-before.txt").write_text(g(f,"status","--porcelain=v1","--branch")+"\n");(o/"git-diff-before.txt").write_text(g(f,"diff","--")+"\n")
 try:
  doc=(f/"docs/agenda/AGENDA_STAGE_04C_R1_EXECUTION_VALIDATION.md").read_text();pre={"head":h,"ancestor":r(["git","merge-base","--is-ancestor",A,h],f).returncode==0,"temp":ps(f,A,h),"product":ps(f,B,P),"r1e":ps(f,P,A),"main":g(f,"rev-parse","origin/main"),"merge_base":g(f,"merge-base",h,"origin/main"),"old_temp_absent":not(f/".github/workflows/agenda-stage-04c-r1-execution-validation.yml").exists()and not(f/"tools/validation/validate_agenda_stage_04c_r1_execution.py").exists(),"decisions":all(z in doc for z in("STAGE 4C-R1 INTEGRATION CONTRACT: ACCEPTED","STAGE 4C-R1 EXECUTION GATE: PASS","STAGE 4C STATIC/SOURCE TEST GATE: PASS","STAGE 4C-V RUNTIME DIFFERENTIAL GATE: OPEN","MAIN MERGE GATE: CLOSED"))};ok=pre["ancestor"]and set(pre["temp"])==T and set(pre["product"])==PT and pre["r1e"]==["docs/agenda/AGENDA_STAGE_04C_R1_EXECUTION_VALIDATION.md"]and pre["merge_base"]==MB and pre["old_temp_absent"]and pre["decisions"];pre["status"]="PASS"if ok else"FAIL"
 except Exception as z:pre={"status":"FAIL","error":str(z)};ok=False;er.append("preflight "+str(z))
 d(o/"preflight.json",pre);pa={"baseline":sh(b/"requirements.txt"),"feature":sh(f/"requirements.txt")};pa["equal"]=(b/"requirements.txt").read_bytes()==(f/"requirements.txt").read_bytes();pa["status"]="PASS"if pa["equal"]else"FAIL";d(o/"requirements-parity.json",pa)
 try:R,V=rt(f,o)
 except Exception as z:R={k:{"status":"FAIL"}for k in("repository_runtime","activity_projection","profile_permission_scope","event_lifecycle","system_admin","coexistence_priority","qt_presentation")};V={};er.append("runtime "+str(z));(o/"runtime-error.txt").write_text(traceback.format_exc())
 E={"os":platform.platform(),"arch":platform.machine(),"python":sys.version.replace("\n"," "),"executable":sys.executable,"pip":r([sys.executable,"-m","pip","--version"],f).stdout.strip(),"pytest":r([sys.executable,"-m","pytest","--version"],f).stdout.strip(),**V,**ev,"root":str(f),"head":h,"github_ref":os.getenv("GITHUB_REF",""),"github_head_ref":os.getenv("GITHUB_HEAD_REF",""),"baseline":B,"product":P,"starting":A,"main":pre.get("main"),"merge_base":pre.get("merge_base")};(o/"environment.txt").write_text("\n".join(f"{k}={v}"for k,v in E.items())+"\n")
 cr=r([sys.executable,"-m","compileall","-q","src","tests"],f,o/"compile.log",ev);(o/"compile-exit.txt").write_text(str(cr.returncode));CS={"absolute_exit":cr.returncode,"status":"PASS"if cr.returncode==0 else"FAIL"}
 tx=o/"static-targeted.xml";tr=r([sys.executable,"-m","pytest","-q",*TF,f"--junitxml={tx}"],f,o/"static-targeted.log",ev);(o/"static-targeted-exit.txt").write_text(str(tr.returncode))
 try:TS=ju(tx)
 except Exception as z:TS={"valid":False,"tests":0,"passed":0,"failures":0,"errors":1,"skipped":0,"nodes":[]};er.append("static junit "+str(z))
 TS["absolute_exit"]=tr.returncode;TS["status"]="PASS"if tr.returncode==0 and TS["tests"]==329 and TS["passed"]==329 and not TS["failures"]and not TS["errors"]and not TS["skipped"]else"FAIL";d(o/"static-targeted-summary.json",TS)
 sr=r([sys.executable,"tests/smoke_sts_agenda_schema.py"],f,o/"agenda-schema-smoke.log",ev);(o/"agenda-schema-smoke-exit.txt").write_text(str(sr.returncode));SC={"absolute_exit":sr.returncode,"markers":"agenda_schema=PASS"in sr.stdout and"schema_version=18"in sr.stdout};SC["status"]="PASS"if sr.returncode==0 and SC["markers"]else"FAIL"
 dr=r([sys.executable,"tests/smoke_sts_database.py"],f,o/"database-smoke.log",ev);(o/"database-smoke-exit.txt").write_text(str(dr.returncode));DB={"absolute_exit":dr.returncode,"ok":any(z.strip()=="ok"for z in dr.stdout.splitlines())};DB["status"]="PASS"if dr.returncode==0 and DB["ok"]else"FAIL"
 def full(w,n):
  z=o/f"{n}-full.xml";rr=r([sys.executable,"-m","pytest","-q",f"--junitxml={z}"],w,o/f"{n}-full.log",ev);(o/f"{n}-full-exit.txt").write_text(str(rr.returncode))
  try:s=ju(z)
  except Exception as y:s={"valid":False,"tests":0,"passed":0,"failures":0,"errors":1,"skipped":0,"nodes":[],"error":str(y)}
  s["absolute_exit"]=rr.returncode;s["infrastructure_ok"]=rr.returncode not in(2,3,4,5);d(o/f"{n}-full-summary.json",s);(o/f"{n}-failure-nodes.txt").write_text("\n".join(s["nodes"])+"\n");return s
 BS=full(b,"baseline");FS=full(f,"feature");fo=sorted(set(FS["nodes"])-set(BS["nodes"]));bo=sorted(set(BS["nodes"])-set(FS["nodes"]));DI={"feature_only":fo,"baseline_only":bo,"feature_only_count":len(fo),"baseline_only_count":len(bo),"feature_more_tests":FS["tests"]>BS["tests"]};DI["status"]="PASS"if pa["equal"]and BS.get("valid")and FS.get("valid")and BS["infrastructure_ok"]and FS["infrastructure_ok"]and not fo and not bo and DI["feature_more_tests"]else"FAIL";d(o/"full-differential.json",DI);(o/"feature-only-nodes.txt").write_text("\n".join(fo)+"\n");(o/"baseline-only-nodes.txt").write_text("\n".join(bo)+"\n")
 vals=[pre["status"],pa["status"],CS["status"],TS["status"],SC["status"],DB["status"],*[R[k]["status"]for k in R],"PASS"if BS.get("valid")and BS["infrastructure_ok"]else"FAIL","PASS"if FS.get("valid")and FS["infrastructure_ok"]else"FAIL",DI["status"]];allok=all(z=="PASS"for z in vals);SU={"stage":S,"baseline_head":B,"product_source_head":P,"starting_head":A,"workflow_head":h,"preflight":pre["status"],"environment":E,"requirements_parity":pa,"compile":CS,"static_targeted":TS,"schema_smoke":SC,"database_smoke":DB,**R,"baseline_full":BS,"feature_full":FS,"differential":DI,"overall":"PASS"if allok else"FAIL","errors":er};d(o/"validation-summary.json",SU);print(json.dumps(SU,ensure_ascii=False,indent=2,default=str));return 0 if allok else 1
if __name__=="__main__":raise SystemExit(main())
