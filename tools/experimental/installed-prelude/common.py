"""Local experimental provenance and bounded execution; no installed defaults."""
import hashlib, importlib.util, json, os, pathlib, signal, subprocess, sys
P = pathlib.Path
HERE = P(__file__).resolve().parent
CONTRACTS = ('source_syntax', 'frontend_semantics', 'builtin_interface', 'primitive_abi')
def digest(data): return hashlib.sha256(data).hexdigest()
def sha(path): return digest(P(path).read_bytes())
def require(ok, message):
    if not ok: raise ValueError(message)
def write(path, value): P(path).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path); result=importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result
def environment():
    env={key:os.environ[key] for key in ('PATH','LD_LIBRARY_PATH','HOME','TMPDIR') if key in os.environ}
    env.update(LC_ALL='C',LANG='C',GHCRTS='',GHC_ENVIRONMENT='-',PYTHONDONTWRITEBYTECODE='1')
    return env
def pack(fields): return ''.join(str(len(s))+':'+s for s in fields).encode('utf-8',errors='strict')
def verify_files(pins):
    for path, expected in pins.items(): require(sha(path)==expected,'identity changed: '+str(path))
def authenticate_producer(root, producer, expected):
    receipt=producer/'receipt.json'; require(sha(receipt)==expected,'producer receipt identity')
    module(root/'tools/shared/test_direct.py','installed_producer_auth').authenticate_build(receipt,producer/'bin',root)
    return json.loads(receipt.read_bytes())
def source_pins(root):
    files=set()
    for directory in ('libraries','bootstrap','package','host/ghc'):
        files.update((root/directory).rglob('*.hs'))
    files.update(HERE.rglob('*.hs')); files.update(HERE.rglob('*.py'))
    files.update((root/'runtime').glob('*.h'))
    files.update([root/'host/ghc/cbits/host.c',root/'runtime/mlf_process_supervisor.c',root/'shared-sources.json',root/'tools/shared/resource_watchdog.py',root/'tools/shared/test_direct.py'])
    return {str(p.resolve()):sha(p) for p in sorted(files)}
def bounded(root, out, argv, data=b'', seconds=180):
    out.mkdir(); log=out/'stdout'; err=out/'stderr'; watch=root/'tools/shared/resource_watchdog.py'
    command=[sys.executable,str(watch),'--seconds',str(seconds),'--address-space-mib','6144','--rss-mib','3072','--max-output-mib','256','--disk-free-mib','2048',str(out),*map(str,argv)]
    write(out/'command.json',command); child=None
    previous=signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(InterruptedError('SIGTERM')))
    try:
        with log.open('wb') as a, err.open('wb') as b:
            child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=a,stderr=b,env=environment(),start_new_session=True)
            try: child.communicate(data,timeout=seconds+30)
            except BaseException:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try: child.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        (out/'CLEANUP_UNCERTAIN').write_text('Do not continue; verify descendant cleanup.\n')
                        os.killpg(child.pid,signal.SIGKILL); child.communicate()
                raise
        require(child.returncode==0,'bounded command failed; preserved at '+str(out))
        report=json.loads((out/'bounded-receipt.json').read_bytes())
        require(report.get('complete') is True and report.get('exit_code')==0 and report.get('reason') is None,'watchdog did not complete successfully')
        # Existing watchdog records the child stream separately from its own JSON stdout.
        return (out/'build.log').read_bytes()
    finally: signal.signal(signal.SIGTERM,previous)
def load_build(path, expected):
    raw=path.read_bytes(); require(digest(raw)==expected,'build receipt identity'); r=json.loads(raw)
    require(r['status']=='complete','incomplete experimental build')
    verify_files(r['pins']); require(sha(r['harness'])==r['harness_sha256'],'harness identity')
    authenticate_producer(P(r['root']),P(r['producer']),r['producer_receipt_sha256'])
    return r
