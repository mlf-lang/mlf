"""Actual PR25 surface compiler artifact to checked resource IR (not an xMLF reparse)."""
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,subprocess,sys,types
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PINNED_COMMIT='7bf7ac6db5e3db2daff2e0a1c249e68ae0db2d0c'
SOURCE_MANIFEST_SHA='bd918d20b7bf4c0fa794d12e22788a9c2f55d1ae721f1d87f58258b808a99dbc'
COMPILER_CONTRACT_SHA='132aa66e8597da232cff4cde91fea2eb86c4f2235fcc7a85a88e27896adc8fb1'
BUILD_SCRIPT_SHA='85f0984ba33ef2efebb5bd8b361a393a20da51771cb516100892c6ee52590c33'
KERNEL_ACCEPTANCE='f71991ae6c2c476d772f5c13036a3f6bf5187e32a0318792fd7d8aa59e7389c9'
REUSED=json.loads((BASE/'provenance/reused-files.json').read_text())
PLANNER_SHA='0c2b6426123c7a78a34b84ca0e47804cc44bf7d4838083a6d1aa35b0691ac1ff'
TRANSPORT_SHA='6a3d24357ecca47eb0e847fbfe03513265fcbb33b163dc0f3ad7df3f14f5c515'
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha(p):return sha_bytes(Path(p).read_bytes())
def kernel_identity(ignored=None):
    receipt=BASE/'provenance/KERNEL_ACCEPTANCE.json'
    if sha(receipt)!=KERNEL_ACCEPTANCE:raise ValueError('accepted resource kernel receipt changed')
    a=json.loads(receipt.read_text())
    if a['status']!='accepted' or a['audit_gate_allows_bridge_integration'] is not True:raise ValueError('resource kernel gate closed')
    files=a['module_sha256'];blobs={}
    if {str(p.relative_to(BASE)) for p in (BASE/'resource_ir').glob('*.py')}!=set(files):raise ValueError('resource kernel module inventory changed')
    for path,digest in files.items():
        blob=(BASE/path).read_bytes()
        if sha_bytes(blob)!=digest:raise ValueError('accepted resource kernel changed: '+path)
        blobs[path]=blob
    return {'kernel_root':a['kernel_root'],'kernel_location':str(BASE),'files':files,'audit_receipt_sha256':KERNEL_ACCEPTANCE,'implementation_manifest_sha256':a['implementation_manifest_sha256']},blobs

def load_kernel(lock,source):
    package='_pr25_resource_audited_kernel'
    for key in [k for k in sys.modules if k==package or k.startswith(package+'.')]:del sys.modules[key]
    module=types.ModuleType(package);module.__path__=[str(BASE/'resource_ir')];module.__package__=package;sys.modules[package]=module
    for short in ['checker','runtime']:
        relative='resource_ir/'+short+'.py';name=package+'.'+short
        child=types.ModuleType(name);child.__package__=package;child.__file__=str(BASE/relative);sys.modules[name]=child
        exec(compile(source[relative],child.__file__,'exec'),child.__dict__);setattr(module,short,child)
    module.__file__=str(BASE/'resource_ir/__init__.py');exec(compile(source['resource_ir/__init__.py'],module.__file__,'exec'),module.__dict__)
    return module

def frozen_reference():
    for path,expected in [('planner.py',PLANNER_SHA),('transport.py',TRANSPORT_SHA),('codegen.py','1899d2681aaab0c2b1730a0b6f76c9cbbe5f1cb98aba630a38d5b1b528f65845')]:
        if sha(BASE/path)!=expected:raise ValueError('accepted candidate generator changed: '+path)
    kernel_identity()
    return sys.modules[__name__]

_transport_blob=(BASE/'transport.py').read_bytes()
if sha_bytes(_transport_blob)!=TRANSPORT_SHA:raise ValueError('accepted transport changed before planner import')
_blob=(BASE/'planner.py').read_bytes()
if sha_bytes(_blob)!=PLANNER_SHA:raise ValueError('candidate generator changed before source-byte import')
_planner=types.ModuleType('_pr25_source_planner');_planner.__file__=str(BASE/'planner.py');sys.modules[_planner.__name__]=_planner
exec(compile(_blob,_planner.__file__,'exec'),_planner.__dict__)
if _planner.TRANSPORT_SHA256!=TRANSPORT_SHA or (BASE/'transport.py').read_bytes()!=_transport_blob:raise ValueError('transport changed while planner imported')


