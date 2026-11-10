#!/usr/bin/env python3
"""Separate foundation14 baseline GC recipe. Never launches any compiler.

Without --producer this only verifies frozen sources and emits an unadmitted
recipe. With a freshly completed producer and bound outer receipt, it also runs
the original read-only producer authentication and explicitly authenticates its
recorded object inventory. The resulting JSON is NOT execution admission.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import types

HERE = Path(__file__).resolve().parent
BASE = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
HELPER = '0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc'
DEPS = []
TARGET_DEPS = ['builtin']
COUNTS = {'mlf-foundation': (14, 173594, 475)}
FOUNDATION_ROWS = 'e85b2776812a28fafd4074b5c4823f26a76ad2e0137492964ade76450f68d7fa'
HOSTS = ['MLF.Primitive', 'MLF.Host.Base', 'MLF.Host.IO', 'MLF.Host.Async']
BUILTIN = 'mlf:builtin-shared-haskell-v1:13'
PACKAGES = ['base', 'array', 'bytestring', 'text', 'containers', 'directory']


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


def module(path, name):
    obj = types.ModuleType(name)
    obj.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), obj.__dict__)
    return obj


def safe_absolute(path):
    path = Path(path)
    # GHC tokenizes compiled-in RTS defaults. Do not introduce quoting rules.
    require(path.is_absolute() and re.fullmatch(r'/[A-Za-z0-9_./-]+', str(path)),
            'absolute ASCII path without spaces/quotes/control characters required')
    require('..' not in path.parts, 'parent path component forbidden')
    for parent in [path, *path.parents]:
        require(not parent.is_symlink(), 'symlink path component forbidden: ' + str(parent))
    return path


def absent(path):
    try:
        Path(path).lstat()
    except FileNotFoundError:
        return
    raise ValueError('path already exists, including symlink: ' + str(path))


def flags(source, producer, manifest):
    answer = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
              '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms',
              '-fno-state-hack', '-i', *['-i'+str(source/r) for r in manifest['source_roots']],
              '-odir', str(producer/'objects'), '-hidir', str(producer/'objects')]
    for package in PACKAGES:
        answer += ['-package', package]
    return answer


def private_flags(original, producer, directory):
    """Only search/output layout changes; all code-generation/package flags stay."""
    result = []
    for value in original:
        if value == '-i':
            result += ['-i', '-i'+str(directory)]
        elif value.startswith('-i'):
            continue
        elif value == str(producer/'objects'):
            result.append(str(directory))
        else:
            result.append(value)
    return result


def source_plan(source, work):
    require(subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == BASE,
            'exact original f9 checkout required')
    require(not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no']),
            'tracked source changes forbidden')
    frozen = module(source/'tools/performance/full-compiler/prepare_workload.py', 'freeze').freeze(source, BASE)
    require(frozen['module_count'] == 90 and frozen['source_bytes'] == 5233364, 'original emlf closure')
    manifest = load(source/'shared-sources.json')
    require(len(manifest['modules']) == 137 and len(manifest['executables']) == 13, 'complete normal producer inventory')
    by_name = {r['module']: r for r in frozen['modules']}
    slices = []
    for name in ['mlf-foundation']:
        path = source/'libraries'/name/'mlf-package.json'
        package = load(path)
        rows = [by_name[n] for n in sorted(package['library']['modules']) if n in by_name]
        for row in rows:
            require(Path(row['source']) == (path.parent/package['library']['modules'][row['module']]).resolve(),
                    'original package ownership')
        count, size, fresh = COUNTS[name]
        require(len(rows) == count and sum(r['bytes'] for r in rows) == size, 'exact dependency intersection')
        dependencies = sorted(package.get('dependencies', {}))
        require(set(dependencies).issubset(DEPS), 'unexpected dependency')
        slices.append(dict(name=name, identity='fresh-split/compiler90/'+name,
                           modules=rows, dependencies=dependencies, expected_fresh=fresh,
                           package_manifest=dict(path=str(path), sha256=sha(path))))
    require(sha(HERE/'reference/foundation14-source.json') == FOUNDATION_ROWS, 'frozen foundation source reference')
    template = load(HERE/'reference/foundation14-source.json')
    require([{k:r[k] for k in ['module','relative','sha256','bytes']} for r in slices[-1]['modules']] ==
            template, 'exact original foundation14 source hashes')
    names = [r['module'] for r in frozen['modules']] + HOSTS
    require(len(names) == len(set(names)) == 94 and 'Main' not in names, '94 unique non-Main modules')
    main = source/'host/ghc/app/emlf/Main.hs'
    require(main.read_bytes() == b'module Main where\nimport MLF.Host.IO (runEntry)\nimport qualified MLF.Entry.Emlf as Entry\nmain :: IO ()\nmain = runEntry Entry.main\n',
            'original emlf Main bytes')
    result = dict(format='baseline-gc-foundation14-static-plan-v1', execution_authorized=False,
                  target='foundation14', target_module_count=14, target_source_bytes=173594, target_fresh_groups=475,
                  compiler_started=False, source_commit=BASE, source=str(source), workspace=str(work),
                  producer_authentication='not supplied', full_source_closure=frozen,
                  full_producer_shared_modules=137, full_producer_host_modules=4,
                  main=dict(path=str(main), sha256=sha(main)),
                  emlf_non_main_modules=names, dependency_build_order=DEPS,
                  target_dependency_order=TARGET_DEPS, slices=slices,
                  limits=dict(setup_seconds=120, qualification_plus_diagnostic_seconds=420,
                              per_compile_seconds=180, full_endpoint_ceiling_seconds=600,
                              rss_bytes=5*1024**3, address_space_bytes=6*1024**3,
                              free_disk_floor_bytes=5*1024**3, host_memory_floor_bytes=3*1024**3,
                              output_cap_bytes=4*1024**3),
                  fresh_builtin_inside_setup=True, separate_four_library_prerequisites=False,
                  historical_artifact_hashes_accepted=False, new_oracle_required=True)
    # Specs are recipes only. No output/cache directories or specs are materialized.
    builtin = work/'thin-setup/builtin'
    prefixes = {'builtin': builtin, **{n:work/'dependencies'/n/'unit' for n in DEPS}}
    specs = {}
    for part in slices:
        labels = ['ordinary-Q', 'diagnostic-D']
        dependencies = [str(builtin)+'.mlfci', *[str(prefixes[n])+'.mlfci' for n in part['dependencies']]]
        for label in labels:
            folder = work/'execution'/label if label in ['ordinary-Q','diagnostic-D'] else work/'dependencies'/label
            fields = ['MLF-CRATE-1', part['identity'], '', 'false',
                      pack([pack([r['module'],r['source']]) for r in part['modules']]),
                      pack(dependencies), str(folder/'queries'), str(builtin)]
            specs[label] = dict(directory=str(folder), spec=str(folder/'crate.spec'), fields=fields,
                                packed=pack(fields), prefix=str(folder/'unit'),
                                dependency_identities={BUILTIN:str(builtin)+'.mlfci',
                                    **{'fresh-split/compiler90/'+n:str(prefixes[n])+'.mlfci' for n in part['dependencies']}})
    result['spec_recipes'] = specs
    result['builtin_prefix'] = str(builtin)
    return result, manifest


def authenticate_and_commands(result, manifest, source, producer, outer_path, outer_sha):
    require(sha(outer_path) == outer_sha, 'new producer outer receipt pin')
    outer = load(outer_path)
    require(outer.get('complete') is True and outer.get('exit_code') == 0 and outer.get('reason') is None,
            'successful current producer outer guard required')
    hp = source/'tools/performance/a1-private-index/helper.py'
    require(sha(hp) == HELPER, 'unchanged authentication helper')
    H = module(hp, 'original_authentication')
    auth = H.authenticate(producer, source)  # Original verifier, no relaxed schema.
    require(auth['flags'] == flags(source, producer, manifest), 'exact original O2 flags')
    require(auth['prepared_verification']['kind'] == 'empty', 'ordinary bootstrap producer required')
    expected = auth['object_inputs']
    require(isinstance(expected, dict) and expected, 'recorded producer object inventory required')
    actual = {str(p.relative_to(producer)) for p in (producer/'objects').rglob('*') if p.is_file()}
    require(set(expected) == actual, 'no missing/unlisted producer object/interface files')
    for name, digest in expected.items():
        path = producer/name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and name.startswith('objects/'), 'safe recorded object path')
        require(path.resolve() == path and not path.is_symlink() and sha(path) == digest, 'recorded object content changed')
    selected = []
    for name in result['emlf_non_main_modules']:
        for suffix in ['.o', '.hi']:
            relative = 'objects/'+name.replace('.', '/')+suffix
            require(relative in expected, 'closure object/interface missing: '+relative)
            selected.append(dict(module=name, suffix=suffix, path=str(producer/relative), sha256=expected[relative]))
    work = Path(result['workspace']); setup = work/'thin-setup'; interfaces = setup/'objects'
    stats = safe_absolute(work/'execution/diagnostic-stats.txt')
    absent(stats)
    require(not (setup/'used-once.json').exists(), 'diagnostic already claimed')
    private = private_flags(auth['flags'], producer, interfaces)
    commands = []
    for label, relative in [('host','host/ghc/cbits/host.c'), ('supervisor','runtime/mlf_process_supervisor.c')]:
        original = [auth['cc']['path'], '-O2', '-std=c11', '-I'+str(source/'runtime'),
                    '-c', str(source/relative), '-o', str(producer/(label+'.o'))]
        recorded = [r for r in auth['commands'] if r['argv'] == original]
        require(len(recorded) == 1 and recorded[0]['cwd'] == str(source) and recorded[0]['exit_code'] == 0,
                'exact original C compile command required')
        commands.append(dict(label='rebuild-'+label, argv=[*original[:-1], str(setup/(label+'.o'))],
                             cwd=str(source), byte_equality_required_with=original[-1],
                             current_unlisted_original_sha256=sha(original[-1]),
                             historical_authentication=False))
    commands.append(dict(label='compile-private-emlf-main', cwd=str(source),
                         argv=[auth['ghc']['path'], '-c', '-fforce-recomp', *private, str(setup/'Main.hs'), '-o', str(interfaces/'Main.o')]))
    commands.append(dict(label='link-one-use-diagnostic', cwd=str(source),
                         argv=[auth['ghc']['path'], *private, '-rtsopts=ignoreAll', '-with-rtsopts=-s'+str(stats),
                               str(interfaces/'Main.o'), *[r['path'] for r in selected if r['suffix']=='.o'],
                               str(setup/'host.o'), str(setup/'supervisor.o'), '-o', str(setup/'emlf-statistics')]))
    # Existing Main.o is inventory-hashed, but never copied or linked as emlf Main.
    result.update(producer_authentication='original verifier plus all recorded object_inputs checked',
                  producer=str(producer), producer_receipt_sha256=sha(producer/'receipt.json'),
                  producer_outer=dict(path=str(outer_path), sha256=outer_sha),
                  selected_objects_and_interfaces=selected, thin_setup_command_recipes=commands,
                  interface_copy_required=True, original_main_copy_required=True,
                  ordinary_binary=auth['outputs']['emlf'], statistics_path=str(stats),
                  statistics_binary=str(setup/'emlf-statistics'),
                  required_post_setup_checks=['exact rebuilt C bytes', 'all pre-input pins',
                      'copied Main and 94 interfaces', 'new binary/output pins', 'statistics path still absent'],
                  authentication_does_not_grant_execution=True,
                  outer_command_binding_verified=False, execution_eligible=False)
    for label in ['ordinary-Q', 'diagnostic-D']:
        row = result['spec_recipes'][label]
        binary = auth['outputs']['emlf']['path'] if label == 'ordinary-Q' else result['statistics_binary']
        row['compile_argv'] = [binary, '--compile-crate', row['spec'], '-o', row['prefix']]
        row['postcheck_argv'] = [auth['outputs']['emlf']['path'], '--show-crate', row['prefix']+'.mlfci']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--workspace', type=Path, required=True, help='new future cohort root; never created here')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--producer', type=Path)
    p.add_argument('--producer-outer', type=Path)
    p.add_argument('--producer-outer-sha256')
    a = p.parse_args()
    source = safe_absolute(a.source); work = safe_absolute(a.workspace)
    require(source.resolve() == source, 'canonical source path')
    absent(work); absent(a.output)
    result, manifest = source_plan(source, work)
    supplied = [a.producer is not None, a.producer_outer is not None, a.producer_outer_sha256 is not None]
    require(all(supplied) or not any(supplied), 'producer requires exact successful outer receipt and hash')
    if a.producer:
        authenticate_and_commands(result, manifest, source, safe_absolute(a.producer),
                                  a.producer_outer, a.producer_outer_sha256)
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    print(json.dumps(dict(plan=str(a.output), sha256=sha(a.output), execution_authorized=False,
                          producer_authentication=result['producer_authentication'])))


if __name__ == '__main__':
    main()
