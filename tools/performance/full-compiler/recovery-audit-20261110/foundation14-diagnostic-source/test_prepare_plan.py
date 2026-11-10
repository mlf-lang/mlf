import importlib.util
import tempfile
import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('prepare', Path(__file__).with_name('prepare_plan.py'))
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


class Contracts(unittest.TestCase):
    def test_pack_preserves_empty_fields(self):
        self.assertEqual(P.pack(['MLF-CRATE-1', '', 'false']), '11:MLF-CRATE-10:5:false')

    def test_no_whitespace_or_rts_token_injection(self):
        for path in ['/tmp/a b', '/tmp/a\nb', '/tmp/"x"', '/tmp/a;-A64m', 'relative']:
            with self.assertRaises(ValueError):
                P.safe_absolute(path)

    def test_reject_parent(self):
        with self.assertRaises(ValueError):
            P.safe_absolute('/tmp/x/../y')

    def test_reject_symlink_and_dangling_stats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            link = root/'stats'; link.symlink_to(root/'missing')
            with self.assertRaises(ValueError):
                P.absent(link)
            with self.assertRaises(ValueError):
                P.safe_absolute(link)

    def test_reject_symlink_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'actual').mkdir(); (root/'link').symlink_to(root/'actual')
            with self.assertRaises(ValueError):
                P.safe_absolute(root/'link'/'future')

    def test_private_search_does_not_drop_demand_flags(self):
        source, producer, private = Path('/source'), Path('/producer'), Path('/private')
        original = P.flags(source, producer, {'source_roots':['bootstrap','host/ghc']})
        selected = P.private_flags(original, producer, private)
        self.assertEqual([x for x in selected if x.startswith('-i')], ['-i','-i/private'])
        self.assertIn('-fpedantic-bottoms', selected)
        self.assertIn('-fno-state-hack', selected)
        self.assertIn('-O2', selected)
        self.assertEqual(selected.count('/private'), 2)
        self.assertNotIn('/producer/objects', selected)
        self.assertNotIn('-i/source/bootstrap', selected)
        self.assertEqual(selected.count('-package'), 6)

    def test_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'value.json'; path.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError):
                P.load(path)


class SyntheticRecipeContracts(unittest.TestCase):
    """Mocks ONLY existing producer auth; no claim of authenticating a real build."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source'; self.source.mkdir()
        self.producer = self.root/'producer'; self.producer.mkdir()
        (self.producer/'objects').mkdir()
        self.manifest = {'source_roots':['bootstrap','host/ghc']}
        names = ['Shared.M'+str(i) for i in range(90)] + P.HOSTS
        objects = {}
        for name in [*names, 'Main']:
            for suffix in ['.o','.hi']:
                relative = 'objects/'+name.replace('.','/')+suffix
                path = self.producer/relative; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name+suffix); objects[relative] = P.sha(path)
        for name in ['host','supervisor']:
            (self.producer/(name+'.o')).write_text(name)
        self.auth = dict(flags=P.flags(self.source,self.producer,self.manifest),
                         prepared_verification={'kind':'empty'}, object_inputs=objects,
                         cc={'path':'/tools/cc'}, ghc={'path':'/tools/ghc'},
                         outputs={'emlf':{'path':str(self.producer/'bin/emlf'),'sha256':'f'*64}},commands=[])
        for label, relative in [('host','host/ghc/cbits/host.c'),('supervisor','runtime/mlf_process_supervisor.c')]:
            self.auth['commands'].append(dict(argv=['/tools/cc','-O2','-std=c11','-I'+str(self.source/'runtime'),
                      '-c',str(self.source/relative),'-o',str(self.producer/(label+'.o'))],cwd=str(self.source),exit_code=0))
        (self.producer/'receipt.json').write_text(json.dumps(self.auth))
        self.outer = self.root/'outer.json'
        self.outer.write_text(json.dumps(dict(complete=True,exit_code=0,reason=None)))
        self.result = dict(workspace=str(self.root/'future'),emlf_non_main_modules=names,
                           spec_recipes={label:dict(spec='/future/'+label+'/spec',prefix='/future/'+label+'/unit')
                                         for label in ['ordinary-Q','diagnostic-D']})
        self.helper = self.source/'tools/performance/a1-private-index/helper.py'
        realsha = P.sha
        self.sha_mock = patch.object(P, 'sha', side_effect=lambda path:P.HELPER if Path(path)==self.helper else realsha(path))
        self.module_mock = patch.object(P, 'module', return_value=SimpleNamespace(authenticate=lambda *args:self.auth))
        self.sha_mock.start(); self.addCleanup(self.sha_mock.stop)
        self.module_mock.start(); self.addCleanup(self.module_mock.stop)

    def run_recipe(self):
        P.authenticate_and_commands(self.result,self.manifest,self.source,self.producer,self.outer,P.sha(self.outer))

    def test_exact_thin_commands(self):
        self.run_recipe()
        commands=self.result['thin_setup_command_recipes']
        self.assertEqual(len(commands),4)
        self.assertEqual(len(self.result['selected_objects_and_interfaces']),188)
        self.assertIn('-c',commands[2]['argv'])
        link=commands[3]['argv']
        self.assertIn('-rtsopts=ignoreAll',link)
        self.assertEqual(len([x for x in link if x.endswith('.o')]),97)
        self.assertNotIn(str(self.producer/'objects/Main.o'),link)
        self.assertNotIn('--make',link)
        self.assertEqual(len([x for x in link if x.startswith('-with-rtsopts=')]),1)
        self.assertFalse(self.result['execution_eligible'])
        self.assertFalse(self.result['outer_command_binding_verified'])

    def test_missing_recorded_interface_rejected(self):
        del self.auth['object_inputs']['objects/Shared/M0.hi']
        with self.assertRaisesRegex(ValueError,'missing/unlisted'):
            self.run_recipe()

    def test_changed_object_rejected(self):
        (self.producer/'objects/Shared/M0.o').write_text('changed')
        with self.assertRaisesRegex(ValueError,'content changed'):
            self.run_recipe()

    def test_extra_profile_flag_rejected(self):
        self.auth['flags'].append('-prof')
        with self.assertRaisesRegex(ValueError,'exact original O2'):
            self.run_recipe()

    def test_changed_original_c_command_rejected(self):
        self.auth['commands'][0]['argv'][1] = '-O0'
        with self.assertRaisesRegex(ValueError,'exact original C'):
            self.run_recipe()


if __name__ == '__main__':
    unittest.main()