def build_identity():
    path=BASE/'validation/compiler-build.json'
    if not path.is_file():raise ValueError('actual PR25 compiler build missing; run build_compiler.py with existing official GHC9.14.1')
    if sha(BASE/'provenance/pr25-source.json')!=SOURCE_MANIFEST_SHA:raise ValueError('pinned PR25 source manifest changed')
    if sha(BASE/'provenance/compiler-inputs.json')!=COMPILER_CONTRACT_SHA:raise ValueError('audited compiler input contract changed')
    if sha(BASE/'build_compiler.py')!=BUILD_SCRIPT_SHA:raise ValueError('audited compiler builder changed')
    contract=json.loads((BASE/'provenance/compiler-inputs.json').read_text())
    expected=dict(contract);expected['tools/experimental/resource-native/build_compiler.py']=BUILD_SCRIPT_SHA;expected['tools/experimental/resource-native/provenance/pr25-source.json']=SOURCE_MANIFEST_SHA
    receipt=json.loads(path.read_text())
    if receipt.get('inputs')!=expected:raise ValueError('actual compiler receipt has missing/changed source inventory')
    if receipt.get('base_commit')!=PINNED_COMMIT or receipt.get('compiler_contract_sha256')!=COMPILER_CONTRACT_SHA or receipt.get('source_manifest_sha256')!=SOURCE_MANIFEST_SHA or receipt.get('ghc_version')!='9.14.1':raise ValueError('actual compiler receipt identity differs')
    required={'MLF.Entry.Emlf','MLF.ResourceExport','MLF.PreparedCompiler','Bootstrap.CompilerCore','Bootstrap.X.Checked','Bootstrap.X.Check','Bootstrap.Parser'}
    resolved=receipt.get('resolved_modules',{})
    if not required<=set(resolved):raise ValueError('actual compiler resolved closure missing')
    for name,item in resolved.items():
        if item.get('path') not in expected or item.get('sha256')!=expected[item['path']]:raise ValueError('actual compiler resolved-source evidence differs: '+name)
    manifest=json.loads((ROOT/'shared-sources.json').read_text())
    shared_names={item['module'] for item in manifest['modules']}
    interfaces=receipt.get('inferred_shared_interfaces',{})
    if set(interfaces)!=set(resolved)&shared_names:raise ValueError('actual compiler inferred-interface inventory differs')
    for name,item in interfaces.items():
        signatures=item.get('signatures')
        if type(signatures) is not str or item.get('unresolved_literal_constraints') is not False or sha_bytes(signatures.encode())!=item.get('sha256'):
            raise ValueError('actual compiler inferred-interface evidence differs: '+name)
        import re
        if re.search(r'\b(?:Num|Fractional|IsString)\b',signatures):raise ValueError('unresolved host literal overloading: '+name)
    commands=receipt.get('commands',[])
    if len(commands)!=3 or any(c.get('exit_code')!=0 for c in commands):raise ValueError('actual compiler successful build commands missing')
    if receipt.get('status')!='built' or not receipt.get('immutable_inputs_verified_after'):raise ValueError('no successful actual PR25 compiler build receipt')
    for p,digest in receipt['inputs'].items():
        if sha(ROOT/p)!=digest:raise ValueError('actual compiler input changed since build: '+p)
    if sha(receipt['binary'])!=receipt['binary_sha256']:raise ValueError('actual PR25 compiler binary changed')
    if receipt['base_commit']!=json.loads((BASE/'provenance/pr25-source.json').read_text())['source_commit']:raise ValueError('compiler baseline identity differs')
    return receipt

@dataclass(frozen=True)
class Prepared:
    canonical_ir:str
    source:bytes
    evidence_json:str
    def program(self):return json.loads(self.canonical_ir)
    def evidence(self):return json.loads(self.evidence_json)

def prepare_source(source:bytes,*,groups=False,borrows=False,no_prelude=False):
    frozen_reference();build=build_identity()
    if type(source) is not bytes or len(source)>65536:raise ValueError('surface source requires immutable UTF8 bytes bounded to64KiB')
    source.decode('utf-8',errors='strict')
    argv=[build['binary']]+(['--no-prelude'] if no_prelude else [])+['--emit-resource-json','-']
    result=subprocess.run(argv,input=source,capture_output=True,timeout=30)
    if result.returncode:raise ValueError(result.stderr.decode('utf-8',errors='replace').strip())
    if result.stderr:raise ValueError('successful surface compiler wrote diagnostics')
    manifest=json.loads((BASE/'provenance/pr25-source.json').read_text())
    envelope=_planner.baseline.parse_envelope(result.stdout.decode('utf-8'),manifest=manifest)
    candidate=_planner.plan(envelope,groups=groups,borrows=borrows)
    lock,blobs=kernel_identity();kernel=load_kernel(lock,blobs);checked=kernel.check(candidate['program'])
    if checked.sha256!=candidate['binding']['candidate_sha256']:raise ValueError('candidate artifact binding changed')
    build_identity();frozen_reference()
    evidence={'scope':'actual PR25 surface Parser/inference/evidence/elaboration/CheckedTerm; experimental bounded native target',
      'base_commit':manifest['source_commit'],'source_sha256':sha_bytes(source),'compiler_argv':argv,'compiler_binary_sha256':build['binary_sha256'],
      'compiler_build_receipt_sha256':sha(BASE/'validation/compiler-build.json'),'compiler_input_sha256':build['inputs'],
      'actual_checked_export':envelope.data(),'binding':candidate['binding'],'resource_check':checked.report(),
      'genuine_CheckedTerm_execution':True,'direct_XMLF_parser_used':False,'source_execution_used_to_generate_IR':False,
      'preparation_executed_IR':False,'no_prelude':no_prelude,'kernel_receipt_sha256':KERNEL_ACCEPTANCE}
    return Prepared(checked.canonical_json,source,json.dumps(evidence,sort_keys=True,separators=(',',':')))

def python_observation(prepared):
    lock,source=kernel_identity();kernel=load_kernel(lock,source);checked=kernel.check(prepared.program())
    if checked.sha256!=prepared.evidence()['resource_check']['sha256']:raise ValueError('prepared artifact changed')
    try:return kernel.run(checked,event_limit=100000)
    except kernel.RuntimeFault as error:
        if error.code not in ['BUSY','HOLE','FUEL','HOST_STACK_LIMIT']:raise
        return {'status':'terminal-pure-machine-fault','fault_code':error.code,'cleanup_claim':False}
