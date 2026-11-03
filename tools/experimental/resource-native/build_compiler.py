#!/usr/bin/env python3
"""Fresh current-target resource producer; no installer/native stdlib/cache.

The historical PR25 manifests stay unchanged. Current source and its exact
reviewed transition are pinned separately; inferred interfaces come from GHC.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,signal,subprocess,time,types
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PINNED_COMMIT='c5928b5be73cd78d194405e734aa012415570e1a'
SOURCE_MANIFEST_SHA='b0ada8dcc8df7be5281d7a1a572600b0c912f2f13c3b727ab3f358c482ea72a8'
COMPILER_CONTRACT_SHA='0af6ad8809a442b8065796c22eab48548c40cb0a8f9dd8d057e49e9ee3822944'
PRODUCER_TRANSITION_SHA='825339cfc513aaacf9b88160c3dbaa3fa1e8307d67ffbeadaca33c9d322daff0'
PRODUCER_HELPER_SHA='eb63f5d367014700098681dfe63f928adcde2f01dcf0f987dfcdb114c856dc8b'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atom(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');temporary.replace(path)
def custody():
    path=BASE/'provenance/current-producer.py';blob=path.read_bytes()
    if hashlib.sha256(blob).hexdigest()!=PRODUCER_HELPER_SHA:raise ValueError('current producer helper changed before source-byte import')
    module=types.ModuleType('_current_resource_producer');module.__file__=str(path)
    exec(compile(blob,str(path),'exec'),module.__dict__)
    return module

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ghc',required=True,type=Path);p.add_argument('--build-dir',required=True,type=Path);args=p.parse_args()
    helper=custody()
    baseline,contract,inputs,mapping,manifest=helper.validate(ROOT,BASE,source_sha=SOURCE_MANIFEST_SHA,contract_sha=COMPILER_CONTRACT_SHA,transition_sha=PRODUCER_TRANSITION_SHA,helper_sha=PRODUCER_HELPER_SHA)
    ghc=args.ghc.resolve(strict=True);cc=Path(shutil.which('cc')).resolve(strict=True)
    if subprocess.check_output([str(ghc),'--numeric-version'],text=True).strip()!='9.14.1':raise ValueError('requires existing official GHC9.14.1')
    upstream=helper.upstream_module(ROOT,contract)
    if upstream.load_manifest()!=manifest:raise ValueError('current complete source inventory changed during shared validation')
    build=args.build_dir.resolve();build.mkdir(parents=True,exist_ok=False);(build/'objects').mkdir()
    report={'status':'building','base_commit':baseline['source_commit'],'base_tree':baseline['source_tree'],'historical_anchors':baseline['historical_anchors'],'inputs':inputs,'commands':[],'tools':{str(ghc):sha(ghc),str(cc):sha(cc)},'tool_roles':{'ghc':str(ghc),'cc':str(cc)},'compiler_contract_sha256':COMPILER_CONTRACT_SHA,'source_manifest_sha256':SOURCE_MANIFEST_SHA,'producer_transition_sha256':PRODUCER_TRANSITION_SHA,'producer_helper_sha256':PRODUCER_HELPER_SHA,'ghc_version':'9.14.1','build_directory':str(build),'producer_kind':'fresh-current-target-resource-O0','historical_receipt_adopted':False}
    receipt=BASE/'validation/compiler-build.json'
    def save():
        atom(receipt,report);atom(build/'receipt.json',report)
    def run(argv,label):
        start=time.monotonic();log=build/(label+'.log');process=None
        entry={'label':label,'argv':argv,'cwd':str(ROOT),'status':'launch-recorded','started':time.time(),'wall_seconds':600,'log':str(log)}
        report['commands'].append(entry);save()
        try:
            with log.open('wb')as stream:
                process=subprocess.Popen(argv,cwd=ROOT,env=dict(os.environ,GHC_ENVIRONMENT='-',GHCRTS='',LC_ALL='C.UTF-8'),stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                entry.update(pid=process.pid,pgid=process.pid,status='running');save()
                process.wait(timeout=600)
            entry.update(exit_code=process.returncode,status='terminal')
        except BaseException as error:
            entry.update(status='UNKNOWN',error=type(error).__name__+': '+str(error))
            if process is not None:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=5)
                entry['exit_code']=process.returncode
            raise
        finally:
            entry.update(seconds=time.monotonic()-start,finished=time.time())
            if log.exists():entry['log_sha256']=sha(log)
            save()
        if process.returncode:raise ValueError('actual compiler build failed: '+str(log))
    save()
    try:
        for label,argv in helper.command_recipe(ROOT,build,manifest,str(ghc),str(cc)):run(argv,label)
        resolved,interfaces=helper.actual_interfaces(ROOT,(build/'compile.log').read_text(),mapping,inputs,manifest,upstream)
        report.update(status='built',binary=str(build/'emlf'),binary_sha256=sha(build/'emlf'),resolved_modules=resolved,inferred_shared_interfaces=interfaces)
        helper.authenticate_logs(ROOT,report,mapping,inputs,manifest,contract)
    except BaseException as error:
        report.update(status='UNKNOWN'if any(r['status']=='UNKNOWN'for r in report['commands'])else'failed',error=type(error).__name__+': '+str(error))
        raise
    finally:
        report['immutable_inputs_verified_after']=all((ROOT/path).is_file()and sha(ROOT/path)==digest for path,digest in inputs.items())
        if not report['immutable_inputs_verified_after']:report['status']='invalidated'
        save()
    print(receipt)
if __name__=='__main__':main()
