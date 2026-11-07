"""Candidate prepared-source identity contract; no runtime qualification.

This layer authenticates exact current source and reversible historical projection.
It does not attest compilation, generator execution, native fixed point or merge.
"""
from pathlib import Path
import copy
import hashlib
import types

CI_CODE_SHA = '97c6887065e459d655256f6d94807c88bcc4760f78ee842abd641d9df9bba868'
CI_MANIFEST_SHA = '8335183e3341de4e023362330e4e1eaa153110d20b7f101172e7f1ff8c219a8c'
CI_VALUE_SHA = '8dc771f8f71e402cf758793b6f6460be74b3cbe227ee0e586a3d587d65c15e5b'
BASE_HEAD = '5b96787c9247504e5494f2664bf30126cf240e8d'
BASE_TREE = '31417fe654a9b6543480c2bd500c31d43819f6ab'
SOURCES = {'Bootstrap.CrateGraph': 'libraries/mlf-crates/Bootstrap/CrateGraph.hs',
           'Bootstrap.CrateQuery': 'libraries/mlf-crates/Bootstrap/CrateQuery.hs'}
# Reviewed draft ONLY. A changed candidate requires a deliberate new code review.
DRAFT_IDENTITIES = {
 'libraries/mlf-crates/Bootstrap/CrateGraph.hs': ('cbb7cbada11d4730348e5b63ada4da6cf7935d50c420609bd57be5fc24ed77a7','27bcc346fb979e45fd4f0702105dda93e7e975080a23a5daf02585869d98da65'),
 'libraries/mlf-crates/Bootstrap/CrateQuery.hs': ('fcb773fe34201e4e230f60698c87233675e20a03bdf4f68eb62fa4a368c55210','8ce2ab4ac86b3fccd525419a458412cbad495cfe69bd540e198411cb5ba1cd79')}
LOCK_IDENTITIES = ('0323366b84ac8a85adcd5511f04ac296fbeaa3a77de707a217be62d1dd5b1f5b', 'e526c31b229b07cfa19bbf06cf5782ebc1a0e2b67b852920fdec383e11d63c23')
CURRENT_INVENTORY_SHA = 'e8bb2b2284f354602c93738a7c1af99cb603f4104ab76d84d882d43378776d87'
CURRENT_REGISTRY_SHA = '97930cfb741a2f13b882697523277bbe738c55946f4d4a9c6c63e86590dfaa06'
CI_LOADER_SHA = 'f2686aafe3122dc68523061a212970873eeb144e09a537dfb9e25cab7361294a'
NAME = 'prepared-source-candidate.json'
FIELD = 'prepared_source_candidate'
FORMAT = 'prepared-source-candidate-source-v1'
SCOPE = 'Candidate exact source identity only; no compilation, native, fixed-point or merge qualification.'

# Reuse the separately pinned parent's safe code reader before executing it.
import os
import stat

# Record platform support before tests wrap os.open. No unsafe whole-path fallback.
_RELATIVE_READ_SUPPORTED = (os.open in os.supports_dir_fd and
                            os.stat in os.supports_dir_fd and
                            os.stat in os.supports_follow_symlinks)

