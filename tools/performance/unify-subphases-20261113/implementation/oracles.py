"""Strict source, target and receipt oracles. No compiler execution in this module."""
from pathlib import Path
import hashlib, json, os, re, stat, subprocess, sys, types
BASE = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
FOUNDATION_ROWS_SHA = 'e85b2776812a28fafd4074b5c4823f26a76ad2e0137492964ade76450f68d7fa'
HELPER_SHA = '0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc'
IDENTITY = 'fresh-split/compiler90/mlf-foundation'
BUILTIN = 'mlf:builtin-shared-haskell-v1:13'
PACKAGES = ['base', 'array', 'bytestring', 'text', 'containers', 'directory']
SUFFIXES = ('.mlfci', '.mlfco', '.queries')
FORBIDDEN = ('MLF_QUERY_PROFILE', 'MLF_QUERY_SEMANTIC_AUDIT', 'MLF_QUERY_FAILPOINT')

def require(condition, message):
    if not condition: raise ValueError(message)

def safe(path, exists=False):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and re.fullmatch(r'/[A-Za-z0-9_./+-]+',str(path)), 'canonical ASCII absolute path required')
    for p in [path,*path.parents]: require(not p.is_symlink(), 'symlink path component: '+str(p))
    if exists: require(path.exists(), 'missing path: '+str(path))
    return path

def regular(path):
    path = safe(path, True)
    require(stat.S_ISREG(path.lstat().st_mode), 'not regular: '+str(path))
    return path

def sha(path):
    with regular(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def digest(raw): return hashlib.sha256(raw).hexdigest()

def loads(raw):
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'duplicate JSON key: '+k); out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def load(path): return loads(regular(path).read_bytes())

def save(path, value):
    path=safe(path); temp=path.with_name(path.name+'.tmp')
    with temp.open('x') as f: json.dump(value,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temp,path)

def absent(path):
    path=safe(path)
    try: path.lstat()
    except FileNotFoundError: return
    raise ValueError('path must be absent: '+str(path))

def pin(path):
    path=regular(path); return {'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}

def verify_pin(item):
    path=regular(item['path']); require(sha(path)==item['sha256'],'pin changed: '+str(path))
    if 'bytes' in item: require(path.stat().st_size==item['bytes'],'size changed')
    return path

def check_pins(pins):
    for path,value in pins.items(): require(sha(path)==value,'pin changed: '+path)

def module(path, expected=None):
    path=regular(path)
    if expected: require(sha(path)==expected,'reviewed module pin changed')
    result=types.ModuleType(path.stem); result.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),result.__dict__)
    return result

def frozen_source(source):
    source=safe(source,True)
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    require(head==BASE,'frozen source commit differs')
    require(not subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no']),'frozen tracked source changed')
    manifest=load(source/'shared-sources.json')
    require(len(manifest['modules'])==137 and len(manifest['executables'])==13,'full137/13 inventory required')
    return manifest

def foundation(source, reference):
    require(sha(reference)==FOUNDATION_ROWS_SHA,'foundation14 source reference changed')
    rows=load(reference)
    require(len(rows)==14 and len({r['module'] for r in rows})==14 and sum(r['bytes'] for r in rows)==173594,'foundation14 inventory')
    package=load(Path(source)/'libraries/mlf-foundation/mlf-package.json')
    require(package.get('dependencies',{})=={},'foundation dependencies changed')
    for row in rows:
        p=Path(source)/row['relative']; verify_pin(dict(path=str(p),sha256=row['sha256'],bytes=row['bytes']))
        require(p==Path(source)/'libraries/mlf-foundation'/package['library']['modules'][row['module']],'foundation package owner changed')
    return rows

def pack(values): return ''.join(str(len(x))+':'+x for x in values)

def unpack(text):
    result=[]
    while text:
        n,sep,tail=text.partition(':'); require(sep and re.fullmatch(r'0|[1-9][0-9]*',n),'noncanonical length')
        n=int(n); require(n<=len(tail),'truncated packed field'); result.append(tail[:n]); text=tail[n:]
    return result

def fresh(report, identity=IDENTITY, count=475):
    require(type(report.get('format')) is int and report['format']==1 and report['crate']==identity,'query format/identity')
    groups=report['groups']; require(isinstance(groups,list),'ordered query groups list required')
    require(type(report['inferred_groups']) is int and type(report['reused_groups']) is int and report['inferred_groups']==len(groups)==count and report['reused_groups']==0,'exact fresh/zero reuse')
    require(all(g['cached'] is False and isinstance(g['id'],str) for g in groups),'cached or invalid group')
    require(len({g['id'] for g in groups})==count,'duplicate query id')
    return report

def interface(text, identity, modules, dependencies):
    lines=text.splitlines(); require(lines and lines[0]=='crate '+identity,'interface crate')
    owners=[x[7:] for x in lines if x.startswith('module ')]
    require(len(owners)==len(modules) and set(owners)==set(modules),'all module owners required')
    deps=[x[11:].split(' ',1) for x in lines if x.startswith('dependency ')]
    require(all(len(x)==2 and ' ' in x[1] for x in deps),'dependency grammar')
    found=[(n,tail.rsplit(' ',1)[0]) for n,tail in deps]
    require(len(found)==len(dependencies) and dict(found)==dependencies,'dependency identities/paths')

def three_artifacts(prefix, reference=None):
    paths=[regular(str(prefix)+s) for s in SUFFIXES]
    report=fresh(load(paths[-1]))
    if reference is not None:
        refs=[regular(str(reference)+s) for s in SUFFIXES]
        require(all(p.read_bytes()==r.read_bytes() for p,r in zip(paths,refs)),'full three raw artifacts differ')
        require(report==fresh(load(refs[-1])),'complete ordered query JSON differs')
    return {str(p):sha(p) for p in paths}

def original_flags(source, producer, manifest):
    args=['-XHaskell2010','-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages','-O2','-fpedantic-bottoms','-fno-state-hack','-i',*['-i'+str(Path(source)/r) for r in manifest['source_roots']],'-odir',str(Path(producer)/'objects'),'-hidir',str(Path(producer)/'objects')]
    for p in PACKAGES: args += ['-package',p]
    return args

def authenticate(producer, source):
    manifest=frozen_source(source)
    H=module(Path(source)/'tools/performance/a1-private-index/helper.py',HELPER_SHA)
    auth=H.authenticate(Path(producer),Path(source))
    require(auth['flags']==original_flags(source,producer,manifest),'original flags changed')
    require(auth['prepared_verification']['kind']=='empty','ordinary bootstrap required')
    require(len(auth['shared_inputs'])==137 and len(auth['resolved_host_modules'])==4 and len(auth['outputs'])==13,'complete ordinary producer')
    expected=auth['object_inputs']; actual={str(p.relative_to(producer)) for p in (Path(producer)/'objects').rglob('*') if p.is_file()}
    require(set(expected)==actual and actual,'full ordinary object inventory')
    for name,value in expected.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and name.startswith('objects/'),'unsafe object relative path')
        require(sha(Path(producer)/name)==value,'ordinary object changed')
    return auth
