#!/usr/bin/env python3
"""Separate authenticated GHC -> native A -> native B route.

Default is authenticated dry-run. Never invokes the released-seed bridge.
Cold, separate caches only: this driver does not manufacture or seed artifacts.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import signal
import time
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ('emlf', 'mlfpkg')
PLAN_NAMES = {'root', 'tests', 'testing-tools', 'async', 'tests-shared', 'async-fixtures'}
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
spec = importlib.util.spec_from_file_location('direct_auth', ROOT / 'tools/shared/test_direct.py')
direct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(direct)
sha = direct.sha


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink()
            and path.resolve() == path, 'noncanonical regular file: ' + str(path))
    return path


def verified(path, digest):
    path = regular(path)
    require(bool(DIGEST.fullmatch(digest)) and sha(path) == digest, 'hash mismatch: ' + str(path))
    return path


def below(path, parent):
    path = Path(path)
    require(path.resolve().is_relative_to(parent.resolve()), 'path outside owned directory: ' + str(path))
    return path


def authenticate_gate(path, digest, producer_digest):
    gate = read(verified(path, digest))
    require(gate.get('status') == 'passed' and gate.get('producer_receipt_sha256') == producer_digest,
            'foundational gate is not passed for this producer')
    expected = {'mlf-foundation/0.3.0/library', 'mlf-async/0.3.0/library',
                'mlf-language-core/0.3.0/library', 'mlf-frontend/0.3.0/library'}
    require(set(gate.get('results', {})) == expected, 'incomplete foundational gate')
    require(sum(v['module_count'] for v in gate['results'].values()) == 31,
            'unexpected foundational module inventory')
    require(all(v.get('reused_groups') == 0 for v in gate['results'].values()), 'foundational gate is not cold')
    for section in ('inputs', 'artifacts'):
        require(bool(gate.get(section)), 'missing gate ' + section)
        for name, value in gate[section].items():
            verified(name, value)
    require(len(gate.get('commands', [])) == 4 and all(
        c.get('status') == 'passed' and c.get('resource', {}).get('complete') is True
        for c in gate['commands']), 'failed foundational command')
    return gate


def authenticate_plans(folder, producer_digest, root=ROOT):
    receipt = read(folder / 'receipt.json')
    require(receipt.get('complete') is True and receipt.get('producer_sha256') == producer_digest,
            'locked plans have a different/incomplete producer')
    rows = receipt.get('roots', [])
    require(len(rows) == 6 and {r['name'] for r in rows} == PLAN_NAMES, 'six locked roots required')
    tracked = {str(regular(folder / 'receipt.json')): sha(folder / 'receipt.json')}
    for row in rows:
        manifest = below(verified(row['manifest'], row['manifest_sha256']), root)
        lock = manifest.parent / 'mlf.lock'
        verified(lock, row['after_lock'])
        plan = verified(folder / (row['name'] + '-plan.json'), row['plan_sha256'])
        for path in (manifest, lock, plan):
            tracked[str(path)] = sha(path)
        for phase in ('lock', 'plan'):
            command = row[phase]
            require(command.get('exit') == 0, 'failed locked plan command')
            bounded_path = Path(command['receipt'])
            bounded = read(regular(bounded_path))
            require(bounded.get('complete') is True and bounded.get('exit_code') == 0,
                    'failed lock/plan bounded receipt')
            tracked[str(bounded_path)] = sha(bounded_path)
        for package in read(plan)['packages']:
            directory = below((manifest.parent / package['path']).resolve(), root)
            package_file = verified(directory / 'mlf-package.json', package['manifest'])
            tracked[str(package_file)] = sha(package_file)
            for relative, digest in package['sources'].items():
                source = below(directory / relative, directory)
                verified(source, digest)
                tracked[str(source)] = digest
    return tracked


def stamp(cache, row):
    key = row.get('key', '')
    require(bool(DIGEST.fullmatch(key)), 'invalid manager artifact key')
    directory = below(cache / key, cache)
    value = read(regular(directory / 'artifact.json'))
    require(value.get('key') == key and bool(value.get('files')), 'invalid artifact stamp')
    for name, digest in value['files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'unsafe artifact filename')
        verified(below(directory / name, directory), digest)
    return directory, value


def verify_stage(stage, cache, pair, helper, clang, runtime_inputs, expected_packages, expected_targets, pkg, expected_crates, source_root):
    report_file = regular(stage / 'build-report.json')
    report = read(report_file)
    require(report.get('complete') is True and report.get('implementation') == 'MLF', 'incomplete native stage')
    require(report.get('cache_directory') == str(cache) and report.get('packages') == {'format': 1, 'packages': expected_packages},
            'stage package snapshot/cache mismatch')
    tools = report.get('toolchain', {})
    require(tools.get('system') == 'Linux' and not tools.get('ir-flags') and 'windows' not in tools,
            'this reviewed driver supports only the current Linux non-PGO route')
    for label, path in [('compiler', pair / 'emlf'), ('manager', pair / 'mlfpkg'), ('clang', clang), ('pkg-config', pkg)]:
        actual = tools.get(label, {})
        require(actual.get('path') == str(path) and actual.get('sha256') == sha(path), 'wrong stage ' + label)
    require(tools.get('runtime') == runtime_inputs, 'stage runtime inventory differs')
    package_data = {}
    reviewed_sources = {}
    for package in expected_packages:
        directory = below((source_root / package['path']).resolve(), source_root)
        manifest = verified(directory / 'mlf-package.json', package['manifest'])
        data = read(manifest)
        package_data[package['name']] = (manifest, data)
        for name, digest in package['sources'].items():
            path = below(directory / name, directory).resolve(strict=True)
            verified(path, digest)
            reviewed_sources[str(path)] = (digest, package['name'])
    crate_plans = {c['crate']: c for c in expected_crates}
    schedulers = report.get('scheduler', [])
    require(bool(schedulers), 'missing actual scheduler evidence')
    for scheduler in schedulers:
        actual = scheduler.get('helper', {})
        require(actual.get('path') == str(helper) and actual.get('sha256') == sha(helper), 'wrong scheduler helper')
        verified(below(Path(scheduler['plan']), stage), scheduler['plan_digest'])
    require(len(report.get('scheduler_results', [])) == len(schedulers), 'missing scheduler outcomes')
    scheduler_evidence = {}
    worker_results = {}
    scheduled_jobs = {}
    merged_worker_rows = []
    for scheduler, outcome in zip(schedulers, report['scheduler_results']):
        directory = Path(scheduler['plan']).parent
        context_path = regular(directory / 'context.json')
        context = read(context_path)
        invocation = sha(context_path)
        require(context.get('tools') == tools and context.get('initial') == report['packages'], 'worker context inputs mismatch')
        config = context.get('config', {})
        require(config.get('cache-dir') == str(cache) and config.get('build-directory') == str(stage)
                and config.get('jobs') == '1' and not config.get('native-pgo'), 'worker context configuration mismatch')
        graph_packages = context.get('graph', {}).get('packages', [])
        require(len(graph_packages) == len(package_data), 'incomplete worker package graph')
        seen_packages = set()
        for graph_package in graph_packages:
            data = graph_package.get('data', {})
            name = data.get('name')
            require(name in package_data and name not in seen_packages, 'unreviewed worker package')
            seen_packages.add(name)
            manifest, expected_data = package_data[name]
            require(graph_package.get('path') == str(manifest) and data == expected_data, 'worker manifest differs from reviewed source')
            actual_modules = {m.get('name'): m.get('source') for m in graph_package.get('modules', [])}
            expected_modules = {n: str((manifest.parent / p).resolve()) for n, p in data.get('library', {}).get('modules', {}).items()}
            require(actual_modules == expected_modules, 'worker library module selection mismatch')
        require(scheduler.get('invocation_id') == invocation and context.get('jobs') == scheduler.get('jobs'),
                'scheduler context mismatch')
        actual_path = regular(directory / 'runner-result.json')
        require(read(actual_path) == outcome, 'scheduler result changed')
        jobs = scheduler.get('jobs', [])
        tasks = outcome.get('tasks', [])
        require(jobs and outcome.get('protocol_version') == 1 and outcome.get('complete') is True
                and outcome.get('invocation_id') == invocation and outcome.get('plan_digest') == scheduler['plan_digest']
                and outcome.get('jobs') == 1 and outcome.get('exit_code') == 0
                and [j['id'] for j in jobs] == [t.get('id') for t in tasks]
                and all(t.get('state') == 'succeeded' and t.get('exit_code') == 0 for t in tasks),
                'invalid scheduler task outcomes')
        for path in (context_path, actual_path, regular(directory / 'plan.bin')):
            scheduler_evidence[str(path)] = sha(path)
        for job in jobs:
            require(re.fullmatch(r'[A-Za-z0-9_.-]+', job['id']), 'unsafe scheduler job id')
            result_path = regular(directory / 'jobs' / job['id'] / 'result.json')
            result = read(result_path)
            require(result.get('complete') is True and result.get('invocation_id') == invocation
                    and result.get('id') == job['id'], 'invalid worker result')
            value = result.get('result', {})
            artifact, saved = stamp(cache, value)
            require(value.get('artifact') == str(artifact) and value.get('files') == saved['files'],
                    'worker artifact identity mismatch')
            worker_report_path = regular(result_path.parent / 'build-report.json')
            worker_report = read(worker_report_path)
            require(result.get('report') == worker_report, 'worker embedded report mismatch')
            matching_rows = [r for r in worker_report.get('builds', []) if r.get('key') == value.get('key')
                             and r.get('kind') == value.get('kind')]
            require(len(matching_rows) == 1 and matching_rows[0].get('cached') is False,
                    'worker result lacks fresh matching action row')
            kind = job.get('kind')
            expected_kind = {'runtime': 'runtime object', 'emit': 'LLVM emission', 'object': 'LLVM object',
                             'link': 'native link', 'assemble': 'executable mlf-compiler:' + job.get('selection', {}).get('name', '')}.get(kind)
            require((kind in ('library', 'target') and value.get('kind', '').startswith('crate '))
                    or (expected_kind is not None and value.get('kind') == expected_kind), 'worker result action kind mismatch')
            require(job['id'] not in worker_results, 'duplicate scheduler job identity')
            worker_results[job['id']] = (value, saved)
            scheduled_jobs[job['id']] = job
            merged_worker_rows.extend({**r, 'job_id': job['id']} for r in worker_report.get('builds', []))
            scheduler_evidence[str(result_path)] = sha(result_path)
            scheduler_evidence[str(worker_report_path)] = sha(worker_report_path)
    commands = report.get('commands', [])
    require(bool(commands) and all(c.get('exit_code') == 0 for c in commands), 'failed/missing manager command')
    evidence = {str(report_file): sha(report_file)}
    evidence.update(scheduler_evidence)
    relocated_logs = {}
    for command in commands:
        for field in ('stdout', 'stderr'):
            if command.get(field):
                path = Path(command[field])
                require(path.resolve().is_relative_to(stage) or path.resolve().is_relative_to(cache),
                        'unowned manager command log')
                if not path.exists():
                    relative = path.relative_to(cache) if path.is_relative_to(cache) else None
                    match = re.fullmatch(r'([0-9a-f]{64})\.work-[A-Za-z0-9]{8}', relative.parts[0]) if relative else None
                    require(match is not None and len(relative.parts) > 1, 'missing manager command log: ' + str(path))
                    target = cache / match.group(1) / Path(*relative.parts[1:])
                    _, published = stamp(cache, {'key': match.group(1)})
                    name = str(Path(*relative.parts[1:]))
                    require(name in published['files'], 'relocated output absent from genuine stamp')
                    verified(target, published['files'][name])
                    relocated_logs[str(path)] = {'published': str(target), 'sha256': sha(target),
                                                'reason': 'Package.Build atomic work-directory publication'}
                    path = target
                evidence[str(regular(path))] = sha(path)
    dependency_bindings = {}
    def dependencies(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('libraries', 'headers') and isinstance(item, dict):
                    for original, digest in item.items():
                        path = Path(original).resolve(strict=True)
                        verified(path, digest)
                        evidence[str(path)] = digest
                        dependency_bindings[original] = str(path)
                else:
                    dependencies(item)
        elif isinstance(value, list):
            for item in value:
                dependencies(item)
    dependencies(tools)
    rows = report.get('builds', [])
    require(rows == merged_worker_rows, 'aggregate action rows do not match actual worker reports')
    require(all(row.get('cached') is False for row in rows), 'cold route reused intermediate action')
    for job in scheduled_jobs.values():
        require(all(dependency in scheduled_jobs for dependency in job.get('dependencies', [])),
                'unknown scheduler predecessor')
        if job.get('kind') not in ('library', 'target'):
            continue
        result, saved = worker_results[job['id']]
        crate = saved.get('inputs', {})
        identity = crate.get('crate')
        require(identity in crate_plans and result.get('kind') == 'crate ' + identity, 'unreviewed crate identity')
        planned = crate_plans[identity]
        require(crate.get('compiler') == tools['compiler'] and crate.get('manager') == tools['manager'],
                'crate producer mismatch')
        require(crate.get('entry') == planned['entry'] and crate.get('no-prelude') is False
                and job.get('no-prelude', False) is False, 'crate entry/prelude mismatch')
        sources = crate.get('sources', {})
        require(sorted(sources) == sorted(planned['modules']), 'crate module inventory mismatch')
        if job['kind'] == 'target':
            require(job.get('entry') == planned['entry'], 'target entry mismatch')
            selected_modules = {m['name']: m['source'] for m in job.get('modules', [])}
        else:
            manifest, data = package_data[job.get('package')]
            selected_modules = {n: str((manifest.parent / p).resolve()) for n,p in data.get('library', {}).get('modules', {}).items()}
        require(selected_modules == {n: v.get('path') for n,v in sources.items()}, 'scheduler/source selection mismatch')
        for name, value in sources.items():
            path = value.get('path')
            require(path in reviewed_sources and value.get('sha256') == reviewed_sources[path][0], 'unreviewed crate source')
            text = Path(path).read_text()
            match = re.search(r'^\s*module\s+([A-Z][A-Za-z0-9_.\']*)', text, re.M)
            require(match is not None and match.group(1) == name, 'source module name mismatch')
            syntax = 'shared-haskell-v1' if re.search(r'^--\s*mlf:syntax shared-haskell-v1\s*$', text, re.M) else 'legacy-emlf-v1'
            require(value.get('syntax') == syntax, 'crate source syntax mismatch')
        crate_dependencies = []
        predecessor_crates = []
        for dependency in job.get('dependencies', []):
            dep, dep_stamp = worker_results[dependency]
            require(scheduled_jobs[dependency].get('kind') == 'library', 'nonlibrary crate predecessor')
            predecessor_crates.append(dep_stamp['inputs']['crate'])
            crate_dependencies.append({'path': str(Path(dep['artifact'])/'unit.mlfci'),
                                 'metadata': dep_stamp['files']['unit.mlfci'], 'object': dep_stamp['files']['unit.mlfco']})
        require(crate.get('dependencies') == crate_dependencies and sorted(predecessor_crates) == sorted(planned['dependencies']),
                'crate predecessor metadata provenance mismatch')
    artifacts = []
    for row in rows:
        directory, value = stamp(cache, row)
        evidence[str(directory / 'artifact.json')] = sha(directory / 'artifact.json')
        evidence.update({str(directory / name): digest for name, digest in value['files'].items()})
        native = value.get('inputs', {})
        if row.get('kind') in ('LLVM object', 'native link', 'runtime object'):
            keys = ['clang', 'system', 'machine', 'native_environment']
            if row['kind'] in ('native link', 'runtime object'):
                keys += ['gmp']
            if row['kind'] == 'runtime object':
                keys += ['runtime', 'runtime-path']
            require(all(key in tools and native.get(key) == tools[key] for key in keys), 'native artifact tool/input mismatch')
            if row['kind'] == 'LLVM object':
                flags = ['-O2', '-Wno-override-module', '-c']
            else:
                gc_input = native.get('gc')
                require(gc_input in report.get('native_inputs', []), 'missing authenticated GC identity')
                all_flags = tools['gmp']['flags'] + gc_input['flags']
                flags = (['-O2', '-std=c11'] + [x for x in all_flags if x.startswith(('-I', '-D'))]
                         if row['kind'] == 'runtime object' else ['-O2', '-Wno-override-module'] + all_flags + ['-lm'])
            require(native.get('flags') == flags and not any('pgo' in key or 'profile' in key for key in native),
                    'unexpected native flags/PGO')
        dependencies(value.get('inputs', {}))
        artifacts.append((row, directory, value))
    outputs = {}
    for target in TARGETS:
        matches = [a for a in artifacts if a[0].get('kind') == 'executable mlf-compiler:' + target]
        require(len(matches) == 1, 'missing/duplicate final executable: ' + target)
        row, directory, value = matches[0]
        require(row.get('cached') is False, 'final executable reused: ' + target)
        assembly = scheduled_jobs.get(row.get('job_id'), {})
        require(assembly.get('kind') == 'assemble' and assembly.get('selection', {}).get('name') == target
                and assembly.get('selection', {}).get('target') == expected_targets[target], 'wrong target assembly job')
        def predecessor(job, field, kind):
            identity = job.get(field)
            require(identity in job.get('dependencies', []) and identity in worker_results
                    and scheduled_jobs[identity].get('kind') == kind, 'invalid ' + field + ' predecessor')
            result, saved = worker_results[identity]
            return scheduled_jobs[identity], result, saved
        crate_job, crate_result, crate_stamp = predecessor(assembly, 'crate', 'target')
        emit_job, emit_result, emit_stamp = predecessor(assembly, 'emitted', 'emit')
        link_job, link_result, link_stamp = predecessor(assembly, 'linked', 'link')
        object_job, object_result, object_stamp = predecessor(link_job, 'llvm', 'object')
        runtime_job, runtime_result, runtime_stamp = predecessor(link_job, 'runtime', 'runtime')
        require(emit_job.get('crate') == crate_job['id'] and crate_job['id'] in emit_job.get('dependencies', [])
                and object_job.get('emitted') == emit_job['id'] and emit_job['id'] in object_job.get('dependencies', []),
                'broken target crate/emission/object chain')
        require(emit_stamp['inputs'].get('compiler') == tools['compiler']
                and emit_stamp['inputs'].get('crate-path') == crate_result['artifact']
                and emit_stamp['inputs'].get('metadata') == crate_stamp['files']['unit.mlfci']
                and emit_stamp['inputs'].get('object') == crate_stamp['files']['unit.mlfco']
                and emit_stamp['files']['program.ll'] == value['files']['program.ll']
                and object_stamp['inputs'].get('llvm') == emit_stamp['files']['program.ll']
                and link_stamp['inputs'].get('llvm-object') == object_stamp['files']['program.o']
                and link_stamp['inputs'].get('runtime-object') == runtime_stamp['files']['runtime.o']
                and link_stamp['files']['program'] == value['files']['program']
                and value['inputs'].get('crate-path') == crate_result['artifact']
                and crate_stamp['files']['unit.mlfci'] == value['files']['unit.mlfci']
                and crate_stamp['files']['unit.mlfco'] == value['files']['unit.mlfco'],
                'disconnected target artifact chain')
        llvm = verified(directory / 'program.ll', value['files']['program.ll'])
        binary = verified(directory / 'program', value['files']['program'])
        installed = verified(stage / 'bin' / target, sha(binary))
        evidence[str(installed)] = sha(installed)
        final_inputs = value.get('inputs', {})
        require(final_inputs.get('toolchain') == tools and final_inputs.get('target') == expected_targets[target]
                and final_inputs.get('llvm') == sha(llvm) and final_inputs.get('binary') == sha(binary),
                'final executable stamp input mismatch')
        require(final_inputs.get('metadata') == value['files'].get('unit.mlfci')
                and final_inputs.get('object') == value['files'].get('unit.mlfco')
                and final_inputs.get('metadata') is not None and final_inputs.get('object') is not None,
                'final crate metadata/object provenance missing')
        objects = [a for a in artifacts if a[0].get('kind') == 'LLVM object'
                   and a[2].get('inputs', {}).get('llvm') == sha(llvm)]
        require(bool(objects), 'missing linked LLVM object')
        object_hashes = {a[2]['files'].get('program.o') for a in objects}
        require(len(object_hashes) == 1 and None not in object_hashes, 'ambiguous native object')
        object_hash = next(iter(object_hashes))
        links = [a for a in artifacts if a[0].get('kind') == 'native link'
                 and a[2].get('inputs', {}).get('llvm-object') == object_hash
                 and a[2].get('files', {}).get('program') == sha(binary)]
        require(bool(links), 'missing actual native link provenance')
        for link in links:
            runtime_hash = link[2]['inputs'].get('runtime-object')
            require(any(a[0].get('kind') == 'runtime object' and a[2]['files'].get('runtime.o') == runtime_hash
                        for a in artifacts), 'missing authenticated runtime object')
        outputs[target] = {'llvm_sha256': sha(llvm), 'object_sha256': object_hash,
                           'binary_sha256': sha(installed), 'cached': False}
    published_helper = verified(stage / 'bin/mlf-build-runner', sha(helper))
    evidence[str(published_helper)] = sha(published_helper)
    native_identity = {key: tools[key] for key in ('clang', 'pkg-config', 'system', 'machine',
                       'native_environment', 'runtime', 'runtime-path', 'gmp')}
    native_identity['gc'] = sorted({json.dumps(value, sort_keys=True) for value in report.get('native_inputs', [])})
    native_identity['action_flags'] = sorted({json.dumps([row['kind'], value['inputs']['flags']])
        for row, _, value in artifacts if row['kind'] in ('LLVM object', 'runtime object', 'native link')})
    return {'report_sha256': sha(report_file), 'outputs': outputs, 'evidence': evidence,
            'native_input_signature': native_identity,
            'relocated_command_outputs': relocated_logs, 'dependency_path_bindings': dependency_bindings}


def compare_stages(a, b):
    require(a.get('native_input_signature') is not None and a['native_input_signature'] == b.get('native_input_signature'),
            'fixed point native inputs/flags differ')
    comparisons = {}
    for target in TARGETS:
        comparisons[target] = {}
        for kind in ('llvm_sha256', 'object_sha256', 'binary_sha256'):
            require(a['outputs'][target][kind] == b['outputs'][target][kind],
                    'fixed point differs: ' + target + ' ' + kind)
            comparisons[target][kind] = b['outputs'][target][kind]
    return comparisons


def stage_command(root, pair, stage, cache, clang, gc, seconds, pkg):
    return [str(pair / 'mlfpkg'), '--manifest', str(root / 'mlf-package.json'),
            '--compiler', str(pair / 'emlf'), '--runtime', str(root / 'runtime/mlf_runtime.c'),
            '--clang', str(clang), '--pkg-config', str(pkg), '--gc-prefix', str(gc), '--timeout', str(seconds), '--jobs', '1',
            '--build-dir', str(stage), '--cache-dir', str(cache), '--offline', '--locked',
            'build', '--target', 'emlf', '--target', 'mlfpkg']


def pin_clang_trace(trace, pin):
    """Pin actual -### tool/CRT selections and recursively selected GNU ld scripts."""
    commands = [shlex.split(line.strip()) for line in trace.splitlines() if line.lstrip().startswith('"')]
    require(commands, 'clang did not expose invocation trace')
    selected_tools = []
    seen = set()
    for command in commands:
        tool = Path(command[0])
        require(tool.is_absolute() and tool.is_file(), 'unresolved clang subtool')
        pin(tool); selected_tools.append(tool)
        directories = [Path(x[2:]) for x in command if x.startswith('-L')]
        def select_library(name, extra=()):
            names = [name[1:]] if name.startswith(':') else ['lib'+name+'.so', 'lib'+name+'.a']
            for directory in [*extra, *directories]:
                for filename in names:
                    candidate = directory / filename
                    if candidate.is_file():
                        library(candidate)
                        return
            raise ValueError('unresolved actual linker library: ' + name)
        def library(path):
            actual = path.resolve(strict=True)
            pin(path)
            if actual in seen:
                return
            seen.add(actual)
            prefix = actual.read_bytes()[:65536]
            if prefix.startswith((b'\x7fELF', b'!<arch>')):
                return
            text = prefix.decode('utf-8', errors='strict')
            require('GROUP' in text or 'INPUT' in text, 'unrecognized selected linker input: ' + str(path))
            text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
            for token in re.findall(r'-l[^\s()]+|[A-Za-z0-9_./+-]+\.(?:so(?:\.[0-9]+)*|a|o)', text):
                if token.startswith('-l'):
                    select_library(token[2:], [actual.parent])
                else:
                    selected = Path(token)
                    if not selected.is_absolute():
                        selected = next((d/token for d in [actual.parent, *directories] if (d/token).is_file()), None)
                    require(selected is not None and selected.is_file(), 'unresolved GNU ld script member: ' + token)
                    library(selected)
        for index, token in enumerate(command):
            if token == '-resource-dir':
                directory = Path(command[index+1])
                require(directory.is_dir(), 'missing clang resource tree')
                for path in directory.rglob('*'):
                    if path.is_file(): pin(path)
            path = Path(token)
            if path.is_absolute() and path.is_file():
                if path.suffix in ('.so', '.a') or '.so.' in path.name:
                    library(path)
                else:
                    pin(path)
            if token.startswith('-l') and len(token) > 2:
                select_library(token[2:])
    return selected_tools


