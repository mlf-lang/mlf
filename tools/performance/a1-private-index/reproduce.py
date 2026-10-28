#!/usr/bin/env python3
"""Reproduce the frozen A1 experiment locally; never an acceptance/3x assertion.

The maintained producer builder is intentionally unchanged and Linux-only.
No native compiler bootstrap, target cache reuse, source rewriting or output
normalization is performed. See README.md before starting this long operation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tarfile

from helper import (Runner, SerialLock, authenticate, below, check_pins, env,
                    file_pins, host, load, module, regular, require, save, sha)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
FIXTURE_SHA256 = 'b23d7f0dc3482e86e58ba27f7484c48170732589662feca807db8ce2bc7106ba'
ORDER = [['GHC', 'P3', 'A1'], ['A1', 'GHC', 'P3'], ['P3', 'A1', 'GHC']]
PACKAGES = ['base', 'array', 'bytestring', 'text', 'containers', 'directory']
SUFFIXES = ['.mlfci', '.mlfco']
PROVIDERS = ['mlf-foundation', 'mlf-language-core', 'mlf-frontend', 'mlf-xmlf', 'mlf-inference', 'mlf-llvm']


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


def fixture_contract():
    manifest = regular(FIXTURES / 'manifest.json')
    require(sha(manifest) == FIXTURE_SHA256, 'published fixture contract changed')
    data = load(manifest)
    require(data['format'] == 'a1-private-index-fixtures-v1', 'fixture format')
    target = data['target']
    require(target['crate_id'] == 'mlf-crates/0.3.0/library' and len(target['modules']) == 14,
            'exact frozen 14-module target required')
    require(len(target['order']) == 14 and set(target['order']) == set(target['modules']), 'target order')
    require(target['inferred_groups'] == 544 and target['reused_groups'] == 0, '544 fresh / 0 reused required')
    require([p['name'] for p in data['providers']] == PROVIDERS, 'exact provider DAG order')
    require(sum(len(p['modules']) for p in data['providers']) == 54, 'exact 54 provider modules')
    require(len(data['target_dependencies']) == 6 and set(data['target_dependencies']) == set(PROVIDERS), 'six target providers')
    require(len(data['ghc']['modules']) == 70 and len(set(data['ghc']['target_modules'])) == 14 and
            set(data['ghc']['target_modules']) == set(target['modules']), 'exact GHC 70 = 56 + 14 closure')
    inputs = {str(manifest): sha(manifest)}
    def item(row):
        path = below(FIXTURES, row['path'])
        require(sha(path) == row['sha256'], 'fixture bytes changed: ' + row['path'])
        inputs[str(path)] = row['sha256']
        return path
    for rows in [target['modules'], data['ghc']['modules']]:
        for name, row in rows.items():
            path = item(row)
            match = re.search(r'^module\s+([A-Z][\w.]*)\b', path.read_text(), re.M)
            require(match and match.group(1) == name, 'fixture module identity: ' + name)
    prior = set()
    for provider in data['providers']:
        path = item(provider['manifest'])
        declaration = load(path)
        require(declaration['name'] == provider['name'] and declaration['version'] == provider['version'], 'provider identity')
        require(sorted(declaration.get('dependencies', {})) == provider['dependencies'], 'provider direct dependencies')
        require(set(provider['dependencies']) <= prior, 'provider order is not topological')
        require(set(declaration['library']['modules']) == set(provider['modules']), 'provider module inventory')
        for name, row in provider['modules'].items():
            source = item(row)
            require((path.parent / declaration['library']['modules'][name]).resolve() == source, 'provider source registration')
        prior.add(provider['name'])
    for root in data['ghc']['source_roots']:
        below(FIXTURES, root, directory=True)
    item(data['validator'])
    projection = load(item(data['query_group_projection']))
    require(len(projection) == 544 and all(set(row) == {'id', 'members'} for row in projection), 'fixed query projection')
    data['projection'] = projection
    require(len(inputs) == 81 and set(file_pins(FIXTURES)) == set(inputs), 'exact 81-file fixture inventory')
    inputs.update(file_pins(HERE))
    return data, inputs


def implementation(source, data, side):
    key = 'base' if side == 'P3' else 'candidate'
    expected = data['implementation_pins'][key]
    observed = dict(expected)
    for relative, digest in expected.items():
        actual = sha(below(source, relative))
        if sys.platform == 'darwin' and relative == 'tools/shared/build.py' and actual != digest:
            require(actual == sha(HERE.parents[2] / relative), side + ' platform builder patch mismatch')
            observed[relative] = actual
        else:
            require(actual == digest, side + ' implementation pin: ' + relative)
    builder = module(source / 'tools/shared/build.py', 'unaltered_static_builder_' + side)
    manifest = builder.load_manifest()
    require(len(manifest['modules']) == data['implementation_module_counts'][key], 'implementation closure count')
    # Every source selected by the official builder must be covered by the fixed
    # publication contract, not merely by a later self-generated receipt.
    for row in manifest['modules']:
        require(row['path'] in expected, 'unpinned registered shared source: ' + row['path'])
    for relative in manifest['host_only']:
        require(relative in expected, 'unpinned registered host source: ' + relative)
    return {str(below(source, relative)): digest for relative, digest in observed.items()}


def git_snapshot(repo, ref, destination, runner, output):
    commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}'],
                                     env=env(), text=True).strip()
    require(re.fullmatch(r'[0-9a-f]{40}', commit), 'resolved full git commit required')
    runner.run(['git', '-C', repo, 'archive', '--format=tar', commit], repo, output)
    require(not destination.exists(), 'fresh source snapshot required')
    destination.mkdir(parents=True)
    with tarfile.open(output / 'stdout', mode='r:') as archive:
        for entry in archive:
            relative = Path(entry.name)
            require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe git archive path')
            target = destination / relative
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                require(entry.isfile(), 'links/special files are not admitted from source archive')
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(entry) as source, target.open('wb') as out:
                    shutil.copyfileobj(source, out)
                target.chmod(entry.mode & 0o777)
    return commit


def compiled(output):
    text = (output / 'stdout').read_text() + (output / 'stderr').read_text()
    return [(name, Path(path.strip()).resolve()) for name, path in
            re.findall(r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)\s+\(\s*([^,\n]+),', text, re.M)]


def ghc_argv(ghc, objects, data):
    command = [ghc, '--make', '-no-link', '-j1', '-O2', '-XHaskell2010', '-package-env', '-',
               '-clear-package-db', '-global-package-db', '-no-user-package-db', '-hide-all-packages', '-i']
    command += ['-i' + str(below(FIXTURES, root, directory=True)) for root in data['ghc']['source_roots']]
    command += ['-odir', objects, '-hidir', objects]
    for package in PACKAGES:
        command += ['-package', package]
    command += [below(FIXTURES, data['target']['modules'][name]['path']) for name in data['target']['order']]
    return command


def crate_spec(path, identity, modules, dependencies, queries, builtin):
    require(not queries.exists(), 'target/setup query directory must initially be absent')
    entries = [pack([name, str(below(FIXTURES, row['path']))]) for name, row in sorted(modules.items())]
    fields = ['MLF-CRATE-1', identity, '', 'false', pack(entries),
              pack([str(value) for value in dependencies]), str(queries), str(builtin)]
    path.write_text(pack(fields))
    return fields


def artifacts(prefix):
    return {str(Path(str(prefix) + suffix)): sha(regular(str(prefix) + suffix)) for suffix in SUFFIXES}


def validate_query(path, data=None):
    report = load(path)
    require(report['format'] == 1 and report['reused_groups'] == 0, 'query cache reuse forbidden')
    groups = report['groups']
    require(report['inferred_groups'] == len(groups) and all(row['cached'] is False for row in groups), 'all groups freshly inferred')
    require(len({row['id'] for row in groups}) == len(groups), 'duplicate query group')
    require(all(re.fullmatch(r'[0-9a-f]{64}', row['query_key']) for row in groups), 'invalid actual query digest')
    if data:
        require(report['crate'] == data['target']['crate_id'] and report['inferred_groups'] == 544,
                'exact frozen target fresh-group count')
        observed = [{'id': row['id'], 'members': row['members']} for row in groups]
        require(observed == data['projection'], 'fixed 544 group id/member oracle changed')
    return report


def prepare_dependencies(work, source, producer, data, runner):
    base = work / 'dependencies'
    base.mkdir()
    builtin = base / 'builtin'
    require(all(not Path(str(builtin) + suffix).exists() for suffix in SUFFIXES), 'fresh builtin prefix required')
    prefixes = {name: base / name / 'unit' for name in PROVIDERS}
    record = {'complete': False, 'native_bootstrap': False, 'target_inference': False,
              'producer': str(producer), 'steps': [], 'artifacts': {}}
    receipt = base / 'receipt.json'
    save(receipt, record)
    try:
        for provider in data['providers']:
            name = provider['name']
            folder = base / name
            folder.mkdir()
            dependencies = [Path(str(prefixes[key]) + '.mlfci') for key in provider['dependencies']]
            require(all(path.is_file() for path in dependencies), 'provider dependency not yet materialized')
            spec, queries, prefix = folder / 'crate.spec', folder / 'queries', prefixes[name]
            crate_spec(spec, name + '/' + provider['version'] + '/library', provider['modules'], dependencies, queries, builtin)
            command = [producer / 'bin/emlf', '--compile-crate', spec, '-o', prefix]
            run = runner.run(command, folder, folder / 'command')
            query = validate_query(Path(str(prefix) + '.queries'))
            require(query['inferred_groups'] > 0, 'empty provider inference')
            actual = artifacts(prefix)
            builtins = artifacts(builtin)
            require({suffix: builtins[str(builtin) + suffix] for suffix in SUFFIXES} == data['builtin_artifacts'],
                    'canonical builtin pair differs from frozen portable bytes')
            check_pins(record['artifacts'])
            record['artifacts'].update(actual)
            record['artifacts'].update(builtins)
            record['steps'].append({'name': name, 'module_count': len(provider['modules']),
                                    'command': run, 'queries': query, 'query_sha256': sha(str(prefix) + '.queries')})
            save(receipt, record)
            authenticate(producer, source)
        require(len(record['artifacts']) == 14, 'six provider pairs plus builtin pair required')
        record.update(complete=True, builtin_prefix=str(builtin),
                      provider_prefixes={name: str(value) for name, value in prefixes.items()},
                      target_dependencies=[str(prefixes[name]) + '.mlfci' for name in data['target_dependencies']])
    except BaseException as error:
        record['error'] = repr(error)
        raise
    finally:
        save(receipt, record)
    return record


def validate_dependencies(work, source, producer, data, dependencies, runner):
    original = authenticate(producer, source)
    folder = work / 'dependency-validation'
    folder.mkdir()
    objects = folder / 'objects'
    shutil.copytree(producer / 'objects', objects)
    for suffix in ['.hi', '.o']:
        (objects / ('Main' + suffix)).unlink(missing_ok=True)
    copied = file_pins(objects)
    entry = str(source / 'host/ghc/app/emlf/Main.hs')
    commands = [row['argv'] for row in original['commands'] if entry in row['argv']]
    require(len(commands) == 1, 'unique authenticated emlf link command')
    helper = below(FIXTURES, data['validator']['path'])
    binary = folder / 'validate-dependencies'
    replace = {str(producer / 'objects'): str(objects), str(producer / 'bin/emlf'): str(binary), entry: str(helper)}
    argv = [replace.get(token, token) for token in commands[0]]
    runner.run(argv, source, folder / 'build')
    require(compiled(folder / 'build') == [('Main', helper)], 'validator must compile only independent Main')
    check_pins(copied)
    require(set(file_pins(objects)) - set(copied) == {str(objects / ('Main' + x)) for x in ['.hi', '.o']},
            'validator altered implementation closure')
    runner.run([binary, *dependencies['target_dependencies']], source, folder / 'check-seven')
    require(load(folder / 'check-seven/stdout') == {'complete': True, 'checked_objects': 7, 'reused_objects': 0},
            'actual independent seven-object reload required')
    require((folder / 'check-seven/stderr').read_bytes() == b'', 'dependency validation stderr')
    negative = folder / 'negative'
    negative.mkdir()
    foundation = Path(dependencies['provider_prefixes']['mlf-foundation'])
    shutil.copy2(str(foundation) + '.mlfci', negative / 'invalid.mlfci')
    (negative / 'invalid.mlfco').write_text('not a crate\n')
    runner.run([binary, '--single-foundation-control', negative / 'invalid.mlfci'], source,
               folder / 'reject-invalid-object', expected_exit=1)
    failure = (folder / 'reject-invalid-object/stderr').read_text()
    require(failure.startswith('OBJECT_REJECTED: ') and str(negative / 'invalid.mlfco') in failure and
            (folder / 'reject-invalid-object/stdout').read_bytes() == b'', 'independent malformed-object rejection')
    check_pins(copied)
    check_pins(dependencies['artifacts'])
    authenticate(producer, source)
    result = {'complete': True, 'checked_objects': 7, 'reused_objects': 0,
              'independent_invalid_object_rejected': True, 'inputs': dependencies['artifacts'],
              'helper_sha256': sha(binary), 'no_target_inference': True, 'outputs': file_pins(folder)}
    save(folder / 'receipt.json', result)
    return result


def prepare_ghc(work, ghc, data, runner):
    folder = work / 'ghc-dependencies'
    folder.mkdir()
    objects = folder / 'objects'
    objects.mkdir()
    argv = ghc_argv(ghc, objects, data)
    runner.run(argv, folder, folder / 'compile')
    expected = {name: below(FIXTURES, row['path']) for name, row in data['ghc']['modules'].items()}
    rows = compiled(folder / 'compile')
    require(len(rows) == 70 and dict(rows) == expected, 'GHC setup exact 70-module source resolution')
    targets = set(data['target']['modules'])
    dependencies = set(expected) - targets
    require(len(dependencies) == 56, 'exact reusable GHC 56-module dependency closure')
    reusable = folder / 'reusable'
    reusable.mkdir()
    copied = {}
    for name in sorted(dependencies):
        for suffix in ['.hi', '.o']:
            relative = Path(name.replace('.', '/') + suffix)
            source, destination = objects / relative, reusable / relative
            regular(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied[str(relative)] = sha(destination)
    require(len(copied) == 112 and len(file_pins(reusable)) == 112, 'exact reusable interface/object pairs')
    result = {'complete': True, 'ghc': str(ghc), 'ghc_sha256': sha(ghc), 'plain_o2_no_link': True,
              'compiled_modules': rows and [name for name, _ in rows],
              'reusable_directory': str(reusable), 'reusable_dependency_files': copied,
              'target_objects_copied': 0, 'setup_target_objects_discarded_from_reuse': 14,
              'outputs': file_pins(folder / 'compile')}
    save(folder / 'receipt.json', result)
    return result


def verify_controls(path):
    value = load(path)
    require(value.get('complete') is True and value.get('all_controls_passed') is True and
            value.get('immutable_inputs_verified_after') is True, 'complete literal A1 controls required')
    require(value.get('session_groups_passed') == 6 and value.get('finite_trace_cases') == 28 and
            value.get('admission_controls_passed') is True and value.get('negative_cases_passed') == 4,
            'focused control inventory changed')
    require(value.get('admission_inventory') == {'hand_positive': 8, 'exact_error': 8, 'counter_demand': 3, 'local_ordering': 3},
            'exact finite admission controls required')
    require(len(value.get('file_cases', [])) == 9 and
            all(row.get('complete') is True for row in value['file_cases']), 'all nine file controls required')
    check_pins(value['inputs'])
    check_pins(value['outputs'])
    return value


def prepare(args, data, fixture_inputs):
    work, repo = args.work_dir.resolve(), args.source_checkout.resolve()
    require(not work.exists(), 'preparation requires a new work directory; failed runs are retained, not silently resumed')
    require(not work.is_relative_to(repo) and not repo.is_relative_to(work), 'work directory must be outside the source checkout')
    work.mkdir(parents=True)
    with SerialLock(work):
        runner = Runner(work, limits(args))
        record = {'format': 'a1-private-index-preparation-v1', 'complete': False, 'work_dir': str(work),
                  'host': host(), 'fixture_manifest_sha256': FIXTURE_SHA256,
                  'inputs': dict(fixture_inputs), 'sources': {}, 'producers': {}, 'refs': {},
                  'limits': limits(args), 'native_bootstrap': False, 'local_full_qualification': False,
                  'campaign_order': ORDER, 'target_modules': 14, 'fresh_groups': 544, 'reused_groups': 0}
        receipt = work / 'preparation.json'
        save(receipt, record)
        try:
            ghc = Path(shutil.which(str(args.ghc)) or str(args.ghc)).resolve(strict=True)
            cc = Path(shutil.which(str(args.cc)) or str(args.cc)).resolve(strict=True)
            require(subprocess.check_output([ghc, '--numeric-version'], text=True, env=env()).strip() == '9.14.1',
                    'ordinary GHC 9.14.1 only')
            for side, ref in [('P3', args.base_ref), ('A1', args.candidate_ref)]:
                source, producer = work / 'sources' / side, work / 'producers' / side
                commit = git_snapshot(repo, ref, source, runner, work / 'setup' / ('archive-' + side))
                record['refs'][side] = {'requested': ref, 'commit': commit}
                record['sources'][side], record['producers'][side] = str(source), str(producer)
                record['inputs'].update(implementation(source, data, side))
                check_pins(record['inputs'])
                if sys.platform == 'darwin':
                    builder = source / 'tools/shared/build.py'
                    adapter = HERE.parents[2] / 'tools/shared/build.py'
                    original = sha(builder)
                    shutil.copyfile(adapter, builder)
                    adapted = sha(builder)
                    record.setdefault('platform_patches', {})[side] = {
                        'file': str(builder), 'original_sha256': original, 'adapted_sha256': adapted,
                        'reason': 'Darwin Mach-O and dyld toolchain collection'}
                    record['inputs'][str(builder.resolve())] = adapted
                    record['inputs'][str(adapter.resolve())] = adapted
                    save(receipt, record)
                runner.run([sys.executable, '-B', source / 'tools/shared/build.py', '--ghc', ghc, '--cc', cc,
                            '--optimization', '2', '--build-dir', producer], source, work / 'setup' / ('producer-' + side))
                authenticate(producer, source)
                record['inputs'][str(producer / 'receipt.json')] = sha(producer / 'receipt.json')
                save(receipt, record)
            left, right = [authenticate(Path(record['producers'][side]), Path(record['sources'][side])) for side in ['P3','A1']]
            for field in ['ghc', 'cc', 'ghc_settings', 'toolchain', 'installed_dependencies']:
                require(left[field] == right[field], 'base/candidate toolchain mismatch: ' + field)
            source, producer = Path(record['sources']['P3']), Path(record['producers']['P3'])
            dependencies = prepare_dependencies(work, source, producer, data, runner)
            validate_dependencies(work, source, producer, data, dependencies, runner)
            prepare_ghc(work, ghc, data, runner)
            a1source, a1producer = Path(record['sources']['A1']), Path(record['producers']['A1'])
            controls_runner = a1source / 'tools/performance/a1-private-index/run_controls.py'
            require(sha(regular(controls_runner)) == sha(HERE / 'run_controls.py'),
                    'archived candidate controls runner differs from published runner')
            runner.run([sys.executable, '-B', controls_runner, '--source-root', a1source,
                        '--producer', a1producer, '--builtin-prefix', dependencies['builtin_prefix'],
                        '--output', work / 'focused-controls'], a1source, work / 'setup/focused-controls')
            verify_controls(work / 'focused-controls/receipt.json')
            for path in [work/'dependencies/receipt.json', work/'dependency-validation/receipt.json',
                         work/'ghc-dependencies/receipt.json', work/'focused-controls/receipt.json']:
                record['inputs'][str(path)] = sha(path)
            record['inputs'].update(dependencies['artifacts'])
            for side in ['P3', 'A1']:
                authenticate(Path(record['producers'][side]), Path(record['sources'][side]))
            check_pins(record['inputs'])
            record.update(complete=True, immutable_inputs_verified_after=True,
                          mandatory_preparation_controls_passed=True,
                          scope='official fresh local P3/A1 producers; literal focused controls; exact frozen dependency preparation; not complete compiler qualification')
        except BaseException as error:
            record['error'] = repr(error)
            raise
        finally:
            save(receipt, record)
        print('Preparation complete:', receipt, flush=True)
        print('SHA256:', sha(receipt), flush=True)
        return receipt


def verify_preparation(path, work, data):
    require(regular(path) == work / 'preparation.json', 'preparation receipt must belong to this exact work directory')
    record = load(path)
    require(record.get('format') == 'a1-private-index-preparation-v1' and record.get('complete') is True and
            record.get('immutable_inputs_verified_after') is True and record.get('mandatory_preparation_controls_passed') is True,
            'successful complete preparation required')
    require(record['work_dir'] == str(work) and record['fixture_manifest_sha256'] == FIXTURE_SHA256 and
            record['campaign_order'] == ORDER, 'preparation location/fixture/order mismatch')
    check_pins(record['inputs'])
    for side in ['P3', 'A1']:
        require(record['sources'][side] == str(work/'sources'/side) and
                record['producers'][side] == str(work/'producers'/side), 'unexpected prepared source/producer path')
        implementation(Path(record['sources'][side]), data, side)
        authenticate(Path(record['producers'][side]), Path(record['sources'][side]))
    dependencies = load(work/'dependencies/receipt.json')
    validation = load(work/'dependency-validation/receipt.json')
    ghc = load(work/'ghc-dependencies/receipt.json')
    require(dependencies['complete'] and len(dependencies['steps']) == 6 and len(dependencies['artifacts']) == 14,
            'complete shared provider setup required')
    require(validation['complete'] and validation['checked_objects'] == 7 and validation['reused_objects'] == 0 and
            validation['independent_invalid_object_rejected'], 'independent seven-object validator required')
    check_pins(dependencies['artifacts'])
    for step in dependencies['steps']:
        require(step['command']['complete'], 'incomplete provider command')
        check_pins(step['command']['logs'])
        prefix = dependencies['provider_prefixes'][step['name']]
        require(sha(prefix + '.queries') == step['query_sha256'], 'provider query report changed')
        validate_query(prefix + '.queries')
    check_pins(validation['inputs'])
    check_pins(validation['outputs'])
    require(ghc['complete'] and ghc['plain_o2_no_link'] and len(ghc['reusable_dependency_files']) == 112 and
            ghc['target_objects_copied'] == 0, 'exact GHC dependency preparation required')
    require(sha(ghc['ghc']) == ghc['ghc_sha256'], 'GHC binary changed')
    check_pins(ghc['outputs'])
    names = set(data['ghc']['modules']) - set(data['target']['modules'])
    require(set(ghc['reusable_dependency_files']) ==
            {name.replace('.', '/') + suffix for name in names for suffix in ['.hi', '.o']},
            'reusable GHC filenames must be exactly the 56 non-target modules')
    reusable = Path(ghc['reusable_directory'])
    require(reusable == work/'ghc-dependencies/reusable', 'unexpected reusable-object path')
    check_pins({str(reusable/rel): digest for rel, digest in ghc['reusable_dependency_files'].items()})
    require(set(file_pins(reusable)) == {str(reusable/rel) for rel in ghc['reusable_dependency_files']}, 'extra reusable object')
    verify_controls(work/'focused-controls/receipt.json')
    return record, dependencies, ghc


def campaign(args, preparation, data):
    work = args.work_dir.resolve()
    require(work.is_dir(), 'prepared work directory required')
    with SerialLock(work):
        prep, dependencies, ghc = verify_preparation(preparation, work, data)
        if args.preparation_sha256:
            require(sha(preparation) == args.preparation_sha256, 'preparation receipt hash differs')
        root = work/'campaign'
        require(not root.exists(), 'campaign must be fresh; failed/previous campaigns are never overwritten or favorably resampled')
        root.mkdir()
        runner = Runner(work, prep['limits'])
        record = {'format': 'a1-private-index-campaign-v1', 'complete': False, 'experimental': True,
                  'optimization_accepted': False, 'local_full_qualification': False, 'host': host(),
                  'preparation_receipt': str(preparation), 'preparation_sha256': sha(preparation),
                  'order': ORDER, 'order_predeclared_before_first_leg': True, 'legs': [],
                  'endpoint_asymmetry': 'plain GHC -O2 no-link objects versus all checked MLF/xMLF crate outputs',
                  'os_cache_flush': False, 'cloud_wall_comparison': False,
                  'artifact_policy': 'exact raw checked artifact bytes against this local P3, at common local dependency paths; no normalization'}
        receipt = root/'receipt.json'
        save(receipt, record)
        reference = None
        initial_affinity = sorted(os.sched_getaffinity(0)) if sys.platform != 'darwin' else None
        try:
            for round_number, sides in enumerate(ORDER, 1):
                for side in sides:
                    verify_preparation(preparation, work, data)
                    require(initial_affinity is None or sorted(os.sched_getaffinity(0)) == initial_affinity, 'CPU affinity changed during campaign')
                    folder = root/(str(round_number)+'-'+side)
                    folder.mkdir()
                    leg = {'round': round_number, 'side': side, 'complete': False, 'folder': str(folder)}
                    record['legs'].append(leg)
                    save(receipt, record)
                    if side == 'GHC':
                        objects = folder/'objects'
                        shutil.copytree(ghc['reusable_directory'], objects)
                        require(len(file_pins(objects)) == 112, 'GHC copy must contain dependencies only')
                        argv = ghc_argv(ghc['ghc'], objects, data)
                    else:
                        spec, queries = folder/'crate.spec', folder/'queries'
                        fields = crate_spec(spec, data['target']['crate_id'], data['target']['modules'],
                                            dependencies['target_dependencies'], queries, dependencies['builtin_prefix'])
                        save(folder/'spec-fields.json', fields)
                        require(not queries.exists(), 'timed target cache is not absent')
                        argv = [Path(prep['producers'][side])/'bin/emlf', '--compile-crate', spec, '-o', folder/'unit']
                        leg['target_cache_initially_absent'] = True
                    run = runner.run(argv, folder, folder/'command', timed=True)
                    leg['measurement'] = run
                    save(receipt, record)
                    if side == 'GHC':
                        rows = compiled(folder/'command')
                        expected = {name: below(FIXTURES, row['path']) for name,row in data['target']['modules'].items()}
                        require(len(rows) == 14 and dict(rows) == expected, 'timed GHC must rebuild exactly 14 targets, no dependencies')
                        check_pins({str(objects/rel): digest for rel,digest in ghc['reusable_dependency_files'].items()})
                        leg.update(compiled_modules=[name for name,_ in rows], reused_dependency_modules=56,
                                   output_artifacts={name:{suffix:sha(objects/(name.replace('.','/')+suffix))
                                                          for suffix in ['.hi','.o']} for name in expected})
                    else:
                        report = validate_query(folder/'unit.queries', data)
                        require(len(list((folder/'queries').glob('*.mlfq'))) == 544, 'exact 544 newly materialized query files')
                        current = {suffix: Path(str(folder/'unit')+suffix).read_bytes() for suffix in SUFFIXES}
                        if reference is None:
                            require(side == 'P3' and round_number == 1, 'local P3 must establish the reference')
                            reference = current
                        require(current == reference, 'raw checked artifact mismatch against local P3; stop, never normalize')
                        leg.update(query_report_sha256=sha(folder/'unit.queries'), inferred_groups=report['inferred_groups'],
                                   reused_groups=report['reused_groups'], exact_fixed_group_projection=True,
                                   output_artifacts={suffix:hashlib.sha256(value).hexdigest() for suffix,value in current.items()},
                                   byte_identical_to_local_P3=True)
                    verify_preparation(preparation, work, data)
                    leg.update(complete=True, immutable_inputs_verified_after=True)
                    save(receipt, record)
                    print('Round', round_number, side, 'compiler wall', format(run['wall_seconds'], '.6f'), 'seconds', flush=True)
            require(len(record['legs']) == 9 and all(leg['complete'] for leg in record['legs']), 'complete fixed nine-leg campaign')
            medians = {side: statistics.median(leg['measurement']['wall_seconds'] for leg in record['legs'] if leg['side']==side)
                       for side in ['GHC','P3','A1']}
            record.update(complete=True, median_compiler_wall_seconds=medians,
                          A1_improvement_over_P3_percent=100*(1-medians['A1']/medians['P3']),
                          A1_over_GHC_ratio=medians['A1']/medians['GHC'],
                          P3_over_GHC_ratio=medians['P3']/medians['GHC'],
                          five_percent_screen_met=medians['A1'] <= 0.95*medians['P3'],
                          three_x_slice_met=medians['A1'] <= 3*medians['GHC'],
                          caveat='Same-machine frozen-slice experiment only. Neither a screen nor this receipt accepts an optimization or establishes full/native/macOS qualification.')
        except BaseException as error:
            record['error'] = repr(error)
            raise
        finally:
            save(receipt, record)
        print(json.dumps({key: record[key] for key in ['complete','median_compiler_wall_seconds','A1_improvement_over_P3_percent','A1_over_GHC_ratio','optimization_accepted']}, indent=2))
        print('Raw receipts:', receipt, flush=True)


def limits(args):
    return {'process_tree_rss_bytes': args.rss_mib*1024**2,
            'address_space_per_process_bytes': args.address_space_mib*1024**2,
            'host_available_floor_bytes': args.host_available_mib*1024**2,
            'disk_free_floor_bytes': args.disk_free_mib*1024**2,
            'max_work_bytes': args.max_work_gib*1024**3, 'wall_seconds': args.command_timeout}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-checkout', type=Path, default=HERE.parents[2])
    parser.add_argument('--candidate-ref', default='HEAD')
    parser.add_argument('--base-ref', default='875e483de49655030c4ffba1995b60610a50273a')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--ghc', default='ghc')
    parser.add_argument('--cc', default='cc')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--run-campaign', action='store_true')
    parser.add_argument('--preparation-receipt', type=Path)
    parser.add_argument('--preparation-sha256')
    parser.add_argument('--rss-mib', type=int, default=5120)
    parser.add_argument('--address-space-mib', type=int, default=6144)
    parser.add_argument('--host-available-mib', type=int, default=3072)
    parser.add_argument('--disk-free-mib', type=int, default=4096)
    parser.add_argument('--max-work-gib', type=int, default=16)
    parser.add_argument('--command-timeout', type=int, default=21600)
    args = parser.parse_args()
    host()  # Fail closed before writes or builds on unsupported operating systems.
    require(all(value>0 for value in [args.rss_mib,args.address_space_mib,args.host_available_mib,
                                    args.disk_free_mib,args.max_work_gib,args.command_timeout]), 'positive resource limits required')
    if args.run_campaign:
        require(args.preparation_receipt is not None, '--run-campaign requires --preparation-receipt')
    else:
        require(args.preparation_receipt is None and args.preparation_sha256 is None,
                'preparation receipts belong only to --run-campaign; no producer/cache reuse during preparation')
    data, inputs = fixture_contract()
    if args.run_campaign:
        campaign(args, args.preparation_receipt.resolve(), data)
    else:
        receipt = prepare(args, data, inputs)
        if not args.prepare_only:
            campaign(args, receipt, data)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print('STOP:', error, file=sys.stderr)
        raise SystemExit(1)
