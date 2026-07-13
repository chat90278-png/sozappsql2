from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, sys, tempfile, traceback
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

B="bc5feca2aa755b4e12c98b9932810778ec08d6cb"
P="973c96af0bc431029a0d027ec39dea3e5261e275"
TMP={".github/workflows/agenda-stage-04a-v-runtime-validation.yml","tools/validation/agenda_stage_04a_v_runtime_validation.py"}
NOW=datetime(2026,7,13,12,0,0)

def req(x,m):
    if not x: raise AssertionError(m)
def text(x): return json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True,default=str)
def jdump(p,x): p.write_text(text(x),encoding="utf-8")
def run(cmd,cwd,log,env=None):
    e=os.environ.copy(); e.update(env or {})
    r=subprocess.run(cmd,cwd=cwd,env=e,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,errors="replace")
    log.write_text("$ "+subprocess.list2cmdline(cmd)+f"\nexit_code={r.returncode}\n\n"+r.stdout,encoding="utf-8")
    return r
def gout(cwd,*a):
    r=subprocess.run(["git",*a],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    req(r.returncode==0,f"git {' '.join(a)}: {r.stderr}"); return r.stdout.strip()
def jsum(p):
    root=ET.parse(p).getroot(); cases=list(root.iter("testcase"))
    nodes=sorted({f"{c.get('classname','')}::{c.get('name','')}" for c in cases if c.find("failure") is not None or c.find("error") is not None})
    return {"tests":len(cases),"failures":sum(c.find("failure") is not None for c in cases),"errors":sum(c.find("error") is not None for c in cases),"skipped":sum(c.find("skipped") is not None for c in cases),"nodes":nodes}
def sha(p):
    b=p.read_bytes(); return {"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}

class CS:
    def __init__(self,x): self.x=x; self.p=[]; self.a=[]; self.l=[]
    def list_personal_contract_ids(self,i): self.p.append(i); return self.x.list_personal_contract_ids(i)
    def list_all_contract_ids(self): self.a.append(1); return self.x.list_all_contract_ids()
    def load_personal_sources(self,ids): self.l.append(sorted(ids)); return self.x.load_personal_sources(ids)
class ST:
    def __init__(self,x): self.x=x; self.c=defaultdict(list)
    def _f(self,n,*a,**k): self.c[n].append([list(a),k]); return getattr(self.x,n)(*a,**k)
    def get_states(self,*a,**k): return self._f("get_states",*a,**k)
    def touch_presented(self,*a,**k): return self._f("touch_presented",*a,**k)
    def mark_seen(self,*a,**k): return self._f("mark_seen",*a,**k)
    def snooze(self,*a,**k): return self._f("snooze",*a,**k)
    def clear_snooze(self,*a,**k): return self._f("clear_snooze",*a,**k)
class CP:
    def __init__(self,x): self.x=x; self.code=x.code; self.e=0; self.b=0
    def is_enabled(self,c): self.e+=1; return self.x.is_enabled(c)
    def build(self,c,s): self.b+=1; return self.x.build(c,s)
class OFF:
    code="off"
    def __init__(self): self.e=0; self.b=0
    def is_enabled(self,c): self.e+=1; return False
    def build(self,c,s): self.b+=1; return ()
def calls(s,st,ps): return {"source":{"personal":s.p,"all":len(s.a),"load":s.l},"state":dict(st.c),"providers":{p.code:{"enabled":p.e,"build":p.b} for p in ps}}

def seed(db):
    from src.models.share_models import SHARE_STATUS_RETURNED
    c=db.conn
    with db.tx():
        roles={r["name"]:int(r["id"]) for r in c.execute("select id,name from roles")}
        c.execute("insert into roles(name,display_name,is_system) values('custom_agenda','Custom',0)")
        roles["custom_agenda"]=c.execute("select id from roles where name='custom_agenda'").fetchone()[0]
        for rn,allow in {"personnel":{"view_contracts","edit_contracts"},"viewer":{"view_contracts"},"manager":{"view_contracts","edit_contracts"},"custom_agenda":{"view_contracts"}}.items():
            for code in ("view_contracts","edit_contracts"):
                c.execute("insert into role_permissions(role_id,permission_code,is_allowed) values(?,?,?) on conflict(role_id,permission_code) do update set is_allowed=excluded.is_allowed",(roles[rn],code,int(code in allow)))
        ids={}
        for k,rn in (("personnel","personnel"),("viewer","viewer"),("manager","manager"),("custom","custom_agenda")):
            ids[k]=c.execute("insert into staff(device_name,full_name,password_hash,role,role_id,is_active) values(?,?,?,?,?,1)",(f"v-{k}",k,"x",rn,roles[rn])).lastrowid
        pf=c.execute("insert into platforms(name,display_name,is_active) values('V','V',1)").lastrowid
        ids["c1"]=c.execute("insert into contracts(platform_id,contract_no,contract_type,status,completion_date,merge_uid,revision) values(?,?,?,?,?,?,?)",(pf,"C1","Ana","Açık","2026-07-14","m1",1)).lastrowid
        ids["c2"]=c.execute("insert into contracts(platform_id,contract_no,contract_type,status,completion_date,merge_uid,revision) values(?,?,?,?,?,?,?)",(pf,"C2","Ana","Açık","TBD","m2",1)).lastrowid
        c.execute("insert into contract_responsible_engineers(contract_id,staff_id,is_primary) values(?,?,1)",(ids["c1"],ids["personnel"]))
        c.execute("insert into contract_responsible_engineers(contract_id,staff_id,is_primary) values(?,?,1)",(ids["c2"],ids["custom"]))
        c.execute("""insert into share_packages(share_package_id,contract_id,contract_merge_uid,source_contract_revision,permission_mode,share_format_version,snapshot_format_version,base_snapshot_sha256,created_at,created_by_staff_id,created_by_full_name,exported_filename,status,last_imported_at,last_imported_by_staff_id,last_remote_snapshot_sha256,return_count) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",("pkg",ids["c1"],"m1",1,"edit",2,1,"h","2026-07-12",ids["personnel"],"P","p.sts",SHARE_STATUS_RETURNED,"2026-07-12",ids["personnel"],"rh",1))
        c.execute("""insert into staff_agenda_state(staff_id,agenda_key,first_presented_at,last_presented_at,seen_at,seen_version,created_at,updated_at) values(?,?,?,?,?,?,?,?)""",(ids["personnel"],"collision:seed","2026-07-01","2026-07-02","2026-07-03","V1","2026-07-01","2026-07-03"))
    req(ids["personnel"]==1,"staff collision id not 1"); return {k:int(v) for k,v in ids.items()}

def sess(ids,k,perms,role): return {"id":ids[k],"role":role,"full_name":k,"device_name":f"v-{k}","is_active":1,"permissions":frozenset(perms)}
def runtime(feature,ev):
    os.chdir(feature); sys.path.insert(0,str(feature))
    from src import auth
    from src.domain.agenda.constants import AgendaContractScopeCode as S, AgendaPresentationProfileCode as R
    from src.domain.agenda.providers import DeadlineAgendaProvider,ReturnedShareAgendaProvider,UnknownDateAgendaProvider
    from src.services.agenda_context_factory import PersonalAgendaContextFactory
    from src.services.agenda_source_repository import AgendaSourceRepository
    from src.services.agenda_state_repository import AgendaStateRepository
    from src.services.personal_agenda_facade import PersonalAgendaFacade,AgendaInteractionError
    from src.services.staff_agenda_service import StaffAgendaService
    from src.services.sts_database import STSDatabase,CURRENT_SCHEMA_VERSION
    out={"status":"FAIL"}
    with tempfile.TemporaryDirectory() as td:
        db=STSDatabase(Path(td)/"v.sts",source="04A-V"); ids=seed(db); req(CURRENT_SCHEMA_VERSION==18,"schema")
        F=PersonalAgendaContextFactory(now_provider=lambda:NOW)
        def one(ss,prof,scope,contracts,override=(),touch=False,off=False):
            sr=CS(AgendaSourceRepository(db)); st=ST(AgendaStateRepository(db))
            ps=[CP(DeadlineAgendaProvider()),CP(ReturnedShareAgendaProvider()),CP(UnknownDateAgendaProvider())]+([OFF()] if off else [])
            ctx=F.build(ss,now=NOW,personal_contract_ids=override); req(ctx.presentation_profile.code==prof,"profile"); req(ctx.contract_scope==scope,"scope")
            res=StaffAgendaService(db,state_repository=st,source_repository=sr,providers=ps).build(ctx,touch_presented=touch)
            req({i.contract_id for i in res.items}==set(contracts),"contracts")
            return ctx,res,calls(sr,st,ps)
        p=sess(ids,"personnel",{"view_contracts","edit_contracts"},"personnel")
        v=sess(ids,"viewer",{"view_contracts"},"viewer")
        m=sess(ids,"manager",{"view_contracts","edit_contracts"},"manager")
        x=sess(ids,"custom",{"view_contracts"},"custom_agenda")
        _,pr,pc=one(p,R.PERSONAL,S.RESPONSIBLE,{ids["c1"]})
        _,vr,vc=one(v,R.VIEW_ONLY,S.ALL_VISIBLE,{ids["c1"],ids["c2"]}); req("returned_share" not in {i.kind for i in vr.items},"viewer share")
        _,mr,mc=one(m,R.MANAGEMENT,S.ALL_VISIBLE,{ids["c1"],ids["c2"]},off=True); req({"deadline","unknown_date","returned_share"}<={i.kind for i in mr.items},"manager kinds"); req(mc["source"]["load"] and len(mc["source"]["load"])==1,"load once"); req(mc["providers"]["off"]["build"]==0,"off build")
        xc,xr,xx=one(x,R.PERSONAL,S.RESPONSIBLE,{ids["c2"]}); req(xc.permissions==frozenset({"view_contracts"}),"custom synthesis")
        _,orr,oc=one(p,R.PERSONAL,S.RESPONSIBLE,{ids["c2"]},override={ids["c2"]}); req(not oc["source"]["personal"] and oc["source"]["all"]==0 and oc["source"]["load"]==[[ids["c2"]]],"override")
        nv=dict(m); nv["permissions"]=frozenset(); _,nvr,nvc=one(nv,R.MANAGEMENT,S.ALL_VISIBLE,set()); req(nvc["source"]=={"personal":[],"all":0,"load":[]} and all(z=={"enabled":0,"build":0} for z in nvc["providers"].values()),"no view")
        mv=dict(m); mv["permissions"]=frozenset({"view_contracts"}); _,mvr,mvc=one(mv,R.MANAGEMENT,S.ALL_VISIBLE,{ids["c1"],ids["c2"]}); req("returned_share" not in {i.kind for i in mvr.items},"no edit")
        pv=dict(p); pv["permissions"]=frozenset({"view_contracts"}); _,pvr,pvc=one(pv,R.PERSONAL,S.RESPONSIBLE,{ids["c1"]}); req("returned_share" not in {i.kind for i in pvr.items},"p no edit")
        trace=[]; db.conn.set_trace_callback(trace.append); bc=db.conn.total_changes; bt=db.conn.in_transaction; allids=AgendaSourceRepository(db).list_all_contract_ids(); at=db.conn.in_transaction; ac=db.conn.total_changes; db.conn.set_trace_callback(None)
        req(allids==frozenset({ids["c1"],ids["c2"]}) and bc==ac and bt==at and trace and all(q.lstrip().upper().startswith("SELECT") for q in trace),"readonly")
        _,r0,c0=one(pv,R.PERSONAL,S.RESPONSIBLE,{ids["c1"]},touch=False); req(not c0["state"].get("touch_presented"),"touch false")
        _,r1,c1=one(pv,R.PERSONAL,S.RESPONSIBLE,{ids["c1"]},touch=True); req(len(c1["state"].get("touch_presented",[]))==1 and c1["state"]["touch_presented"][0][0][0]==ids["personnel"],"touch true")
        before=dict(db.conn.execute("select * from staff_agenda_state where staff_id=1 and agenda_key='collision:seed'").fetchone())
        auth.create_system_admin(db.conn,"root","pw"); row=auth.verify_system_admin_login(db.conn,"root","pw"); sa=auth.build_system_admin_session(row,"sys")
        req(sa["id"]==0 and sa["admin_id"]==1 and sa["is_admin"] is True and sa["is_active"]==1 and "permissions" not in sa,"session")
        sc=F.build(sa,now=NOW); req(sc.presentation_profile.code==R.SYSTEM and sc.contract_scope==S.ALL_VISIBLE and sc.staff_id is None and sc.permissions==frozenset() and sc.current_staff["id"]==0 and sc.current_staff["admin_id"]==1,"system context")
        def guard(ss,override=()):
            sr=CS(AgendaSourceRepository(db)); st=ST(AgendaStateRepository(db)); ps=[CP(DeadlineAgendaProvider()),CP(ReturnedShareAgendaProvider()),CP(UnknownDateAgendaProvider())]
            svc=StaffAgendaService(db,state_repository=st,source_repository=sr,providers=ps); fac=PersonalAgendaFacade(db,context_factory=F,agenda_service=svc,state_repository=st)
            snap=fac.load(ss,now=NOW,personal_contract_ids=override); req(not snap.all_items and not sr.p and not sr.a and not sr.l and not st.c and all(q.e==q.b==0 for q in ps),"system load")
            return fac,st,calls(sr,st,ps)
        _,_,sg=guard(sa); inj={**sa,"permissions":frozenset({"view_contracts","edit_contracts"})}; fac,ist,ig=guard(inj); _,_,og=guard(inj,{ids["c1"]})
        item=mr.items[0]
        for ss in (sa,{**sa,"permissions":frozenset({"view_contracts"})}):
            for op in ("mark_seen","snooze","clear_snooze"):
                try:
                    if op=="mark_seen": fac.mark_seen(ss,item,seen_at=NOW)
                    elif op=="snooze": fac.snooze(ss,item,until=NOW+timedelta(days=1),now=NOW)
                    else: fac.clear_snooze(ss,item)
                    raise AssertionError("interaction success")
                except AgendaInteractionError: pass
        req(not ist.c,"interaction state")
        fk=[list(r) for r in db.conn.execute("pragma foreign_key_list(staff_agenda_state)")]; req(any(r[2]=="staff" and r[3]=="staff_id" and r[4]=="id" for r in fk),"fk")
        after=dict(db.conn.execute("select * from staff_agenda_state where staff_id=1 and agenda_key='collision:seed'").fetchone()); req(before==after,"collision row")
        out={"status":"PASS","schema":18,"ids":ids,"personnel":pc,"viewer":vc,"manager":mc,"custom":xx,"override":oc,"manager_no_view":nvc,"manager_view_no_edit":mvc,"personnel_view_no_edit":pvc,"readonly":{"ids":sorted(allids),"before_changes":bc,"after_changes":ac,"before_tx":bt,"after_tx":at,"trace":trace},"state":{"touch_false":c0,"touch_true":c1},"system":{"session":sa,"context":{"profile":str(sc.presentation_profile.code),"scope":str(sc.contract_scope),"staff_id":sc.staff_id,"permissions":list(sc.permissions)},"real":sg,"injected":ig,"override":og,"interactions":dict(ist.c),"fk":fk,"collision_before":before,"collision_after":after}}
        db.close()
    jdump(ev/"real-scope-capability-smoke.json",out); jdump(ev/"system-admin-fail-closed-smoke.json",out["system"])
    (ev/"real-scope-capability-smoke.log").write_text("PASS\n",encoding="utf-8"); (ev/"system-admin-fail-closed-smoke.log").write_text("PASS\n",encoding="utf-8")
    return out

def main():
    a=argparse.ArgumentParser(); a.add_argument("--baseline",required=True); a.add_argument("--feature",required=True); a.add_argument("--evidence",required=True); z=a.parse_args()
    b=Path(z.baseline).resolve(); f=Path(z.feature).resolve(); e=Path(z.evidence).resolve(); e.mkdir(parents=True,exist_ok=True)
    gates={}; errs=[]
    try:
        bh=gout(b,"rev-parse","HEAD"); fh=gout(f,"rev-parse","HEAD"); ch=[x for x in gout(f,"diff","--name-only",P,fh).splitlines() if x]
        req(bh==B and set(ch)==TMP and len(ch)==2,"refs/diff"); d={"baseline":bh,"product":P,"feature":fh,"changed":ch}; jdump(e/"ref-preflight.json",d); (e/"ref-preflight.txt").write_text(text(d),encoding="utf-8"); gates["preflight"]={"status":"PASS",**d}
    except Exception as x: errs.append("preflight "+repr(x)); gates["preflight"]={"status":"FAIL","error":repr(x)}
    try:
        q={"baseline":sha(b/"requirements.txt"),"feature":sha(f/"requirements.txt")}; q["equal"]=q["baseline"]==q["feature"]; req(q["equal"],"requirements"); jdump(e/"requirements-parity.json",q); (e/"requirements-parity.txt").write_text(text(q),encoding="utf-8"); gates["requirements"]={"status":"PASS",**q}
    except Exception as x: errs.append("requirements "+repr(x)); gates["requirements"]={"status":"FAIL","error":repr(x)}
    env={"platform":platform.platform(),"python":sys.version}
    for n,c in (("pip",[sys.executable,"-m","pip","--version"]),("pytest",[sys.executable,"-m","pytest","--version"]),("pyside",[sys.executable,"-c","import PySide6;print(PySide6.__version__)"])):
        r=run(c,f,e/(n+".log")); env[n]={"exit":r.returncode,"output":r.stdout.strip()}; req(r.returncode==0,n)
    jdump(e/"environment.json",env); (e/"environment.txt").write_text(text(env),encoding="utf-8"); gates["environment"]={"status":"PASS",**env}
    r=run([sys.executable,"-m","compileall","-q","src","tests"],f,e/"compile.log"); gates["compile"]={"status":"PASS" if r.returncode==0 else "FAIL","exit":r.returncode}; errs+=[] if r.returncode==0 else ["compile"]
    files=["tests/test_agenda_context_factory.py","tests/test_agenda_source_repository.py","tests/test_deadline_agenda_provider.py","tests/test_unknown_date_agenda_provider.py","tests/test_returned_share_agenda_provider.py","tests/test_staff_agenda_service.py","tests/test_personal_agenda_facade.py","tests/test_agenda_lifecycle.py","tests/test_agenda_models.py","tests/test_agenda_state_repository.py","tests/test_sts_database_transactions.py"]+[x for x in ["tests/test_agenda_presentation.py","tests/test_agenda_compact_widget.py","tests/test_agenda_detail_window.py","tests/test_main_page_agenda_integration.py"] if (f/x).exists()]
    tx=e/"targeted.xml"; r=run([sys.executable,"-m","pytest","-q",*files,f"--junitxml={tx}"],f,e/"targeted.log",{"QT_QPA_PLATFORM":"offscreen"}); ts=jsum(tx); ok=r.returncode==0 and ts["failures"]==ts["errors"]==0; gates["targeted"]={"status":"PASS" if ok else "FAIL","exit":r.returncode,**ts}; errs+=[] if ok else ["targeted"]
    try: runtime(f,e); gates["runtime_smokes"]={"status":"PASS"}
    except Exception as x: errs.append("runtime "+repr(x)); gates["runtime_smokes"]={"status":"FAIL","error":repr(x)}; (e/"runtime-error.log").write_text(traceback.format_exc(),encoding="utf-8")
    for n,p in (("schema","tests/smoke_sts_agenda_schema.py"),("database","tests/smoke_sts_database.py")):
        if not (f/p).exists(): gates[n]={"status":"FAIL","error":"missing"}; errs.append(n); continue
        r=run([sys.executable,p],f,e/(n+"-smoke.log")); ok=r.returncode==0 and ("schema_version=18" in r.stdout or n=="database"); gates[n]={"status":"PASS" if ok else "FAIL","exit":r.returncode,"schema_version":18,"tail":r.stdout[-1000:]}; errs+=[] if ok else [n]
    full={}
    for n,cwd in (("baseline",b),("feature",f)):
        x=e/(n+"-full.xml"); r=run([sys.executable,"-m","pytest","-q",f"--junitxml={x}"],cwd,e/(n+"-full.log"),{"QT_QPA_PLATFORM":"offscreen"}); s=jsum(x); valid=r.returncode in (0,1) and s["tests"]>0; full[n]={"valid":valid,"exit":r.returncode,**s}; errs+=[] if valid else [n+" full"]
    fo=sorted(set(full["feature"]["nodes"])-set(full["baseline"]["nodes"])); diff={"baseline":full["baseline"],"feature":full["feature"],"feature_only":fo,"feature_only_count":len(fo)}; jdump(e/"differential-summary.json",diff); (e/"differential-summary.txt").write_text(text(diff),encoding="utf-8"); gates["differential"]={"status":"PASS" if not fo else "FAIL",**diff}; errs+=[] if not fo else ["feature only"]
    ok=not errs and all(v["status"]=="PASS" for v in gates.values()); summary={"status":"PASS" if ok else "FAIL","gates":gates,"errors":errs}; jdump(e/"validation-summary.json",summary); (e/"validation-summary.txt").write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    gs=os.getenv("GITHUB_STEP_SUMMARY")
    if gs: Path(gs).write_text("# Agenda Stage 4A-V\n\n"+f"**Final: {summary['status']}**\n\n"+"|Gate|Result|\n|---|---|\n"+"\n".join(f"|{k}|{v['status']}|" for k,v in gates.items())+"\n",encoding="utf-8")
    return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
