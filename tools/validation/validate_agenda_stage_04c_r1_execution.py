from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, sys, traceback
import xml.etree.ElementTree as ET
from pathlib import Path

STAGE="04C-R1-E"
SOURCE="e1bfe4014b05c0e694cb1012198bf0134e8cfc77"
R1="db3a93995ee0718de891a15bd7a089d30b1bc99f"
PROMPT_MAIN="e1ed9a66318e19178f132602d3114a97880fa27f"
MERGE_BASE="2931fa267560397d4d849d6365acde504f376775"
TEMP={".github/workflows/agenda-stage-04c-r1-execution-validation.yml","tools/validation/validate_agenda_stage_04c_r1_execution.py"}
R1_PATHS={"docs/agenda/AGENDA_STAGE_04C_CONTRACT_ACTIVITY_PROVIDER.md","src/services/staff_agenda_service.py","tests/test_agenda_source_repository.py","tests/test_personal_agenda_facade.py","tests/test_staff_agenda_service.py"}
TESTS=[
"tests/test_agenda_source_repository.py",
"tests/test_activity_agenda_provider.py",
"tests/test_staff_agenda_service.py",
"tests/test_personal_agenda_facade.py",
"tests/test_agenda_context_factory.py",
"tests/test_agenda_lifecycle.py",
"tests/test_agenda_models.py",
"tests/test_deadline_agenda_provider.py",
"tests/test_unknown_date_agenda_provider.py",
"tests/test_returned_share_agenda_provider.py",
"tests/test_document_lock_agenda_provider.py",
]

def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
def run(cmd,cwd,env=None):
    e=os.environ.copy(); e.update(env or {})
    return subprocess.run(cmd,cwd=cwd,env=e,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,errors="replace",check=False)
def logged(cmd,cwd,log,exitf,env=None):
    r=run(cmd,cwd,env); log.write_text("$ "+subprocess.list2cmdline(cmd)+f"\nabsolute_exit={r.returncode}\n\n"+r.stdout,encoding="utf-8"); exitf.write_text(str(r.returncode)+"\n",encoding="utf-8"); return r
def git(root,*args,check=True):
    r=run(["git",*args],root)
    if check and r.returncode: raise RuntimeError(f"git {' '.join(args)} failed: {r.stdout}")
    return r.stdout.strip()
def paths(root,a,b): return sorted(x.replace("\\","/") for x in git(root,"diff","--name-only",a,b).splitlines() if x.strip())
def junit(p):
    if not p.exists(): return {"present":False,"tests":0,"passed":0,"failures":0,"errors":0,"skipped":0,"duration":0.0}
    root=ET.parse(p).getroot(); cases=list(root.iter("testcase"))
    f=sum(c.find("failure") is not None for c in cases); e=sum(c.find("error") is not None for c in cases); s=sum(c.find("skipped") is not None for c in cases)
    return {"present":True,"tests":len(cases),"passed":len(cases)-f-e-s,"failures":f,"errors":e,"skipped":s,"duration":sum(float(c.get("time") or 0) for c in cases),"failed_nodes":sorted(f"{c.get('classname','')}::{c.get('name','')}" for c in cases if c.find("failure") is not None or c.find("error") is not None)}
