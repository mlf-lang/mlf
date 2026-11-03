"""Actual rebuilt standalone compiler to checked resource IR, not an xMLF reparse.

PINNED_COMMIT/source_commit identify the current unmodified target dependency baseline,
NOT a commit identity for this new modified exporter. Fresh build.inputs and the
compiler contract bind every actual current producer source byte independently.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,subprocess,sys,types
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PINNED_COMMIT='c5928b5be73cd78d194405e734aa012415570e1a'
SOURCE_MANIFEST_SHA='b0ada8dcc8df7be5281d7a1a572600b0c912f2f13c3b727ab3f358c482ea72a8'
COMPILER_CONTRACT_SHA='0af6ad8809a442b8065796c22eab48548c40cb0a8f9dd8d057e49e9ee3822944'
PRODUCER_TRANSITION_SHA='825339cfc513aaacf9b88160c3dbaa3fa1e8307d67ffbeadaca33c9d322daff0'
PRODUCER_HELPER_SHA='eb63f5d367014700098681dfe63f928adcde2f01dcf0f987dfcdb114c856dc8b'
BUILD_SCRIPT_SHA='7678f5ec5049cdb0eea651195f1fb548c8fa5d01568cd4c078286be0d5710075'
KERNEL_ACCEPTANCE='430de879911762663a568dd8a68c1bffc17552aba373cad6ddaa000016c983a4'
REUSED=json.loads((BASE/'provenance/reused-files.json').read_text())
PLANNER_SHA='d1e9bbaec1457c813f9a2b4fbe3981e751ed2df68b8d28313dcea5b4ea996054'
TRANSPORT_SHA='7dea8b97932818785f24a2f311e2e63c2090572ca3841c77c37747c42a2c41d3'
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
    for path,expected in [('planner.py',PLANNER_SHA),('transport.py',TRANSPORT_SHA),('codegen.py','a07c17655f08bd576363ce49ec81d6c7a0075b278d2680733d06e3218b082200')]:
        if sha(BASE/path)!=expected:raise ValueError('accepted candidate generator changed: '+path)
    kernel_identity()
    if globals().get('_module_route_blobs'):load_module_route()
    return sys.modules[__name__]

_transport_blob=(BASE/'transport.py').read_bytes()
if sha_bytes(_transport_blob)!=TRANSPORT_SHA:raise ValueError('accepted transport changed before planner import')
_blob=(BASE/'planner.py').read_bytes()
if sha_bytes(_blob)!=PLANNER_SHA:raise ValueError('candidate generator changed before source-byte import')
_planner=types.ModuleType('_pr25_source_planner');_planner.__file__=str(BASE/'planner.py');sys.modules[_planner.__name__]=_planner
exec(compile(_blob,_planner.__file__,'exec'),_planner.__dict__)
if _planner.TRANSPORT_SHA256!=TRANSPORT_SHA or (BASE/'transport.py').read_bytes()!=_transport_blob:raise ValueError('transport changed while planner imported')


def current_producer():
    path=BASE/'provenance/current-producer.py';blob=path.read_bytes()
    if sha_bytes(blob)!=PRODUCER_HELPER_SHA:raise ValueError('current producer helper changed before source-byte import')
    module=types.ModuleType('_current_resource_producer');module.__file__=str(path)
    exec(compile(blob,str(path),'exec'),module.__dict__)
    return module

def current_source_manifest():
    path=BASE/'provenance/current-target-source.json'
    if sha(path)!=SOURCE_MANIFEST_SHA:raise ValueError('pinned current-target source manifest changed')
    return current_producer().read(path)

def build_identity():
    path=BASE/'validation/compiler-build.json'
    if not path.is_file():raise ValueError('actual current-target compiler build missing; run build_compiler.py with existing official GHC9.14.1')
    helper=current_producer()
    baseline,contract,expected,mapping,manifest=helper.validate(ROOT,BASE,source_sha=SOURCE_MANIFEST_SHA,
        contract_sha=COMPILER_CONTRACT_SHA,transition_sha=PRODUCER_TRANSITION_SHA,
        helper_sha=PRODUCER_HELPER_SHA,build_sha=BUILD_SCRIPT_SHA)
    receipt=helper.read(path)
    if receipt.get('inputs')!=expected:raise ValueError('actual compiler receipt has missing/changed source inventory')
    if (receipt.get('base_commit')!=PINNED_COMMIT or receipt.get('base_tree')!=baseline['source_tree'] or
        receipt.get('historical_anchors')!=baseline['historical_anchors'] or
        receipt.get('compiler_contract_sha256')!=COMPILER_CONTRACT_SHA or receipt.get('source_manifest_sha256')!=SOURCE_MANIFEST_SHA or
        receipt.get('producer_transition_sha256')!=PRODUCER_TRANSITION_SHA or receipt.get('producer_helper_sha256')!=PRODUCER_HELPER_SHA or
        receipt.get('producer_kind')!='fresh-current-target-resource-O0' or receipt.get('historical_receipt_adopted') is not False or receipt.get('ghc_version')!='9.14.1'):
        raise ValueError('actual current compiler receipt identity differs')
    required={'MLF.Entry.Emlf','MLF.ResourceExport','MLF.ResourceModules','MLF.ResourceProjection','MLF.ResourceModuleExport','MLF.PreparedCompiler','Bootstrap.CompilerCore','Bootstrap.X.Checked','Bootstrap.X.Check','Bootstrap.Parser'}
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
    if receipt['base_commit']!=baseline['source_commit']:raise ValueError('compiler baseline identity differs')
    helper.authenticate_logs(ROOT,receipt,mapping,expected,manifest,contract)
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
    manifest=current_source_manifest()
    envelope=_planner.baseline.parse_envelope(result.stdout.decode('utf-8'),manifest=manifest)
    candidate=_planner.plan(envelope,groups=groups,borrows=borrows)
    lock,blobs=kernel_identity();kernel=load_kernel(lock,blobs);checked=kernel.check(candidate['program'])
    if checked.sha256!=candidate['binding']['candidate_sha256']:raise ValueError('candidate artifact binding changed')
    build_identity();frozen_reference()
    evidence={'scope':'actual rebuilt surface Parser/inference/evidence/elaboration/CheckedTerm; new bounded scalar native target',
      'base_commit':manifest['source_commit'],'source_sha256':sha_bytes(source),'compiler_argv':argv,'compiler_binary_sha256':build['binary_sha256'],
      'compiler_build_receipt_sha256':sha(BASE/'validation/compiler-build.json'),'compiler_input_sha256':build['inputs'],
      'producer_revision':{'current_target_commit':manifest['source_commit'],'current_target_tree':manifest['source_tree'],
                          'historical_anchors':manifest['historical_anchors'],
                          'new_compiler_contract_sha256':COMPILER_CONTRACT_SHA,
                          'modified_source_is_not_claimed_as_an_existing_git_commit':True,
                          'export_source_commit_field_means':'unmodified current target dependency baseline only',
                          'current_transition_sha256':PRODUCER_TRANSITION_SHA},
      'actual_checked_export':envelope.data(),'binding':candidate['binding'],'resource_check':checked.report(),
      'genuine_CheckedTerm_execution':True,'direct_XMLF_parser_used':False,'source_execution_used_to_generate_IR':False,
      'preparation_executed_IR':False,'no_prelude':no_prelude,'kernel_receipt_sha256':KERNEL_ACCEPTANCE}
    return Prepared(checked.canonical_json,source,json.dumps(evidence,sort_keys=True,separators=(',',':')))

# Source-byte loading for the NEW opt-in route. These exact identities are
# finalized before genuine source admission; old standalone code remains separate.
MODULE_ROUTE_SHA256 = {'module_projection': '9f9c2019b2c84d54b7aff3a774bd13abe5d1cb4fb6f1f4520d215437ad16c869', 'module_inventory': 'c52b1409387f1777cfc774e1ffca1639f783e0096134260c9614259b90abe159', 'module_custody': '1f35c77caa66a902a37ad7efe0a228b45107326ec65064b0dd06bbe339e2703e', 'module_transport': '125103f776da784b063655da6733105e83663fe1bcc6a626782d1b2d0d108574', 'module_prepare': '0d1cd458cfa11109576bf5c1cf39802d1605b5068b0c5690954978c9e60f1a1a'}  # exact reviewed current-source preparation identities
_module_route_blobs = {}
def load_module_route():
    expected=['module_projection','module_inventory','module_custody','module_transport','module_prepare']
    if set(MODULE_ROUTE_SHA256)!=set(expected):raise ValueError('new module route source identity gate is incomplete')
    blobs={name:(BASE/(name+'.py')).read_bytes()for name in expected}
    for name,blob in blobs.items():
        if sha_bytes(blob)!=MODULE_ROUTE_SHA256[name]:raise ValueError('module route source changed: '+name)
    if _module_route_blobs:
        if blobs!=_module_route_blobs:raise ValueError('module route source changed after capture')
        return sys.modules['module_prepare']
    sys.modules['transport']=_planner.baseline
    for name in expected:
        module=types.ModuleType(name);module.__file__=str(BASE/(name+'.py'));sys.modules[name]=module
        exec(compile(blobs[name],module.__file__,'exec'),module.__dict__)
    if any((BASE/(name+'.py')).read_bytes()!=blob for name,blob in blobs.items()):raise ValueError('module route changed during source-byte loading')
    _module_route_blobs.update(blobs)
    return sys.modules['module_prepare']

def prepare_module_source(source_path,*,module_root,build_parent,groups=False,borrows=False,no_prelude=False):
    return load_module_route().prepare_module_source(sys.modules[__name__],source_path,module_root=module_root,
        build_parent=build_parent,groups=groups,borrows=borrows,no_prelude=no_prelude)

def verify_source_package(evidence):
    if 'module_package' in evidence:load_module_route().verify_source_package(evidence)


def python_observation(prepared):
    lock,source=kernel_identity();kernel=load_kernel(lock,source);checked=kernel.check(prepared.program())
    if checked.sha256!=prepared.evidence()['resource_check']['sha256']:raise ValueError('prepared artifact changed')
    try:return kernel.run(checked,event_limit=100000)
    except kernel.RuntimeFault as error:
        if error.code not in ['BUSY','HOLE','FUEL','HOST_STACK_LIMIT']:raise
        return {'status':'terminal-pure-machine-fault','fault_code':error.code,'cleanup_claim':False}
