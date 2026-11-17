#!/usr/bin/env python3
"""Pure/synthetic admission only. Never project interpreter qualification."""
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
import qualification_source as source
from header_validation_adapter import fixed_history
ROOT=source.ROOT
OUT=ROOT/".mlf-build/header-candidate-qualification"
COUNTS={"test_header_validation_adapter":15,"test_candidate_batch_contract":8,"test_candidate_batch_worker":11,"test_direct_candidate_entry":9,"test_qualify_header_only":13,"test_qualify_candidate_only":14,"test_qualification_stage":11}
def main():
    before=source.snapshot(OUT/"admission-source.json")
    evidence=OUT/"pure-results";evidence.mkdir(exist_ok=False)
    history=evidence/"historical-header-source.hs"
    record={"complete":False,"commands":[],"scope":"source contracts and real synthetic owned-tree cleanup; not GHC/project interpretation"}
    path=evidence/"receipt.json"
    def save():path.write_text(json.dumps(record,indent=2)+"\n")
    save()
    try:
        history_command=[sys.executable,"-B",str(ROOT/"tools/testing/prepare_history_refs.py")]
        subprocess.run(history_command,cwd=ROOT,check=True,timeout=30)
        history.write_bytes(fixed_history(ROOT))
        record["history_preparation"]={"argv":history_command,"timeout":30,"exit_code":0,
            "fixed_blob":"dd5b4630a80803c19afdb219dba2dc4bffc3ea1b",
            "source_sha256":hashlib.sha256(history.read_bytes()).hexdigest()}
        save()
        for mode,flags in (("normal",[]),("optimized",["-O"])):
            for name,count in COUNTS.items():
                env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONNOUSERSITE":"1"}
                env.update(HEADER_FIXTURE=str(ROOT/"tools/shared/fixtures/native/HeaderValidationTests.hs"),
                           HEADER_HISTORY_SOURCE=str(history),
                           HEADER_ORACLE=str(ROOT/"tools/shared/fixtures/native/HeaderNamingOracle.hs"))
                if name=="test_direct_candidate_entry":
                    env["MLF_CANDIDATE_TEST_EVIDENCE"]=str(evidence/("managed-synthetic-"+mode))
                if name=="test_qualification_stage":
                    env["QUALIFICATION_SYNTHETIC_OUTPUT"]=str(evidence/("outer-synthetic-"+mode))
                argv=[sys.executable,*flags,"-B","-m","unittest","-v",name]
                row={"name":name,"mode":mode,"argv":argv,"state":"running","expected_tests":count}
                record["commands"].append(row);save();started=time.monotonic()
                prefix=evidence/(mode+"-"+name)
                try:
                    with prefix.with_suffix(".stdout").open("xb") as out,prefix.with_suffix(".stderr").open("xb") as err:
                        result=subprocess.run(argv,cwd=ROOT/"tools/shared",env=env,stdout=out,stderr=err,timeout=50)
                    row["exit_code"]=result.returncode
                    stdout=prefix.with_suffix(".stdout").read_bytes();stderr=prefix.with_suffix(".stderr").read_bytes()
                    source.require(len(stdout)+len(stderr)<=4*1024**2,"bounded pure test capture")
                    row.update(stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest())
                    source.require(type(result.returncode)is int and result.returncode==0,"pure test failed: "+name)
                    matches=re.findall(rb"^test_[^\n]*",stderr,re.M)
                    source.require(len(matches)==count and len(set(matches))==count and
                        re.search(rb"\nRan "+str(count).encode()+rb" tests? in [0-9.]+s\n\nOK\n$",stderr),
                        "exact test count and zero skip required: "+name)
                    row.update(state="passed",actual_tests=count,skipped=0)
                finally:row["seconds"]=time.monotonic()-started;save()
        subprocess.run(["git","diff","--check",source.BASE,"HEAD","--"],cwd=ROOT,check=True,timeout=10)
        after=source.snapshot(OUT/"pure-source-after.json")
        source.require(before==after,"pure tracked source changed")
        record["complete"]=True
    except BaseException as error:record["error"]=repr(error);raise
    finally:save()
if __name__=="__main__":main()