def source_checkpoint(root, git, env, expected, executing):
    env = {k: v for k, v in env.items() if not k.startswith('GIT_') or k in ('GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL')}
    def query(*arguments):
        return subprocess.check_output([str(git), *arguments], cwd=root, env=env, text=True).strip()
    require(Path(query('rev-parse', '--show-toplevel')).resolve() == root.resolve(), 'Git checkout mismatch')
    head = query('rev-parse', 'HEAD')
    dirty = query('status', '--porcelain', '--untracked-files=normal')
    if executing:
        require(head == expected and not dirty, 'execution requires exact clean reviewed source checkpoint')
    return {'head': head, 'dirty': bool(dirty), 'expected': expected, 'git': str(git), 'git_sha256': sha(git)}


def interrupted(signum, frame):
    raise InterruptedError('bootstrap driver interrupted by signal ' + str(signum))


def managed_run(argv, cwd, env):
    # The watchdog owns independently sessioned native descendants. Give its
    # TERM handler time to reap them; retain PID/start-time identities as backup.
    proc = subprocess.Popen(argv, cwd=cwd, env=env, start_new_session=True)
    tracked = {}
    def descendants():
        table = {}
        for path in Path('/proc').glob('[0-9]*/stat'):
            try:
                fields = path.read_text().rsplit(') ', 1)[1].split()
                table[int(path.parent.name)] = (int(fields[1]), fields[19], fields[0])
            except (OSError, ValueError, IndexError):
                pass
        owned = {pid for pid, start in tracked.items() if pid in table and table[pid][1] == start}
        if proc.pid in table: owned.add(proc.pid)
        while True:
            added = {pid for pid, entry in table.items() if entry[0] in owned} - owned
            if not added: break
            owned.update(added)
        for pid in owned: tracked[pid] = table[pid][1]
        return {pid: table[pid] for pid in owned if table[pid][2] != 'Z'}
    try:
        while proc.poll() is None:
            descendants()
            time.sleep(.2)
        return proc.returncode
    except BaseException:
        descendants()
        if proc.poll() is None: proc.send_signal(signal.SIGTERM)
        deadline = time.monotonic() + 15
        while proc.poll() is None and time.monotonic() < deadline:
            descendants(); time.sleep(.1)
        remaining = descendants()
        for pid in remaining:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
        proc.wait()
        raise


