#!/usr/bin/env python3
"""Current ordinary-producer C4 correctness gates. No benchmark or source build.

Full mode compares nine files across two authenticated producers. Focused mode
runs all graph/transaction/layout controls with one producer and explicitly does
not claim the nine-file gate. Every failed attempt remains on disk.
"""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import sys
import types

import contracts as C

HERE = Path(__file__).resolve().parent
A1 = HERE.parent / 'a1-private-index'
BUILTIN_PATH = 'bootstrap/MLF/BuiltinPreludeData.hs'
OLD_MODULES = {'FrozenGraph', 'FrozenSolver', 'FrozenConstraint', 'SessionOracle',
               'SessionGraftFixtures', 'SessionFieldFixtures', 'PublicControls', 'TransactionOracle'}
C4_MODULES = {'C4Fixtures', 'C4ProjectionOracle', 'C4TransactionOracle', 'C4TransactionControls'}
VALIDATION_DIR = HERE.parent / 'validation-reuse'
VALIDATION_PINS = {
    'source_contract.py': '039bb8833ef6a232e80458b584005ad88bb46cd9797459d6ef813b7b378cddc6',
    'source-contract.json': 'ec83da63b4021b65a882c0edd9bd5b7f39d4fcb14f47af61655389d1caeea6c5'}
BUILTIN_STDOUT = b'PASS current builtin: canonical literal, full check, exact wire, 7 malformed/mismatch rejections\n'


def pack(values):
    return ''.join(str(len(s))+':'+s for s in values)


def load_helper(manifest):
    for relative, expected in manifest['shared_support_pins'].items():
        C.require(C.sha_bytes((A1 / relative).read_bytes()) == expected, 'unchanged shared support '+relative)
    module = types.ModuleType('c4_unchanged_resource_helper')
    module.__file__ = str(A1 / 'helper.py')
    exec(compile((A1 / 'helper.py').read_bytes(), module.__file__, 'exec'), module.__dict__)
    return module


def source_contract(record, source):
    return {str(Path(row['path']).relative_to(source)): row['sha256']
            for category in ['shared_inputs', 'host_inputs', 'configuration_inputs', 'builtin_verification_helpers']
            for row in record[category].values()}