def contract(root,head):
    svc=(root/"src/services/staff_agenda_service.py").read_text(encoding="utf-8")
    st=(root/"tests/test_staff_agenda_service.py").read_text(encoding="utf-8")
    repo=(root/"tests/test_agenda_source_repository.py").read_text(encoding="utf-8")
    fac=(root/"tests/test_personal_agenda_facade.py").read_text(encoding="utf-8")
    order=["DeadlineAgendaProvider()","ReturnedShareAgendaProvider()","DocumentLockAgendaProvider()","UnknownDateAgendaProvider()","ActivityAgendaProvider()"]
    idx=[svc.find(x) for x in order]
    changed=paths(root,SOURCE,head)
    tracked={p:git(root,"ls-files","--error-unmatch",p,check=False)==p for p in TESTS}
    out={
      "service":{
       "inspect_signature_absent":all(x not in svc for x in ("from inspect import signature","inspect.signature","signature(load_sources)")),
       "conditional_fallback_absent":'if "activity_since" in signature' not in svc and "load_sources = self.source_repository.load_personal_sources" not in svc,
       "direct_activity_since_contract":"self.source_repository.load_personal_sources(" in svc and "activity_since=activity_source_cutoff(context.now)" in svc,
       "provider_order":order,
       "provider_order_pass":all(i>=0 for i in idx) and idx==sorted(idx),
      },
      "test_double":{
       "activity_since_keyword":"def load_personal_sources(self, contract_ids, *, activity_since=None):" in st,
       "last_activity_since":"last_activity_since" in st,
       "activity_since_calls":"activity_since_calls" in st,
       "activities_bundle_keyword":"activities=tuple(" in st,
      },
      "committed_tests":{
       "repository_activity_tests":"def test_activity_" in repo,
       "service_activity_tests":"def test_activity_" in st,
       "facade_activity_tests":"def test_activity_" in fac,
       "tracked":tracked,
      },
      "source_head_to_workflow_head_paths":changed,
      "temporary_allowlist_exact":set(changed)==TEMP,
      "changed_activity_product_files":sorted(set(changed)&{"src/domain/agenda/activity.py","src/domain/agenda/source_models.py","src/domain/agenda/providers/activity.py","src/services/agenda_source_repository.py","src/services/staff_agenda_service.py"}),
      "forbidden_product_changes":sorted(p for p in changed if p.startswith(("src/","tests/")) or p=="requirements.txt"),
      "no_schema_auth_ui_log_writer_diff":not any(p.startswith("src/ui/") or p in {"src/auth.py","src/services/sts_database.py","src/services/sts_store.py"} or "migration" in p.lower() for p in changed),
    }
    ok=out["service"]["inspect_signature_absent"] and out["service"]["conditional_fallback_absent"] and out["service"]["direct_activity_since_contract"] and out["service"]["provider_order_pass"]
    ok=ok and all(out["test_double"].values()) and all(v for k,v in out["committed_tests"].items() if k!="tracked") and all(tracked.values())
    ok=ok and out["temporary_allowlist_exact"] and not out["changed_activity_product_files"] and not out["forbidden_product_changes"] and out["no_schema_auth_ui_log_writer_diff"]
    out["overall"]="PASS" if ok else "FAIL"; return out
