#!/usr/bin/env python3
"""Collect and independently read back genuine GHC-origin prerequisites.

Default only prints the proposed commands. --execute is an explicit, separate
allocation: it creates a new evidence directory and never resumes or overwrites.
No native-output execution, GHC/Clang invocation, old seed, network, or lock writer is used.
The compiler's four --compile-crate calls are real compilation, not native A/B
qualification. The two --locked plan calls per root are no-change lock
validation, never recorded as a successful `lock` invocation. Receipts bind raw
commands/output and files; they are integrity records, not signed attestations
or a complete OS-access audit. Filesystem/mock tests are not execution evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import types
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
KIND = 'ghc-native-prerequisites-v1'
PLAN_ROOTS = {'root': '.', 'tests': 'tests', 'testing-tools': 'testing/tools',
              'async': 'libraries/mlf-async', 'tests-shared': 'tests/shared',
              'async-fixtures': 'tests/async-package'}
FOUNDATIONS = ('mlf-foundation', 'mlf-async', 'mlf-language-core', 'mlf-frontend')
FOUNDATIONAL_DEPENDENCIES = {
    'mlf-foundation': (),
    'mlf-async': ('mlf-foundation',),
    'mlf-language-core': ('mlf-foundation',),
    'mlf-frontend': ('mlf-foundation', 'mlf-language-core'),
}
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
MIB = 1024 ** 2
AUTH_HELPERS = ('test_direct.py', 'verify_builtin_prelude.py', 'builtin_prelude_identity.py',
                'verify_prepared_libraries.py', 'native_install.py', 'pool_generated_strings.py')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(MIB), b''):
            h.update(data)
    return h.hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read(path):
    return json.loads(regular(path).read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + x)))


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink()
            and path.resolve(strict=True) == path and path.stat().st_nlink == 1,
            'noncanonical or hardlinked regular file: ' + str(path))
    return path


def canonical_dir(path):
    path = Path(path)
    require(path.is_absolute() and path.is_dir() and path.resolve(strict=True) == path,
            'noncanonical directory: ' + str(path))
    return path


def verified(path, digest):
    path = regular(path)
    require(isinstance(digest, str) and DIGEST.fullmatch(digest) and sha(path) == digest,
            'hash mismatch: ' + str(path))
    return path


def identity(path):
    path = regular(path)
    return {'path': str(path), 'sha256': sha(path)}


def relative_file(parent, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute()
            and str(Path(name)) == name and '..' not in Path(name).parts,
            'unsafe or aliased relative source path')
    path = regular(parent / name)
    require(path.is_relative_to(parent), 'source escapes package')
    return path


def module_name(path):
    # Source declarations, not file basename or claimed report count, define names.
    found = re.search(r'^\s*module\s+([A-Z][\w\'.]*(?:\.[A-Z][\w\']*)*)\b',
                      path.read_text(), re.MULTILINE)
    require(found is not None, 'missing module declaration: ' + str(path))
    return found.group(1)


def module_inventory(manifest):
    data = read(manifest)
    result, paths = {}, set()
    for name, relative in data.get('library', {}).get('modules', {}).items():
        path = relative_file(manifest.parent, relative)
        require(path not in paths and module_name(path) == name, 'aliased or wrongly named module')
        paths.add(path)
        result[name] = identity(path)
    return result


def foundational_inventory(root):
    root = canonical_dir(root)
    result, modules, paths = {}, set(), set()
    for name in FOUNDATIONS:
        manifest = regular(root / 'libraries' / name / 'mlf-package.json')
        data = read(manifest)
        require(data.get('format') == 1 and data.get('name') == name and data.get('version') == '0.3.0',
                'unexpected foundational package identity')
        require(data.get('dependencies', {}) == {
                    dep: {'path': '../' + dep} for dep in FOUNDATIONAL_DEPENDENCIES[name]},
                'unreviewed foundational dependency graph: ' + name)
        inventory = module_inventory(manifest)
        require(inventory and not modules.intersection(inventory), 'empty or duplicate module inventory')
        require(not paths.intersection(v['path'] for v in inventory.values()), 'duplicate source inventory')
        modules.update(inventory)
        paths.update(v['path'] for v in inventory.values())
        result[name + '/0.3.0/library'] = {'manifest': identity(manifest), 'modules': inventory}
    return result


def package_graph(root, manifest):
    """Rebuild the local manifest/source snapshot, independently of a saved plan."""
    done, active, names, inputs = {}, set(), {}, {}
    def visit(path):
        path = regular(path)
        require(path.is_relative_to(root) and path not in active, 'escaping or cyclic package dependency')
        if path in done:
            return
        data = read(path)
        name = data.get('name')
        require(data.get('format') == 1 and isinstance(name, str) and name not in names,
                'duplicate/invalid package identity')
        names[name] = path
        active.add(path)
        for depname, dep in sorted(data.get('dependencies', {}).items()):
            require(set(dep) == {'path'}, 'only reviewed offline local source dependencies supported')
            depdir = path.parent / dep['path']
            require(not Path(dep['path']).is_absolute() and
                    os.path.abspath(depdir) == str(depdir.resolve(strict=True)), 'aliased dependency path')
            child = regular(depdir.resolve(strict=True) / 'mlf-package.json')
            require(read(child).get('name') == depname, 'wrong dependency package name')
            visit(child)
        sources = {v['path']: v['sha256'] for v in module_inventory(path).values()}
        for section in ('executables', 'tests'):
            for target in data.get(section, {}).values():
                if 'main' not in target:
                    continue
                main = relative_file(path.parent, target['main'])
                sources[str(main)] = sha(main)
                target_paths = set()
                for name, rel in target.get('modules', {}).items():
                    p = relative_file(path.parent, rel)
                    require(p != main and p not in target_paths and module_name(p) == name,
                            'duplicate/aliased target module')
                    target_paths.add(p)
                    sources[str(p)] = sha(p)
        inputs[str(path)] = sha(path)
        inputs.update(sources)
        done[path] = {'name': data['name'], 'version': data['version'],
                      'path': os.path.relpath(path.parent, manifest.parent), 'manifest': sha(path),
                      'sources': {os.path.relpath(p, path.parent): digest for p, digest in sorted(sources.items())}}
        active.remove(path)
    visit(manifest)
    return {'format': 1, 'packages': list(done.values())}, inputs


def check_source_locks(root):
    """Fail before allocation on stale locks; this is NOT manager-run evidence."""
    inputs = {}
    for name, relative in PLAN_ROOTS.items():
        manifest = root / relative / 'mlf-package.json'
        snapshot, sources = package_graph(root, manifest)
        lock = regular(manifest.parent / 'mlf.lock')
        saved = read(lock)
        require(set(saved) == {'format', 'packages'} and saved.get('format') == 1
                and len(saved['packages']) == len(snapshot['packages'])
                and {r['name']: r for r in saved['packages']} == {r['name']: r for r in snapshot['packages']},
                'stale source lock requires review and a new checkpoint: ' + name)
        inputs.update(sources)
        inputs[str(lock)] = sha(lock)
    return inputs


def verify_plan(plan, root, manifest):
    expected, inputs = package_graph(root, manifest)
    require(set(plan) == {'format', 'packages', 'modules', 'crates', 'executables', 'tests'}
            and plan.get('format') == 1, 'invalid plan format')
    rows = plan.get('packages', [])
    require(len(rows) == len(expected['packages']) and
            {r['name']: r for r in rows} == {r['name']: r for r in expected['packages']},
            'plan package/source snapshot mismatch')
    lock = regular(manifest.parent / 'mlf.lock')
    saved = read(lock)
    require(set(saved) == {'format', 'packages'} and saved.get('format') == 1
            and len(saved['packages']) == len(rows)
            and {r['name']: r for r in saved['packages']} == {r['name']: r for r in rows},
            'stale lock or plan/lock mismatch')
    inputs[str(lock)] = sha(lock)
    data = read(manifest)
    # Package.Command emits Manifest.keys over the parsed manifest's objects.
    # Json.objectAt/items and Manifest.keys preserve declaration order. Rendering
    # sorts JSON object fields, but never these target-name arrays. Check the
    # exact ordered inventory, not sorted copies that hide missing/order errors.
    require(plan.get('executables') == list(data.get('executables', {})) and
            plan.get('tests') == list(data.get('tests', {})), 'plan target inventory mismatch')
    packages, all_modules, expected_crates = {}, set(), {}
    for row in rows:
        path = (manifest.parent / row['path']).resolve(strict=True) / 'mlf-package.json'
        packages[row['name']] = (path, read(path), module_inventory(path))
    def deps(data, selected):
        require(len(selected) == len(set(selected)) and set(selected) <= set(data.get('dependencies', {})),
                'invalid target dependency selection')
        return [name + '/' + packages[name][1]['version'] + '/library' for name in sorted(selected)
                if packages[name][2]]
    for name, (path, pkg, mods) in packages.items():
        require(not all_modules.intersection(mods), 'duplicate plan library module')
        all_modules.update(mods)
        if mods:
            crate = name + '/' + pkg['version'] + '/library'
            expected_crates[crate] = {'crate': crate, 'entry': '', 'modules': sorted(mods),
                                      'dependencies': deps(pkg, list(pkg.get('dependencies', {})))}
    for section, prefix in [('executables', 'target-'), ('tests', 'target-test-')]:
        for name, target in data.get(section, {}).items():
            if 'main' not in target:
                continue
            entry = module_name(relative_file(manifest.parent, target['main']))
            mods = [entry, *target.get('modules', {})]
            require(len(set(mods)) == len(mods) and not all_modules.intersection(mods), 'duplicate target module')
            dependencies = deps(data, target.get('dependencies', list(data.get('dependencies', {}))))
            if packages[data['name']][2]:
                dependencies.append(data['name'] + '/' + data['version'] + '/library')
            crate = data['name'] + '/' + data['version'] + '/' + prefix + name
            expected_crates[crate] = {'crate': crate, 'entry': entry, 'modules': sorted(mods), 'dependencies': dependencies}
    actual = plan.get('crates', [])
    require(len(actual) == len(expected_crates) and {r['crate']: r for r in actual} == expected_crates,
            'plan crate/module/dependency mismatch')
    modules = plan.get('modules', [])
    require(len(modules) == len(all_modules) and set(modules) == all_modules, 'plan module inventory mismatch')
    return inputs


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


def crate_spec(root, output, crate):
    manifest = root / 'libraries' / crate.split('/')[0] / 'mlf-package.json'
    data = read(manifest)
    directory = output / 'crates' / data['name']
    modules = module_inventory(manifest)
    dependencies = [output / 'crates' / name / 'unit.mlfci' for name in sorted(data.get('dependencies', {}))]
    require(set(data.get('dependencies', {})) <= set(FOUNDATIONS), 'unreviewed foundational dependency')
    fields = ['MLF-CRATE-1', crate, '', 'false',
              pack([pack([name, item['path']]) for name, item in sorted(modules.items())]),
              pack([str(p) for p in dependencies]), str(directory / 'queries'), str(directory / 'builtin/unit')]
    return pack(fields)


def plan_command(binding, output, name):
    manifest = Path(binding['source_root']) / PLAN_ROOTS[name] / 'mlf-package.json'
    return [binding['manager']['path'], '--manifest', str(manifest),
            '--build-dir', str(output / 'plans' / (name + '-work')),
            '--cache-dir', str(output / 'plans' / (name + '-cache')),
            '--compiler', binding['compiler']['path'], '--offline', '--locked', 'plan']


def crate_command(binding, output, crate):
    directory = output / 'crates' / crate.split('/')[0]
    return [binding['compiler']['path'], '--compile-crate', str(directory / 'crate.spec'), '-o', str(directory / 'unit')]


def limits(binding, phase):
    a = binding['allocation']
    return {'wall_seconds': a['plan_seconds'] if phase == 'plan' else a['crate_seconds'],
            'address_space_per_process': a['address_space_mib'] * MIB,
            'process_tree_rss_bytes': a['rss_mib'] * MIB, 'host_available_floor': 3 * 1024 ** 3,
            'disk_free_floor': a['disk_free_mib'] * MIB, 'max_output_bytes': a['output_mib'] * MIB,
            'workspace_allocated_bytes': a['workspace_mib'] * MIB}


def wrapper_command(binding, output, directory, argv, phase):
    a = binding['allocation']
    return [binding['python']['path'], '-B', binding['watchdog']['path'], '--output-root', str(output),
            '--workspace-root', binding['workspace_root'], '--workspace-limit-mib', str(a['workspace_mib']),
            '--seconds', str(limits(binding, phase)['wall_seconds']), '--address-space-mib', str(a['address_space_mib']),
            '--rss-mib', str(a['rss_mib']), '--max-output-mib', str(a['output_mib']),
            '--disk-free-mib', str(a['disk_free_mib']), str(directory), *argv]


def environment(output):
    return {'PATH': '/usr/bin:/bin', 'HOME': str(output / 'home'), 'TMPDIR': str(output / 'tmp'),
            'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}


def authentication_inputs(root):
    return {str(root / 'tools/shared' / name): sha(regular(root / 'tools/shared' / name)) for name in AUTH_HELPERS}


def load_supervisor(expected=None):
    """Reuse the reviewed same-checkout supervisor by pinned bytes and exact path.

    No named import, bytecode lookup, sys.path mutation or sys.modules registration
    occurs here. Only its resource/supervision APIs are used; source authentication
    continues through this collector's original-source helper chain.
    """
    path = regular(ROOT / 'tools/shared/bootstrap_ghc_native.py')
    expected = identity(path) if expected is None else expected
    require(expected['path'] == str(path), 'wrong supervisor path')
    verified(path, expected['sha256'])
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected['sha256'], 'supervisor changed before loading')
    module = types.ModuleType('prerequisite_resource_supervisor')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    require(module.ROOT == ROOT and module.PRODUCER_AUTH_HELPERS == AUTH_HELPERS,
            'supervisor root or helper inventory differs')
    verified(path, expected['sha256'])
    return module


def budget_arguments(binding):
    a = binding['allocation']
    # workspace_mib is already the usable cap below the global checkpoint reserve.
    return types.SimpleNamespace(window_seconds=a['total_seconds'], max_output_mib=a['output_mib'],
        rss_mib=a['rss_mib'], address_space_mib=a['address_space_mib'], disk_free_mib=a['disk_free_mib'],
        workspace_limit_mib=a['workspace_mib'] + 512, checkpoint_reserve_mib=512)


def check_binding(binding, producer_digest, root, output):
    require(binding['source_root'] == str(root) and binding['producer']['sha256'] == producer_digest,
            'wrong producer or source root')
    require(COMMIT.fullmatch(binding['source_checkpoint']) and COMMIT.fullmatch(binding['driver_checkpoint']),
            'missing exact source/driver checkpoint')
    for field in ('producer', 'compiler', 'manager', 'python', 'git', 'watchdog', 'collector', 'supervisor'):
        item = binding[field]
        verified(item['path'], item['sha256'])
    helpers = authentication_inputs(root)
    require(binding.get('authentication_helpers') == helpers, 'source authentication helper closure differs')
    producer = Path(binding['producer']['path'])
    require(binding['compiler']['path'] == str(producer.parent / 'bin/emlf') and
            binding['manager']['path'] == str(producer.parent / 'bin/mlfpkg'), 'wrong producer binaries')
    require(binding['collector'] == identity(Path(__file__).resolve()) and
            binding['watchdog'] == identity(Path(__file__).resolve().with_name('resource_watchdog.py')) and
            binding['supervisor'] == identity(ROOT / 'tools/shared/bootstrap_ghc_native.py') and
            binding['driver_root'] == str(ROOT), 'different collector/driver closure')
    require(binding['environment'] == environment(output), 'unexpected environment')
    a = binding['allocation']
    require(set(a) == {'plan_seconds', 'crate_seconds', 'total_seconds', 'address_space_mib', 'rss_mib',
                       'disk_free_mib', 'output_mib', 'workspace_mib'} and
            all(type(v) is int and v > 0 for v in a.values()), 'invalid resource allocation')
    require(a['disk_free_mib'] >= 8192 and a['workspace_mib'] <= 16384 - 512 and
            a['output_mib'] <= 256 and a['rss_mib'] <= 4096 and a['address_space_mib'] <= 8192,
            'unreviewed resource limits')
    require(output.is_relative_to(canonical_dir(binding['workspace_root'])) and
            not root.is_relative_to(output) and not producer.is_relative_to(output), 'unowned/overlapping evidence output')
    return {**helpers, **{item['path']: item['sha256'] for key, item in binding.items()
            if key in ('producer', 'compiler', 'manager', 'python', 'git', 'watchdog', 'collector', 'supervisor')}}


def verify_maps(value):
    tracked = {}
    for section in ('inputs', 'artifacts'):
        require(isinstance(value.get(section), dict) and value[section], 'missing evidence map: ' + section)
        for path, digest in value[section].items():
            verified(path, digest)
            require(path not in tracked or tracked[path] == digest, 'conflicting evidence map')
            tracked[path] = digest
    return tracked


def verify_command(row, binding, output, directory, argv, phase, tracked):
    expected_invocation = {'cwd': binding['source_root'], 'environment': binding['environment'],
                           'argv': argv, 'wrapper_argv': wrapper_command(binding, output, directory, argv, phase)}
    invocation = directory / 'invocation.json'
    bounded_path = directory / 'bounded-receipt.json'
    exit_path = directory / 'exit.json'
    for path in (invocation, bounded_path, exit_path, directory / 'build.log', directory / 'wrapper.log', directory / 'supervisor.json'):
        require(tracked.get(str(path)) == sha(regular(path)), 'raw command evidence missing from map')
    require(read(invocation) == expected_invocation and row['argv'] == argv and
            row['invocation'] == identity(invocation), 'command argv/cwd/environment changed')
    require(row['receipt'] == str(bounded_path) and row['receipt_sha256'] == sha(bounded_path),
            'bounded receipt binding changed')
    supervision = read(directory / 'supervisor.json')
    require(supervision.get('drained') is True and supervision.get('remaining') == [],
            'parent supervisor did not drain owned descendants')
    bounded = read(bounded_path)
    require(read(exit_path) == {'wrapper_exit': 0} and row.get('exit') == 0 and row.get('status') == 'passed',
            'failed command exit')
    require(bounded.get('final_owned_descendants') == [], 'bounded command left descendants or omitted teardown evidence')
    require(bounded.get('complete') is True and type(bounded.get('exit_code')) is int and bounded['exit_code'] == 0
            and bounded.get('reason') is None and bounded.get('command') == argv,
            'failed or altered bounded command')
    require(bounded.get('limits') == limits(binding, phase) and bounded.get('output_root') == str(output)
            and bounded.get('workspace_root') == binding['workspace_root'], 'resource limits/root mismatch')
    require(read(directory / 'wrapper.log') == {k: v for k, v in bounded.items() if k != 'samples'},
            'wrapper output differs from original bounded receipt')
    elapsed = bounded.get('elapsed_seconds')
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and
            0 <= elapsed < limits(binding, phase)['wall_seconds'] + 3, 'invalid bounded duration')
    samples = bounded.get('samples', [])
    require(samples, 'missing actual resource samples')
    previous = -1
    lim = limits(binding, phase)
    for sample in samples:
        for key in ('seconds', 'group_rss', 'host_available', 'disk_free', 'output_bytes', 'workspace_allocated_bytes'):
            require(type(sample.get(key)) in (int, float) and math.isfinite(sample[key]) and sample[key] >= 0,
                    'invalid resource sample')
        require(previous <= sample['seconds'] <= elapsed and sample['seconds'] < lim['wall_seconds']
                and sample['group_rss'] <= lim['process_tree_rss_bytes']
                and sample['host_available'] >= lim['host_available_floor']
                and sample['disk_free'] >= lim['disk_free_floor']
                and sample['output_bytes'] <= lim['max_output_bytes']
                and sample['workspace_allocated_bytes'] <= lim['workspace_allocated_bytes'], 'resource limit exceeded')
        previous = sample['seconds']
    require(type(bounded.get('process_group')) is int and bounded['process_group'] > 0, 'missing bounded process identity')
    require(bounded.get('peak_group_rss') == max(x['group_rss'] for x in samples), 'peak resource mismatch')
    return bounded


def authenticate_plans(folder, producer_digest, root=ROOT):
    folder, root = canonical_dir(folder), canonical_dir(root)
    output = folder.parent
    receipt_path = folder / 'receipt.json'
    value = read(receipt_path)
    require(value.get('kind') == KIND and value.get('complete') is True, 'unsupported/incomplete locked plans')
    binding = value['binding']
    required_inputs = check_binding(binding, producer_digest, root, output)
    tracked = verify_maps(value)
    actual_artifacts = files_under(folder)
    actual_artifacts.pop(str(receipt_path), None)
    require(value['artifacts'] == actual_artifacts, 'plan artifact tree differs from retained inventory')
    rows = value.get('roots', [])
    require(len(rows) == len(PLAN_ROOTS) and {r['name'] for r in rows} == set(PLAN_ROOTS), 'six unique locked roots required')
    for row in rows:
        name = row['name']
        manifest = regular(root / PLAN_ROOTS[name] / 'mlf-package.json')
        lock = regular(manifest.parent / 'mlf.lock')
        require(row['manifest'] == str(manifest) and row['manifest_sha256'] == sha(manifest)
                and row['before_lock'] == row['after_lock'] == sha(lock), 'wrong root or changed/stale lock')
        path = verified(folder / (name + '-plan.json'), row['plan_sha256'])
        require(tracked.get(str(path)) == sha(path), 'plan missing from raw evidence map')
        raw = path.read_bytes()
        plan = read(path)
        required_inputs.update(verify_plan(plan, root, manifest))
        for phase in ('lock-validation', 'plan'):
            command = row[phase]
            require(phase != 'lock-validation' or command.get('mode') == 'validate-no-change', 'not no-change lock validation')
            directory = folder / (name + '-' + phase)
            verify_command(command, binding, output, directory, plan_command(binding, output, name), 'plan', tracked)
            require((directory / 'build.log').read_bytes() == raw, 'raw plan/validation output mismatch')
    require(all(value['inputs'].get(p) == d for p, d in required_inputs.items()), 'plan source/tool input omitted')
    tracked[str(receipt_path)] = sha(receipt_path)
    return tracked


def authenticate_gate(path, digest, producer_digest, root=ROOT):
    path, root = verified(path, digest), canonical_dir(root)
    output = path.parent
    gate = read(path)
    require(gate.get('kind') == KIND and gate.get('status') == 'passed' and gate.get('complete') is True,
            'unsupported/incomplete foundational gate')
    binding = gate['binding']
    required_inputs = check_binding(binding, producer_digest, root, output)
    require(gate.get('producer_receipt_sha256') == producer_digest, 'wrong gate producer')
    inventory = foundational_inventory(root)
    require(gate.get('inventory') == inventory, 'foundational manifest/source inventory differs')
    # The frozen manifest DAG has exactly one dependency-free crate. The reviewed
    # withPreludeUsing/loadGraph source installs there and lets all consumers
    # inherit Prelude + MLF.Primitive through their loaded dependency closure.
    # This is a source/command/retained-bytes contract, not independent CI-field
    # decoding or a guarantee against self-consistent receipt repackaging.
    builtin_owner, = [name for name in FOUNDATIONS if not FOUNDATIONAL_DEPENDENCIES[name]]
    results, commands = gate.get('results', {}), gate.get('commands', [])
    require(set(results) == set(inventory) and len(commands) == len(inventory)
            and {c['crate'] for c in commands} == set(inventory), 'exact four cold crates required')
    tracked = verify_maps(gate)
    require(gate['artifacts'] == files_under(output / 'crates'), 'gate artifact tree differs from retained inventory')
    for crate, inv in inventory.items():
        for item in (inv['manifest'], *inv['modules'].values()):
            required_inputs[item['path']] = item['sha256']
        directory = output / 'crates' / crate.split('/')[0]
        spec = regular(directory / 'crate.spec')
        require(spec.read_text() == crate_spec(root, output, crate), 'crate spec/modules/dependencies/cache mismatch')
        required_inputs[str(spec)] = sha(spec)
        row = next(c for c in commands if c['crate'] == crate)
        verify_command(row, binding, output, directory, crate_command(binding, output, crate), 'crate', tracked)
        start = read(directory / 'cold-start.json')
        require(start == {'crate': crate, 'queries': [], 'builtin': [], 'outputs': []}, 'nonempty cold start')
        require(tracked.get(str(directory / 'cold-start.json')) == sha(directory / 'cold-start.json'), 'missing cold-start evidence')
        report_path = regular(directory / 'unit.queries')
        report = read(report_path)
        require(report.get('format') == 1 and report.get('crate') == crate and report.get('reused_groups') == 0,
                'wrong crate or warm-as-cold report')
        groups = report.get('groups', [])
        require(type(report.get('inferred_groups')) is int and report['inferred_groups'] == len(groups)
                and groups and isinstance(report.get('semantic_fingerprint'), str)
                and report['semantic_fingerprint'], 'invalid genuine query report')
        ids, members = set(), set()
        for group in groups:
            require(group.get('cached') is False and isinstance(group.get('id'), str) and group['id'] not in ids
                    and isinstance(group.get('query_key'), str) and group['query_key']
                    and isinstance(group.get('semantic_fingerprint'), str) and group['semantic_fingerprint'],
                    'reused or malformed query group')
            names = group.get('members', [])
            require(names and len(names) == len(set(names)) and not members.intersection(names), 'duplicate query members')
            ids.add(group['id']); members.update(names)
        expected_result = {'module_count': len(inv['modules']), 'reused_groups': 0,
                           'inferred_groups': report['inferred_groups'], 'report': identity(report_path)}
        require(results[crate] == expected_result, 'query report/result mismatch')
        for suffix in ('mlfci', 'mlfco', 'queries'):
            artifact = regular(directory / ('unit.' + suffix))
            require(artifact.stat().st_size > 0 and tracked.get(str(artifact)) == sha(artifact), 'missing crate output')
        builtin = canonical_dir(directory / 'builtin')
        expected_builtin = {'unit.mlfci', 'unit.mlfco', 'unit.lock'} if directory.name == builtin_owner else set()
        require({entry.name for entry in builtin.iterdir()} == expected_builtin,
                'unexpected builtin directory contents: ' + str(builtin))
        for name in expected_builtin:
            artifact = regular(builtin / name)
            require((name == 'unit.lock' or artifact.stat().st_size > 0)
                    and gate['artifacts'].get(str(artifact)) == sha(artifact), 'missing cold builtin output')
        # Retain every query-cache and emitted artifact byte, not merely a summary.
        for artifact in directory.rglob('*'):
            if artifact.is_file():
                require(tracked.get(str(regular(artifact))) == sha(artifact), 'unbound crate/cache artifact')
    require(all(gate['inputs'].get(p) == d for p, d in required_inputs.items()), 'gate source/tool/spec input omitted')
    return gate


def checkpoint(root, expected, git, env):
    require(COMMIT.fullmatch(expected or ''), 'exact reviewed checkpoint required')
    def query(*args):
        return subprocess.check_output([str(git), '-c', 'core.preloadIndex=false', '-c', 'index.threads=1',
                                        *args], cwd=root, env=env, text=True, timeout=15).strip()
    require(query('rev-parse', '--show-toplevel') == str(root) and query('rev-parse', 'HEAD') == expected
            and not query('status', '--porcelain', '--untracked-files=normal'), 'source/driver checkpoint is not exact and clean')


def authenticate_producer(path, root, expected_helpers=None):
    expected_helpers = authentication_inputs(root) if expected_helpers is None else expected_helpers
    require(authentication_inputs(root) == expected_helpers, 'source authentication helper closure differs before authentication')
    helper = regular(root / 'tools/shared/test_direct.py')
    module = types.ModuleType('ghc_prerequisite_direct_auth')
    module.__file__ = str(helper)
    # Load source bytes at their original absolute path, with no .pyc or
    # shared sys.modules state from the separate driver checkout.
    exec(compile(helper.read_bytes(), str(helper), 'exec'), module.__dict__)
    producer = module.authenticate_build(path, path.parent / 'bin', root=root)
    require(authentication_inputs(root) == expected_helpers, 'source authentication helper closure changed during authentication')
    require(producer['optimization'] == '2', 'authenticated GHC O2 producer required')
    return producer


def verify_prerequisites(*, gate_receipt, gate_sha256, plans_dir, plans_sha256,
                         producer_receipt, producer_sha256, source_root, source_checkpoint,
                         driver_root=None, driver_checkpoint=None):
    """Strict public driver boundary. Return all reauthenticated evidence hashes."""
    root = canonical_dir(source_root)
    producer_path = verified(producer_receipt, producer_sha256)
    plans = canonical_dir(plans_dir)
    verified(plans / 'receipt.json', plans_sha256)
    gate = authenticate_gate(gate_receipt, gate_sha256, producer_sha256, root)
    binding = gate['binding']
    require(binding == read(plans / 'receipt.json')['binding'] and plans.parent == Path(gate_receipt).parent,
            'gate/plans provenance or output roots differ')
    require(binding['source_checkpoint'] == source_checkpoint and binding['producer']['path'] == str(producer_path),
            'wrong checkpoint or producer receipt')
    if driver_root is not None:
        require(binding['driver_root'] == str(canonical_dir(driver_root)), 'wrong driver root')
    if driver_checkpoint is not None:
        require(binding['driver_checkpoint'] == driver_checkpoint, 'wrong driver checkpoint')
    checkpoint(root, source_checkpoint, binding['git']['path'], binding['environment'])
    checkpoint(ROOT, binding['driver_checkpoint'], binding['git']['path'], binding['environment'])
    authenticate_producer(producer_path, root, binding['authentication_helpers'])
    tracked = authenticate_plans(plans, producer_sha256, root)
    tracked.update(verify_maps(gate))
    tracked[str(Path(gate_receipt))] = gate_sha256
    output = Path(gate_receipt).parent
    require(not (output / 'failure.json').exists(), 'collection has retained failure evidence')
    admission = output / 'admission.json'
    require(read(admission) == binding, 'admission binding changed')
    seal_path = output / 'complete.json'
    seal = read(seal_path)
    elapsed = seal.get('elapsed_seconds')
    require(seal.get('kind') == KIND and seal.get('complete') is True
            and seal.get('gate') == identity(gate_receipt) and seal.get('plans') == identity(plans / 'receipt.json')
            and type(elapsed) in (int, float) and math.isfinite(elapsed)
            and 0 <= elapsed < binding['allocation']['total_seconds'], 'missing/invalid final collection seal')
    resource_path = output / 'driver-resources-final.json'
    resources = read(resource_path)
    require(resources.get('kind') == KIND and resources.get('complete') is True
            and resources.get('seal') == identity(seal_path), 'missing/invalid parent resource seal binding')
    observation = resources.get('observation', {})
    require(observation.get('failure') is None and observation.get('scope') == 'whole driver and observed descendants'
            and type(observation.get('samples')) is int and observation['samples'] > 0,
            'missing successful whole-collector resource observations')
    sample = observation.get('last_sample', {})
    allocation = binding['allocation']
    require(observation.get('checkpoint_reserve_mib') == 512
            and 0 < observation.get('driver_address_space_bytes', 0) <= allocation['address_space_mib'] * MIB,
            'collector address-space/reserve evidence differs')
    for key, maximum in [('seconds', allocation['total_seconds']),
                         ('process_tree_rss_bytes', allocation['rss_mib'] * MIB),
                         ('output_bytes', allocation['output_mib'] * MIB),
                         ('workspace_allocated_bytes', allocation['workspace_mib'] * MIB)]:
        value = sample.get(key)
        require(type(value) in (int, float) and math.isfinite(value) and 0 <= value
                and (value < maximum if key == 'seconds' else value <= maximum),
                'collector final resource overage: ' + key)
        if key != 'seconds':
            peak = observation.get('peaks', {}).get(key)
            require(type(peak) is int and value <= peak <= maximum, 'collector resource peak differs: ' + key)
    require(sample.get('host_available_bytes', 0) >= 3*1024**3
            and sample.get('disk_free_bytes', 0) >= allocation['disk_free_mib'] * MIB,
            'collector final host/disk floor violated')
    tracked[str(resource_path)] = sha(resource_path)
    tracked[str(admission)] = sha(admission)
    tracked[str(seal_path)] = sha(seal_path)
    return {'inputs': tracked}


def write_new(path, value):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')


def files_under(path):
    result = {}
    for file in sorted(path.rglob('*')):
        require(not file.is_symlink(), 'symlink in evidence tree')
        if file.is_file():
            result[str(regular(file))] = sha(file)
    return result


def managed_run(wrapper, *, cwd, env, stdout, timeout, teardown=None, supervisor=None):
    module = load_supervisor(supervisor)
    code = module.managed_run(wrapper, cwd, env, teardown=teardown, stdout=stdout, timeout=timeout)
    return types.SimpleNamespace(returncode=code)


def run_command(binding, output, directory, argv, phase):
    directory.mkdir(parents=True, exist_ok=True)
    wrapper = wrapper_command(binding, output, directory, argv, phase)
    invocation = {'cwd': binding['source_root'], 'environment': binding['environment'], 'argv': argv, 'wrapper_argv': wrapper}
    write_new(directory / 'invocation.json', invocation)
    teardown = {}
    try:
        with (directory / 'wrapper.log').open('xb') as log:
            result = managed_run(wrapper, cwd=binding['source_root'], env=binding['environment'], stdout=log,
                                 timeout=limits(binding, phase)['wall_seconds'] + 15, teardown=teardown,
                                 supervisor=binding['supervisor'])
    finally:
        write_new(directory / 'supervisor.json', teardown)
    require(teardown.get('drained') is True and teardown.get('remaining') == [], 'parent supervisor did not drain descendants')
    write_new(directory / 'exit.json', {'wrapper_exit': result.returncode})
    bounded = read(directory / 'bounded-receipt.json')
    require(result.returncode == 0 and bounded.get('complete') is True and bounded.get('exit_code') == 0,
            'bounded prerequisite command failed')
    return {'argv': argv, 'invocation': identity(directory / 'invocation.json'), 'exit': result.returncode,
            'receipt': str(directory / 'bounded-receipt.json'), 'receipt_sha256': sha(directory / 'bounded-receipt.json'),
            'status': 'passed'}


def collect(binding, output):
    """Execution entry, called only by explicit --execute; failure keeps raw evidence."""
    output.mkdir(parents=True, exist_ok=False)
    root = Path(binding['source_root'])
    start = time.monotonic()
    guard = None
    previous_handlers = {}
    alarm_owned = False
    failure_finalizing = False
    interruption_delivered = False
    def interrupted(signum, frame):
        nonlocal interruption_delivered
        # Cancellation is delivered once. Repeated/deferred signals must not
        # interrupt descendant teardown or corrupt the explicit failure record.
        if failure_finalizing or interruption_delivered:
            return
        interruption_delivered = True
        raise InterruptedError('prerequisite collection interrupted by signal ' + str(signum))
    def integrity(phase=None):
        guard.check()
        remaining = binding['allocation']['total_seconds'] - (time.monotonic() - start)
        require(remaining > (limits(binding, phase)['wall_seconds'] + 60 if phase else 0),
                'total collection window exhausted or insufficient for next bounded action')
        checkpoint(root, binding['source_checkpoint'], binding['git']['path'], binding['environment'])
        checkpoint(ROOT, binding['driver_checkpoint'], binding['git']['path'], binding['environment'])
        check_binding(binding, binding['producer']['sha256'], root, output)
        guard.check()
    try:
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'existing alarm conflicts with collector whole-window guard')
        for name in (signal.SIGTERM, signal.SIGALRM):
            previous_handlers[name] = signal.signal(name, interrupted)
        signal.setitimer(signal.ITIMER_REAL, binding['allocation']['total_seconds'])
        alarm_owned = True
        supervisor = load_supervisor(binding['supervisor'])
        guard = supervisor.DriverBudget(output, Path(binding['workspace_root']), budget_arguments(binding))
        guard.start()
        for name in ('home', 'tmp', 'plans', 'crates'):
            (output / name).mkdir()
        write_new(output / 'admission.json', binding)
        integrity()
        authenticate_producer(Path(binding['producer']['path']), root, binding['authentication_helpers'])
        inputs = check_binding(binding, binding['producer']['sha256'], root, output)
        inputs.update(check_source_locks(root))
        plans = {'kind': KIND, 'complete': True, 'binding': binding, 'inputs': dict(inputs), 'roots': []}
        for name, relative in PLAN_ROOTS.items():
            integrity('plan')
            manifest = regular(root / relative / 'mlf-package.json')
            lock = regular(manifest.parent / 'mlf.lock')
            before = sha(lock)
            row = {'name': name, 'manifest': str(manifest), 'manifest_sha256': sha(manifest), 'before_lock': before}
            for phase in ('lock-validation', 'plan'):
                integrity('plan')
                directory = output / 'plans' / (name + '-' + phase)
                row[phase] = run_command(binding, output, directory, plan_command(binding, output, name), 'plan')
                if phase == 'lock-validation':
                    row[phase]['mode'] = 'validate-no-change'
                require(sha(lock) == before, 'lock changed: stop for source review and new checkpoint')
                integrity()
            raw = (output / 'plans' / (name + '-plan') / 'build.log').read_bytes()
            with (output / 'plans' / (name + '-plan.json')).open('xb') as stream:
                stream.write(raw)
            row.update(after_lock=sha(lock), plan_sha256=sha(output / 'plans' / (name + '-plan.json')))
            plans['inputs'].update(verify_plan(read(output / 'plans' / (name + '-plan.json')), root, manifest))
            plans['roots'].append(row)
        plans['artifacts'] = files_under(output / 'plans')
        write_new(output / 'plans/receipt.json', plans)
        authenticate_plans(output / 'plans', binding['producer']['sha256'], root)
        inventory = foundational_inventory(root)
        gate = {'kind': KIND, 'complete': True, 'status': 'passed', 'binding': binding,
                'producer_receipt_sha256': binding['producer']['sha256'], 'inventory': inventory,
                'inputs': dict(inputs), 'results': {}, 'commands': []}
        for crate, inv in inventory.items():
            integrity('crate')
            directory = output / 'crates' / crate.split('/')[0]
            directory.mkdir()
            (directory / 'queries').mkdir(); (directory / 'builtin').mkdir()
            write_new(directory / 'cold-start.json', {'crate': crate, 'queries': [], 'builtin': [], 'outputs': []})
            with (directory / 'crate.spec').open('x') as stream:
                stream.write(crate_spec(root, output, crate))
            gate['inputs'][str(directory / 'crate.spec')] = sha(directory / 'crate.spec')
            for item in (inv['manifest'], *inv['modules'].values()):
                gate['inputs'][item['path']] = item['sha256']
            command = run_command(binding, output, directory, crate_command(binding, output, crate), 'crate')
            command['crate'] = crate
            gate['commands'].append(command)
            report = read(directory / 'unit.queries')
            gate['results'][crate] = {'module_count': len(inv['modules']), 'reused_groups': report['reused_groups'],
                                      'inferred_groups': report['inferred_groups'], 'report': identity(directory / 'unit.queries')}
            integrity()
        gate['artifacts'] = files_under(output / 'crates')
        write_new(output / 'gate.json', gate)
        authenticate_gate(output / 'gate.json', sha(output / 'gate.json'), binding['producer']['sha256'], root)
        authenticate_producer(Path(binding['producer']['path']), root, binding['authentication_helpers'])
        integrity()
        write_new(output / 'complete.json', {'kind': KIND, 'complete': True, 'elapsed_seconds': time.monotonic() - start,
                                            'gate': identity(output / 'gate.json'), 'plans': identity(output / 'plans/receipt.json')})
        guard.check()  # Includes the final seal write, not just child commands.
        write_new(output / 'driver-resources-final.json', {'kind': KIND, 'complete': True,
                  'seal': identity(output / 'complete.json'), 'observation': guard.summary()})
        guard.check()  # Includes the resource record itself.
        verify_prerequisites(gate_receipt=output / 'gate.json', gate_sha256=sha(output / 'gate.json'),
            plans_dir=output / 'plans', plans_sha256=sha(output / 'plans/receipt.json'),
            producer_receipt=Path(binding['producer']['path']), producer_sha256=binding['producer']['sha256'],
            source_root=root, source_checkpoint=binding['source_checkpoint'],
            driver_root=ROOT, driver_checkpoint=binding['driver_checkpoint'])
        guard.check()
        guard.stop_monitor()
        guard.check()  # AS remains in force; no latent background failure may escape success.
        print(json.dumps({'collector_resource_observations': guard.summary()}, sort_keys=True))
    except BaseException as error:
        failure_finalizing = True
        if alarm_owned:
            signal.setitimer(signal.ITIMER_REAL, 0)
        stop_error = None
        if guard is not None:
            try:
                guard.stop_monitor()
            except BaseException as cleanup_error:
                stop_error = type(cleanup_error).__name__ + ': ' + str(cleanup_error)
        # Keep AS in force. The failure path cannot become successful even if
        # stopping the monitor failed; retain that separate cleanup error too.
        write_new(output / 'failure.json', {'kind': KIND, 'complete': False,
                  'error': type(error).__name__ + ': ' + str(error), 'elapsed_seconds': time.monotonic() - start,
                  'monitor_stop_error': stop_error,
                  'driver_resource': guard.summary() if guard is not None else None})
        raise
    finally:
        try:
            if guard is not None:
                guard.close()
        finally:
            if alarm_owned:
                signal.setitimer(signal.ITIMER_REAL, 0)
            for name, handler in previous_handlers.items():
                signal.signal(name, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'producer-receipt', 'output', 'workspace-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('source-checkpoint', 'driver-checkpoint', 'producer-sha256'):
        parser.add_argument('--' + name, required=True)
    for name in ('plan-seconds', 'crate-seconds', 'total-seconds', 'address-space-mib', 'rss-mib',
                 'disk-free-mib', 'output-mib', 'workspace-mib'):
        parser.add_argument('--' + name, type=int, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.absolute()
    require(output.resolve() == output and not output.exists(), 'output must be canonical and new')
    root = canonical_dir(args.source_root)
    producer = verified(args.producer_receipt, args.producer_sha256)
    binding = {'source_root': str(root), 'source_checkpoint': args.source_checkpoint,
               'driver_root': str(ROOT), 'driver_checkpoint': args.driver_checkpoint,
               'authentication_helpers': authentication_inputs(root),
               'producer': identity(producer), 'compiler': identity(producer.parent / 'bin/emlf'),
               'manager': identity(producer.parent / 'bin/mlfpkg'), 'collector': identity(Path(__file__).resolve()),
               'watchdog': identity(Path(__file__).resolve().with_name('resource_watchdog.py')),
               'supervisor': identity(ROOT / 'tools/shared/bootstrap_ghc_native.py'),
               'python': identity(Path(sys.executable).resolve(strict=True)),
               'git': identity(Path(shutil.which('git')).resolve(strict=True)),
               'workspace_root': str(canonical_dir(args.workspace_root)), 'environment': environment(output),
               'allocation': {name: getattr(args, name) for name in
                              ('plan_seconds', 'crate_seconds', 'total_seconds', 'address_space_mib', 'rss_mib',
                               'disk_free_mib', 'output_mib', 'workspace_mib')}}
    if args.execute:
        collect(binding, output)
    else:
        check_binding(binding, args.producer_sha256, root, output)
        checkpoint(root, args.source_checkpoint, binding['git']['path'], binding['environment'])
        checkpoint(ROOT, args.driver_checkpoint, binding['git']['path'], binding['environment'])
        authenticate_producer(producer, root, binding['authentication_helpers'])
        print(json.dumps({'kind': KIND, 'complete': False, 'execution_requested': False, 'binding': binding,
              'commands': [plan_command(binding, output, name) for name in PLAN_ROOTS for _ in range(2)] +
                          [crate_command(binding, output, crate) for crate in foundational_inventory(root)]}, indent=2))


if __name__ == '__main__':
    main()
