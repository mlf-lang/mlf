#!/usr/bin/env python3
"""Finite A1 controls against the explicitly reviewed current source schema.

Historical run_controls.py remains byte-identical for fixed-ref reproduction.
This runner shares its immutable control constants/helpers, not its source or
builtin byte-identity contract. See current/README.md for the migration proof.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import types

HERE = Path(__file__).resolve().parent
COMPATIBILITY = HERE / 'current/source-compatibility.json'
COMPATIBILITY_SHA256 = '44ce8da0daba21192d997b0167d89a07f0ebcedd057a044175b2ca6681b31bd2'
MIGRATION = HERE / 'current/source-migration-cf39.json'
MIGRATION_SHA256 = '4ebe8a70eb2cfe9072f43ed5c0b0c327e2ca155a45bef272a644632af7c3cf82'
QUERY_MIGRATION = HERE / 'current/source-migration-query-v6.json'
QUERY_MIGRATION_SHA256 = '1fa270c2f1b27be978b0bf796a20af89a9311d9b680389c3569c92798f0a6923'
if hashlib.sha256(COMPATIBILITY.read_bytes()).hexdigest() != COMPATIBILITY_SHA256:
    raise ValueError('previous A1 source compatibility anchor changed')
compatibility = json.loads(COMPATIBILITY.read_text())
historical_path = HERE / 'run_controls.py'
if hashlib.sha256(historical_path.read_bytes()).hexdigest() != compatibility['historical_runner_sha256']:
    raise ValueError('historical A1 control runner changed')
historical = types.ModuleType('frozen_a1_controls')
historical.__file__ = str(historical_path)
exec(compile(historical_path.read_bytes(), str(historical_path), 'exec'), historical.__dict__)
OWNER_SHA, KERNEL_SHA = historical.OWNER_SHA, historical.KERNEL_SHA
OLD_HEADER, NEW_HEADER = historical.OLD_HEADER, historical.NEW_HEADER
TEST_MODULES, CONTROL_HASHES = historical.TEST_MODULES, historical.CONTROL_HASHES
NEGATIVE_CASES = historical.NEGATIVE_CASES
req, sha, verify, save, files_below = (historical.req, historical.sha,
    historical.verify, historical.save, historical.files_below)
req(compatibility['format'] == 'a1-current-source-compatibility-v1' and
    compatibility['module_count'] == 126 and
    len(compatibility['changed_shared_inputs']) == 15 and
    len(compatibility['added_shared_inputs']) == 3 and
    compatibility['removed_shared_inputs'] == [], 'explicit reviewed source migration')
req(set(compatibility['changed_shared_inputs']) <= set(historical.SHARED_HASHES) and
    not (set(compatibility['added_shared_inputs']) & set(historical.SHARED_HASHES)),
    'source migration categories')
PREVIOUS_SHARED_HASHES = {**historical.SHARED_HASHES, **compatibility['changed_shared_inputs'],
                         **compatibility['added_shared_inputs']}
MIGRATED_MODULES = frozenset({'Bootstrap.BuiltinPreludeLiteral', 'Bootstrap.LLVM.Build',
    'Bootstrap.LLVM.Codegen', 'Bootstrap.PreparedLibraryLiteral', 'MLF.BuiltinPreludeData',
    'MLF.Entry.BuiltinPrelude'})
NEWLY_CHANGED_MODULES = frozenset({'Bootstrap.BuiltinPreludeLiteral',
    'Bootstrap.PreparedLibraryLiteral', 'MLF.Entry.BuiltinPrelude'})


def parse_migration(raw):
    # This is a reviewed source inventory, never an observed behavioral oracle.
    req(hashlib.sha256(raw).hexdigest() == MIGRATION_SHA256,
        'fixed cf39 source migration manifest changed')
    return json.loads(raw)


def migrate_source_hashes(base, value, prior_digest):
    metadata = {
        'format': 'a1-current-source-migration-v1',
        'from_ref': 'c4b0132aa9daeb068d6628e2668accb17078958d',
        'from_tree': 'ac3108587a5b2406efcf8d5586d9950c39eebe13',
        'to_ref': 'cf39c68ecb3bf861a7c910356684e01f014af1f0',
        'to_tree': 'f0bee12bb2bb457144ed7952b15162170b764ae7',
        'prior_compatibility_sha256': COMPATIBILITY_SHA256,
        'module_count': 126, 'unchanged_shared_input_count': 120,
        'historical_changed_count': 18, 'historical_added_count': 3,
        'added_shared_inputs': {}, 'removed_shared_inputs': []}
    req(isinstance(value, dict) and set(value) == set(metadata) | {'changed_shared_inputs'},
        'exact cf39 migration schema')
    req(all(value[name] == expected for name, expected in metadata.items()) and
        prior_digest == COMPATIBILITY_SHA256, 'exact cf39 migration refs, trees and base anchor')
    req(base == PREVIOUS_SHARED_HASHES and len(base) == 126,
        'exact previous 126-module source snapshot')
    delta = value['changed_shared_inputs']
    req(isinstance(delta, dict) and set(delta) == MIGRATED_MODULES,
        'exact six reviewed cf39 changed modules')
    result = dict(base)
    for name, row in delta.items():
        req(isinstance(row, dict) and set(row) == {'old', 'new'} and row['old'] == base[name],
            'exact previous source hash: ' + name)
        req(isinstance(row['new'], str) and re.fullmatch('[0-9a-f]{64}', row['new']) is not None and
            row['new'] not in (row['old'], '0' * 64), 'distinct valid target source hash: ' + name)
        result[name] = row['new']
    unchanged = set(base) - MIGRATED_MODULES
    req(len(unchanged) == 120 and all(result[name] == base[name] for name in unchanged),
        'other 120 shared inputs unchanged')
    changed = {name for name, digest in result.items()
               if name in historical.SHARED_HASHES and digest != historical.SHARED_HASHES[name]}
    added = set(result) - set(historical.SHARED_HASHES)
    req(changed == set(compatibility['changed_shared_inputs']) | NEWLY_CHANGED_MODULES and
        len(changed) == 18 and added == set(compatibility['added_shared_inputs']) and
        len(added) == 3 and len(result) == 126, 'explicit 18 changed plus three added projection')
    return result


migration = parse_migration(MIGRATION.read_bytes())
CF39_SHARED_HASHES = migrate_source_hashes(PREVIOUS_SHARED_HASHES, migration, sha(COMPATIBILITY))


def query_source_hashes(base, raw):
    # This exact committed source delta does not change any behavioral oracle.
    req(hashlib.sha256(raw).hexdigest() == QUERY_MIGRATION_SHA256,
        'fixed query-v6 source migration changed')
    value = json.loads(raw)
    req(base == CF39_SHARED_HASHES and len(base) == 126 and
        value['from_ref'] == migration['to_ref'] and
        value['from_tree'] == migration['to_tree'] and
        value['prior_migration_sha256'] == MIGRATION_SHA256,
        'exact cf39 base for query-v6 source migration')
    delta = value['changed_shared_inputs']
    req(set(delta) == {'Bootstrap.CrateQuery'} and
        value['module_count'] == 126 and value['unchanged_shared_input_count'] == 125 and
        value['added_shared_inputs'] == {} and value['removed_shared_inputs'] == [],
        'exact query-v6 source delta')
    result = dict(base)
    for name, row in delta.items():
        req(row['old'] == base[name] and row['new'] != row['old'],
            'exact prior query-v6 source input: ' + name)
        result[name] = row['new']
    return result


QUERY_SHARED_HASHES = query_source_hashes(CF39_SHARED_HASHES, QUERY_MIGRATION.read_bytes())
C4_MIGRATION = HERE / 'current/source-migration-c4.json'
C4_MIGRATION_SHA256 = '0cbe2a1ab0076f57aba13eabca9111bacdce1d05e5846df8208cf5510e46e4a4'
C4_NEW_HASHES = {
    'Bootstrap.Constraint': 'ec4520331a84a51a8e702fe027a7bd59d88d6219c7495779d96eec9acf9e3852',
    'Bootstrap.Graph.Solver': '482d1752c7e1a219f32841d7c609c69cc228c33dc4c4ffe5f645f434487af69f',
    'MLF.BuiltinPreludeData': '3659f0e24183e601d8b78392d6744c5d2c63137becdf47e5b52f359ecd1ddf95'}


def parse_c4_migration(raw):
    req(hashlib.sha256(raw).hexdigest() == C4_MIGRATION_SHA256,
        'fixed C4 source migration manifest changed')
    return json.loads(raw)


def migrate_c4_source_hashes(base, value, prior_digest):
    metadata = {
        'format': 'a1-current-source-migration-c4-query-v6-v1',
        'parent_ref': 'd96f67726599fa4e21f236462886106434c8e417',
        'prior_compatibility_sha256': COMPATIBILITY_SHA256,
        'prior_cf39_migration_sha256': MIGRATION_SHA256,
        'prior_migration_sha256': QUERY_MIGRATION_SHA256,
        'module_count': 126, 'unchanged_shared_input_count': 123,
        'added_shared_inputs': {}, 'removed_shared_inputs': [],
        'scope': 'C4 prepared-public representation compatibility only; original A1 private algorithm and all frozen expectations unchanged'}
    req(isinstance(value, dict) and set(value) == set(metadata) | {'changed_shared_inputs'},
        'exact C4 migration schema')
    req(all(value[name] == expected for name, expected in metadata.items()) and
        prior_digest == QUERY_MIGRATION_SHA256, 'exact C4 parent and prior query-v6 migration binding')
    req(base == QUERY_SHARED_HASHES and len(base) == 126, 'exact prior query-v6 source snapshot')
    delta = value['changed_shared_inputs']
    req(isinstance(delta, dict) and set(delta) == set(C4_NEW_HASHES),
        'exact three reviewed C4 source modules')
    result = dict(base)
    for name, expected in C4_NEW_HASHES.items():
        req(delta[name] == {'old': base[name], 'new': expected},
            'exact authored C4 old/new source hashes: ' + name)
        result[name] = expected
    req(len(set(base) - set(delta)) == 123 and
        all(result[name] == base[name] for name in set(base) - set(delta)),
        'other 123 source inputs unchanged')
    return result


c4_migration = parse_c4_migration(C4_MIGRATION.read_bytes())
C4_SHARED_HASHES = migrate_c4_source_hashes(QUERY_SHARED_HASHES, c4_migration, sha(QUERY_MIGRATION))
BALANCE_MIGRATION = HERE / 'current/source-migration-balance.json'
BALANCE_MIGRATION_SHA256 = '44e1aee620640e25f4453b553eb7a91e180fc7b3bfee2508c90eca9879eb798c'


def balance_source_hashes(base, raw):
    # Source admission only: original oracle bytes and expected results stay fixed.
    req(hashlib.sha256(raw).hexdigest() == BALANCE_MIGRATION_SHA256,
        'fixed map-balance source migration changed')
    value = json.loads(raw)
    req(base == C4_SHARED_HASHES and len(base) == 126 and
        value['prior_c4_migration_sha256'] == C4_MIGRATION_SHA256 and
        value['format'] == 'a1-map-balance-source-migration-v1' and
        value['base_ref'] == '51953cb8a61e755943eda95666746b2599ab2b9f',
        'exact qualified base for map-balance source migration')
    delta = value['changed_shared_inputs']
    req(set(delta) == {'Bootstrap.Map', 'MLF.BuiltinPreludeData'} and
        value['module_count'] == 126 and value['unchanged_shared_input_count'] == 124 and
        value['added_shared_inputs'] == {} and value['removed_shared_inputs'] == [],
        'exact map-balance and freshly regenerated Prelude source delta')
    result = dict(base)
    for name, row in delta.items():
        req(row['old'] == base[name] and row['new'] != row['old'],
            'exact prior map-balance source input: ' + name)
        result[name] = row['new']
    return result


SHARED_HASHES = balance_source_hashes(C4_SHARED_HASHES, BALANCE_MIGRATION.read_bytes())
CURRENT_MODULES = {'CurrentBuiltinControls', 'CurrentC4TransactionOracle', 'CurrentC4OracleControls'}
CURRENT_SOURCE_HASHES = {'CurrentBuiltinControls.hs': 'eb512024358872e69ce2df3b429a28ef6f12755c0c5d194147ddc36a627c944d', 'CurrentC4TransactionOracle.hs': '04819913a2b842aad5a20a3ec95f36755609b16b7ef5e7cae517e937e9f3c43a', 'CurrentC4OracleControls.hs': 'c92530ef213706972465b7d30fff0875fd8ccf6104d7fe190960ceecec3133da', 'c4_session_adapter.py': 'c3e5243e069b7d61eb6911b449c4b0308e0d31c252f9cbdf0067c2da5d2b25d8'}
CURRENT_BUILTIN_STDOUT = b'PASS current builtin: canonical literal, full check, exact wire, 7 malformed/mismatch rejections\n'
CURRENT_C4_STDOUT = b'PASS current C4 comparator: allowed reverse rebalance, exact errors, 13 authored rejections\n'


def load_c4_adapter(current):
    path = current / 'c4_session_adapter.py'
    req(sha(path) == CURRENT_SOURCE_HASHES[path.name], 'pinned C4 session adapter source')
    module = types.ModuleType('current_c4_session_adapter')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    module.verify_transaction_oracle((current / 'CurrentC4TransactionOracle.hs').read_bytes())
    return module


def current_fixture_pins(directory, manifest):
    req(manifest == CURRENT_SOURCE_HASHES, 'exact pinned current fixture/adapter source inventory')
    return {str(directory / relative): digest for relative, digest in manifest.items()}


def authenticate_current_source(value):
    req(value['optimization'] == '2' and set(value['resolved_modules']) == set(SHARED_HASHES) and
        set(value['inferred_shared_interfaces']) == set(SHARED_HASHES),
        'complete official O2 exact 126-module producer inventory')
    req({name: row['sha256'] for name, row in value['shared_inputs'].items()} == SHARED_HASHES,
        'exact reviewed current A1 production source snapshot')


def snapshot_builtin(prefix):
    # Observations are never sufficient for admission. CurrentBuiltinControls
    # below must validate decoded content against a fixed source oracle.
    observed = {suffix: sha(prefix + suffix) for suffix in ['.mlfci', '.mlfco']}
    req(observed != historical.BUILTIN_HASHES, 'historical builtin pair is not the current representation')
    return {prefix + suffix: digest for suffix, digest in observed.items()}


def require_builtin_result(code, stdout, stderr):
    req(code == 0 and stdout == CURRENT_BUILTIN_STDOUT and stderr == b'',
        'current builtin canonical-literal admission and malformed rejection')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--builtin-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, build = args.source_root.resolve(strict=True), args.producer.resolve(strict=True)
    out = args.output.resolve()
    req(not out.exists(), 'fresh output required; retain failures and choose a new directory')
    req(not source.is_relative_to(out) and not build.is_relative_to(out) and
        not out.is_relative_to(build), 'output must not contain source/producer or modify producer')
    runner = Path(__file__).resolve()
    req(runner == source / 'tools/performance/a1-private-index/run_current_controls.py', 'runner/source-root binding')
    controls = runner.parent / 'controls'
    pins = {str(controls / rel): digest for rel, digest in CONTROL_HASHES.items()}
    current = runner.parent / 'current'
    pins.update({str(COMPATIBILITY): COMPATIBILITY_SHA256, str(MIGRATION): MIGRATION_SHA256,
                 str(QUERY_MIGRATION): QUERY_MIGRATION_SHA256,
                 str(C4_MIGRATION): C4_MIGRATION_SHA256,
                 str(BALANCE_MIGRATION): BALANCE_MIGRATION_SHA256,
                 str(historical_path): sha(historical_path)})
    current_manifest = current / 'manifest.json'
    pins[str(current_manifest)] = sha(current_manifest)
    pins.update(current_fixture_pins(current, json.loads(current_manifest.read_text())))
    verify(pins)
    c4_adapter = load_c4_adapter(current)
    original_session = (controls / 'SessionTests.hs').read_bytes()
    adapted_session = c4_adapter.adapt_session(original_session)
    req((controls / 'session.expected.stdout').read_bytes().count(b'PASS ') == 6,
        'six original finite session groups')
    original_cases = json.loads((controls / 'file-cases.json').read_text())
    req(original_cases['case_count'] == len(original_cases['cases']) == 9, 'nine literal file cases')
    bp = build / 'receipt.json'
    auth_file = source / 'tools/shared/test_direct.py'
    auth = types.ModuleType('a1_official_producer_auth')
    auth.__file__ = str(auth_file)
    exec(compile(auth_file.read_bytes(), str(auth_file), 'exec'), auth.__dict__)

    def authenticate():
        value = auth.authenticate_build(bp, build / 'bin', root=source)
        authenticate_current_source(value)
        req(Path(value['build_driver']['path']) == source / 'tools/shared/build.py', 'producer source root')
        return value

    producer = authenticate()
    owner = source / 'libraries/mlf-crates/Bootstrap/CrateSession.hs'
    kernel = source / 'libraries/mlf-inference/Bootstrap/Graph/IndexStore.hs'
    req(sha(owner) == OWNER_SHA and sha(kernel) == KERNEL_SHA, 'exact controlled private implementation')
    raw = owner.read_bytes()
    req(raw.count(OLD_HEADER) == 1 and NEW_HEADER not in raw, 'sole sealed production header')
    copied_raw = raw.replace(OLD_HEADER, NEW_HEADER)
    req(copied_raw.count(NEW_HEADER) == 1 and copied_raw.replace(NEW_HEADER, OLD_HEADER) == raw,
        'byte-exact inverse of test-only module/export header change')
    links = [row for row in producer['commands'] if Path(row['log']).name == 'link-emlf.log']
    req(len(links) == 1 and links[0]['exit_code'] == 0 and links[0]['cwd'] == str(source),
        'one successful authenticated emlf link')
    prior = dict(argv=links[0]['argv'])
    expected_link = [producer['ghc']['path'], '--make', '-j1', *producer['flags'],
                     '-rtsopts=ignoreAll', str(source / 'host/ghc/app/emlf/Main.hs'),
                     str(build / 'host.o'), str(build / 'supervisor.o'), '-o', str(build / 'bin/emlf')]
    req(prior['argv'] == expected_link and producer['flags'].count('-i') == 1 and
        '-O2' in producer['flags'], 'unaltered maintained producer link and import-reset flags')
    inputs = {str(runner): sha(runner), str(auth_file): sha(auth_file), str(bp): sha(bp), **pins}
    for field in ['shared_inputs', 'host_inputs', 'configuration_inputs', 'builtin_verification_helpers']:
        for item in producer[field].values():
            inputs[item['path']] = item['sha256']
    inputs.update({item['path']: item['sha256'] for item in producer['outputs'].values()})
    object_baseline = files_below(build / 'objects')
    req({'objects/' + rel: digest for rel, digest in object_baseline.items()} == producer['object_inputs'],
        'exact complete authentic Haskell object inventory, without unexpected extras')
    inputs.update({str(build / 'objects' / rel): digest for rel, digest in object_baseline.items()})
    c_objects = {}
    for name, relative in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
        path = build / (name + '.o')
        rows = [row for row in producer['commands'] if Path(row['log']).name == 'c-' + name + '.log']
        expected = [producer['cc']['path'], '-O2', '-std=c11', '-I' + str(source / 'runtime'),
                    '-c', str(source / relative), '-o', str(path)]
        req(len(rows) == 1 and rows[0]['argv'] == expected and rows[0]['exit_code'] == 0 and
            rows[0]['cwd'] == str(source), 'authenticated C source/command/output binding: ' + name)
        req(path.is_file() and path.resolve() == path, 'regular resolved C object')
        c_objects[name + '.o'] = sha(path)
        inputs[str(path)] = c_objects[name + '.o']
    builtin_prefix = str(args.builtin_prefix.resolve())
    # These hashes detect mutation, not semantic validity or historical byte identity.
    # CurrentBuiltinControls must validate both bytes against the committed literal.
    builtin_pins = snapshot_builtin(builtin_prefix)
    inputs.update(builtin_pins)
    verify(inputs)
    contract = dict(expected_stdout=(controls / 'session.expected.stdout').read_text(),
                    admission_expected_stdout=(controls / 'admission.expected.stdout').read_text(),
                    materializer_stdout='PASS materialized nine independent parsed-file controls\n',
                    materializer_stderr='', admission_inventory=dict(hand_positive=8, exact_error=8,
                    counter_demand=3, local_ordering=3), negative_cases=[])
    for case in NEGATIVE_CASES:
        contract['negative_cases'].append({**case, 'source': str(controls / 'negative' / (case['name'] + '.hs'))})
    out.mkdir(parents=True)
    (out / 'tmp').mkdir()
    generated = out / 'test-source'
    generated.mkdir()
    test_copy = generated / 'SessionUnderTest.hs'
    test_copy.write_bytes(copied_raw)
    inputs[str(test_copy)] = sha(test_copy)
    req(test_copy.read_bytes().replace(NEW_HEADER, OLD_HEADER) == owner.read_bytes(), 'written copy inverse')
    save(out / 'test-copy-receipt.json', dict(complete=True, test_copy_not_production=True,
         original=str(owner), original_sha256=OWNER_SHA, copy=str(test_copy), copy_sha256=sha(test_copy),
         old_header=OLD_HEADER.decode(), new_header=NEW_HEADER.decode(),
         only_module_name_and_export_list_changed=True, byte_exact_inverse_verified=True))
    session_copy = generated / 'SessionTests.hs'
    session_copy.write_bytes(adapted_session)
    req(c4_adapter.restore_session(session_copy.read_bytes()) == original_session and
        (controls / 'SessionTests.hs').read_bytes() == original_session,
        'written C4 session copy inverse and frozen source unchanged')
    inputs[str(session_copy)] = sha(session_copy)
    save(out / 'c4-session-copy-receipt.json', dict(complete=True,
         original=str(controls / 'SessionTests.hs'), original_sha256=sha(controls / 'SessionTests.hs'),
         copy=str(session_copy), copy_sha256=sha(session_copy),
         adapter_sha256=sha(current / 'c4_session_adapter.py'),
         independent_oracle_sha256=c4_adapter.FROZEN_ORACLE_SHA256,
         only_one_prepared_public_comparator_changed=True,
         private_and_other_public_assertions_unchanged=True, byte_exact_inverse_verified=True))
    contract['module_sources'] = {name: str(controls / (name + '.hs'))
                                  for name in TEST_MODULES | {'FileMain', 'AdmissionTests'}}
    contract['module_sources']['SessionUnderTest'] = str(test_copy)
    contract['module_sources']['SessionTests'] = str(session_copy)
    contract['module_sources'].update({name: str(current / (name + '.hs')) for name in CURRENT_MODULES})
    objects = out / 'objects'
    shutil.copytree(build / 'objects', objects)
    req(files_below(objects) == object_baseline, 'exact authenticated production object copy')
    for suffix in ['.hi', '.o']:
        (objects / ('Main' + suffix)).unlink()
    immutable_objects = {str(p): sha(p) for p in objects.rglob('*') if p.is_file()}
    for name, digest in c_objects.items():
        shutil.copy2(build / name, out / name)
        inputs[str(out / name)] = digest
    # Preserve the original Linux UTF-8 control environment.
    env = {**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8',
           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MAKEFLAGS': '-j1',
           'TMPDIR': str(out / 'tmp'), 'PYTHONDONTWRITEBYTECODE': '1'}
    for key in list(env):
        if key.startswith('MLF_DIAGNOSTIC_'):
            del env[key]
    receipt = dict(complete=False, all_controls_passed=False, qualified=False, goal_evidence=False,
                   experimental_not_accepted=True, official_producer_authenticated=True,
                   production_owner_sha256=OWNER_SHA, inputs=inputs, test_copy_only=True,
                   candidate_output_used_for_expectations=False, commands=[], file_cases=[],
                   source_root=str(source), producer=str(build), shared_builtin_prefix=builtin_prefix,
                   format='current-a1-controls-v1', historical_ref_selected=False,
                   historical_builtin_identity_claimed=False,
                   source_compatibility_sha256=sha(COMPATIBILITY),
                   source_migration_sha256=sha(MIGRATION),
                   query_source_migration_sha256=sha(QUERY_MIGRATION),
                   c4_source_migration_sha256=sha(C4_MIGRATION),
                   balance_source_migration_sha256=sha(BALANCE_MIGRATION),
                   c4_representation_relation='Only reverse-map and reverse-bucket tree shape may differ; graph/aliases/counter/scopes physical; independent full edge/invariant/validator/finish checks on both',
                   builtin_provenance='Exact committed RawPrelude literal and canonical wire validation; pair hashes are immutable observations, not generated expectations',
                   c_object_provenance='Successful authenticated producer C commands, actual local hashes pinned before/after; producer schema does not itself store C object digests',
                   c_object_sha256=c_objects)
    save(out / 'receipt.json', receipt)
    def run(label, command, cwd=source):
        before = time.perf_counter_ns()
        with (out / (label + '.stdout')).open('wb') as so, (out / (label + '.stderr')).open('wb') as se:
            result = subprocess.run(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=so, stderr=se)
        row = dict(label=label, argv=command, cwd=str(cwd), exit_code=result.returncode,
                   process_wall_ns=time.perf_counter_ns() - before,
                   stdout_sha256=sha(out / (label + '.stdout')),
                   stderr_sha256=sha(out / (label + '.stderr')))
        receipt['commands'].append(row)
        save(out / 'receipt.json', receipt)
        return result.returncode, (out / (label + '.stdout')).read_bytes(), (out / (label + '.stderr')).read_bytes()

    def build_driver(module, wanted):
        wrapper = out / (module + '-Main.hs')
        wrapper.write_text('{-# OPTIONS_GHC -O0 #-}\nmodule Main where\n'
                           'import qualified ' + module + ' as Driver\n'
                           'main :: IO ()\nmain = Driver.main\n')
        inputs[str(wrapper)] = sha(wrapper)
        for suffix in ['.hi', '.o']:
            (objects / ('Main' + suffix)).unlink(missing_ok=True)
        command = []
        for token in prior['argv']:
            token = {str(build / 'objects'): str(objects),
                     str(build / 'host.o'): str(out / 'host.o'),
                     str(build / 'supervisor.o'): str(out / 'supervisor.o'),
                     str(build / 'bin/emlf'): str(out / module),
                     str(source / 'host/ghc/app/emlf/Main.hs'): str(wrapper)}.get(token, token)
            command.append(token)
            if token == '-i':
                command += ['-i' + str(generated), '-i' + str(current), '-i' + str(controls)]
        code, so, se = run('compile-' + module, command)
        req(code == 0, 'control compilation failed: ' + module)
        rows = re.findall(r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)\s+\(\s*([^,\n]+),',
                          (so + se).decode(), re.M)
        actual = {name: str((source / path.strip()).resolve()) for name, path in rows}
        expected = {name: contract['module_sources'][name] for name in wanted}
        expected['Main'] = str(wrapper)
        req(len(rows) == len(expected) and actual == expected, 'exact fresh control module closure')
        verify(immutable_objects)
        return out / module

    try:
        builtin_driver = build_driver('CurrentBuiltinControls', {'CurrentBuiltinControls'})
        code, so, se = run('current-builtin', [str(builtin_driver), builtin_prefix])
        require_builtin_result(code, so, se)
        receipt['builtin_controls_passed'] = True
        receipt['builtin_malformed_rejections'] = 7
        save(out / 'receipt.json', receipt)
        session_driver = build_driver('SessionTests', TEST_MODULES | {'CurrentC4TransactionOracle'})
        code, so, se = run('session-tests', [str(session_driver)])
        req(code == 0 and so == contract['expected_stdout'].encode() and se == b'',
            'six independent finite session groups')
        receipt['session_groups_passed'] = 6
        receipt['finite_trace_cases'] = 28
        save(out / 'receipt.json', receipt)
        c4_driver = build_driver('CurrentC4OracleControls', {'CurrentC4OracleControls'})
        code, so, se = run('current-c4-comparator', [str(c4_driver)])
        req(code == 0 and so == CURRENT_C4_STDOUT and se == b'',
            'complete C4 comparator positive/error/13 rejection controls')
        receipt['c4_comparator_controls_passed'] = True
        receipt['c4_comparator_rejections'] = 13
        save(out / 'receipt.json', receipt)
        admission_driver = build_driver('AdmissionTests', {'AdmissionTests'})
        code, so, se = run('admission-tests', [str(admission_driver)])
        req(code == 0 and so == contract['admission_expected_stdout'].encode() and se == b'',
            'independent direct-admission controls')
        receipt['admission_controls_passed'] = True
        receipt['admission_inventory'] = contract['admission_inventory']
        save(out / 'receipt.json', receipt)
        file_driver = build_driver('FileMain', {'FileMain'})
        files = out / 'files'
        code, so, se = run('materialize-files', [sys.executable, '-B', str(controls / 'materialize_file_cases.py'),
                                               '--output', str(files), '--builtin-prefix', builtin_prefix])
        req(code == 0 and so == contract['materializer_stdout'].encode() and
            se == contract['materializer_stderr'].encode(), 'authored file materialization')
        materialized = json.loads((files / 'materialized.json').read_text())
        req(materialized['complete'] and materialized['materialization_only'] and
            len(materialized['cases']) == 9, 'exact nine finite file cases')
        req(materialized['shared_builtin_prefix'] == builtin_prefix and
            materialized['shared_dependency_pins'] == builtin_pins, 'identical immutable dependency input')
        req([row['name'] for row in materialized['cases']] == [row['name'] for row in original_cases['cases']],
            'same ordered literal file case inventory')
        req(materialized['artifact_comparison_suffixes'] == ['.mlfci', '.mlfco', '.queries'],
            'all original exact artifact comparisons, no normalization')
        for case in materialized['cases']:
            verify(case['source_pins'])
            inputs.update(case['source_pins'])
            req(all(not Path(p).exists() for p in case['missing_sources']), 'authored missing source')
            outcomes = []
            for side in case['runs']:
                spec = Path(side['spec'])
                req(sha(spec) == side['spec_sha256'], 'authored spec bytes')
                inputs[str(spec)] = side['spec_sha256']
                req(list(Path(side['cache']).iterdir()) == [], 'each target cache begins empty')
                label = 'file-' + case['name'] + '-' + side['implementation']
                code, so, se = run(label, [str(file_driver), *side['argv']], files)
                req(code == 0 and se == b'', 'file control failed: ' + label)
                wanted = case['expected_type']
                if wanted == 'reject':
                    req(so.startswith(b'REJECT ') and so.endswith(b'\n') and so.count(b'\n') == 1,
                        'ordinary complete rejection line')
                    for fragment in case['required_error_fragments']:
                        req(fragment.encode() in so, 'handwritten error fragment')
                    if 'exact_error' in case:
                        req(so == ('REJECT ' + json.dumps(case['exact_error'], ensure_ascii=False) + '\n').encode(),
                            'handwritten exact rejection')
                    req(not Path(side['prefix'] + '.mlfci').exists() and
                        not Path(side['prefix'] + '.mlfco').exists(), 'no checked artifacts from rejection')
                    artifacts = {}
                else:
                    req(so == ('PASS file checked ' + wanted + '\n').encode(), 'handwritten file type oracle')
                    report = json.loads(Path(side['prefix'] + '.queries').read_text())
                    req(report['inferred_groups'] > 0 and report['reused_groups'] == 0 and
                        len(report['groups']) == report['inferred_groups'] and
                        all(not row['cached'] for row in report['groups']), 'every successful file group fresh')
                    artifacts = {suffix: sha(Path(side['prefix'] + suffix))
                                 for suffix in materialized['artifact_comparison_suffixes']}
                outcomes.append(dict(implementation=side['implementation'], stdout=so.decode(), artifacts=artifacts))
            req([x['implementation'] for x in outcomes] == ['old', 'session'] and
                outcomes[0]['stdout'] == outcomes[1]['stdout'] and
                outcomes[0]['artifacts'] == outcomes[1]['artifacts'], 'exact independent old/private file comparison')
            receipt['file_cases'].append(dict(name=case['name'], complete=True, outcomes=outcomes))
            save(out / 'receipt.json', receipt)
        object_pins = {str(p): sha(p) for p in objects.rglob('*') if p.is_file()}
        req(len(contract['negative_cases']) == 4, 'four sealed interface negatives')
        for case in contract['negative_cases']:
            target = out / ('negative-' + case['name'])
            target.mkdir()
            flags = []
            original_flags = iter(producer['flags'])
            for flag in original_flags:
                if flag in ['-odir', '-hidir']:
                    next(original_flags)
                    continue
                if flag == '-i' or flag.startswith('-i/'):
                    continue
                flags.append(flag)
            command = [producer['ghc']['path'], '-c', '-fno-code', '-fno-write-interface', *flags,
                       '-i', '-i' + str(objects), '-odir', str(target), '-hidir', str(objects),
                       '-ohi', str(target / (case['module'] + '.hi')), case['source']]
            code, so, se = run('negative-' + case['name'], command)
            diagnostic = (so + se).decode()
            compared = diagnostic.lower() if case.get('fragments_case_insensitive') else diagnostic
            fragments = [x.lower() if case.get('fragments_case_insensitive') else x
                         for x in case['required_error_fragments']]
            req(code == 1 and all(fragment in compared for fragment in fragments), 'intended interface rejection')
            req(len(re.findall(r'\berror:', diagnostic, re.I)) == case['expected_error_count'] and
                Path(case['source']).name in diagnostic, 'negative source and error count')
            req(not any(x in diagnostic.lower() for x in ['could not find module', 'panic!', 'internal error',
                                                          'parse error']), 'unrelated failure is not interface proof')
            verify(object_pins)
        verify(inputs)
        req(c4_adapter.restore_session(session_copy.read_bytes()) ==
            (controls / 'SessionTests.hs').read_bytes(), 'post-control frozen session inverse')
        verify(immutable_objects)
        authenticate()
        req(sha(owner) == OWNER_SHA and sha(kernel) == KERNEL_SHA, 'post-control source freeze')
        req(files_below(build / 'objects') == object_baseline, 'producer object inventory unchanged')
        receipt.update(complete=True, all_controls_passed=True, negative_cases_passed=4,
                       immutable_inputs_verified_after=True)
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        receipt['outputs'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file() and p != out / 'receipt.json'}
        save(out / 'receipt.json', receipt)
    print('PASS current A1 controls: 6 groups, 28 traces, 22 admission, 9 files, 4 seal negatives; no speed claim')


if __name__ == '__main__':
    main()
