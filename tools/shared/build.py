#!/usr/bin/env python3
"""Build the committed shared implementation directly with the installed GHC.

No implementation source is emitted, preprocessed, copied or overlaid for
compilation. Fresh builtin literal stdout is verification evidence only.
The static manifest and Cabal package describe the same closed source set.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[2]
GHC_VERSION = '9.14.1'
DEMAND_FLAGS = ['-fpedantic-bottoms', '-fno-state-hack']
# Audit only the forced implementation closure, never source programs it compiles.
EXHAUSTIVENESS_FLAGS = ['-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns']
# Preserve all user arguments, including literal +RTS/-RTS sequences.
LINK_FLAGS = ['-rtsopts=ignoreAll']
PACKAGES = ['base', 'array', 'bytestring', 'text', 'containers', 'directory']
# Audited closed-corpus exceptions: datatype declarations and a pure re-export.
# All other owned modules must produce actual value-scheme dump evidence.
SIGNATURELESS_MODULES = {'Bootstrap.Types', 'Async.Task.Internal'}
BUILTIN_VERIFICATION_HELPERS = ('tools/shared/builtin_prelude_identity.py',
                                'tools/shared/verify_builtin_prelude.py')


def builtin_verifier():
    path = Path(__file__).resolve().with_name('verify_builtin_prelude.py')
    module = types.ModuleType('verify_builtin_prelude')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def identified(path):
    resolved = Path(path).resolve(strict=True)
    return {'path': str(resolved), 'sha256': sha(resolved)}


def executable(name):
    found = shutil.which(str(name))
    if not found:
        raise RuntimeError('required installed tool is missing: ' + str(name))
    return Path(found).resolve()


def load_manifest():
    manifest = json.loads((ROOT / 'shared-sources.json').read_text())
    if manifest['format'] != 1 or manifest['source_syntax'] != 'shared-haskell-v1':
        raise RuntimeError('unsupported shared source manifest')
    modules = manifest['modules']
    names, paths = set(), set()
    for item in modules:
        name, path = item['module'], Path(item['path'])
        if name in names or path in paths or path.is_absolute() or '..' in path.parts:
            raise RuntimeError('duplicate or invalid shared module: ' + str(item))
        names.add(name)
        paths.add(path)
        source = ROOT / path
        if not source.is_file() or source.suffix != '.hs':
            raise RuntimeError('missing raw shared implementation source: ' + str(path))
        text = source.read_text()
        if not text.startswith('-- mlf:syntax shared-haskell-v1\n'):
            raise RuntimeError('missing shared source marker: ' + str(path))
        declared = re.search(r'^module\s+([A-Z][\w.]*)\b', text, re.M)
        if not declared or declared.group(1) != name:
            raise RuntimeError('module identity mismatch: ' + str(path))
        if re.search(r'^\s*import\s+(?:qualified\s+)?MLF\.Host\.', text, re.M):
            raise RuntimeError('shared implementation imports host internals: ' + str(path))
        for forbidden in ['{-# OPTIONS_GHC', '{-# LANGUAGE CPP', '#include']:
            if forbidden in text:
                raise RuntimeError('source preprocessing is forbidden: ' + str(path))
    cabal = (ROOT / 'mlf-shared.cabal').read_text()
    exposed = re.search(r'^  exposed-modules: (.+)$', cabal, re.M)
    roots = re.search(r'^  hs-source-dirs: (.+)$', cabal, re.M)
    if not exposed or not roots:
        raise RuntimeError('missing static Cabal source inventory')
    cabal_names = [x.strip() for x in exposed.group(1).split(',')]
    if len(cabal_names) != len(set(cabal_names)) or set(cabal_names) != names | {'MLF.Host.IO'}:
        raise RuntimeError('Cabal/shared manifest module inventory disagrees')
    if set(x.strip() for x in roots.group(1).split(',')) != set(manifest['source_roots']):
        raise RuntimeError('Cabal/shared manifest source roots disagree')
    if set(re.findall(r'^executable (\S+)$', cabal, re.M)) != {x['name'] for x in manifest['executables']}:
        raise RuntimeError('Cabal/shared manifest executable inventory disagrees')
    # The static package and direct builder must select the same stable wrappers,
    # not merely happen to expose executables with the same names.
    source_roots = manifest['source_roots']
    if len(source_roots) != len(set(source_roots)) or any(
            Path(value).is_absolute() or '..' in Path(value).parts or not (ROOT / value).is_dir() for value in source_roots):
        raise RuntimeError('invalid or duplicate shared source root')
    if [x.strip() for x in roots.group(1).split(',')] != source_roots:
        raise RuntimeError('Cabal/shared source root order disagrees')
    executables = manifest['executables']
    executable_names = [item['name'] for item in executables]
    if len(executable_names) != len(set(executable_names)):
        raise RuntimeError('duplicate shared executable')
    if len(re.findall(r'^executable (\S+)$', cabal, re.M)) != len(executable_names):
        raise RuntimeError('duplicate Cabal executable')
    stanzas = dict(re.findall(r'^executable (\S+)\n(.*?)(?=^executable |\Z)', cabal, re.M | re.S))
    for item in executables:
        wrapper = Path(item['wrapper'])
        if item['module'] not in names or wrapper != Path('host/ghc/app') / item['name'] / 'Main.hs':
            raise RuntimeError('invalid stable shared executable: ' + item['name'])
        stanza = stanzas[item['name']]
        dirs = re.search(r'^  hs-source-dirs: (.+)$', stanza, re.M)
        main = re.search(r'^  main-is: (.+)$', stanza, re.M)
        if not dirs or not main or Path(dirs.group(1)) / main.group(1) != wrapper:
            raise RuntimeError('Cabal executable resolves a different wrapper: ' + item['name'])
        text = (ROOT / wrapper).read_text()
        if not re.search(r'^import qualified ' + re.escape(item['module']) + r' as Entry$', text, re.M) or not re.search(
                r'^main = runEntry Entry\.main$', text, re.M):
            raise RuntimeError('wrapper does not select the declared shared entry: ' + item['name'])
        if '-rtsopts=ignoreAll' not in stanza or any(flag not in stanza for flag in DEMAND_FLAGS):
            raise RuntimeError('Cabal executable is missing contract flags: ' + item['name'])
    host_files = {'host/ghc/MLF/Primitive.hs', 'host/ghc/MLF/Host/Base.hs', 'host/ghc/MLF/Host/IO.hs',
                  'host/ghc/MLF/Host/Async.hs', 'host/ghc/cbits/host.c', 'runtime/mlf_process_supervisor.c'}
    host_files.update(item['wrapper'] for item in executables)
    if len(manifest['host_only']) != len(set(manifest['host_only'])) or set(manifest['host_only']) != host_files:
        raise RuntimeError('shared host-only inventory disagrees with fixed adapters and wrappers')
    library = cabal.split('\nexecutable ', 1)[0]
    for field, expected in [('other-modules', {'MLF.Primitive', 'MLF.Host.Base', 'MLF.Host.Async'}),
                            ('c-sources', {'host/ghc/cbits/host.c', 'runtime/mlf_process_supervisor.c'})]:
        match = re.search(r'^  ' + field + r': (.+)$', library, re.M)
        if not match or {x.strip() for x in match.group(1).split(',')} != expected:
            raise RuntimeError('Cabal host inventory disagrees: ' + field)
    if any(flag not in library for flag in DEMAND_FLAGS):
        raise RuntimeError('Cabal library is missing demand-preserving flags')
    # Validate native module identities and source paths, including target-local
    # helper modules. Legacy guest fixtures remain outside the shared inventory.
    by_path = {(ROOT / item['path']).resolve(): item['module'] for item in modules}
    by_name = {item['module']: (ROOT / item['path']).resolve() for item in modules}
    native_paths, packages = set(), {}
    manifests = [*sorted(ROOT.glob('libraries/*/mlf-package.json')), ROOT / 'mlf-package.json',
                 ROOT / 'tests/mlf-package.json', ROOT / 'tests/shared/mlf-package.json', ROOT / 'testing/mlf-package.json', ROOT / 'testing/tools/mlf-package.json']
    for path in manifests:
        data = json.loads(path.read_text())
        packages[path.resolve()] = data
        maps = [data.get('library', {}).get('modules', {})]
        for target in data.get('executables', {}).values():
            maps.append(target.get('modules', {}))
            main = (path.parent / target['main']).resolve()
            if main.suffix == '.hs':
                if main not in by_path:
                    raise RuntimeError('native executable is outside shared inventory: ' + str(main))
                native_paths.add(main)
        for mapping in maps:
            for name, value in mapping.items():
                source = (path.parent / value).resolve()
                if source.suffix == '.hs':
                    if by_name.get(name) != source:
                        raise RuntimeError('native/shared module path disagrees: ' + name)
                    native_paths.add(source)
    if native_paths != set(by_path):
        raise RuntimeError('native/shared closed module inventories disagree')
    for item in executables:
        path = ROOT / ('tests/shared/mlf-package.json' if item.get('role') == 'direct-test' else 'mlf-package.json')
        target = packages[path.resolve()].get('executables', {}).get(item['name'])
        if target is None or (path.parent / target['main']).resolve() != by_name[item['module']]:
            raise RuntimeError('native/shared executable entry disagrees: ' + item['name'])
    def visible_modules(path, selected=None):
        # Match Package.Manifest.visible/visibleWith: imports can name this
        # package's library and selected DIRECT dependency libraries only.
        # Transitive packages participate in builds, not import visibility.
        data = packages[path]
        result = set(data.get('library', {}).get('modules', {}))
        for name, dependency in data.get('dependencies', {}).items():
            if selected is None or name in selected:
                child = (path.parent / dependency['path'] / 'mlf-package.json').resolve()
                if child not in packages:
                    raise RuntimeError('native shared dependency outside inventory: ' + str(child))
                result.update(packages[child].get('library', {}).get('modules', {}))
        return result
    for path, data in packages.items():
        own = data.get('library', {}).get('modules', {})
        checks = [(visible_modules(path), own)]
        for target in data.get('executables', {}).values():
            selected = target.get('dependencies', data.get('dependencies', {}))
            if len(selected) != len(set(selected)):
                raise RuntimeError('native target selects a duplicate dependency')
            if not set(selected).issubset(data.get('dependencies', {})):
                raise RuntimeError('native target selects an undeclared dependency')
            # The library was checked above against its own direct dependencies;
            # a target's narrower selection only constrains its private modules.
            local = dict(target.get('modules', {}))
            main = (path.parent / target['main']).resolve()
            if main in by_path:
                local[by_path[main]] = target['main']
            available = visible_modules(path, selected) | set(local)
            checks.append((available, local))
        for available, mapping in checks:
            for name, value in mapping.items():
                source = (path.parent / value).resolve()
                if source not in by_path:
                    continue
                imports = set(re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)', source.read_text(), re.M))
                missing = imports - available - {'MLF.Primitive'}
                if missing:
                    raise RuntimeError('native direct dependency visibility omits imports for ' + name + ': ' + ', '.join(sorted(missing)))
    return manifest


def package_inputs(dump, package_names):
    """Bind the transitive installed binary/interface closure, not just versions."""
    records = {}
    for block in re.split(r'\n---\s*\n', dump):
        fields, active = {}, None
        for line in block.splitlines():
            match = re.match(r'^([\w-]+):\s*(.*)$', line)
            if match:
                active = match.group(1)
                fields[active] = match.group(2)
            elif active and line[:1].isspace():
                fields[active] += ' ' + line.strip()
        if fields.get('id'):
            records[fields['id']] = fields
    pending = []
    for name in package_names:
        matches = [identifier for identifier, record in records.items() if record.get('name') == name]
        if len(matches) != 1:
            raise RuntimeError('expected one global installed package: ' + name)
        pending += matches
    selected, files = {}, {}
    while pending:
        identifier = pending.pop()
        if identifier in selected:
            continue
        record = records.get(identifier)
        if record is None:
            raise RuntimeError('missing transitive installed dependency: ' + identifier)
        selected[identifier] = record
        roots = shlex.split(record.get('pkgroot', ''))
        if len(roots) != 1:
            raise RuntimeError('missing installed package root: ' + identifier)
        record = {key: value.replace('${pkgroot}', roots[0]) for key, value in record.items()}
        pending += shlex.split(record.get('depends', ''))
        for directory in shlex.split(record.get('import-dirs', '')):
            path = Path(directory)
            if not path.is_dir():
                raise RuntimeError('missing package interface directory: ' + directory)
            for suffix in ['*.hi', '*.dyn_hi']:
                for file in path.rglob(suffix):
                    files[str(file.resolve())] = sha(file)
        directories = set(shlex.split(record.get('library-dirs', '')) + shlex.split(record.get('dynamic-library-dirs', '')))
        for directory in directories:
            if not Path(directory).is_dir():
                raise RuntimeError('missing package library directory: ' + directory)
        for library in shlex.split(record.get('hs-libraries', '')):
            found = set()
            for directory in directories:
                found.update(file.resolve() for file in Path(directory).glob('lib' + library + '*') if file.is_file())
            if not found:
                raise RuntimeError('missing installed package library: ' + library)
            for file in found:
                files[str(file)] = sha(file)
    if not files:
        raise RuntimeError('installed package closure has no binary/interface inputs')
    return {'packages': sorted(selected), 'files': files}


def toolchain_inputs(ghc, libdir, ghc_info, cc):
    # Official bindists expose a shell launcher. Bind its actual compiler and
    # package-tool binaries as well, plus their loaded shared-library closure.
    private_bin = libdir.parent / 'bin'
    actual_ghc = private_bin / ('ghc-' + GHC_VERSION)
    if not actual_ghc.is_file():
        raise RuntimeError('cannot identify actual GHC bindist executable: ' + str(actual_ghc))
    paths = {ghc.resolve(), cc.resolve(), actual_ghc.resolve()}
    paths.update(p.resolve() for p in private_bin.iterdir() if p.is_file())
    for key, command in re.findall(r'\("([^"\n]*command)","([^"\n]*)"\)', ghc_info):
        # This driver uses GHC's native code generator, never the optional LLVM/JS tools.
        if key.startswith(('LLVM ', 'JavaScript ')) or (sys.platform == 'darwin' and key == 'windres command'):
            continue
        words = shlex.split(command)
        if words and not words[0].startswith('$'):
            paths.add(executable(words[0]))
    # GCC invokes these private subprograms rather than the driver itself.
    for program in ['cc1', 'as', 'ld', 'collect2']:
        value = subprocess.check_output([cc, '-print-prog-name=' + program], text=True).strip()
        if value and Path(value).is_file():
            paths.add(Path(value).resolve())
        elif value and shutil.which(value):
            paths.add(executable(value))
    if sys.platform == 'darwin':
        return darwin_toolchain_inputs(paths, actual_ghc, libdir)
    if sys.platform != 'linux':
        raise RuntimeError('this qualified direct build driver currently records Linux toolchains only')
    for path in list(paths):
        # ldd is used only on the installed trusted compiler/toolchain binaries.
        with path.open('rb') as stream:
            is_elf = stream.read(4) == b'\x7fELF'
        if not is_elf:
            continue
        result = subprocess.run(['ldd', str(path)], capture_output=True, text=True)
        if result.returncode and 'not a dynamic executable' not in result.stderr + result.stdout:
            raise RuntimeError('cannot identify dynamic toolchain dependencies: ' + str(path))
        if 'not found' in result.stdout:
            raise RuntimeError('missing dynamic toolchain dependency: ' + str(path))
        for match in re.findall(r'(?:=>\s+|^\s*)(/[^\s]+)', result.stdout, re.M):
            paths.add(Path(match).resolve(strict=True))
    return {'actual_ghc': identified(actual_ghc), 'files': {str(path): sha(path) for path in sorted(paths)}}



def darwin_toolchain_inputs(initial_paths, actual_ghc, libdir):
    """Record the real Mach-O dependency closure and dyld shared-cache bytes."""
    sdk = Path(subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()).resolve(strict=True)
    cache_dir = Path('/System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld')
    cache_map = cache_dir / 'dyld_shared_cache_arm64e.map'
    if not cache_map.is_file():
        raise RuntimeError('cannot identify Darwin shared-cache map')
    cache_text = cache_map.read_text()
    caches = sorted(p for p in cache_dir.glob('dyld_shared_cache_arm64e*') if p.is_file())
    if not caches:
        raise RuntimeError('missing dyld shared-cache files')
    paths = set(initial_paths)
    for name in ['clang', 'ld', 'as', 'ar', 'ranlib', 'otool', 'install_name_tool']:
        value = subprocess.check_output(['xcrun', '--find', name], text=True).strip()
        paths.add(Path(value).resolve(strict=True))
    paths.add((sdk / 'SDKSettings.json').resolve(strict=True))
    paths.update(p.resolve() for p in caches)
    ghc_libraries = {}
    for root in [libdir, Path('/Library/Developer/CommandLineTools/usr/lib')]:
        for path in root.rglob('*.dylib'):
            ghc_libraries.setdefault(path.name, set()).add(path.resolve())
    pending = list(paths - set(caches)); visited = set(); system_names = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        kind = subprocess.check_output(['/usr/bin/file', '-b', str(path)], text=True)
        if 'Mach-O' not in kind:
            continue
        result = subprocess.run(['/usr/bin/otool', '-L', str(path)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('otool failed: ' + str(path))
        for line in result.stdout.splitlines():
            match = re.match(r'^\s+(\S+) \(compatibility version ', line)
            if not match:
                continue
            name = match.group(1)
            if name.startswith('/usr/lib/') or name.startswith('/System/Library/'):
                if name not in cache_text:
                    raise RuntimeError('system dylib absent from dyld cache map: ' + name)
                system_names.add(name)
                continue
            if name.startswith('@rpath/'):
                candidates = ghc_libraries.get(Path(name).name, set())
                if len(candidates) != 1:
                    raise RuntimeError('cannot uniquely resolve Mach-O dependency: ' + name)
                dependency = next(iter(candidates))
            elif name.startswith('@loader_path/'):
                dependency = (path.parent / name[len('@loader_path/'):]).resolve(strict=True)
            elif name.startswith('/'):
                dependency = Path(name).resolve(strict=True)
            else:
                raise RuntimeError('unsupported Mach-O dependency: ' + name)
            if dependency not in paths:
                paths.add(dependency)
                pending.append(dependency)
    return {'actual_ghc': identified(actual_ghc), 'files': {str(path): sha(path) for path in sorted(paths)},
            'platform_qualification': 'Darwin Mach-O and dyld cache; experimental',
            'sdk': str(sdk), 'system_dylibs': sorted(system_names)}


def audit_inferred_interfaces(log, inputs):
    """Inspect GHC's actual schemes for every owned module, under actual flags."""
    result = {}
    blocks = re.split(r'(?m)^\[\s*\d+ of \d+\] Compiling\s+', log)
    for block in blocks[1:]:
        name = block.split(None, 1)[0]
        if name not in inputs:
            continue
        marker = 'TYPE SIGNATURES\n'
        if 'Dependent modules:' not in block or not re.search(
                r'(?m)^!!! Renamer/typechecker \[' + re.escape(name) + r'\]: finished', block):
            raise RuntimeError('missing completed inferred-interface dump for ' + name)
        if marker not in block:
            if name not in SIGNATURELESS_MODULES:
                raise RuntimeError('missing value-scheme evidence for ' + name)
            signatures = ''
        else:
            signatures = block.split(marker, 1)[1]
            signatures = re.split(r'(?m)^(?:TYPE CONSTRUCTORS|DATA CONSTRUCTORS|CLASS INSTANCES|FAMILY INSTANCES|Dependent modules:|Dependent packages:|\*\*\*)', signatures, maxsplit=1)[0]
        if re.search(r'\b(?:Num|Fractional|IsString)\b', signatures):
            raise RuntimeError('unresolved host literal overloading in shared module ' + name)
        result[name] = {'sha256': hashlib.sha256(signatures.encode()).hexdigest(),
                        'signatures': signatures, 'unresolved_literal_constraints': False}
    if set(result) != set(inputs):
        raise RuntimeError('missing actual inferred-interface audit modules')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', default='ghc')
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    parser.add_argument('--optimization', choices=['0', '2'], default='0')
    parser.add_argument('--build-dir', type=Path, default=ROOT / '.mlf-build/shared-ghc')
    parser.add_argument('--typecheck-only', action='store_true')
    options = parser.parse_args()
    output = options.build_dir.resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise RuntimeError('build directory must not contain the source checkout')
    output.mkdir(parents=True, exist_ok=True)
    # A new attempt invalidates an earlier success before manifest/tool discovery.
    # Failure during any preflight must never leave a complete stale receipt.
    receipt_path = output / 'receipt.json'
    receipt_path.write_text(json.dumps({'format': 1, 'complete': False,
        'phase': 'preflight', 'started': time.time()}, indent=2) + '\n')
    manifest = load_manifest()
    (output / 'objects').mkdir(exist_ok=True)
    (output / 'bin').mkdir(exist_ok=True)
    ghc = executable(options.ghc)
    cc = executable(options.cc)
    version = subprocess.check_output([ghc, '--numeric-version'], text=True).strip()
    if version != GHC_VERSION:
        raise RuntimeError('qualified GHC version is ' + GHC_VERSION + '; found ' + version)
    package_tool = ghc.with_name('ghc-pkg')
    if not package_tool.exists():
        package_tool = executable('ghc-pkg')
    package_dump = subprocess.check_output([package_tool, 'dump', '--global', '--no-user-package-db'], text=True)
    (output / 'packages.txt').write_text(package_dump)
    installed_inputs = package_inputs(package_dump, PACKAGES)
    ghc_info = subprocess.check_output([ghc, '--info'], text=True)
    (output / 'ghc-info.txt').write_text(ghc_info)
    libdir = Path(subprocess.check_output([ghc, '--print-libdir'], text=True).strip())
    settings = libdir / 'settings'
    if not settings.is_file():
        raise RuntimeError('GHC toolchain settings file is missing')
    toolchain = toolchain_inputs(ghc, libdir, ghc_info, cc)
    inputs = {item['module']: {**item, **identified(ROOT / item['path'])} for item in manifest['modules']}
    configuration_paths = [ROOT / 'cabal.project', ROOT / 'mlf-shared.cabal', ROOT / 'shared-sources.json',
        *sorted(ROOT.glob('libraries/*/mlf-package.json')), ROOT / 'mlf-package.json',
        ROOT / 'tests/mlf-package.json', ROOT / 'tests/shared/mlf-package.json',
        ROOT / 'testing/mlf-package.json', ROOT / 'testing/tools/mlf-package.json']
    host_paths = [*sorted((ROOT / 'host/ghc').rglob('*.hs')), *sorted((ROOT / 'host/ghc').rglob('*.c')),
                  ROOT / 'runtime/mlf_process_supervisor.c', *sorted((ROOT / 'runtime').glob('*.h'))]
    receipt = {'format': 1, 'complete': False, 'implementation_language': 'MLF/shared-haskell-v1',
               'producer_host': 'GHC', 'source_syntax': manifest['source_syntax'],
               'orchestrator': {**identified(sys.executable), 'version': sys.version},
               'build_driver': identified(__file__), 'cabal_manifest': identified(ROOT / 'mlf-shared.cabal'),
               'primitive_abi': manifest['primitive_abi'], 'builtin_interface': manifest['builtin_interface'],
               'frontend_semantics': manifest['frontend_semantics'], 'ghc': {**identified(ghc), 'version': version},
               'cc': identified(cc), 'toolchain': toolchain, 'ghc_info_sha256': sha(output / 'ghc-info.txt'),
               'ghc_settings': identified(settings), 'installed_dependencies': installed_inputs,
               'package_database_sha256': sha(output / 'packages.txt'),
               'manifest_sha256': sha(ROOT / 'shared-sources.json'), 'optimization': options.optimization,
               'shared_inputs': inputs,
               'configuration_inputs': {str(p.relative_to(ROOT)): identified(p) for p in configuration_paths},
               'host_inputs': {str(p.relative_to(ROOT)): identified(p) for p in host_paths},
               'builtin_verification_helpers': {path: identified(ROOT / path) for path in BUILTIN_VERIFICATION_HELPERS},
               'builtin_verification': None,
               'commands': [], 'resolved_modules': {}, 'outputs': {}, 'typecheck_only': options.typecheck_only}

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    def run(args, label):
        args = list(map(str, args))
        log = output / (label + '.log')
        entry = {'argv': args, 'cwd': str(ROOT), 'log': str(log), 'started': time.time()}
        receipt['commands'].append(entry)
        save()
        print('+ ' + ' '.join(args), flush=True)
        with log.open('w') as stream:
            result = subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, 'GHC_ENVIRONMENT': '-'})
        entry.update(exit_code=result.returncode, seconds=time.time()-entry['started'], log_sha256=sha(log))
        save()
        if result.returncode:
            print(log.read_text()[-12000:], flush=True)
            raise RuntimeError(label + ' failed; full log: ' + str(log))
        return log.read_text()

    roots = [str((ROOT / value).resolve()) for value in manifest['source_roots']]
    flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
             '-no-user-package-db', '-hide-all-packages', '-O' + options.optimization,
             *DEMAND_FLAGS, '-i', *['-i' + root for root in roots],
             '-odir', output / 'objects', '-hidir', output / 'objects']
    for package in PACKAGES:
        flags.extend(['-package', package])
    receipt['flags'] = list(map(str, flags))
    mode = '-fno-code' if options.typecheck_only else '-no-link'
    log = run([ghc, '--make', '-j1', '-fforce-recomp', '-v', '-ddump-types', mode, *EXHAUSTIVENESS_FLAGS, *flags,
               *[ROOT / item['path'] for item in manifest['modules']]], 'shared-compile')
    # This comes from GHC's actual compilation progress, not just input hashing.
    # All units are forced above, so stale .hi files cannot supply this proof.
    expected_resolution = {name: Path(item['path']) for name, item in inputs.items()}
    expected_resolution.update({name: ROOT / path for name, path in {
        'MLF.Primitive': 'host/ghc/MLF/Primitive.hs',
        'MLF.Host.Base': 'host/ghc/MLF/Host/Base.hs',
        'MLF.Host.Async': 'host/ghc/MLF/Host/Async.hs',
        'MLF.Host.IO': 'host/ghc/MLF/Host/IO.hs'}.items()})
    seen = set()
    receipt['resolved_host_modules'] = {}
    for name, path in re.findall(r'Compiling\s+([\w.]+)\s+\(\s*([^,\n]+),', log):
        if name not in expected_resolution:
            raise RuntimeError('GHC compiled an unlisted source module: ' + name)
        if name in seen:
            raise RuntimeError('GHC compiled duplicate module identity: ' + name)
        seen.add(name)
        resolved = Path(path.strip())
        if not resolved.is_absolute():
            resolved = ROOT / resolved
        if resolved.resolve() != expected_resolution[name].resolve():
            raise RuntimeError('GHC resolved an overlay for ' + name + ': ' + str(resolved))
        key = 'resolved_modules' if name in inputs else 'resolved_host_modules'
        receipt[key][name] = identified(resolved)
    missing = set(expected_resolution) - seen
    if missing:
        raise RuntimeError('GHC log lacks direct-input provenance: ' + ', '.join(sorted(missing)))
    receipt['inferred_shared_interfaces'] = audit_inferred_interfaces(log, inputs)
    save()
    if not options.typecheck_only:
        c_objects = []
        for label, source in [('host', ROOT / 'host/ghc/cbits/host.c'), ('supervisor', ROOT / 'runtime/mlf_process_supervisor.c')]:
            obj = output / (label + '.o')
            run([cc, '-O2', '-std=c11', '-I' + str(ROOT / 'runtime'), '-c', source, '-o', obj], 'c-' + label)
            c_objects.append(obj)
        for item in manifest['executables']:
            # Each stable wrapper has a distinct Main object; shared interfaces
            # and objects are reused without compiling an alternate source tree.
            destination = output / 'bin' / item['name']
            for suffix in ['.o', '.hi']:
                (output / 'objects' / ('Main' + suffix)).unlink(missing_ok=True)
            run([ghc, '--make', '-j1', *flags, *LINK_FLAGS, ROOT / item['wrapper'], *c_objects, '-o', destination], 'link-' + item['name'])
            receipt['outputs'][item['name']] = identified(destination)
        emlf = output / 'bin/emlf'
        run([emlf, '--check-shared', *[ROOT / item['path'] for item in manifest['modules']]], 'shared-profile')
        identity = run([emlf, '--implementation-identity'], 'implementation-identity').strip()
        if identity != 'MLF/shared-haskell-v1 GHC':
            raise RuntimeError('unexpected implementation identity: ' + identity)
        receipt['implementation_identity'] = identity
        for item in receipt['builtin_verification_helpers'].values():
            if sha(item['path']) != item['sha256']:
                raise RuntimeError('builtin verification helper changed during build: ' + item['path'])
        # This gate only compares fresh generator stdout with the committed
        # literal. It never updates/recompiles source or trusts a previous run.
        verifier = builtin_verifier()
        verification = verifier.verify(ROOT, output / 'bin/emlf',
            output / 'bin/builtin-prelude', output / 'builtin-verification')
        receipt['builtin_verification'] = identified(verification)
        save()
    if sha(ROOT / 'shared-sources.json') != receipt['manifest_sha256']:
        raise RuntimeError('shared manifest changed during build')
    for item in inputs.values():
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('shared source changed during build: ' + item['path'])
    for item in receipt['configuration_inputs'].values():
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('build configuration changed during build: ' + item['path'])
    for item in receipt['host_inputs'].values():
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('host source changed during build: ' + item['path'])
    for item in receipt['builtin_verification_helpers'].values():
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('builtin verification helper changed during build: ' + item['path'])
    for item in receipt['outputs'].values():
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('executable changed during build: ' + item['path'])
    for key in ['build_driver', 'cabal_manifest', 'orchestrator']:
        if sha(receipt[key]['path']) != receipt[key]['sha256']:
            raise RuntimeError(key + ' changed during build')
    for path, digest in toolchain['files'].items():
        if sha(path) != digest:
            raise RuntimeError('toolchain input changed during build: ' + path)
    for path, digest in installed_inputs['files'].items():
        if sha(path) != digest:
            raise RuntimeError('installed dependency changed during build: ' + path)
    if sha(settings) != receipt['ghc_settings']['sha256']:
        raise RuntimeError('GHC settings changed during build')
    receipt['object_inputs'] = {str(p.relative_to(output)): sha(p)
                              for p in sorted((output / 'objects').rglob('*')) if p.is_file()}
    if not options.typecheck_only:
        verifier.authenticate(receipt['builtin_verification'], ROOT,
            output / 'bin/emlf', output / 'bin/builtin-prelude')
    receipt['complete'] = True
    save()
    print(receipt_path)


if __name__ == '__main__':
    main()