def clear_pointers(output):
    for name in ('compiler.path', 'manager.path', 'compiler.path.pending', 'manager.path.pending'):
        (output / name).unlink(missing_ok=True)


def publish_pointers(output, compiler, manager):
    try:
        for name, path in [('compiler.path', compiler), ('manager.path', manager)]:
            (output / (name + '.pending')).write_text(str(path) + '\n')
        for name in ('compiler.path', 'manager.path'):
            (output / (name + '.pending')).replace(output / name)
    except BaseException:
        clear_pointers(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('producer-receipt', 'frontend-receipt', 'plans-dir', 'output', 'clang', 'gc-prefix'):
        parser.add_argument('--' + arg, required=True, type=Path)
    parser.add_argument('--producer-sha256', required=True)
    parser.add_argument('--frontend-sha256', required=True)
    parser.add_argument('--plans-sha256', required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true', help='explicitly execute reviewed native stages (default dry-run)')
    mode.add_argument('--prepare-runner', action='store_true', help='authenticate and build only the small C scheduling helper; no native compiler stages')
    parser.add_argument('--checkpoint', help='exact clean reviewed Git HEAD required for execution')
    parser.add_argument('--release-note', help='required auditable human release reference with --execute')
    parser.add_argument('--seconds', type=int, default=21600)
    parser.add_argument('--rss-mib', type=int, default=3072)
    parser.add_argument('--address-space-mib', type=int, default=4096)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    require(not args.execute or (bool(args.release_note) and bool(re.fullmatch(r'[0-9a-f]{40}', args.checkpoint or ''))),
            '--execute requires explicit release-note and exact reviewed checkpoint')
    require(min(args.seconds, args.rss_mib, args.address_space_mib) > 0, 'positive resource caps required')
    out = args.output.absolute()
    require(not out.is_symlink() and not ROOT.is_relative_to(out.resolve()) and
            (not out.exists() or not any(out.iterdir())), 'new empty nonancestor output directory required')
    out.mkdir(parents=True, exist_ok=True)
    receipt = {'format': 1, 'route': 'authenticated-GHC-pair/native-A/native-B', 'complete': False,
               'fixed_point_qualified': False, 'mode': 'execute' if args.execute else ('runner-preflight' if args.prepare_runner else 'dry-run'),
               'release_note': args.release_note, 'commands': [], 'stages': {}, 'phase': 'preflight'}
    def save():
        temporary = out / 'receipt.json.tmp'
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        temporary.replace(out / 'receipt.json')
    save()
    try:
        git = Path('/usr/bin/git').resolve(strict=True)
        git_environment = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C',
                           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
        def checkpoint():
            return source_checkpoint(ROOT, git, git_environment, args.checkpoint, args.execute)
        receipt['source_checkpoint'] = checkpoint()
        producer_path = verified(args.producer_receipt, args.producer_sha256)
        pair = producer_path.parent / 'bin'
        direct.authenticate_build(producer_path, pair, ROOT)
        gate = authenticate_gate(args.frontend_receipt, args.frontend_sha256, args.producer_sha256)
        verified(args.plans_dir.resolve() / 'receipt.json', args.plans_sha256)
        inputs = authenticate_plans(args.plans_dir.resolve(), args.producer_sha256)
        inputs.update(gate['inputs']); inputs.update(gate['artifacts'])
        runtime_inputs = {str(p.resolve()): sha(p) for p in (ROOT / 'runtime').iterdir()
                          if p.suffix in ('.c', '.h') and p.is_file()}
        inputs.update(runtime_inputs)
        clang = args.clang.resolve(strict=True)
        gc = args.gc_prefix.resolve(strict=True)
        pkg = Path(shutil.which('pkg-config')).resolve(strict=True)
        bindings = {}
        for p in [producer_path, args.frontend_receipt.resolve(), Path(__file__).resolve(),
                  ROOT / 'tools/shared/test_direct.py', ROOT / 'tools/shared/resource_watchdog.py',
                  clang, pkg, git, Path(sys.executable).resolve(), Path(shutil.which('nice')).resolve(), gc / 'lib/libgc.a', *sorted((gc / 'include').rglob('*.h'))]:
            resolved = p.resolve(strict=True)
            inputs[str(regular(resolved))] = sha(resolved)
            bindings[str(p)] = str(resolved)
        receipt['inputs'] = inputs
        receipt['path_bindings'] = bindings
        receipt['producer_receipt_sha256'] = args.producer_sha256
        receipt['frontend_receipt_sha256'] = args.frontend_sha256
        receipt['plans_receipt_sha256'] = args.plans_sha256
        # No ambient build overrides or loader injection. Pin tool resolution explicitly.
        env = {'PATH': str(clang.parent) + ':' + str(pkg.parent) + ':/usr/bin:/bin',
               'HOME': os.environ.get('HOME', '/tmp'), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
               'CC': str(clang), 'MLF_CLANG': str(clang), 'MLF_GC_PREFIX': str(gc),
               'GHC_ENVIRONMENT': '-', 'GC_INITIAL_HEAP_SIZE': '16777216', 'GC_FREE_SPACE_DIVISOR': '8'}
        receipt['environment'] = env.copy()
        def check_inputs():
            checkpoint()
            for original, resolved in bindings.items():
                require(str(Path(original).resolve(strict=True)) == resolved, 'input symlink changed: ' + original)
            for name, digest in inputs.items():
                verified(name, digest)
            direct.authenticate_build(producer_path, producer_path.parent / 'bin', ROOT)
        helper = out / 'tools/mlf-build-runner'
        commands = []
        for name, selected in [('A', pair), ('B', out / 'stage-A/bin')]:
            commands.append(stage_command(ROOT, selected, out / ('stage-' + name), out / ('cache-' + name), clang, gc, args.seconds, pkg))
        receipt['planned_stage_commands'] = commands
        if not args.execute and not args.prepare_runner:
            check_inputs()
            receipt.update(phase='authenticated-dry-run', preflight_passed=True)
            save()
            print('Authenticated dry-run only: ' + str(out / 'receipt.json'))
            return
        def run(argv, label, timeout=None):
            check_inputs()
            logdir = out / 'commands' / label
            wrapper = [sys.executable, str(ROOT / 'tools/shared/resource_watchdog.py'),
                       '--seconds', str(timeout or args.seconds), '--rss-mib', str(args.rss_mib),
                       '--address-space-mib', str(args.address_space_mib), '--disk-free-mib', '4096',
                       str(logdir), 'nice', '-n', '19', *map(str, argv)]
            entry = {'argv': list(map(str, argv)), 'watchdog_argv': wrapper, 'environment': env.copy()}
            receipt['commands'].append(entry); save()
            result = managed_run(wrapper, cwd=ROOT, env=env)
            bounded = read(logdir / 'bounded-receipt.json')
            entry.update(exit_code=result, bounded_receipt=str(logdir / 'bounded-receipt.json'),
                         bounded_sha256=sha(logdir / 'bounded-receipt.json'), log_sha256=sha(logdir / 'build.log'))
            save()
            require(result == 0 and bounded.get('complete') is True, 'bounded command failed: ' + label)
            check_inputs()
            return (logdir / 'build.log').read_text()
        helper.parent.mkdir()
        receipt['phase'] = 'native-toolchain-preflight'; save()
        ldd = Path(shutil.which('ldd')).resolve(strict=True)
        inputs[str(ldd)] = sha(ldd)
        for number, tool in enumerate((clang, pkg, Path(sys.executable).resolve())):
            listing = run([ldd, tool], 'native-loader-' + str(number), 30)
            for line in listing.splitlines():
                match = re.search(r'(?:=>\s+|^\s*)(/[^\s]+)', line)
                if match:
                    original = Path(match.group(1)); resolved = original.resolve(strict=True)
                    inputs[str(regular(resolved))] = sha(resolved)
                    bindings[str(original)] = str(resolved)
        gmp_flags = run([pkg, '--cflags', '--libs', 'gmp'], 'gmp-flags', 30).strip().split()
        gmp_dir = Path(run([pkg, '--variable=libdir', 'gmp'], 'gmp-libdir', 30).strip())
        gmp_library = gmp_dir / 'libgmp.so'
        inputs[str(regular(gmp_library.resolve(strict=True)))] = sha(gmp_library)
        bindings[str(gmp_library)] = str(gmp_library.resolve(strict=True))
        receipt['native_gmp_flags'] = gmp_flags
        def pin_native(path):
            resolved = path.resolve(strict=True)
            inputs[str(regular(resolved))] = sha(resolved)
            bindings[str(path)] = str(resolved)
        trace = run([clang, '-###', '-O2', ROOT / 'runtime/mlf_build_runner.c',
                     gc / 'lib/libgc.a', *gmp_flags, '-lm', '-lpthread', '-ldl',
                     '-o', out / 'tools/not-built-link-probe'], 'clang-link-selection', 30)
        subtools = pin_clang_trace(trace, pin_native)
        receipt['clang_selected_tools'] = [str(p.resolve()) for p in subtools]
        for number, tool in enumerate(dict.fromkeys(subtools)):
            listing = run([ldd, tool], 'selected-tool-loader-' + str(number), 30)
            for line in listing.splitlines():
                match = re.search(r'(?:=>\s+|^\s*)(/[^\s]+)', line)
                if match: pin_native(Path(match.group(1)))

        def header_dependencies(source, name, include_flags):
            dependency = out / 'tools' / (name + '.d')
            run([clang, '-M', '-std=c11', *include_flags, '-MF', dependency, source], name + '-dependencies', 60)
            text = dependency.read_text().replace('\\\n', ' ')
            require(': ' in text, 'missing header dependency inventory')
            for filename in text.split(': ', 1)[1].split():
                original = Path(filename)
                if not original.is_absolute():
                    original = ROOT / original
                resolved = original.resolve(strict=True)
                inputs[str(regular(resolved))] = sha(resolved)
                bindings[str(original)] = str(resolved)
            inputs[str(dependency)] = sha(dependency)
        header_dependencies(ROOT / 'runtime/mlf_build_runner.c', 'runner', [])
        header_dependencies(ROOT / 'runtime/mlf_runtime.c', 'runtime',
                            ['-I' + str(gc / 'include')] + [x for x in gmp_flags if x.startswith(('-I', '-D'))])
        receipt['phase'] = 'runner-preflight'; save()
        run([clang, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
             ROOT / 'runtime/mlf_build_runner.c', '-o', helper], 'build-runner', 120)
        require(run([helper, '--protocol-version'], 'runner-protocol', 30).strip() == '1', 'runner protocol mismatch')
        inputs[str(helper)] = sha(helper)
        receipt['runner'] = {'path': str(helper), 'sha256': sha(helper)}
        if args.prepare_runner:
            check_inputs()
            receipt.update(phase='runner-preflight-complete', preflight_passed=True, native_stages_started=False)
            save()
            print('Runner preflight only: ' + str(out / 'receipt.json'))
            return
        for index, name in enumerate(('A', 'B')):
            receipt['phase'] = 'native-' + name; save()
            selected = pair if name == 'A' else out / 'stage-A/bin'
            selected_helper = helper if name == 'A' else selected / 'mlf-build-runner'
            env['MLF_BUILD_RUNNER'] = str(selected_helper)
            run(commands[index], 'stage-' + name)
            stage = verify_stage(out / ('stage-' + name), out / ('cache-' + name), selected,
                                 selected_helper, clang, runtime_inputs,
                                 read(args.plans_dir / 'root-plan.json')['packages'],
                                 read(ROOT / 'mlf-package.json')['executables'], pkg,
                                 read(args.plans_dir / 'root-plan.json')['crates'], ROOT)
            receipt['stages'][name] = stage
            inputs.update(stage['evidence'])
            bindings.update(stage['dependency_path_bindings'])
            for target in TARGETS:
                binary = out / ('stage-' + name) / 'bin' / target
                require(run([binary, '--implementation-identity'], name + '-' + target + '-identity', 30).strip()
                        == 'MLF/shared-haskell-v1 native-MLF', 'wrong native identity')
                inputs[str(binary)] = sha(binary)
            save()
        receipt['comparisons'] = compare_stages(receipt['stages']['A'], receipt['stages']['B'])
        check_inputs()
        publish_pointers(out, out / 'stage-B/bin/emlf', out / 'stage-B/bin/mlfpkg')
        receipt.update(phase='fixed-point-complete', complete=True, fixed_point_qualified=True,
                       capability_scope='identity only; language/backend/async qualification is separate')
        save()
    except BaseException as error:
        clear_pointers(out)
        receipt.update(complete=False, fixed_point_qualified=False, error=type(error).__name__ + ': ' + str(error))
        save()
        raise


if __name__ == '__main__':
    main()
