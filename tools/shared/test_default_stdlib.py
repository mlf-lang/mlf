#!/usr/bin/env python3
"""Default-install dispatch preserves the public output and bootstrap boundary."""
import importlib.util
from pathlib import Path
import json
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('default_stdlib', HERE / 'default_stdlib.py')
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)

class Defaults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        manifest = self.root / 'libraries/mlf-foundation/mlf-package.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'library':{'modules':{'Ordinary':'Ordinary.hs','Another':'Another.hs'}}}))
        config = self.root / 'native.json'
        config.write_text('{}')
        self.options = types.SimpleNamespace(build_dir=self.root/'install',ghc='ghc',cc='cc',
                                             optimization='0',native_config=config,clang='clang')

    def test_full_inventory_dispatch_and_public_layout(self):
        with patch.object(D.subprocess,'run') as run:
            D.build(self.root,self.options)
        argv = run.call_args.args[0]
        self.assertIn('--standard-library',argv)
        self.assertNotIn('--module',argv)
        self.assertIn('--compiler-at-root',argv)
        self.assertEqual(argv[argv.index('--compiler-optimization')+1],'0')
        self.assertEqual(argv[argv.index('--lexical-root')+1],str(self.options.build_dir/'sources/libraries/mlf-foundation'))
        self.assertEqual(argv[argv.index('--output')+1],str(self.options.build_dir))

    def test_existing_install_not_overwritten(self):
        self.options.build_dir.mkdir()
        marker = self.options.build_dir/'receipt.json'
        marker.write_text('old evidence')
        with patch.object(D.subprocess,'run') as run, self.assertRaises(RuntimeError):
            D.build(self.root,self.options)
        run.assert_not_called()
        self.assertEqual(marker.read_text(),'old evidence')

    def test_discovered_config_is_present_for_child_and_removed_after(self):
        self.options.native_config = None
        config = {'clang':'/clang','runtime_flags':[],'link_args':['/gmp','/gc','-lm']}
        def child(argv,**kwargs):
            path=Path(argv[argv.index('--native-config')+1])
            self.assertEqual(json.loads(path.read_text()),config)
            self.saved=path
        with patch.object(D,'configuration',return_value=config),patch.object(D.subprocess,'run',side_effect=child):
            D.build(self.root,self.options)
        self.assertFalse(self.saved.exists())

    def test_optimization_defaults_follow_build_route(self):
        source=(HERE/'build.py').read_text()
        for route,expected in [([], '2'),(['--bootstrap-only'],'0'),(['--typecheck-only'],'0')]:
            for explicit in [None,'0','2']:
                module=types.ModuleType('builder');module.__file__=str(HERE/'build.py')
                exec(compile(source,str(HERE/'build.py'),'exec'),module.__dict__)
                argv=['build.py',*route,'--build-dir',str(self.root/'route-build')]
                if explicit is not None:
                    argv += ['--optimization',explicit]
                captured=[]
                original=module.argparse.ArgumentParser.parse_args
                def parse(parser,*args,**kwargs):
                    options=original(parser,*args,**kwargs);captured.append(options);return options
                with patch('sys.argv',argv),patch.object(module.argparse.ArgumentParser,'parse_args',parse),patch.object(module.types,'ModuleType',side_effect=RuntimeError('route reached')),patch.object(module,'prepared_verifier',side_effect=RuntimeError('route reached')):
                    with self.assertRaisesRegex(RuntimeError,'route reached'):
                        module.main()
                self.assertEqual(captured[0].optimization,explicit or expected)

    def test_containing_output_requires_owned_authentication_before_writes(self):
        source=(HERE/'build.py').read_text()
        module=types.ModuleType('builder');module.__file__=str(HERE/'build.py')
        exec(compile(source,str(HERE/'build.py'),'exec'),module.__dict__)
        output=self.root/'owned'; owned=output/'sources'; owned.mkdir(parents=True)
        marker=output/'receipt.json';marker.write_text('preserve')
        verifier=types.SimpleNamespace(verify=lambda root: {'kind':'empty'})
        with patch.object(module,'ROOT',owned),patch.object(module,'prepared_verifier',return_value=verifier),patch('sys.argv',['build.py','--bootstrap-only','--build-dir',str(output)]):
            with self.assertRaisesRegex(RuntimeError,'authenticated owned'):
                module.main()
        self.assertEqual(marker.read_text(),'preserve')
        verifier.verify=lambda root: {'kind':'prepared'}
        with patch.object(module,'ROOT',owned),patch.object(module,'prepared_verifier',return_value=verifier),patch.object(module,'load_manifest',side_effect=RuntimeError('normal gates reached')),patch('sys.argv',['build.py','--bootstrap-only','--build-dir',str(output)]):
            with self.assertRaisesRegex(RuntimeError,'normal gates reached'):
                module.main()
        self.assertFalse(json.loads(marker.read_text())['complete'])
        with patch.object(module,'ROOT',owned),patch('sys.argv',['build.py','--bootstrap-only','--build-dir',str(self.root)]):
            with self.assertRaisesRegex(RuntimeError,'must not contain'):
                module.main()

    def test_bootstrap_and_typecheck_do_not_dispatch(self):
        source=(HERE/'build.py').read_text()
        module=types.ModuleType('builder');module.__file__=str(HERE/'build.py')
        exec(compile(source,str(HERE/'build.py'),'exec'),module.__dict__)
        for flag in ['--bootstrap-only','--typecheck-only']:
            with self.subTest(flag=flag),patch('sys.argv',['build.py',flag,'--build-dir',str(self.root/flag)]),patch.object(module,'prepared_verifier',side_effect=RuntimeError('reached low-level gate')):
                with self.assertRaisesRegex(RuntimeError,'reached low-level gate'):
                    module.main()

if __name__=='__main__':
    unittest.main()
