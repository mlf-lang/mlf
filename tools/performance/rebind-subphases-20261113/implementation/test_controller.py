"""Lightweight target, flags and launch-policy negatives. Never runs GHC."""
from pathlib import Path
import copy, importlib, json, os, tempfile, unittest
from unittest.mock import patch
import controller as C
import oracles as O

class Oracles(unittest.TestCase):
    def report(self,n=475):
        return {'format':1,'crate':O.IDENTITY,'inferred_groups':n,'reused_groups':0,'groups':[{'id':str(i),'members':[str(i)],'cached':False,'result':{'ordered':[i,i+1]}} for i in range(n)]}
    def test_fresh_complete(self): O.fresh(self.report())
    def test_fresh_bad(self):
        for key,value in [('format',True),('inferred_groups',True),('reused_groups',1),('crate','tiny')]:
            r=self.report();r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):O.fresh(r)
    def test_cache_hit(self):
        r=self.report();r['groups'][0]['cached']=True
        with self.assertRaises(ValueError):O.fresh(r)
    def test_duplicate(self):
        r=self.report();r['groups'][0]['id']='1'
        with self.assertRaises(ValueError):O.fresh(r)
    def test_shortened(self):
        with self.assertRaises(ValueError):O.fresh(self.report(1))
    def test_three_raw_full_order(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a';b=Path(d)/'b'
            for p in [a,b]:
                for suf in O.SUFFIXES:Path(str(p)+suf).write_bytes(json.dumps(self.report()).encode() if suf=='.queries' else b'whole-binary\x00')
            O.three_artifacts(a,b)
            r=self.report();r['groups'].reverse();Path(str(a)+'.queries').write_text(json.dumps(r))
            with self.assertRaises(ValueError):O.three_artifacts(a,b)
    def test_any_raw_change(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a';b=Path(d)/'b'
            for p in [a,b]:
                for suf in O.SUFFIXES:Path(str(p)+suf).write_text(json.dumps(self.report()) if suf=='.queries' else 'same')
            for suf in O.SUFFIXES[:2]:
                Path(str(a)+suf).write_text('different')
                with self.assertRaises(ValueError):O.three_artifacts(a,b)
                Path(str(a)+suf).write_text('same')
    def test_interface_all_owners(self):
        names=['M'+str(i) for i in range(14)];text='crate c\n'+''.join('module '+n+'\n' for n in names)+'dependency b /a/b.mlfci digest\n'
        O.interface(text,'c',names,{'b':'/a/b.mlfci'})
        with self.assertRaises(ValueError):O.interface(text.replace('module M13\n',''),'c',names,{'b':'/a/b.mlfci'})
    def test_interface_dependency_order_identity(self):
        with self.assertRaises(ValueError):O.interface('crate c\nmodule A\ndependency wrong /b.mlfci hash\n','c',['A'],{'builtin':'/b.mlfci'})
    def test_length_pack_unicode(self):
        values=['λ雪🙂','42','',O.pack(['a','b'])];self.assertEqual(O.unpack(O.pack(values)),values)
    def test_noncanonical_packing(self):
        for s in ['01:x','3:x','-1:x','x']:
            with self.subTest(s=s),self.assertRaises(ValueError):O.unpack(s)
    def test_json_duplicates_nonfinite(self):
        for s in ['{"x":1,"x":2}','{"x":NaN}']:
            with self.assertRaises(ValueError):O.loads(s)
    def test_path_symlink_stale(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'real').write_text('x');(root/'link').symlink_to(root/'real')
            with self.assertRaises(ValueError):O.sha(root/'link')
            with self.assertRaises(ValueError):O.absent(root/'real')
    def test_original_cpp_path_plus_is_safe_but_whitespace_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);tool=root/'x86_64-linux-gnu-g++-14';tool.write_bytes(b'original tool')
            self.assertEqual(O.sha(tool),O.digest(b'original tool'))
            for name in ['tool with space','tool;command','tool\nname']:
                with self.subTest(name=name),self.assertRaises(ValueError):O.safe(root/name)
            with self.assertRaises(ValueError):O.safe(root/'..'/'escape')
    def alias_stage(self,root):
        s=C.Stage.__new__(C.Stage);s.source=root;s.alias_bindings=[];s.alias_binding_keys=set()
        s.record={'alias_bindings':[],'input_pins':{},'output_pins':{}};return s
    def test_exact_alias_duplicates_verify_before_collapsing(self):
        import runtime_pins as R
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'file';p.write_bytes(b'x');binding=R.binding(p);s=self.alias_stage(root)
            with patch.object(R,'binding',wraps=R.binding) as check:
                s.pin_inputs(binding);s.pin_inputs(dict(reversed(list(binding.items()))))
                self.assertEqual(check.call_count,2)
            self.assertEqual(s.alias_bindings,[binding]);self.assertEqual(s.record['alias_bindings'],[binding])
            self.assertEqual(s.record['input_pins'],{str(p):binding['sha256']})
    def test_different_alias_paths_same_file_retained(self):
        import runtime_pins as R
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'file';p.write_bytes(b'x');alias=root/'alias';alias.symlink_to('file');s=self.alias_stage(root)
            bindings=[R.binding(p),R.binding(alias)];s.pin_inputs(bindings)
            self.assertEqual(s.alias_bindings,bindings);self.assertEqual(len(s.record['input_pins']),1)
    def test_same_path_different_metadata_retained_and_fails_checkpoint(self):
        import runtime_pins as R
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'file';p.write_bytes(b'old');s=self.alias_stage(root);old=R.binding(p);s.pin_inputs(old)
            p.write_bytes(b'new and longer');new=R.binding(p);s.pin_inputs(new)
            self.assertEqual(s.alias_bindings,[old,new])
            with patch.object(O,'frozen_source'),self.assertRaisesRegex(ValueError,'alias drift'):s.recheck()
    def test_duplicate_old_binding_still_rejected_after_file_changes(self):
        import runtime_pins as R
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'file';p.write_bytes(b'old');s=self.alias_stage(root);binding=R.binding(p);s.pin_inputs(binding);p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'alias binding changed'):s.pin_inputs(binding)
            self.assertEqual(s.alias_bindings,[binding])
    def test_each_checkpoint_rechecks_distinct_aliases_and_all_pins(self):
        import runtime_pins as R
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'file';p.write_bytes(b'x');alias=root/'alias';alias.symlink_to('file');s=self.alias_stage(root)
            s.pin_inputs([R.binding(p),R.binding(alias),R.binding(p)])
            with patch.object(O,'frozen_source'),patch.object(R,'binding',wraps=R.binding) as check,patch.object(O,'check_pins',wraps=O.check_pins) as pins:
                s.recheck();s.recheck();self.assertEqual(check.call_count,4);self.assertEqual(pins.call_count,4)
    def test_flags_keep_demand_packages(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir();mirror=root/'mirror';mirror.mkdir();(mirror/'lib').mkdir()
            producer=root/'producer';manifest={'source_roots':['lib','absent']}
            original=O.original_flags(source,producer,manifest)
            result=C.profile_flags(original,source,producer,mirror,root/'profile-objects')
            self.assertIn('-prof',result);self.assertIn('-fpedantic-bottoms',result);self.assertIn('-fno-state-hack',result);self.assertIn('-O2',result)
            self.assertNotIn('-i'+str(source/'lib'),result);self.assertNotIn('-fprof-auto',result);self.assertNotIn('-fprof-late',result)
            self.assertEqual([result[i+1] for i,x in enumerate(result) if x=='-package'],O.PACKAGES)
    def test_one_shot_main_retains_common_interface_lookup(self):
        objects=Path('/build/common');main=Path('/build/emlf-main')
        flags=['-prof','-O2','-fpedantic-bottoms','-fno-state-hack','-osuf','p_o','-hisuf','p_hi','-odir',str(objects),'-hidir',str(objects)]
        result=C.main_profile_flags(flags,objects,main)
        self.assertEqual(result,['-prof','-O2','-fpedantic-bottoms','-fno-state-hack','-osuf','p_o','-hisuf','p_hi','-odir',str(main),'-hidir',str(objects),'-i'+str(objects),'-ohi',str(main/'Main.p_hi')])
        self.assertEqual(flags[-4:],['-odir',str(objects),'-hidir',str(objects)])
    def test_two_main_interfaces_remain_separate(self):
        objects=Path('/build/common');flags=['-odir',str(objects),'-hidir',str(objects)]
        outputs=[]
        for role in ['emlf','builtin-prelude']:
            result=C.main_profile_flags(flags,objects,Path('/build')/(role+'-main'))
            self.assertEqual(result[result.index('-hidir')+1],str(objects));outputs.append(result[-1])
        self.assertEqual(len(set(outputs)),2);self.assertNotIn(str(objects/'Main.p_hi'),outputs)
    def test_main_flag_foreign_interface_root_rejected(self):
        with self.assertRaises(ValueError):C.main_profile_flags(['-odir','/build/common','-hidir','/ordinary'],'/build/common','/build/main')
    def test_main_flag_ambiguous_overrides_rejected(self):
        flags=['-odir','/build/common','-hidir','/build/common']
        for extra in [['-hidir','/other'],['-ohi','/other/Main.p_hi']]:
            with self.subTest(extra=extra),self.assertRaises(ValueError):C.main_profile_flags(flags+extra,'/build/common','/build/main')
    def test_original_builtin_relative_metadata_is_not_a_file_pin(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'canonical.hs';source.write_text('canonical')
            receipt=root/'receipt.json';receipt.write_text('{}')
            rows=[]
            for label in ['check-candidate','fresh-literal']:
                out=root/(label+'.stdout');out.write_text('result')
                err=root/(label+'.stderr');err.write_text('')
                rows.append({'label':label,'stdout':O.pin(out),'stderr':O.pin(err)})
            verified={'complete':True,'immutable_inputs_verified_after':True,
                'inputs':{str(source):O.sha(source)},'commands':rows,
                'source_identity_inputs':{'modules':{'MLF.Entry.BuiltinPrelude':
                    {'path':'bootstrap/MLF/Entry/BuiltinPrelude.hs','sha256':O.sha(source)}}}}
            inputs,outputs=C.verified_builtin_pins(verified,receipt)
            self.assertEqual(inputs,{str(source):O.sha(source)})
            self.assertEqual(len(outputs),5)
            self.assertNotIn('bootstrap/MLF/Entry/BuiltinPrelude.hs',inputs)
            with self.assertRaises(ValueError):O.verify_pin(verified['source_identity_inputs']['modules']['MLF.Entry.BuiltinPrelude'])
    def test_builtin_absolute_input_map_still_rejects_relative(self):
        with tempfile.TemporaryDirectory() as d:
            receipt=Path(d)/'receipt.json';receipt.write_text('{}')
            with self.assertRaises(ValueError):C.verified_builtin_pins({'complete':True,'immutable_inputs_verified_after':True,'inputs':{'relative':'0'*64},'commands':[]},receipt)
    def test_exact_two_entry_roots(self):
        root=Path('/review/mirror')
        m={'union':{'MLF.Entry.Emlf':'bootstrap/MLF/Entry/Emlf.hs',
                    'MLF.Entry.BuiltinPrelude':'bootstrap/MLF/Entry/BuiltinPrelude.hs',
                    'Other.Module':'lib/Other/Module.hs'}}
        self.assertEqual(C.build_entry_roots(m,root),[root/'bootstrap/MLF/Entry/Emlf.hs',root/'bootstrap/MLF/Entry/BuiltinPrelude.hs'])
    def test_original_toolchain_environment_preserved_except_tmp(self):
        original={'PATH':'/tool/bin:/usr/bin','LD_LIBRARY_PATH':'/tool/lib','LIBRARY_PATH':'/tool/lib',
                  'CC':'/usr/bin/cc','TC':'/tool','PKG_CONFIG_PATH':'/tool/pkgconfig','TMPDIR':'/old/tmp'}
        expected=dict(original,TMPDIR='/work/tmp')
        C.validate_original_environment(expected,original,Path('/work'))
        for key in ['PATH','LD_LIBRARY_PATH','LIBRARY_PATH','CC','TC','PKG_CONFIG_PATH']:
            with self.subTest(key=key),self.assertRaises(ValueError):
                C.validate_original_environment(dict(expected,**{key:'changed'}),original,Path('/work'))
        with self.assertRaises(ValueError):C.validate_original_environment(original,original,Path('/work'))
    def test_fixed_budget_inventory(self):
        self.assertEqual(C.BUDGETS,{'BUILD':600,'QUALIFY':180,'PROBE-CONTROLS':420,'TARGET-QUALIFICATION':420,'ATTRIBUTION':240})
    def test_admission_pin_before_action(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'admission.json';p.write_text('{}')
            with self.assertRaises(ValueError):C.validate_admission(p,'0'*64,'BUILD')
    def test_unapproved_admission(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'admission.json';p.write_text(json.dumps({'schema':'sparse-scc-admission-v1','phase':'BUILD','approved':False}))
            with self.assertRaises(ValueError):C.validate_admission(p,O.sha(p),'BUILD')
    def test_no_automatic_continuation(self):
        with self.assertRaises(ValueError):C.validate_admission('/missing','0'*64,'BUILD-AND-RUN')
    def test_no_generated_admission_in_prepare_source(self):
        self.assertNotIn('approved=True',C.prepare.__doc__ or '')
    def test_source_frozen_real_reference(self):
        source=Path(os.environ.get('ASTRA_FROZEN_SOURCE',str(Path(__file__).resolve().parents[1]/'source')))
        if not source.exists():self.skipTest('frozen source not present on this reviewer')
        self.assertEqual(len(O.foundation(source,Path(__file__).with_name('foundation14-source.json'))),14)

if __name__=='__main__':unittest.main()
