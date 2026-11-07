"""Provisional source-only controls. No live selector, final seal or producer claims."""
from pathlib import Path
import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
import prepared_input_contract as p

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BUNDLE=Path('tools/performance/artifact-binary')
OLD_TEST_SHA='dce86266203ea100f157b57afd073a7dc5e5069e1246dafa1669f67b3854cb92'
OLD_LOADER_SHA='f2686aafe3122dc68523061a212970873eeb144e09a537dfb9e25cab7361294a'

def encode(value): return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def write(root,path,raw):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
def git_bytes(path):
    return subprocess.check_output(['git','show','98540496cd5e94d2de87894486acdc9bb945fdac:'+path],cwd=ROOT)

def splice(path,old,new):
    # Single exact contiguous splice preserves all common prefix/suffix bytes.
    start=0
    while start<min(len(old),len(new)) and old[start]==new[start]:start+=1
    end=0
    while end<min(len(old),len(new))-start and old[-end-1]==new[-end-1]:end+=1
    return {'format':'binary-source-byte-splices-v1','path':path,'old_sha256':hashlib.sha256(old).hexdigest(),'new_sha256':hashlib.sha256(new).hexdigest(),'old_bytes':len(old),'new_bytes':len(new),'splices':[{'old_at':start,'new_at':start,'old':base64.b64encode(old[start:len(old)-end if end else None]).decode(),'new':base64.b64encode(new[start:len(new)-end if end else None]).decode()}]}

class PreparedSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='prepared-source-controls-')
        cls.base=Path(cls.temp.name); cls.source=cls.base/'candidate';cls.bundle=cls.source/BUNDLE
        # Baseline inventory is parsed only as a path discovery hint. Actual CI
        # constructor authenticates every source byte, metadata pin and history.
        parent_paths=json.loads((HERE/'query-graph-migration.json').read_bytes())['current_files']
        for path in parent_paths:
            write(cls.source,path,git_bytes(path))
        for file in HERE.rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts:
                write(cls.source,str(BUNDLE/file.relative_to(HERE)),file.read_bytes())
        # Frozen histories are authenticated by the parent contract at admission.
        for relative in ('parent-inventory.json','maintenance-parents.json'):
            data=json.loads((HERE/relative).read_bytes())
            paths=data['frozen_history'] if relative.startswith('parent-') else data['files']
            for name in paths: write(cls.source,'tools/performance/'+name,(ROOT/'tools/performance'/name).read_bytes())
        cls.parent=p.CI.Contract(cls.bundle,p.CI_MANIFEST_SHA,cls.source/'tools/performance',source_root=cls.source)
        cls.old={path:(cls.source/path).read_bytes() for path in cls.parent.value['current_files']}
        cls.new=dict(cls.old)
        for path in p.DRAFT_IDENTITIES: cls.new[path]=(ROOT/path).read_bytes()
        lock=cls.old['mlf.lock']
        for old,new in p.DRAFT_IDENTITIES.values():
            if lock.count(old.encode())!=1: raise ValueError('unique baseline lock pin')
            lock=lock.replace(old.encode(),new.encode())
        cls.new['mlf.lock']=lock
        rows={}
        for index,path in enumerate(sorted(set(p.DRAFT_IDENTITIES)|{'mlf.lock'})):
            raw=encode(splice(path,cls.old[path],cls.new[path]));name=f'prepared-input-provisional-deltas/{index}.json'
            write(cls.bundle,name,raw)
            rows[path]={'file':name,'sha256':hashlib.sha256(raw).hexdigest(),'old':hashlib.sha256(cls.old[path]).hexdigest(),'new':hashlib.sha256(cls.new[path]).hexdigest()}
        c=cls.parent._core
        files={path:c.sha(raw) for path,raw in cls.new.items()}
        registry=dict(cls.parent.value['current_registry'])
        for name,path in p.SOURCES.items():registry[name]=files[path]
        cls.edge={'format':p.FORMAT,'provisional':True,'base_head':p.BASE_HEAD,'base_tree':p.BASE_TREE,'parent_value_sha256':p.CI_VALUE_SHA,'scope':p.SCOPE,'deltas':rows,'inventory_sha256':c.canonical_sha(files),'registry_sha256':c.canonical_sha(registry)}
        cls.manifest=encode(cls.edge);write(cls.bundle,p.NAME,cls.manifest)
        for path,raw in cls.new.items():write(cls.source,path,raw)
        cls.contract=p.ProvisionalContract(cls.bundle,c.sha(cls.manifest),cls.source/'tools/performance',source_root=cls.source)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def test_complete_fixed_parent_and_roundtrip(self):
        b=self.contract
        self.assertEqual(b.ci_value,self.parent.value)
        self.assertEqual({path:b._to_ci(raw,path) for path,raw in self.new.items()},self.old)
        self.assertEqual({path:b._from_ci(raw,path) for path,raw in self.old.items()},self.new)
        projected=b.project_tree_bytes(self.new)
        additions={path:self.new[path] for path in b.added_paths}
        self.assertEqual(b.advance_tree_bytes(projected,additions),self.new)
    def test_all_ancestor_projections(self):
        b=self.contract
        for name in ('index','roots','open','builtin','writer','frozen'):
            for path in self.new:
                self.assertEqual(getattr(b,'_to_'+name)(self.new[path],path),getattr(self.parent,'_to_'+name)(self.old[path],path))
    def test_ancestor_provenance_callbacks(self):
        b=self.contract
        b._validate_ci_provenance_record(b.ci_integration_generation_evidence)
        b._validate_index_provenance_record(b.query_index_generation_evidence)
    def test_ci_proxy_identity_is_parent_identity(self):
        proxy=self.contract._ci_proxy()
        self.assertEqual(proxy.manifest_sha256,self.parent.manifest_sha256)
        self.assertEqual(proxy.metadata_paths,self.parent.metadata_paths)
        self.assertEqual(proxy.value,self.parent.value)
        self.assertNotIn(p.NAME,proxy.metadata_paths)

    def test_all_five_historical_provenance_callbacks(self):
        b=self.contract
        roots=self.parent._index_proxy()._roots_proxy()
        open_parent=roots._open_proxy()
        builtin=open_parent._builtin_proxy()
        self.assertEqual(b._core.canonical_sha(open_parent.value),p.CI._INDEX._ROOTS.OPEN_VALUE_SHA256)
        self.assertEqual(b._core.canonical_sha(builtin.value),p.CI._INDEX._ROOTS._OPEN.BUILTIN_VALUE_SHA256)
        cases=[
            ('ci-integration-provenance.json','_validate_ci_provenance_record',self.parent),
            ('query-index-provenance.json','_validate_index_provenance_record',self.parent._index_proxy()),
            ('open-package-roots-provenance.json','_validate_roots_provenance_record',roots),
            ('open-release-provenance.json','_validate_open_release_provenance_record',open_parent),
            ('builtin-regeneration-provenance.json','_validate_provenance_record',builtin),
        ]
        for filename,method,authentic_parent in cases:
            record=json.loads((HERE/filename).read_bytes())
            getattr(authentic_parent,method)(record)
            getattr(b,method)(record)
            forged=copy.deepcopy(record);forged['unreviewed']='must reject'
            with self.assertRaises(ValueError):getattr(authentic_parent,method)(forged)
            with self.assertRaises(ValueError):getattr(b,method)(forged)

    def test_no_live_admission(self):
        with self.assertRaisesRegex(ValueError,'not eligible'):p.live_contract()
    def test_wrong_manifest_pin(self):
        with self.assertRaises(ValueError):p.ProvisionalContract(self.bundle,'0'*64,self.source/'tools/performance',source_root=self.source)
    def test_forged_edge_rehashed_still_rejected(self):
        for key,value in [('provisional',False),('base_head','0'*40),('base_tree','0'*40),('parent_value_sha256','0'*64),('scope','qualified')]:
            edge=copy.deepcopy(self.edge);edge[key]=value
            with self.assertRaises(ValueError):self.contract._validate_edge(edge)
        edge=copy.deepcopy(self.edge);edge['deltas'][next(iter(p.DRAFT_IDENTITIES))]['new']='0'*64
        with self.assertRaises(ValueError):self.contract._validate_edge(edge)
    def test_missing_extra_inventory_and_source_mutation(self):
        for changed in [dict(self.new,extra=b'x'),{k:v for k,v in self.new.items() if k!='mlf.lock'},dict(self.new,**{'mlf.lock':self.new['mlf.lock']+b' '})]:
            with self.assertRaises(ValueError):self.contract.project_tree_bytes(changed)
    def test_bad_delta_and_owner(self):
        b=self.contract;path=next(iter(p.DRAFT_IDENTITIES));row=b.value[p.FIELD]['deltas'][path];file=b.directory/row['file'];raw=file.read_bytes()
        try:
            file.write_bytes(raw+b' ')
            with self.assertRaises(ValueError):b._to_ci(self.new[path],path)
        finally:file.write_bytes(raw)
        delta=json.loads(raw);delta['path']='mlf.lock'
        with self.assertRaises(ValueError):self._bad_owner(b,path,delta)
    def _bad_owner(self,b,path,delta):
        row=b.value[p.FIELD]['deltas'][path];file=b.directory/row['file'];raw=file.read_bytes();before=row['sha256']
        try:
            changed=encode(delta);file.write_bytes(changed);row['sha256']=b._core.sha(changed)
            b._to_ci(self.new[path],path)
        finally:file.write_bytes(raw);row['sha256']=before
    def test_bad_splice_offsets_rehashed(self):
        b=self.contract;path=next(iter(p.DRAFT_IDENTITIES));row=b.value[p.FIELD]['deltas'][path]
        delta=json.loads((b.directory/row['file']).read_bytes())
        delta['splices'][0]['old_at']+=1
        with self.assertRaises(ValueError):self._bad_owner(b,path,delta)
    def test_wrong_value_inventory_and_parent(self):
        b=self.contract;original=b.value
        try:
            for field,key in [('current_files','mlf.lock'),('current_registry','Bootstrap.CrateQuery')]:
                b.value=copy.deepcopy(original);b.value[field][key]='0'*64
                with self.assertRaises(ValueError):b._validate_manifest()
        finally:b.value=original
    def test_delta_symlink_rejected(self):
        b=self.contract;path=next(iter(p.DRAFT_IDENTITIES));file=b.directory/b.value[p.FIELD]['deltas'][path]['file']
        raw=file.read_bytes();target=file.with_suffix('.saved');target.write_bytes(raw)
        file.unlink();file.symlink_to(target)
        try:
            with self.assertRaises(ValueError):b._to_ci(self.new[path],path)
        finally:file.unlink();file.write_bytes(raw);target.unlink()
    def test_independent_relocated_source_root(self):
        target=self.base/'relocated-source'
        for path,raw in self.new.items():write(target,path,raw)
        b=p.ProvisionalContract(self.bundle,self.contract._prepared_manifest_sha,self.source/'tools/performance',source_root=target)
        self.assertEqual(b.source_root,target)
        self.assertEqual(b.evidence_source_root,self.parent.evidence_source_root)
    def test_predecessor_code_pin_before_execution(self):
        file=self.bundle/'ci_integration_contract.py';raw=file.read_bytes()
        try:
            file.write_bytes(raw+b'\nraise RuntimeError("must never execute")\n')
            module=types.ModuleType('tampered_predecessor_control')
            module.__file__=str(self.bundle/'prepared_input_contract.py')
            with self.assertRaisesRegex(ValueError,'predecessor code SHA'):
                exec(compile((HERE/'prepared_input_contract.py').read_bytes(),module.__file__,'exec'),module.__dict__)
        finally:file.write_bytes(raw)
    def test_physical_unchanged_ci_suite(self):
        b=self.contract;target=self.base/'ci-predecessor'
        for path,raw in self.new.items():write(target,path,b._to_ci(raw,path))
        for name in set(b.parent['frozen_history'])|set(b.maintenance_parent['files']):
            write(target,'tools/performance/'+name,(self.source/'tools/performance'/name).read_bytes())
        for name in b.ci_metadata_paths:write(target,str(BUNDLE/name),(HERE/name).read_bytes())
        write(target,str(BUNDLE/'source_migration_adapter.py'),(HERE/'ci-integration-test-loader.py').read_bytes())
        # The unchanged suite pins all its transitive historical executables.
        for file in HERE.glob('*.py'):
            if file.name.startswith('test_') or file.name.endswith('-test-loader.py'):
                write(target,str(BUNDLE/file.name),file.read_bytes())
        self.assertEqual(hashlib.sha256((target/BUNDLE/'source_migration_adapter.py').read_bytes()).hexdigest(),OLD_LOADER_SHA)
        self.assertEqual(hashlib.sha256((target/BUNDLE/'test_ci_integration_migration.py').read_bytes()).hexdigest(),OLD_TEST_SHA)
        result=subprocess.run([sys.executable,'-B']+(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else [])+[str(target/BUNDLE/'test_ci_integration_migration.py')],cwd=target,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=300)
        self.assertEqual(result.returncode,0,result.stdout)
        print('PHYSICAL UNCHANGED CI SUITE:',result.stdout,flush=True)

if __name__=='__main__':unittest.main()
