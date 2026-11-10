#!/usr/bin/env python3
"""Frozen inference11 source-to-checked Q or C, requiring separate admission.

Q is A,B qualification; C is a separately admitted A,B,B,A cohort. Neither
builds a producer, emits LLVM, runs a native generation or measures full90.
The original resource_watchdog must enclose this worker via run-phase.sh.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import math
import os
import re
import statistics
import sys
import time
import types

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'compiler-baseline-20261110'
BASE_PRODUCER = BASE / '.mlf-build/baseline-producer'
BASE_RECEIPT = 'b71bbb5ebb757a206ed41932cdafca982f1e7246218496953be273afad5a8caf'
WORKLOAD = 'd3b0795eaeb995a4a1be9f0926632e335867cc2c411807c1296018bae47a2775'
HELPER = '0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc'
SCOPE = 'd8ffe4256f333c0b48b22b9e68d9c3fa5dc9b471fd22a0d636ba9b157fe419a3'
WATCHDOG = '5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f'
RUNTIME = '6cfa19c71442422d0a5f1b5386618e60bca6883821ab556a4dff67f3643e7093'
RUNTIME_PATH = HERE.parent / 'compiler-graph-read-fusion-20261110/tools/performance/graph-read-fusion/sample-runtime.py'
OWNER = 'libraries/mlf-inference/Bootstrap/Graph.hs'
GRAPH = 'fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3'
CANONICAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
LIMITS = dict(address_space_per_process_bytes=6*1024**3,
              disk_free_floor_bytes=5*1024**3, host_available_floor_bytes=3*1024**3,
              max_work_bytes=4*1024**3, process_tree_rss_bytes=5*1024**3)


def import_exact(path, digest, name):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError('reviewed helper changed: '+str(path))
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def pack(fields):
    return ''.join(str(len(value))+':'+value for value in fields)


def unpack(H, text):
    fields = []
    while text:
        prefix, separator, rest = text.partition(':')
        H.require(separator and re.fullmatch(r'0|[1-9][0-9]*', prefix), 'canonical length prefix')
        size = int(prefix)
        H.require(size <= len(rest), 'truncated packed field')
        fields.append(rest[:size])
        text = rest[size:]
    return fields


def fresh(H, report, identity):
    # Same fresh checks as the qualified B2 common.fresh, plus frozen count.
    groups = report['groups']
    H.require(report['format'] == 1 and report['crate'] == identity, 'query identity/format')
    H.require(report['reused_groups'] == 0 and report['inferred_groups'] == len(groups) == 780,
              'exact 780 fresh groups, no reuse')
    H.require(all(g['cached'] is False for g in groups), 'target cache hit')
    H.require(len({g['id'] for g in groups}) == len(groups), 'duplicate query identity')


def interface(H, text, identity, modules, dependencies):
    # Unchanged B2 common.interface format/ownership checks; no private decoder.
    lines = text.splitlines()
    H.require(lines and lines[0] == 'crate '+identity, 'wrong interface identity')
    actual = [line[7:] for line in lines if line.startswith('module ')]
    H.require(len(actual) == len(modules) and set(actual) == set(modules), 'module ownership')
    deps = [line[11:].split(' ', 1) for line in lines if line.startswith('dependency ')]
    found = [(name, tail.rsplit(' ', 1)[0]) for name, tail in deps]
    H.require(len(found) == len(dependencies) and dict(found) == dependencies, 'dependency identities/paths')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['Q', 'C'])
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--handoff-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qualification', type=Path)
    parser.add_argument('--qualification-outer-sha256')
    parser.add_argument('--qualification-work-sha256')
    a = parser.parse_args()
    a.output = a.output.absolute()
    a.handoff = a.handoff.absolute()
    H = import_exact(BASE/'tools/performance/a1-private-index/helper.py', HELPER, 'guard')
    H.require(os.environ.get('MLF_BUILD_SCOPE') == str(os.getpgrp()), 'watchdog scoped worker required')
    a.output.mkdir(parents=True, exist_ok=False)
    budget = {'Q': 420, 'C': 600}[a.phase]
    order = ['A', 'B'] if a.phase == 'Q' else ['A', 'B', 'B', 'A']
    started = time.monotonic()
    record = dict(format='inference11-phase-v1', complete=False, phase=a.phase,
                  fixed_order=order, legs=[], commands=[], stages=[], inputs={}, output_pins={},
                  full90=False, ghc_ratio=False, native_generation=False, fixed_point=False,
                  whole_toolchain_reauthenticated=False, build_objects_reauthenticated=False,
                  historical_runtime_reproduced=False, explicit_runtime_qualification=True,
                  operating_system_cache_reset=False, no_extra_warmups_or_pilots=True,
                  total_budget_seconds=budget, per_compile_limit_seconds=180,
                  timed_boundary='Popen through exact-child wait4 including with_scope Python exec, compiler startup, source/dependency reads, checking, artifact encoding/writes and fresh query publication; preparation/authentication/oracles excluded from leg wall but charged to phase')
    save = lambda: H.save(a.output/'receipt.json', record)
    save()
    pins = record['inputs']
    def pinned(path, digest):
        path = H.regular(path)
        H.require(H.sha(path) == digest, 'fixed input changed: '+str(path))
        if str(path) in pins:
            H.require(pins[str(path)] == digest, 'conflicting input pin')
        pins[str(path)] = digest
        return H.load(path)
    def stage(label, operation):
        row = dict(label=label, complete=False, started_seconds=time.monotonic()-started)
        record['stages'].append(row); save()
        result = operation()
        row.update(complete=True, ended_seconds=time.monotonic()-started); save()
        return result
    def command(label, argv, timed=False, maximum=15):
        remaining = budget-(time.monotonic()-started)
        H.require(remaining > 0, 'phase deadline exhausted')
        row = dict(label=label, complete=False, timed_target_leg=timed)
        record['commands'].append(row); save()
        wrapped = [sys.executable, '-B', BASE/'tools/performance/process-spawn/with_scope.py', *argv]
        result = H.Runner(a.output, dict(LIMITS, wall_seconds=min(maximum, remaining))).run(
            wrapped, BASE, a.output/'commands'/label, timed=timed)
        row.update(result); save()
        return row, (a.output/'commands'/label/'stdout').read_bytes(), (a.output/'commands'/label/'stderr').read_bytes()
    try:
        with H.SerialLock(BASE/'.mlf-build'):
            workload = pinned(HERE/'workload.json', WORKLOAD)
            handoff = pinned(a.handoff, a.handoff_sha256)
            H.require(handoff['format'] == 'inference11-producer-handoff-v1', 'explicit producer handoff required')
            source, producer = Path(handoff['source']), Path(handoff['producer'])
            library = Path(handoff['runtime_library_dir'])
            H.require(all(p.is_absolute() and p.is_dir() for p in [source, producer, library]), 'existing absolute handoff paths')
            runtime = import_exact(RUNTIME_PATH, RUNTIME, 'runtime_contract')
            environment = runtime.target_environment(library)
            # Deliberate exact environment, not inherited unknown LD_* / query instrumentation.
            H.env = lambda: dict(environment)
            record['environment'] = environment
            for path, digest in [(BASE/'tools/performance/a1-private-index/helper.py', HELPER),
                                 (BASE/'tools/performance/process-spawn/with_scope.py', SCOPE),
                                 (BASE/'tools/shared/resource_watchdog.py', WATCHDOG),
                                 (RUNTIME_PATH, RUNTIME)]:
                H.require(H.sha(path) == digest, 'reviewed execution helper')
                pins[str(path)] = digest
            for path in [HERE/'run.py', HERE/'run-phase.sh', Path(sys.executable).resolve()]:
                pins[str(path)] = H.sha(H.regular(path))
            def provenance():
                base = pinned(BASE_PRODUCER/'receipt.json', BASE_RECEIPT)
                receipt = {}
                for key in ['outer', 'work', 'producer']:
                    item = handoff['receipts'][key]
                    receipt[key] = pinned(item['path'], item['sha256'])
                    H.require(receipt[key]['complete'] is True, 'candidate '+key+' incomplete')
                outer, work, candidate = (receipt[k] for k in ['outer', 'work', 'producer'])
                H.require(outer['exit_code'] == 0 and outer['reason'] is None, 'candidate outer guard failed')
                H.require(work['ordinary_full_producer'] is True and work['performance_samples'] == [] and
                          all(work[k] is True for k in ['derived_canonical_verified', 'qualified_cli',
                          'qualified_independent_semantics', 'pins_unchanged']), 'candidate full normal qualification required')
                H.require(Path(handoff['receipts']['producer']['path']) == producer/'receipt.json' and
                          work['producer_receipt_sha256'] == handoff['receipts']['producer']['sha256'], 'producer receipt binding')
                approved = handoff['canonical']
                H.require(approved['relative'] == CANONICAL, 'only approved generated file')
                H.require(re.fullmatch(r'builtin-source-v1:[0-9a-f]{64}', approved['new_identity']) and
                          approved['new_identity'] != approved['old_identity'], 'distinct derived identity')
                H.require(work['derived_source_identity'] == approved['new_identity'], 'build derived identity binding')
                changes = []
                for group in ['shared_inputs', 'host_inputs', 'configuration_inputs']:
                    H.require(set(candidate[group]) == set(base[group]), 'same build input inventory')
                    for name, old in base[group].items():
                        relative = Path(old['path']).relative_to(BASE)
                        new = candidate[group][name]
                        expected = GRAPH if str(relative) == OWNER else approved['sha256'] if str(relative) == CANONICAL else old['sha256']
                        H.require(Path(new['path']) == source/relative and new['sha256'] == expected, 'unapproved candidate input '+str(relative))
                        for item in [old, new]: pins[item['path']] = item['sha256']
                        if expected != old['sha256']: changes.append(str(relative))
                H.require(set(changes) == {OWNER, CANONICAL}, 'only Graph plus canonical identity delta')
                for key in ['build_driver', 'prepared_verification_helper']:
                    old, new = base[key], candidate[key]
                    relative = Path(old['path']).relative_to(BASE)
                    H.require(new['sha256'] == old['sha256'] and Path(new['path']) == source/relative, 'original builder/verifier '+key)
                    for item in [old, new]: pins[item['path']] = item['sha256']
                H.require(set(candidate['builtin_verification_helpers']) == set(base['builtin_verification_helpers']), 'same builtin verification helpers')
                for name, old in base['builtin_verification_helpers'].items():
                    new = candidate['builtin_verification_helpers'][name]
                    H.require(new['sha256'] == old['sha256'] and Path(new['path']) == source/Path(old['path']).relative_to(BASE), 'original builtin verifier source')
                    for item in [old, new]: pins[item['path']] = item['sha256']
                old_bytes, new_bytes = (BASE/CANONICAL).read_bytes(), (source/CANONICAL).read_bytes()
                old, new = approved['old_identity'].encode(), approved['new_identity'].encode()
                H.require(old_bytes.count(old) == 1 and b'builtin = (RawPrelude "'+old+b'"' in old_bytes and
                          new_bytes == old_bytes.replace(old, new) and new_bytes.replace(new, old) == old_bytes,
                          'exact inverse canonical identity-only bytes')
                H.require(candidate['flags'] == [f.replace(str(BASE_PRODUCER),str(producer)).replace(str(BASE),str(source)) for f in base['flags']], 'same ordinary flags')
                for key in ['ghc', 'cc', 'toolchain', 'installed_dependencies', 'ghc_info_sha256', 'ghc_settings', 'package_database_sha256']:
                    H.require(candidate[key] == base[key], 'historical build tool identity differs '+key)
                H.require(base['complete'] is True and candidate['optimization'] == base['optimization'] == '2' and
                          candidate['typecheck_only'] is False and '-O2' in candidate['flags'] and
                          not any(f.startswith('-prof') for f in candidate['flags']), 'ordinary executable required')
                for key in ['resolved_modules', 'resolved_host_modules', 'outputs']:
                    H.require(set(candidate[key]) == set(base[key]), 'normal full build inventory differs '+key)
                binaries = {'A': BASE_PRODUCER/'bin/emlf', 'B': producer/'bin/emlf'}
                for side, auth in [('A',base), ('B',candidate)]:
                    item = auth['outputs']['emlf']
                    H.require(Path(item['path']) == binaries[side], 'actual compiler path')
                    pins[item['path']] = item['sha256']
                    verified = pinned(auth['builtin_verification']['path'], auth['builtin_verification']['sha256'])
                    H.require(verified['complete'] is True and verified['candidate_verified'] is True and
                              verified['exact_regeneration'] is True and verified['immutable_inputs_verified_after'] is True,
                              'original complete fresh builtin verification required')
                    H.require(verified['compiler'] == item, 'builtin verifier binds exact compiler')
                    H.require(verified['canonical']['sha256'] == auth['shared_inputs']['MLF.BuiltinPreludeData']['sha256'], 'canonical verifier binding')
                    H.require(verified['source_identity'] == approved['old_identity' if side == 'A' else 'new_identity'], 'source identity verifier binding')
                    commands = verified['commands']
                    H.require([r['label'] for r in commands] == ['check-candidate','fresh-literal'] and
                              all(r['exit_code'] == 0 and r['input_pins_verified_before'] and r['input_pins_verified_after'] for r in commands), 'both original builtin gates')
                    generated = commands[1]['stdout']
                    H.require(generated['sha256'] == verified['canonical']['sha256'], 'entire literal equality receipt')
                    pins[generated['path']] = generated['sha256']
                H.require(handoff['binary'] == candidate['outputs']['emlf'] and work['producer_outputs'] == candidate['outputs'], 'candidate exact executable binding')
                record['producer_binaries'] = {side:dict(path=str(path), sha256=pins[str(path)]) for side,path in binaries.items()}
                record['source_changes'] = changes
                return binaries
            binaries = stage('producer-build-provenance', provenance)
            pins.update(workload['input_pins'])
            fields = unpack(H, Path(workload['original_spec']).read_text())
            H.require(len(fields) == 8 and pack(fields).encode() == Path(workload['original_spec']).read_bytes(), 'exact eight-field original spec')
            H.require(fields[:4] == ['MLF-CRATE-1', workload['crate_identity'], '', 'false'] and
                      fields[4] == pack([pack([r['module'],r['source']]) for r in workload['modules']]) and
                      fields[5] == pack([d['prefix']+'.mlfci' for d in workload['direct_dependencies']]) and
                      fields[7] == workload['builtin_prefix'], 'all frozen target/spec fields')
            H.require(len(workload['modules']) == 11 and sum(r['bytes'] for r in workload['modules']) == 515309, 'frozen module inventory')
            for item in [*workload['modules'], *[f for d in workload['direct_dependencies'] for f in d['files']], *workload['reference_artifacts']]:
                H.require(Path(item.get('source',item.get('path'))).stat().st_size == item['bytes'], 'frozen input size')
            reference_query = H.load(workload['reference_artifacts'][2]['path'])
            fresh(H, reference_query, workload['crate_identity'])
            stage('execution-input-pins-before', lambda:H.check_pins(pins))
            if a.phase == 'C':
                H.require(a.qualification and a.qualification_outer_sha256 and a.qualification_work_sha256, 'C requires fixed completed Q')
                qroot = a.qualification.absolute()
                qouter = pinned(qroot/'bounded-receipt.json', a.qualification_outer_sha256)
                q = pinned(qroot/'work/receipt.json', a.qualification_work_sha256)
                H.require(qouter['complete'] is True and qouter['exit_code'] == 0 and qouter['reason'] is None and
                          q['complete'] is True and q['phase'] == 'Q' and q['fixed_order'] == ['A','B'] and
                          len(q['legs']) == 2 and all(r['complete'] for r in q['legs']), 'complete Q required')
                H.require(q['inputs'][str(a.handoff)] == a.handoff_sha256 and q['inputs'][str(HERE/'run.py')] == pins[str(HERE/'run.py')] and
                          q['inputs'][str(HERE/'run-phase.sh')] == pins[str(HERE/'run-phase.sh')] and
                          q['producer_binaries'] == record['producer_binaries'] and q['environment'] == environment and
                          q['inputs'][str(HERE/'workload.json')] == WORKLOAD, 'same qualified controller/producer/target/runtime')
                stage('Q-output-pins', lambda:H.check_pins(q['output_pins']))
            else:
                H.require(not a.qualification and not a.qualification_outer_sha256 and not a.qualification_work_sha256, 'Q cannot borrow a target qualification')
            programs = {**binaries, 'python':Path(sys.executable).resolve(), 'mkdir':Path('/bin/mkdir'),
                        'mv':Path('/bin/mv'), 'rm':Path('/bin/rm'), 'rmdir':Path('/bin/rmdir')}
            def runtime_snapshot(label):
                config = runtime.runtime_configuration(H)
                result = dict(configuration=config, directory=dict(path=str(library),realpath=str(library.resolve(strict=True))), programs={})
                for name, path in programs.items():
                    identity = runtime.identity(H,path)
                    loader = runtime.elf_interpreter(H,path)
                    loader_identity = runtime.identity(H,loader)
                    _, stdout, stderr = command(label+'-'+name, [loader,'--list',path])
                    H.require(not stderr and runtime.identity(H,path) == identity and runtime.identity(H,loader) == loader_identity, 'stable resolved executable')
                    result['programs'][name] = dict(executable=identity, loader=loader_identity, libraries=runtime.loader_rows(H,stdout,loader))
                H.require(result['programs']['A']['libraries'] == result['programs']['B']['libraries'], 'compiler runtime libraries differ')
                return result
            before = stage('runtime-before', lambda:runtime_snapshot('runtime-before'))
            record['runtime_before'] = before; save()
            if a.phase == 'C': H.require(before == q['runtime_after'], 'runtime changed after Q qualification')
            dependencies = {'mlf:builtin-shared-haskell-v1:13':workload['builtin_prefix']+'.mlfci'}
            dependencies.update({'fresh-split/compiler90/'+d['name']:d['prefix']+'.mlfci' for d in workload['direct_dependencies'][1:]})
            for index, side in enumerate(order):
                label = str(index+1)+'-'+side
                folder = a.output/'legs'/label
                folder.mkdir(parents=True, exist_ok=False)
                queries = folder/'queries'; queries.mkdir()
                prefix = folder/'unit'; spec = folder/'crate.spec'
                selected = fields.copy(); selected[6] = str(queries)
                spec.write_text(pack(selected))
                decoded = unpack(H,spec.read_text()); decoded[6] = fields[6]
                H.require(pack(decoded).encode() == Path(workload['original_spec']).read_bytes(), 'only query path may differ')
                row = dict(index=index, side=side, complete=False, spec=str(spec), spec_sha256=H.sha(spec), prefix=str(prefix))
                record['legs'].append(row); save()
                stage('pre-inputs-'+label, lambda:H.check_pins(pins))
                H.require(not any(queries.iterdir()) and not any(Path(str(prefix)+suffix).exists() for suffix in ['.mlfci','.mlfco','.queries']), 'fresh target required')
                result, stdout, stderr = command('compile-'+label, [binaries[side],'--compile-crate',spec,'-o',prefix], timed=True, maximum=180)
                row['compile'] = result; save()
                H.require(not stdout and not stderr, 'unexpected compile output')
                for reference in workload['reference_artifacts']:
                    path = Path(str(prefix)+Path(reference['path']).suffix)
                    H.regular(path)
                    H.require(path.read_bytes() == Path(reference['path']).read_bytes(), 'raw artifact differs: '+str(path))
                    record['output_pins'][str(path)] = H.sha(path)
                report = H.load(str(prefix)+'.queries')
                fresh(H,report,workload['crate_identity'])
                H.require(report == reference_query, 'all ordered query fields must equal historical reference')
                _, shown, errors = command('show-'+label, [binaries['A'],'--show-crate',str(prefix)+'.mlfci'])
                H.require(not errors, 'interface checker diagnostic')
                interface(H, shown.decode(), workload['crate_identity'], [r['module'] for r in workload['modules']], dependencies)
                # POSIX lockf, distinct from the two orchestration flock locks.
                lock = queries/'.lock'
                H.require(lock.is_file(), 'compiler query lock evidence missing')
                with lock.open('r+') as stream:
                    fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.lockf(stream, fcntl.LOCK_UN)
                H.require(H.sha(spec) == row['spec_sha256'], 'target spec changed')
                record['output_pins'][str(spec)] = row['spec_sha256']
                stage('post-inputs-'+label, lambda:H.check_pins(pins))
                row.update(complete=True, raw_three_equal=True, fresh_groups=780, reused_groups=0,
                           query_lock_reacquired=True, interface_checked=True); save()
            after = stage('runtime-after', lambda:runtime_snapshot('runtime-after'))
            record['runtime_after'] = after; save()
            H.require(before == after, 'runtime mapping or bytes changed')
            stage('final-inputs', lambda:H.check_pins(pins))
            stage('final-outputs', lambda:H.check_pins(record['output_pins']))
            H.require(time.monotonic()-started < budget and len(record['legs']) == len(order) and all(r['complete'] for r in record['legs']), 'whole fixed phase must complete')
            if a.phase == 'C':
                values = {side:[r['compile']['wall_seconds'] for r in record['legs'] if r['side']==side] for side in ['A','B']}
                geometric = lambda xs: math.exp(sum(map(math.log,xs))/len(xs))
                record['descriptive_only'] = dict(all_wall_seconds=values,
                    median_candidate_divided_by_base=statistics.median(values['B'])/statistics.median(values['A']),
                    geometric_mean_candidate_divided_by_base=geometric(values['B'])/geometric(values['A']),
                    observations_per_side=2, inference_slice_only=True)
            record.update(complete=True, elapsed_seconds=time.monotonic()-started); save()
    except BaseException as error:
        record.update(error=repr(error), elapsed_seconds=time.monotonic()-started); save(); raise


if __name__ == '__main__':
    main()
