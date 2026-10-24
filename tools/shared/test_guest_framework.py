#!/usr/bin/env python3
"""Actual MLF mixed-framework source checks, not full Build/native/unit qualification.

Compile foundation once, then the exact mixed framework manifest and small class
identity controls. No normal-build source translator or GHC guest-source shim.
Linux only: each compiler is supervised by resource_watchdog.py.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from test_direct import authenticate_build

ROOT = Path(__file__).resolve().parents[2]
WATCHDOG = ROOT / 'tools/shared/resource_watchdog.py'
STANDARD = '''module Standard where
import Prelude hiding (Monad, return, bind)
import MLF.Primitive (Monad, return, bind)
import Bootstrap.Types
import qualified Bootstrap.Std as S
main : Either String Int
main = do { x <- Right 1; Right x }
'''
LEGACY = '''module Legacy where
import Bootstrap.Types
import qualified Bootstrap.Std as S
main : Either String Int
main = do { x <- Right 1; Right x }
'''

def require(value, message):
    if not value:
        raise ValueError(message)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def remember_file(recorded, path):
    key, current = str(path), digest(path)
    require(key not in recorded or recorded[key] == current, 'previously recorded input changed: '+key)
    recorded[key] = current

def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)

def manifest_inputs(path, name, count, dependencies):
    manifest = json.loads(path.read_text())
    require(manifest.get('format') == 1 and manifest.get('name') == name, 'manifest identity changed')
    require(set(manifest.get('dependencies', {})) == set(dependencies), 'direct dependency inventory changed')
    for dep, expected in dependencies.items():
        require(manifest['dependencies'][dep] == {'path': expected}, 'dependency route changed: '+dep)
    modules = manifest.get('library', {}).get('modules', {})
    require(len(modules) == count, 'reviewed module inventory changed')
    result = []
    for module, relative in sorted(modules.items()):
        source = (path.parent / relative).resolve(strict=True)
        require(source.is_file() and source.is_relative_to(ROOT), 'source escapes repository')
        result.append((module, source))
    return manifest, result

def verify_run(resource, status, log):
    require(resource.get('reason') is None, 'resource failure, not a semantic result')
    require(resource.get('exit_code') == status, 'unexpected compiler status')
    require(resource.get('complete') is (status == 0), 'inconsistent resource receipt')
    if status != 0:
        require(status == 1 and 'Resolution:' in log and
                'no instance or given constraint for Monad (Bootstrap.Types.Either String)' in log,
                'negative control rejected for the wrong reason')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    producer_dir = receipt.parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'kind': 'actual-MLF-mixed-framework-source',
              'full_native_unit': False, 'full_manager_build': False,
              'native_or_llvm_output': False, 'commands': []}
    def save():
        (output/'receipt.json').write_text(json.dumps(record, indent=2)+'\n')
    saved_files = {}
    def remember(path):
        remember_file(saved_files, path)
    def authenticate():
        producer = authenticate_build(receipt, producer_dir/'bin')
        require(producer['optimization'] == '2', 'this bounded gate requires the O2 producer')
        for name, sha in producer['object_inputs'].items():
            path = (producer_dir/name).resolve(strict=True)
            require(path.is_relative_to(producer_dir) and digest(path) == sha, 'producer object changed: '+name)
        return producer
    try:
        producer = authenticate()
        compiler = producer_dir/'bin/emlf'
        foundation_path = ROOT/'libraries/mlf-foundation/mlf-package.json'
        framework_path = ROOT/'testing/mlf-package.json'
        foundation, foundation_modules = manifest_inputs(foundation_path, 'mlf-foundation', 12, {})
        framework, framework_modules = manifest_inputs(framework_path, 'mlf-test', 14,
                                                       {'mlf-foundation': '../libraries/mlf-foundation'})
        require(all(path.suffix == '.hs' for _, path in foundation_modules), 'foundation is not shared source')
        require(sum(path.suffix == '.hs' for _, path in framework_modules) == 7 and
                sum(path.suffix == '.emlf' for _, path in framework_modules) == 7,
                'mixed framework source boundary changed')
        inputs = [Path(__file__), WATCHDOG, ROOT/'tools/shared/test_direct.py', ROOT/'tools/shared/build.py',
                  foundation_path, framework_path, receipt, compiler,
                  *[path for _, path in foundation_modules+framework_modules]]
        before = {str(path): digest(path) for path in inputs}
        record.update(producer_receipt_sha256=digest(receipt), inputs=before,
                      library_modules={'foundation': 12, 'framework_shared': 7, 'framework_guest': 7},
                      producer_object_count=len(producer['object_inputs']))
        save()
        builtin = output/'foundation/builtin/unit'
        def compile_crate(label, identity, modules, dependencies, status=0):
            directory = output/label
            directory.mkdir()
            if label == 'foundation':
                (directory/'builtin').mkdir()
            (directory/'queries').mkdir()
            (directory/'artifact').mkdir()
            fields = ['MLF-CRATE-1', identity, '', 'false',
                      pack([pack([name, str(path)]) for name, path in sorted(modules)]),
                      pack([str(path) for path in dependencies]), str(directory/'queries'), str(builtin)]
            spec = directory/'crate.spec'
            spec.write_text(pack(fields))
            (directory/'spec-fields.json').write_text(json.dumps(fields, indent=2)+'\n')
            remember(spec)
            for path in dependencies:
                remember(path)
                remember(path.with_suffix('.mlfco'))
            command = [str(compiler), '--compile-crate', str(spec), '-o', str(directory/'artifact/unit')]
            row = {'label': label, 'command': command, 'expected_exit': status, 'complete': False}
            record['commands'].append(row)
            save()
            supervised = [sys.executable, str(WATCHDOG), '--seconds', '900', '--address-space-mib', '3072',
                          '--rss-mib', '1536', '--max-output-mib', '100', str(directory),
                          'nice', '-n', '19', 'ionice', '-c', '3', *command]
            result = subprocess.run(supervised, cwd=ROOT, capture_output=True)
            (directory/'supervisor.stdout').write_bytes(result.stdout)
            (directory/'supervisor.stderr').write_bytes(result.stderr)
            resource = json.loads((directory/'bounded-receipt.json').read_text())
            log = (directory/'build.log').read_text()
            verify_run(resource, status, log)
            require(result.returncode == (0 if status == 0 else 1), 'watchdog result mismatch')
            if status == 0:
                artifacts = {}
                for extension in ['mlfci', 'mlfco', 'queries']:
                    path = directory/'artifact'/('unit.'+extension)
                    require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0,
                            'missing checked artifact: '+extension)
                    remember(path)
                    artifacts[extension] = {'sha256': digest(path), 'bytes': path.stat().st_size}
                query = json.loads((directory/'artifact/unit.queries').read_text())
                require(query.get('format') == 1 and query.get('crate') == identity and
                        query.get('inferred_groups', 0) > 0 and query.get('reused_groups') == 0,
                        'unexpected fresh inference report')
                row.update(artifacts=artifacts, inferred_groups=query['inferred_groups'], reused_groups=0)
            else:
                require(not (directory/'artifact/unit.mlfci').exists() and
                        not (directory/'artifact/unit.mlfco').exists(), 'rejection published artifacts')
                row['expected_semantic_rejection'] = True
            row.update(complete=True, resource_receipt_sha256=digest(directory/'bounded-receipt.json'),
                       log_sha256=digest(directory/'build.log'))
            save()
            return directory/'artifact/unit.mlfci'
        foundation_interface = compile_crate('foundation', foundation['name']+'/'+foundation['version']+'/library',
                                             foundation_modules, [])
        for extension in ['mlfci', 'mlfco']:
            remember(builtin.with_suffix('.'+extension))
        compile_crate('framework', framework['name']+'/'+framework['version']+'/library',
                      framework_modules, [foundation_interface])
        fixtures = output/'fixtures'
        fixtures.mkdir()
        for label, module, source, status in [('standard-class', 'Standard', STANDARD, 0),
                                              ('legacy-class', 'Legacy', LEGACY, 1)]:
            path = fixtures/(module+'.emlf')
            path.write_text(source)
            remember(path)
            compile_crate(label, 'guest-class-control/'+label, [(module, path)], [foundation_interface], status)
        authenticate()
        require(before == {str(path): digest(path) for path in inputs}, 'source/tool inputs changed during gate')
        require(all(digest(path) == sha for path, sha in saved_files.items()), 'generated checked inputs or artifacts changed')
        record.update(complete=True, generated_files=saved_files, inputs_unchanged=True,
                      producer_reauthenticated=True, checked_artifacts_rehashed=True)
        save()
        print(json.dumps({'complete': True, 'commands': len(record['commands']),
                          'framework_modules': 14, 'full_native_unit': False}))
    except BaseException as error:
        record['error'] = type(error).__name__+': '+str(error)
        save()
        raise

if __name__ == '__main__':
    main()
