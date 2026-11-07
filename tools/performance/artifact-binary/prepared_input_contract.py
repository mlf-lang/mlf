"""PROVISIONAL prepared-input successor. Never selected by the live loader.

Linux-only experiment, not the maintained cross-platform live contract.
Source projection only, not successful compilation, generation, fixed point or
merge qualification. Final pins and producer evidence remain deliberately absent.
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
NAME = 'prepared-input-provisional.json'
FIELD = 'prepared_input_provisional'
FORMAT = 'prepared-input-provisional-source-v1'
SCOPE = 'Provisional exact source projection only; no compilation, native, fixed-point or merge qualification.'

# Reuse the separately pinned parent's safe code reader before executing it.
import os
import stat
import sys

if sys.platform != "linux":
    raise ValueError("Linux-only provisional adapter; live selector remains unchanged")

def read_code(path):
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise ValueError('bounded regular contract implementation required')
        raw = os.read(fd,65537)
        if len(raw)>65536: raise ValueError('implementation byte bound')
        return raw
    except OSError as error:
        raise ValueError('implementation read failed') from error
    finally:
        if fd is not None: os.close(fd)

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


class ProvisionalContract(CI.Contract):
    def __init__(self,directory,manifest_sha256,history_root,source_root=None):
        if not isinstance(manifest_sha256,str) or len(manifest_sha256)!=64 or any(c not in '0123456789abcdef' for c in manifest_sha256):
            raise ValueError('explicit provisional manifest SHA required')
        self._prepared_manifest_sha=manifest_sha256
        self._initializing_prepared=True
        super().__init__(directory,CI_MANIFEST_SHA,history_root,source_root=source_root)
        self._initializing_prepared=False
        self.manifest_sha256=manifest_sha256
        self.ci_metadata_paths=self.metadata_paths
        self.metadata_paths=tuple(sorted(set(self.metadata_paths)|{'prepared_input_contract.py',NAME}|
            {row['file'] for row in self.value[FIELD]['deltas'].values()}))

    def _validate_edge(self,edge):
        c=self._core
        c.require(type(edge) is dict and set(edge)=={'format','provisional','base_head','base_tree','parent_value_sha256','scope','deltas','inventory_sha256','registry_sha256'},'provisional edge schema')
        c.require(edge['format']==FORMAT and edge['provisional'] is True and edge['base_head']==BASE_HEAD and edge['base_tree']==BASE_TREE and edge['parent_value_sha256']==CI_VALUE_SHA and edge['scope']==SCOPE,'provisional identity and scope')
        c.require(type(edge['deltas']) is dict and set(edge['deltas'])==set(SOURCES.values())|{'mlf.lock'},'exact two-source and lock edge')
        for path,pins in DRAFT_IDENTITIES.items():
            row=edge['deltas'][path]
            c.require(type(row) is dict and (row.get('old'),row.get('new'))==pins,'reviewed provisional source identity')
        c.require(c.is_sha(edge['inventory_sha256']) and c.is_sha(edge['registry_sha256']),'complete inventory pins')

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
        c.require(type(v) is dict and set(v)==set(self.ci_value)|{FIELD} and v['format']==FORMAT,'provisional current fields')
        edge=v[FIELD];self._validate_edge(edge)
        old=copy.deepcopy(v);del old[FIELD];old['format']=CI.VIEW_FORMAT
        old['source_base_head'],old['source_base_tree']=CI.BASE_HEAD,CI.BASE_TREE
        for path,row in edge['deltas'].items(): old['current_files'][path]=row['old']
        for name,path in SOURCES.items(): old['current_registry'][name]=DRAFT_IDENTITIES[path][0]
        old['current_inventory_sha256']=CI.CURRENT_INVENTORY_SHA256
        old['current_registry_sha256']=CI.CURRENT_REGISTRY_SHA256
        c.require(c.canonical_sha(old)==CI_VALUE_SHA and old==self.ci_value,'full fixed CI predecessor restoration')
        CI.Contract._validate_manifest(self._ci_proxy())
        c.require(v==materialize(old,edge) and c.canonical_sha(v['current_files'])==edge['inventory_sha256'] and c.canonical_sha(v['current_registry'])==edge['registry_sha256'],'complete successor identities')
        self._validate_rows(edge['deltas'],set(SOURCES.values())|{'mlf.lock'},old['current_files'],v['current_files'],'prepared-input-provisional-deltas/')

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
    setattr(ProvisionalContract,'_to_'+name,project)
for name in ('index','roots','open','frozen'):
    def advance(self,raw,path,_method='_from_'+name):
        return self._from_ci(getattr(self._ci_proxy(),_method)(raw,path),path)
    setattr(ProvisionalContract,'_from_'+name,advance)


def live_contract(*args,**kwargs):
    raise ValueError('provisional successor is not eligible for live admission or sealing')