def compile_argv(official, source, producer, folder, wrapper, binary):
    links = [row for row in official['commands'] if Path(row['log']).name == 'link-emlf.log']
    expected = [official['ghc']['path'], '--make', '-j1', *official['flags'],
                '-rtsopts=ignoreAll', str(source/'host/ghc/app/emlf/Main.hs'),
                str(producer/'host.o'), str(producer/'supervisor.o'), '-o', str(producer/'bin/emlf')]
    C.require(len(links) == 1 and links[0]['exit_code'] == 0 and
              links[0]['cwd'] == str(source) and links[0]['argv'] == expected,
              'one exact authenticated ordinary link')
    C.require(official['flags'].count('-i') == 1, 'one resetting import flag')
    replacements = {str(producer/'objects'): str(folder/'objects'),
        str(source/'host/ghc/app/emlf/Main.hs'): str(wrapper),
        str(producer/'host.o'): str(folder/'host.o'), str(producer/'supervisor.o'): str(folder/'supervisor.o'),
        str(producer/'bin/emlf'): str(binary)}
    argv = []
    for token in expected:
        argv.append(replacements.get(token, token))
        if token == '-i':
            argv += ['-i'+str(HERE/'controls'), '-i'+str(A1/'current')]
    return argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source-base', 'producer-base', 'source-candidate', 'producer-candidate', 'builtin-prefix', 'output']:
        parser.add_argument('--'+name, type=Path, required=name in ['source-candidate', 'producer-candidate', 'output'])
    parser.add_argument('--focused-only', action='store_true', help='one producer; no nine-file or performance claim')
    args = parser.parse_args()
    if args.focused_only:
        if args.source_base or args.producer_base:
            parser.error('focused mode does not accept base arguments')
    elif not all([args.source_base, args.producer_base, args.builtin_prefix]):
        parser.error('full mode requires both base arguments and --builtin-prefix')
    manifest = json.loads((HERE/'manifest.json').read_text())
    H = load_helper(manifest)
    validation_pins = {str(VALIDATION_DIR/name): digest for name,digest in VALIDATION_PINS.items()}
    H.check_pins(validation_pins)
    validation_contract = H.module(VALIDATION_DIR/'source_contract.py', 'validation_reuse_source_contract')
    sources = {'candidate': args.source_candidate.resolve(strict=True)}
    producers = {'candidate': args.producer_candidate.resolve(strict=True)}
    if not args.focused_only:
        sources['base'] = args.source_base.resolve(strict=True)
        producers['base'] = args.producer_base.resolve(strict=True)
    out = args.output.absolute()
    H.require(not os.path.lexists(out), 'fresh output required; failures never overwritten')
    out = out.resolve()
    H.require(all(not out.is_relative_to(path) and not path.is_relative_to(out)
                  for path in [HERE.parents[2], *sources.values(), *producers.values()]),
              'output separate from every source and producer')
    out.parent.mkdir(parents=True, exist_ok=True)
    with H.SerialLock(out.parent):
        out.mkdir()
        record = dict(format='c4-focused-current-controls-v1' if args.focused_only else 'c4-full-current-controls-v1',
            complete=False, all_controls_passed=False, full_gate_passed=False, focused_graph_gate_passed=False,
            requested_scope='focused' if args.focused_only else 'full',
            nine_file_comparison_required=not args.focused_only, nine_file_comparison_passed=False,
            performance_measured=False, ordinary_timing_samples_added=0, target_544_executed=False,
            candidate_output_used_for_expectations=False, historical_c3_controls_executed=False,
            before_reference='complete P3/PR25-before core algorithms under the same current collection/host primitives',
            historical_a1_oracle_scope='source identity checked only here; separate A1 runner owns its dynamic gate',
            source_roots={k:str(v) for k,v in sources.items()}, producers={k:str(v) for k,v in producers.items()},
            inputs={}, commands=[], file_cases=[], limits=manifest['limits'])
        def save():
            H.save(out/'receipt.json', record)
        save()
        try:
            input_pins = H.file_pins(HERE)
            input_pins.update(validation_pins)
            for relative, expected in manifest['pins'].items():
                H.require(H.sha(HERE/relative) == expected, 'fixed independent input '+relative)
            for relative, expected in {**manifest['historical_a1_pins'], **manifest['shared_support_pins']}.items():
                H.require(H.sha(A1/relative) == expected, 'unchanged referenced A1 input '+relative)
                input_pins[str(A1/relative)] = expected
            # In focused mode the byte-exact inverse is still checked against its
            # fixed source hash, but the candidate must not stand in for before.
            C.verify_oracles(HERE, manifest, sources.get('base'))
            program = H.load(HERE/'fixtures/program-oracles.json')
            H.require(len(program['programs']) == 8 and H.sha(HERE/'fixtures/GraphUnification.original.emlf.txt') == program['source_sha256'],
                      'fixed independent parsed-expression expectation source')
            authenticated = {side:H.authenticate(producers[side], source) for side,source in sources.items()}
            record['producer_receipt_sha256'] = {side:H.sha(producers[side]/'receipt.json') for side in sources}
            record['actual_source_contracts'] = {side:source_contract(value, sources[side]) for side,value in authenticated.items()}
            record['base_source_commit_contract'] = manifest['base_commit']
            record['candidate_algorithm_sha256'] = manifest['candidate_algorithm_sha256']
            record['ordinary_toolchain'] = {side:dict(ghc=value['ghc'], cc=value['cc'], flags=value['flags'],
                installed_dependencies=value['installed_dependencies'], ghc_settings=value['ghc_settings'])
                for side,value in authenticated.items()}
            expected_base = manifest['before_input_sha256']
            for side, official in authenticated.items():
                actual = source_contract(official, sources[side])
                H.require(actual.keys() == expected_base.keys(), 'exact reviewed production source inventory')
                expected = dict(expected_base)
                if side == 'candidate':
                    expected.update(manifest['candidate_algorithm_sha256'])
                    expected = validation_contract.candidate_dependencies(expected, sources[side])
                    # The authenticated maintained generator independently checks
                    # this literal; allow only its one source-identity token.
                    expected[BUILTIN_PATH] = actual[BUILTIN_PATH]
                    H.require(C.sha_bytes(C.builtin_payload((sources[side]/BUILTIN_PATH).read_bytes())) ==
                              manifest['builtin_semantic_payload_sha256'], 'unchanged generated builtin payload')
                H.require(actual == expected, 'exact reviewed before/current production inputs: '+side)
                H.require(official['flags'].count('-O2') == 1 and '-prof' not in official['flags'], 'ordinary O2, no profiling')
                input_pins[str(producers[side]/'receipt.json')] = H.sha(producers[side]/'receipt.json')
                for helper in ['tools/shared/test_direct.py', 'tools/shared/build.py',
                               'tools/shared/verify_prepared_libraries.py']:
                    input_pins[str(sources[side]/helper)] = H.sha(sources[side]/helper)
                for category in ['shared_inputs', 'host_inputs', 'configuration_inputs', 'builtin_verification_helpers', 'outputs']:
                    for row in official[category].values():
                        input_pins[row['path']] = row['sha256']
            if not args.focused_only:
                for field in ['ghc', 'cc', 'ghc_settings', 'toolchain', 'installed_dependencies', 'package_database_sha256']:
                    H.require(authenticated['base'][field] == authenticated['candidate'][field], 'same toolchain/packages '+field)
            builtin = str(args.builtin_prefix.resolve()) if args.builtin_prefix else None
            record['shared_builtin_prefix'] = builtin
            if builtin:
                for suffix in ['.mlfci', '.mlfco']:
                    input_pins[builtin+suffix] = H.sha(builtin+suffix)
            record['inputs'] = input_pins
            record['host'] = H.host()
            record['builtin_admission_required'] = bool(builtin)
            record['builtin_admission_passed'] = False
            H.check_pins(input_pins)
            save()
            runner = H.Runner(out, manifest['limits'])
            object_sets, immutable, known_modules = {}, {}, {}

            def run(label, argv, cwd):
                command_out = out/label
                try:
                    row = runner.run(argv, cwd, command_out)
                except BaseException:
                    if (command_out/'command.json').exists():
                        record['commands'].append(H.load(command_out/'command.json'))
                        save()
                    raise
                record['commands'].append(row)
                save()
                return (command_out/'stdout').read_bytes(), (command_out/'stderr').read_bytes()

            def build(side, module, fresh, entry=None):
                source, producer, official = sources[side], producers[side], authenticated[side]
                folder = out/side
                objects = folder/'objects'
                if side not in object_sets:
                    folder.mkdir()
                    actual = {str(p.relative_to(producer/'objects')):H.sha(p)
                              for p in (producer/'objects').rglob('*') if p.is_file()}
                    H.require({'objects/'+p:h for p,h in actual.items()} == official['object_inputs'],
                              'complete authenticated ordinary object inventory')
                    shutil.copytree(producer/'objects', objects)
                    H.require({str(p.relative_to(objects)):H.sha(p) for p in objects.rglob('*') if p.is_file()} == actual,
                              'physical, byte-exact ordinary object copy')
                    object_sets[side] = actual
                    for suffix in ['.hi', '.o']:
                        (objects/('Main'+suffix)).unlink()
                    immutable[side] = H.file_pins(objects)
                    known_modules[side] = set()
                    for name, relative in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
                        rows = [r for r in official['commands'] if Path(r['log']).name == 'c-'+name+'.log']
                        wanted = [official['cc']['path'], '-O2', '-std=c11', '-I'+str(source/'runtime'), '-c', str(source/relative), '-o', str(producer/(name+'.o'))]
                        H.require(len(rows) == 1 and rows[0]['argv'] == wanted and rows[0]['exit_code'] == 0 and rows[0]['cwd'] == str(source), 'authenticated C object command')
                        shutil.copy2(producer/(name+'.o'), folder/(name+'.o'))
                        digest = H.sha(producer/(name+'.o'))
                        H.require(H.sha(folder/(name+'.o')) == digest, 'identical C object copy')
                        input_pins[str(producer/(name+'.o'))] = digest
                        immutable[side][str(folder/(name+'.o'))] = digest
                H.require(not (known_modules[side] & fresh), 'every declared fresh module compiles exactly once')
                for suffix in ['.hi', '.o']:
                    (objects/('Main'+suffix)).unlink(missing_ok=True)
                wrapper = folder/(module+'-Main.hs')
                if entry:
                    shutil.copy2(HERE/'entrypoints'/entry, wrapper)
                else:
                    wrapper.write_text('{-# OPTIONS_GHC -O0 #-}\nmodule Main where\nimport qualified '+module+' as Driver\nmain :: IO ()\nmain = Driver.main\n')
                input_pins[str(wrapper)] = H.sha(wrapper)
                binary = folder/module
                argv = compile_argv(official, source, producer, folder, wrapper, binary)
                so, se = run(side+'/build-'+module, argv, source)
                parsed = [(n, str(Path(p.strip()).resolve())) for n,p in re.findall(
                    r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)\s+\(\s*([^,\n]+),', (so+se).decode(), re.M)]
                expected = {n:str((A1/'current' if n == 'CurrentBuiltinControls' else HERE/'controls')/(n+'.hs')) for n in fresh}
                expected['Main'] = str(wrapper)
                H.require(len(parsed) == len(expected) and dict(parsed) == expected,
                          'exact declared control origins only; no production recompilation: '+repr(parsed))
                H.check_pins(immutable[side])
                known_modules[side] |= fresh
                immutable[side].update({str(p):H.sha(p) for p in objects.rglob('*')
                                      if p.is_file() and p.name not in ['Main.o', 'Main.hi']})
                return binary

            if builtin:
                for side in sources:
                    binary = build(side, 'CurrentBuiltinControls', {'CurrentBuiltinControls'})
                    so, se = run(side+'/builtin-execute', [binary, builtin], out)
                    H.require(so == BUILTIN_STDOUT and se == b'', 'full canonical builtin and seven malformed controls')
                record['builtin_admission_passed'] = True
                save()
            public = build('candidate', 'PublicControls', OLD_MODULES)
            record['public_controls'] = C.public_result(*run('public-execute', [public], out))
            save()
            transaction = build('candidate', 'C4TransactionControls', C4_MODULES, 'TransactionMain.hs')
            record['transaction_controls'] = C.transaction_result(*run('transaction-execute', [transaction], out))
            save()
            layout = build('candidate', 'HeteroinputControls', set(), 'HeteroinputMain.hs')
            record['heteroinput_controls'] = C.heteroinput_result(*run('heteroinput-execute', [layout], out), manifest)
            record['focused_graph_gate_passed'] = True
            save()
            if not args.focused_only:
                baseline_file = build('base', 'FileControls', {'FileControls'})
                candidate_file = build('candidate', 'FileControls', {'FileControls'})
                run_files(H, run, save, record, input_pins, out, builtin, baseline_file, candidate_file)
                record['nine_file_comparison_passed'] = True
            H.check_pins(input_pins)
            for side in sources:
                H.check_pins(immutable[side])
                H.require(H.authenticate(producers[side], sources[side]) == authenticated[side], 'producer unchanged after controls')
                H.require({str(p.relative_to(producers[side]/'objects')):H.sha(p)
                           for p in (producers[side]/'objects').rglob('*') if p.is_file()} == object_sets[side],
                          'original production object inventory unchanged')
            record.update(complete=True, immutable_inputs_verified_after=True,
                          all_controls_passed=not args.focused_only, full_gate_passed=not args.focused_only)
        except BaseException as error:
            record['error'] = repr(error)
            raise
        finally:
            record['outputs'] = {str(p):H.sha(p) for p in out.rglob('*')
                                 if p.is_file() and p != out/'receipt.json'}
            save()
        print('PASS C4 '+record['requested_scope']+' controls; no performance claim; receipt '+str(out/'receipt.json'))


def run_files(H, run, save, record, input_pins, out, builtin, baseline_file, candidate_file):
    """Nine authored files, same paths and builtin, complete raw byte comparison."""
    authored = H.load(HERE/'fixtures/file-cases.json')
    H.require(len(authored['cases']) == authored['case_count'] == 9, 'nine independent literal files')
    files_root = out/'files'
    files_root.mkdir()
    for case in authored['cases']:
        folder = files_root/case['name']
        folder.mkdir()
        sources, source_pins, missing = [], {}, []
        for module, contents in sorted(case['modules'].items()):
            path = folder/'src'/(module.replace('.', '/')+'.emlf')
            path.parent.mkdir(parents=True, exist_ok=True)
            if module not in case.get('missing_modules', []):
                path.write_text(contents)
                source_pins[str(path)] = H.sha(path)
            else:
                missing.append(str(path))
            sources.append((module, str(path)))
        input_pins.update(source_pins)
        outcomes, artifacts = [], []
        for side, binary in [('base', baseline_file), ('candidate', candidate_file)]:
            output = folder/side
            output.mkdir()
            cache, prefix, spec = output/'queries', output/'unit', output/'crate.spec'
            H.require(not os.path.lexists(cache), 'fresh parsed-file query directory')
            spec.write_text(pack(['MLF-CRATE-1', case.get('identity', 'session-control/'+case['name']),
                'Main', 'true', pack([pack(pair) for pair in sources]), pack([]), str(cache), builtin]))
            input_pins[str(spec)] = H.sha(spec)
            so, se = run(str(output.relative_to(out))+'/command', [binary, spec, prefix, case['expected_type']], output)
            H.require(se == b'', 'file controls stderr empty')
            row = dict(side=side, stdout=so.decode(), artifacts={}, query_report_sha256=None)
            if case['expected_type'] == 'reject':
                H.require(so.startswith(b'REJECT ') and so.endswith(b'\n') and so.count(b'\n') == 1, 'complete rejection')
                for fragment in case.get('required_error_fragments', []):
                    H.require(fragment.encode() in so, 'authored rejection fragment')
                exact = case.get('exact_error', case.get('exact_error_template'))
                if exact is not None:
                    for module, path in sources:
                        exact = exact.replace('{source:'+module+'}', path)
                    H.require(so == ('REJECT '+json.dumps(exact, ensure_ascii=False)+'\n').encode(), 'authored exact error')
                H.require(all(not os.path.lexists(str(prefix)+s) for s in ['.mlfci', '.mlfco']), 'rejection publishes no artifacts')
                artifacts.append({})
            else:
                H.require(so == ('PASS file checked '+case['expected_type']+'\n').encode(), 'handwritten checked type')
                report = H.load(str(prefix)+'.queries')
                H.require(type(report['inferred_groups']) is int and report['inferred_groups'] > 0 and
                    type(report['reused_groups']) is int and report['reused_groups'] == 0 and
                    len(report['groups']) == report['inferred_groups'] and all(g['cached'] is False for g in report['groups']),
                    'genuinely fresh parsed-file inference')
                actual_bytes = {s:Path(str(prefix)+s).read_bytes() for s in ['.mlfci', '.mlfco']}
                artifacts.append(actual_bytes)
                row.update(artifacts={s:C.sha_bytes(b) for s,b in actual_bytes.items()},
                    query_report_sha256=H.sha(str(prefix)+'.queries'),
                    groups=[{'id':g['id'], 'members':g['members']} for g in report['groups']],
                    inferred_groups=report['inferred_groups'], reused_groups=0)
            outcomes.append(row)
        H.require(outcomes[0]['stdout'] == outcomes[1]['stdout'] and artifacts[0] == artifacts[1],
                  'actual whole checked artifact bytes and complete diagnostics equal; no normalization')
        H.require(outcomes[0].get('groups') == outcomes[1].get('groups'), 'exact ordered source groups')
        H.check_pins(source_pins)
        H.require(all(not os.path.lexists(p) for p in missing), 'missing-file fixtures stayed absent')
        record['file_cases'].append(dict(name=case['name'], complete=True, outcomes=outcomes,
            actual_raw_artifact_bytes_equal=True,
            query_key_policy='raw reports retained; implementation-dependent keys are not an artifact equality oracle'))
        save()


if __name__ == '__main__':
    main()