def read_code(path):
    """Anchor every component to retained directory handles; fail closed otherwise."""
    if (not _RELATIVE_READ_SUPPORTED or not getattr(os,'O_DIRECTORY',0) or
            not getattr(os,'O_NOFOLLOW',0) or not getattr(os,'O_NONBLOCK',0)):
        raise ValueError('secure relative-open API unavailable; no unsafe fallback')
    raw_path=os.fspath(path)
    if not isinstance(raw_path,str) or '..' in raw_path.split(os.sep):
        raise ValueError('noncanonical implementation path')
    path=Path(raw_path).absolute()
    handles=[];entries=[];fd=None
    def identity(info):
        return info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode)
    def ordinary(info,directory):
        return ((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) and
                not getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400))
    try:
        parent=os.open(path.anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        handles.append(parent)
        for component in path.parts[1:-1]:
            before=os.stat(component,dir_fd=parent,follow_symlinks=False)
            if not ordinary(before,True):raise ValueError('implementation parent is not an ordinary directory')
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            handles.append(child)
            if identity(os.fstat(child))!=identity(before):raise ValueError('implementation parent replaced during open')
            entries.append((parent,component,identity(before),True))
            parent=child
        before=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        if not ordinary(before,False) or before.st_size>65536:
            raise ValueError('bounded regular contract implementation required')
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_BINARY',0),dir_fd=parent)
        info=os.fstat(fd)
        if identity(info)!=identity(before):raise ValueError('contract implementation replaced during open')
        entries.append((parent,path.name,identity(before),False))
        raw=b''
        while len(raw)<=65536:
            chunk=os.read(fd,min(8192,65537-len(raw)))
            if not chunk:break
            raw+=chunk
        after=os.fstat(fd)
        if len(raw)>65536 or (info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise ValueError('implementation byte bound or mutation')
        # Verify the original directory entries through the original retained
        # parents. A rename followed by a same-target symlink is NOT accepted.
        for parent,name,expected,directory in entries:
            current=os.stat(name,dir_fd=parent,follow_symlinks=False)
            if not ordinary(current,directory) or identity(current)!=expected:
                raise ValueError('implementation path changed during read')
        return raw
    except OSError as error:
        raise ValueError('implementation relative-open failed') from error
    finally:
        if fd is not None:os.close(fd)
        for handle in reversed(handles):os.close(handle)

read_implementation = read_code

path = Path(__file__).resolve().parent/'ci_integration_contract.py'
raw = read_code(path)
if hashlib.sha256(raw).hexdigest()!=CI_CODE_SHA: raise ValueError('fixed CI predecessor code SHA')
CI = types.ModuleType('prepared_input_fixed_ci_predecessor'); CI.__file__=str(path)
exec(compile(raw,str(path),'exec'),CI.__dict__)


def materialize(parent, edge):
    value=copy.deepcopy(parent)
    value['format']=FORMAT
    value['source_base_head'],value['source_base_tree']=edge['base_head'],edge['base_tree']
    value[FIELD]=copy.deepcopy(edge)
    for path,row in edge['deltas'].items(): value['current_files'][path]=row['new']
    for name,path in SOURCES.items(): value['current_registry'][name]=edge['deltas'][path]['new']
    value['current_inventory_sha256']=edge['inventory_sha256']
    value['current_registry_sha256']=edge['registry_sha256']
    return value


class Contract(CI.Contract):
    def __init__(self,directory,manifest_sha256,history_root,source_root=None):
        if not isinstance(manifest_sha256,str) or len(manifest_sha256)!=64 or any(c not in '0123456789abcdef' for c in manifest_sha256):
            raise ValueError('explicit provisional manifest SHA required')
        self._prepared_manifest_sha=manifest_sha256
        self._initializing_prepared=True
        super().__init__(directory,CI_MANIFEST_SHA,history_root,source_root=source_root)
        self._initializing_prepared=False
        self.manifest_sha256=manifest_sha256
        self.ci_metadata_paths=self.metadata_paths
        if hashlib.sha256(read_code(self.directory/'ci-integration-test-loader.py')).hexdigest()!=CI_LOADER_SHA:
            raise ValueError('fixed historical CI selector SHA')
        self.metadata_paths=tuple(sorted(set(self.metadata_paths)|{'prepared_source_contract.py','ci-integration-test-loader.py',NAME}|
            {row['file'] for row in self.value[FIELD]['deltas'].values()}))

    def _validate_edge(self,edge):
        c=self._core
        c.require(type(edge) is dict and set(edge)=={'format','provisional','base_head','base_tree','parent_value_sha256','scope','deltas','inventory_sha256','registry_sha256'},'provisional edge schema')
        c.require(edge['format']==FORMAT and edge['provisional'] is True and edge['base_head']==BASE_HEAD and edge['base_tree']==BASE_TREE and edge['parent_value_sha256']==CI_VALUE_SHA and edge['scope']==SCOPE,'provisional identity and scope')
        c.require(type(edge['deltas']) is dict and set(edge['deltas'])==set(SOURCES.values())|{'mlf.lock'},'exact two-source and lock edge')
        for row in edge['deltas'].values():
            c.require(type(row) is dict and set(row)=={'file','sha256','old','new'},'complete candidate delta row schema')
        for path,pins in DRAFT_IDENTITIES.items():
            row=edge['deltas'][path]
            c.require(type(row) is dict and (row.get('old'),row.get('new'))==pins,'reviewed provisional source identity')
        c.require((edge['deltas']['mlf.lock'].get('old'),edge['deltas']['mlf.lock'].get('new'))==LOCK_IDENTITIES,'exact candidate raw lock identities')
        c.require(edge['inventory_sha256']==CURRENT_INVENTORY_SHA and edge['registry_sha256']==CURRENT_REGISTRY_SHA,'fixed complete inventory pins')

    def _validate_manifest(self):
        c=self._core
        if getattr(self,'_initializing_prepared',False):
            CI.Contract._validate_manifest(self)
            c.require(c.canonical_sha(self.value)==CI_VALUE_SHA,'complete fixed CI predecessor value')
            self.ci_value=copy.deepcopy(self.value)
            raw=c.read_file(self.directory,NAME,c.MAX_METADATA_BYTES)
            c.require(c.sha(raw)==self._prepared_manifest_sha,'explicit provisional manifest pin')
            edge=c.strict_json(raw);self._validate_edge(edge)
            self.value=materialize(self.ci_value,edge)
            self._initializing_prepared=False
        v=self.value
        c.require(type(v) is dict and set(v)==CI.CURRENT_FIELDS|{FIELD} and v['format']==FORMAT,'provisional current fields')
        edge=v[FIELD];self._validate_edge(edge)
        old=copy.deepcopy(v);del old[FIELD];old['format']=CI.VIEW_FORMAT
        old['source_base_head'],old['source_base_tree']=CI.BASE_HEAD,CI.BASE_TREE
        for path,row in edge['deltas'].items(): old['current_files'][path]=row['old']
        for name,path in SOURCES.items(): old['current_registry'][name]=DRAFT_IDENTITIES[path][0]
        old['current_inventory_sha256']=CI.CURRENT_INVENTORY_SHA256
        old['current_registry_sha256']=CI.CURRENT_REGISTRY_SHA256
        c.require(c.canonical_sha(old)==CI_VALUE_SHA and (not hasattr(self,'ci_value') or old==self.ci_value),'full fixed CI predecessor restoration')
        self.ci_value=old
        trial=self._ci_proxy()
        CI.Contract._validate_manifest(trial)
        for name in ('query_index_value','package_roots_value','open_release_value','builtin_value','writer_value','graph_value'):
            setattr(self,name,getattr(trial,name))
        c.require(v==materialize(old,edge) and c.canonical_sha(v['current_files'])==edge['inventory_sha256'] and c.canonical_sha(v['current_registry'])==edge['registry_sha256'],'complete successor identities')
        self._validate_rows(edge['deltas'],set(SOURCES.values())|{'mlf.lock'},old['current_files'],v['current_files'],'prepared-source-candidate-deltas/')

    def _ci_proxy(self):
        trial=object.__new__(CI.Contract);trial.__dict__=dict(self.__dict__)
        trial.value=self.ci_value;trial._initializing_ci=False
        trial.manifest_sha256=CI_MANIFEST_SHA
        if hasattr(self,'ci_metadata_paths'):
            trial.metadata_paths=self.ci_metadata_paths
        elif hasattr(trial,'metadata_paths'):
            # No parent metadata inventory exists until parent initialization finishes.
            del trial.metadata_paths
        return trial

    def _validate_ci_provenance_record(self,value):
        if not hasattr(self,'ci_value'): return CI.Contract._validate_ci_provenance_record(self,value)
        return self._ci_proxy()._validate_ci_provenance_record(value)

    def _validate_index_provenance_record(self,value):
        if not hasattr(self,'ci_value'): return CI.Contract._validate_index_provenance_record(self,value)
        return self._ci_proxy()._validate_index_provenance_record(value)

    def _validate_roots_provenance_record(self,value):
        if not hasattr(self,'ci_value'): return CI.Contract._validate_roots_provenance_record(self,value)
        return self._ci_proxy()._index_proxy()._roots_proxy()._validate_roots_provenance_record(value)

    def _validate_open_release_provenance_record(self,value):
        if not hasattr(self,'ci_value'): return CI.Contract._validate_open_release_provenance_record(self,value)
        return self._ci_proxy()._index_proxy()._roots_proxy()._open_proxy()._validate_open_release_provenance_record(value)

    def _validate_provenance_record(self,value):
        if not hasattr(self,'ci_value'): return CI.Contract._validate_provenance_record(self,value)
        return self._ci_proxy()._index_proxy()._roots_proxy()._open_proxy()._builtin_proxy()._validate_provenance_record(value)

    def _to_ci(self,raw,path):
        c=self._core
        c.require(path in self.value['current_files'] and type(raw) is bytes and c.sha(raw)==self.value['current_files'][path],'complete provisional source SHA: '+path)
        rows=self.value[FIELD]['deltas']
        return self._apply(raw,path,rows,True) if path in rows else raw

    def _from_ci(self,raw,path):
        c=self._core
        c.require(path in self.ci_value['current_files'] and type(raw) is bytes and c.sha(raw)==self.ci_value['current_files'][path],'complete predecessor source SHA: '+path)
        rows=self.value[FIELD]['deltas']
        return self._apply(raw,path,rows,False) if path in rows else raw

    def _validate_metadata_transition(self,frozen,current):
        c=self._core
        c.require(set(current)==set(self.value['current_files']),'complete transition inputs')
        old={p:self._to_ci(raw,p) for p,raw in current.items()}
        expected=c.strict_json(old['mlf.lock']);seen=set()
        for package in expected['packages']:
            for name,digest in package['sources'].items():
                path=c.lock_path(package['path'],name)
                if path in DRAFT_IDENTITIES:
                    before,after=DRAFT_IDENTITIES[path]
                    c.require(path not in seen and digest==before,'unique old source lock owner')
                    seen.add(path);package['sources'][name]=after
        c.require(seen==set(DRAFT_IDENTITIES) and c.strict_json(current['mlf.lock'])==expected,'exact two-source lock change')
        self._ci_proxy()._validate_metadata_transition(frozen,old)

# Every inherited projection crosses exactly one new edge, then the unchanged
# predecessor implementation. Default args bind each method, not the last loop value.
for name in ('index','roots','open','builtin','writer','frozen'):
    def project(self,raw,path,_method='_to_'+name):
        return getattr(self._ci_proxy(),_method)(self._to_ci(raw,path),path)
    setattr(Contract,'_to_'+name,project)
for name in ('index','roots','open','frozen'):
    def advance(self,raw,path,_method='_from_'+name):
        return self._from_ci(getattr(self._ci_proxy(),_method)(raw,path),path)
    setattr(Contract,'_from_'+name,advance)