def smoke(log):
    n=log.lower()
    return {"agenda_schema_pass_marker":"agenda_schema=pass" in n,"schema_version_18":"schema_version=18" in n,"integrity_check":"integrity_check=ok" in n or "integrity_check: ok" in n,"foreign_key_check":"foreign_key_check=ok" in n or "foreign_key_check: ok" in n or "foreign_key_check=[]" in n,"staff_agenda_state_exists":"staff_agenda_state=present" in n or "staff_agenda_state_exists=true" in n,"agenda_items_absent":"agenda_items=absent" in n or "agenda_items_exists=false" in n}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",default="validation-output"); a=ap.parse_args()
    root=Path.cwd().resolve(); head=git(root,"rev-parse","HEAD")
    status=git(root,"status","--porcelain=v1","--branch"); diff=git(root,"diff","--no-ext-diff","--")
    out=(root/a.output).resolve(); out.mkdir(parents=True,exist_ok=True)
    (out/"git-status-before.txt").write_text(status+"\n",encoding="utf-8"); (out/"git-diff-before.txt").write_text(diff+"\n",encoding="utf-8")
    errors=[]
    try:
      ancestor=run(["git","merge-base","--is-ancestor",SOURCE,head],root).returncode==0
      mainsha=git(root,"rev-parse","origin/main"); mb=git(root,"merge-base",SOURCE,"origin/main")
      temp=paths(root,SOURCE,head); r1=paths(root,R1,SOURCE); msg=git(root,"show","-s","--format=%s",SOURCE)
      svc=(root/"src/services/staff_agenda_service.py").read_text(encoding="utf-8")
      direct="self.source_repository.load_personal_sources(" in svc and "activity_since=activity_source_cutoff(context.now)" in svc
      inspect_abs=all(x not in svc for x in ("from inspect import signature","inspect.signature","signature(load_sources)"))
      forbidden=sorted(p for p in temp if p not in TEMP)
      pp=ancestor and msg=="Complete agenda activity integration tests" and set(temp)==TEMP and set(r1)==R1_PATHS and not forbidden and mb==MERGE_BASE and direct and inspect_abs
      pre={"expected_source_head":SOURCE,"actual_workflow_head":head,"source_head_is_ancestor":ancestor,"source_commit_message":msg,"current_main_sha":mainsha,"main_sha_observed_when_prompt_written":PROMPT_MAIN,"merge_base":mb,"expected_merge_base":MERGE_BASE,"source_to_workflow_paths":temp,"r1_base_to_source_paths":r1,"forbidden_product_changes":forbidden,"direct_activity_since_contract":direct,"inspect_signature_absent":inspect_abs,"status":"PASS" if pp else "FAIL"}
    except Exception as e:
      pp=False; pre={"status":"FAIL","error":str(e)}; errors.append("preflight: "+str(e))
    dump(out/"preflight.json",pre)
    b=(root/"requirements.txt").read_bytes(); (out/"requirements-sha256.txt").write_text(f"path=requirements.txt\nbytes={len(b)}\nsha256={hashlib.sha256(b).hexdigest()}\n",encoding="utf-8")
    env={"os_platform":platform.platform(),"python_version":sys.version.replace("\n"," "),"python_executable":sys.executable,"pip_version":run([sys.executable,"-m","pip","--version"],root).stdout.strip(),"pytest_version":run([sys.executable,"-m","pytest","--version"],root).stdout.strip(),"QT_QPA_PLATFORM":os.environ.get("QT_QPA_PLATFORM",""),"PYTHONUTF8":os.environ.get("PYTHONUTF8",""),"repo_root":str(root),"git_head":head,"github_ref":os.environ.get("GITHUB_REF",""),"github_head_ref":os.environ.get("GITHUB_HEAD_REF",""),"github_sha":os.environ.get("GITHUB_SHA","")}
    (out/"environment.txt").write_text("\n".join(f"{k}={v}" for k,v in env.items())+"\n",encoding="utf-8")
    renv={"QT_QPA_PLATFORM":"offscreen","PYTHONUTF8":"1"}
    cr=logged([sys.executable,"-m","compileall","-q","src","tests"],root,out/"compile.log",out/"compile-exit.txt",renv)
    cs={"command":"python -m compileall -q src tests","absolute_exit":cr.returncode,"status":"PASS" if cr.returncode==0 else "FAIL"}
    jp=out/"stage-04c-r1-targeted.xml"; cmd=[sys.executable,"-m","pytest","-q",*TESTS,f"--junitxml={jp}"]
    tr=logged(cmd,root,out/"targeted.log",out/"targeted-exit.txt",renv)
    try: js=junit(jp)
    except Exception as e: js={"present":jp.exists(),"tests":0,"passed":0,"failures":0,"errors":1,"skipped":0,"duration":0.0,"parse_error":str(e)}; errors.append("junit: "+str(e))
    tp=tr.returncode==0 and js["tests"]>0 and js["failures"]==0 and js["errors"]==0
    ts={"command":"python -m pytest -q "+" ".join(TESTS)+" --junitxml=validation-output/stage-04c-r1-targeted.xml","absolute_exit":tr.returncode,**js,"status":"PASS" if tp else "FAIL"}; dump(out/"targeted-summary.json",ts)
    sr=logged([sys.executable,"tests/smoke_sts_agenda_schema.py"],root,out/"agenda-schema-smoke.log",out/"agenda-schema-smoke-exit.txt",renv); sd=smoke(sr.stdout); sp=sr.returncode==0 and sd["agenda_schema_pass_marker"] and sd["schema_version_18"]; ss={"command":"python tests/smoke_sts_agenda_schema.py","absolute_exit":sr.returncode,**sd,"status":"PASS" if sp else "FAIL"}
    dr=logged([sys.executable,"tests/smoke_sts_database.py"],root,out/"database-smoke.log",out/"database-smoke-exit.txt",renv); okline=any(x.strip().lower()=="ok" for x in dr.stdout.splitlines()); dp=dr.returncode==0 and okline; ds={"command":"python tests/smoke_sts_database.py","absolute_exit":dr.returncode,"output_ok":okline,"status":"PASS" if dp else "FAIL"}
    try: sc=contract(root,head)
    except Exception as e: sc={"overall":"FAIL","error":str(e),"traceback":traceback.format_exc()}; errors.append("source contract: "+str(e))
    dump(out/"source-contract-checks.json",sc)
    overall=pp and cr.returncode==0 and tp and sp and dp and sc.get("overall")=="PASS"
    summary={"stage":STAGE,"source_head":SOURCE,"workflow_head":head,"environment":env,"preflight":"PASS" if pp else "FAIL","compile":cs,"targeted":ts,"agenda_schema_smoke":ss,"database_smoke":ds,"source_contract":sc,"overall":"PASS" if overall else "FAIL","errors":errors}
    dump(out/"validation-summary.json",summary); print(json.dumps(summary,ensure_ascii=False,indent=2,default=str)); return 0 if overall else 1
if __name__=="__main__": raise SystemExit(main())
