"""Synthetic fail-closed current producer custody controls, not compiler execution."""
import ast,copy,hashlib,json,pathlib,tempfile,types,unittest
BASE=pathlib.Path(__file__).resolve().parents[1];ROOT=BASE.parents[2];PROV=BASE/'provenance'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load():
    p=PROV/'current-producer.py';module=types.ModuleType('tested_current_producer');exec(compile(p.read_bytes(),str(p),'exec'),module.__dict__);return module
H=load()
class CurrentProducer(unittest.TestCase):
    def setUp(self):
        self.baseline=H.read(PROV/H.BASELINE);self.contract=H.read(PROV/H.CONTRACT);self.transition=H.read(PROV/H.TRANSITION);self.source_sha=sha(PROV/H.BASELINE)
    def transition_check(self,transition=None,contract=None,baseline=None):
        return H.check_transition(self.baseline if baseline is None else baseline,self.contract if contract is None else contract,self.transition if transition is None else transition,self.source_sha)
    def test_exact_transition(self):
        self.transition_check();self.assertEqual(len(self.baseline['shared_manifest']['modules']),128);self.assertEqual(len(self.transition['shared_rows']),132)
        self.assertEqual(set(self.contract)-set(self.baseline['files']),{r['path']for r in H.ADDED})
    def test_historical_manifests_preserved(self):
        for path,digest in H.HISTORICAL.items():self.assertEqual(sha(PROV/path),digest)
    def test_each_changed_new_and_old_hash_required(self):
        for path in sorted(H.CHANGED):
            for field in ['old','new']:
                t=copy.deepcopy(self.transition);t['changed'][path][field]='0'*64
                with self.subTest(path=path,field=field),self.assertRaises(ValueError):self.transition_check(t)
    def test_each_added_hash_required(self):
        for path in self.transition['added']:
            t=copy.deepcopy(self.transition);t['added'][path]='0'*64
            with self.subTest(path=path),self.assertRaises(ValueError):self.transition_check(t)
    def test_current_baseline_not_old_anchor_or_wrong_target(self):
        for key,value in [('target_commit',H.ANCHORS['common_base']),('target_tree','0'*40),('baseline_sha256','0'*64),('historical_anchors',{})]:
            t=copy.deepcopy(self.transition);t[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.transition_check(t)
    def test_transition_missing_extra_and_partial_rejected(self):
        for kind in ['missing','extra','partial','unchanged']:
            t=copy.deepcopy(self.transition)
            if kind=='missing':t.pop('shared_rows')
            elif kind=='extra':t['unknown']=True
            elif kind=='partial':t['changed'].pop(sorted(H.CHANGED)[0])
            else:t['unchanged'].pop(next(iter(t['unchanged'])))
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.transition_check(t)
    def test_shared_rows_complete_order_paths_roles(self):
        for kind in ['missing','extra','duplicate','reordered','path','role']:
            t=copy.deepcopy(self.transition);rows=t['shared_rows']
            if kind=='missing':rows.pop(1)
            elif kind=='extra':rows.append({'module':'Unexpected','path':'x.hs','role':'implementation'})
            elif kind=='duplicate':rows[2]=dict(rows[1])
            elif kind=='reordered':rows[1],rows[2]=rows[2],rows[1]
            elif kind=='path':rows[1]['path']='wrong.hs'
            else:rows[1]['role']='direct-test'
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.transition_check(t)
    def test_contract_inventory_not_count_only(self):
        for kind in ['missing','extra','stale','unknownordinary','zero']:
            c=dict(self.contract)
            if kind=='missing':c.pop(next(iter(c)))
            elif kind=='extra':c['unreviewed.hs']='f'*64
            elif kind=='stale':c['bootstrap/MLF/Entry/Emlf.hs']=self.baseline['files']['bootstrap/MLF/Entry/Emlf.hs']
            elif kind=='unknownordinary':c['libraries/mlf-foundation/Bootstrap/Types.hs']='f'*64
            else:c['bootstrap/MLF/ResourceExport.hs']='0'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.transition_check(contract=c)
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            p=pathlib.Path(d)/'bad.json';p.write_text('{"x":1,"x":1}')
            with self.assertRaises(ValueError):H.read(p)
    def test_no_historical_fallback_route(self):
        prep=(BASE/'prepare.py').read_text();mod=(BASE/'module_prepare.py').read_text()
        self.assertNotIn("manifest=json.loads((BASE/'provenance/pr25-source.json')",prep)
        self.assertNotIn("manifest=json.loads((host.BASE/'provenance/pr25-source.json')",mod)
        self.assertIn('manifest=current_source_manifest()',prep);self.assertIn('manifest=host.current_source_manifest()',mod)
    def test_fresh_build_command_inventory_and_flags_required(self):
        receipt=H.read(BASE/'validation/compiler-build.json')
        for kind in ['optimization','force','label','status','count']:
            r=copy.deepcopy(receipt)
            if kind=='optimization':r['commands'][2]['argv']=[('-O2'if v=='-O0'else v)for v in r['commands'][2]['argv']]
            elif kind=='force':r['commands'][2]['argv'].remove('-fforce-recomp')
            elif kind=='label':r['commands'][2]['label']='unknown'
            elif kind=='status':r['commands'][1]['status']='running'
            else:r['commands'].pop()
            shared=H.read(ROOT/'shared-sources.json');mapping={x['module']:x['path']for x in shared['modules']}
            with self.subTest(kind=kind),self.assertRaises(ValueError):H.authenticate_logs(ROOT,r,mapping,receipt['inputs'],shared,self.contract)
    def test_receipt_binds_checked_prelude_transition_read_dependency(self):
        receipt=H.read(BASE/'validation/compiler-build.json')
        path='tools/performance/crate-prelude/source-migration.json'
        self.assertEqual(receipt['inputs'][path],H.PRELUDE_MANIFEST_SHA256)
        self.assertEqual(sha(ROOT/path),H.PRELUDE_MANIFEST_SHA256)

    def test_builder_launch_precedes_process_and_receipt_is_atomic(self):
        text=(BASE/'build_compiler.py').read_text();self.assertLess(text.index("report['commands'].append(entry);save()"),text.index('process=subprocess.Popen'))
        self.assertIn('temporary.replace(path)',text);self.assertIn("status='UNKNOWN'",text)
        self.assertIn("build.mkdir(parents=True,exist_ok=False)",text)
    def test_input_path_scope(self):
        for p in ['../escape','/absolute','x/../y','x\\y','./x','']:
            with self.subTest(path=p),self.assertRaises(ValueError):H.relative(p)
    def test_baseline_replays_exact_checked_prelude_step(self):
        H.validate_baseline_lineage(ROOT,PROV,self.baseline)
        old=H.read(PROV/'c592-history/current-target-source.json')
        self.assertEqual(old['source_commit'],'c5928b5be73cd78d194405e734aa012415570e1a')
        self.assertEqual(self.baseline['source_commit'],'a250ec334b70b0e587c2dd6e894d111bf879c024')
        changed={p for p in old['files'] if old['files'][p]!=self.baseline['files'][p]}
        self.assertEqual(changed,{'mlf.lock','bootstrap/MLF/BuiltinPreludeData.hs',
            'bootstrap/MLF/Entry/BuiltinPrelude.hs','bootstrap/MLF/Entry/Emlf.hs',
            'bootstrap/MLF/PreparedCompiler.hs','libraries/mlf-crates/Bootstrap/BuiltinPreludeContext.hs',
            'libraries/mlf-crates/Bootstrap/BuiltinPreludeLiteral.hs','libraries/mlf-crates/Bootstrap/Crate.hs',
            'libraries/mlf-crates/Bootstrap/CrateSession.hs'})
        for path in sorted(changed):
            wrong=copy.deepcopy(self.baseline);wrong['files'][path]=old['files'][path]
            with self.subTest(path=path),self.assertRaises(ValueError):H.validate_baseline_lineage(ROOT,PROV,wrong)
        with self.assertRaises(ValueError):H.validate_baseline_lineage(ROOT,PROV,old)

if __name__=='__main__':unittest.main()
