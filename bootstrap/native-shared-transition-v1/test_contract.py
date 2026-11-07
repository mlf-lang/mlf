#!/usr/bin/env python3
"""Static design/input checks only. Does not compile or qualify a bridge."""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import io
import json
import re
import tarfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE_HEAD = 'c34996ea87bb4d0e96dc21695c352551024d0982'
BASE_TREE = '7f5a711fb7a14636bbdfe8a9f5da029e9cbd1bb5'
ARCHIVE_SHA = 'c83bfa0801e1af0e042b6e2053eebf66af9b54b28cb8ed6f1f874483dfa4cbae'
ORACLE = 'tests/shared/Tests/IndependentCheck.hs'
ORACLE_SHA = '64800f6cf21e0d6dae65c02491ec4a56ce6a3f21056d73cd12c9693b45451757'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(name):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads((HERE / name).read_bytes(), object_pairs_hook=pairs)


def read_relative(root, name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and str(path) == name and
            all(part not in ('.', '..') for part in path.parts), 'relative input path')
    target = root / name
    require(all(not (root / Path(*path.parts[:i])).is_symlink()
                for i in range(1, len(path.parts) + 1)), 'input symlink')
    require(target.is_file(), 'missing ordinary input')
    return target.read_bytes()


def primitive_rows(raw):
    text = raw.decode()
    code_part = text.split('primitiveCode p =', 1)[1].split('primitiveName', 1)[0]
    name_part = text.split('primitiveName p =', 1)[1].split('lookup', 1)[0]
    codes = re.findall(r'\b(P\w+)\s*->\s*(\d+)\b', code_part)
    names = re.findall(r'\b(P\w+)\s*->\s*"([^"\n]+)"', name_part)
    require(len(dict(codes)) == len(codes) and len(dict(names)) == len(names),
            'duplicate primitive declaration')
    names = dict(names)
    require(set(dict(codes)) == set(names), 'primitive code/name sets')
    result = {int(code): (constructor, names[constructor]) for constructor, code in codes}
    require(len(result) == len(codes), 'duplicate primitive opcode')
    return result


def validate_inputs(value, root=ROOT):
    require(value['format'] == 'native-shared-transition-input-identities-v1', 'input format')
    require(value['source_commit'] == BASE_HEAD and value['source_tree'] == BASE_TREE,
            'exact design base')
    sources, metadata = value['source_files'], value['metadata_files']
    require(value['source_count'] == len(sources) == 196 and
            value['metadata_count'] == len(metadata) == 108 and
            not set(sources) & set(metadata), 'complete 196/108 inventories')
    require(sources.get(ORACLE) == ORACLE_SHA, 'independent oracle identity')
    for name, digest in {**sources, **metadata}.items():
        require(re.fullmatch('[0-9a-f]{64}', digest) is not None, 'SHA spelling')
        require(sha(read_relative(root, name)) == digest, 'input SHA: ' + name)
    shared = json.loads(read_relative(root, 'shared-sources.json'))
    modules = value['shared_modules']
    expected = {row['module']: {'path': row['path'], 'sha256': sources[row['path']]}
                for row in shared['modules']}
    require(len(modules) == 135 and modules == expected, 'complete shared registry')
    roots = value['compiler_manager_roots']
    require(roots == ['MLF.Entry.Emlf', 'MLF.Entry.Mlfpkg'], 'paired source roots')
    pending, seen = list(roots), set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        text = read_relative(root, modules[name]['path']).decode()
        pending += [n for n in re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)',
                                         text, re.M) if n in modules and n not in seen]
    require(len(seen) == 95 and sorted(seen) == value['compiler_manager_module_names'],
            'complete paired import closure')
    require(sum(len(read_relative(root, modules[n]['path'])) for n in seen) ==
            value['compiler_manager_source_bytes'] == 5396347, 'closure source bytes')
    frozen = value['frozen_bridge']
    require(frozen['archive_sha256'] == ARCHIVE_SHA, 'unchanged old archive pin')
    packed = read_relative(root, frozen['archive_path'])
    require(sha(packed) == ARCHIVE_SHA, 'unchanged old archive bytes')
    manifest = read_relative(root, frozen['manifest_path'])
    require(sha(manifest) == frozen['manifest_sha256'], 'frozen manifest SHA')
    manifest = json.loads(manifest)
    require(frozen['files'] == manifest['files'] and len(frozen['files']) ==
            frozen['file_count'] == 171, 'complete frozen input inventory')
    with tarfile.open(fileobj=io.BytesIO(packed), mode='r:gz') as archive:
        members = archive.getmembers()
        require(len(members) == 172 and len({m.name for m in members}) == 172 and
                all(m.isfile() for m in members) and sum(m.size for m in members) < 8*1024**2,
                'bounded regular archive members')
        require({m.name for m in members} == set(frozen['files']) | {'bridge-inputs.sha256'},
                'exact archive inventory')
        files = {m.name: archive.extractfile(m).read() for m in members}
    require(all(sha(files[name]) == digest for name, digest in frozen['files'].items()),
            'frozen input SHA')
    identity = value['active_identity']
    require(all(identity[k] == shared[k] for k in
                ('frontend_semantics', 'builtin_interface', 'primitive_abi')) and
            identity['lock_sha256'] == sources['mlf.lock'], 'active builtin/lock identity')
    return files


def validate_matrix(value, frozen, root=ROOT):
    require(value['format'] == 'native-shared-transition-primitive-matrix-v1', 'matrix format')
    old = frozen['libraries/mlf-language-core/Bootstrap/Primitive.emlf']
    current = read_relative(root, 'libraries/mlf-language-core/Bootstrap/Primitive.hs')
    require(sha(old) == value['old_source_sha256'] and
            sha(current) == value['current_source_sha256'], 'primitive source binding')
    old_rows, current_rows = primitive_rows(old), primitive_rows(current)
    require(set(old_rows) == set(range(95)) and set(current_rows) == set(range(132)),
            'complete primitive definitions')
    rows = value['rows']
    require(len(rows) == 132 and [row['code'] for row in rows] == list(range(132)),
            'complete ordered target matrix')
    require(value['old_host_primitive_count'] == 95 and value['target_primitive_count'] == 132,
            'host/target inventory size')
    for row in rows:
        code = row['code']
        require((row['constructor'], row['name']) == current_rows[code], 'target descriptor')
        require(row['old_host_available'] is (code < 95), 'host/target availability distinction')
        require(row['signature_and_semantics'] == 'requires_target_review',
                'no unproved semantic qualification')
        if code < 95:
            require(old_rows[code] == current_rows[code], 'retained opcode/name identity')


def validate_plan(plan):
    require(plan['format'] == 'native-shared-transition-plan-v1' and
            plan['status'] == 'design-only' and plan['bootstrap_qualified'] is False,
            'design is not qualification')
    require(plan['preferred_route'] == ['O', 'H', 'C'], 'explicit minimum route')
    stages = plan['stages']
    require(set(stages) == {'O', 'H', 'C'} and stages['H']['built_by'] == 'O' and
            stages['C']['built_by'] == 'H', 'stage parent identities')
    require(stages['H']['own_host_primitive_codes'] == [0, 94] and
            stages['H']['emitted_target_primitive_codes'] == [0, 131], 'host/target split')
    require(stages['H']['emitted_target_identity'] == {
        'source_commit': BASE_HEAD,
        'frontend_semantics': 'mlf-frontend/shared-haskell-v1/8',
        'builtin_interface': 'mlf-primitive/shared-haskell-v1/11',
        'primitive_abi': 'mlf-primitive-132-v7',
        'runtime_guards': ['mlf_require_haskell_boundary_v4_abi',
                           'mlf_require_byte_file_v2_abi']}, 'exact target generation')
    require(stages['H']['own_host_runtime'] == 'Exact O runtime' and
            'current' in stages['H']['emitted_target_runtime'], 'separate runtime edges')
    require('complete-original-manifest-scan-including-independent-oracle' in
            plan['required_prototype_gates'], 'complete manifest gate')
    require(plan['future_native_estimates']['measured'] is False and plan['open_questions'],
            'unmeasured construction and open proof obligations')


class TransitionDesignControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = load('input-identities.json')
        cls.matrix = load('primitive-matrix.json')
        cls.plan = load('plan.json')
        cls.frozen = validate_inputs(cls.inputs)

    def test_unchanged_complete_input_closure(self):
        validate_inputs(self.inputs)

    def test_all_132_descriptors_and_old_95_distinction(self):
        validate_matrix(self.matrix, self.frozen)

    def test_design_retains_unverified_boundaries(self):
        validate_plan(self.plan)

    def test_oracle_removal_refused(self):
        value = copy.deepcopy(self.inputs)
        del value['source_files'][ORACLE]
        with self.assertRaises(ValueError):
            validate_inputs(value)

    def test_oracle_change_refused(self):
        value = copy.deepcopy(self.inputs)
        value['source_files'][ORACLE] = '0' * 64
        with self.assertRaises(ValueError):
            validate_inputs(value)

    def test_unknown_current_source_hash_refused(self):
        value = copy.deepcopy(self.inputs)
        value['source_files']['libraries/mlf-frontend/Bootstrap/Lexer.hs'] = '0' * 64
        with self.assertRaises(ValueError):
            validate_inputs(value)

    def test_missing_metadata_refused(self):
        value = copy.deepcopy(self.inputs)
        value['metadata_files'].pop(next(iter(value['metadata_files'])))
        with self.assertRaises(ValueError):
            validate_inputs(value)

    def test_new_old_archive_pin_refused(self):
        value = copy.deepcopy(self.inputs)
        value['frozen_bridge']['archive_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            validate_inputs(value)

    def test_missing_target_primitive_refused(self):
        value = copy.deepcopy(self.matrix)
        value['rows'].pop()
        with self.assertRaises(ValueError):
            validate_matrix(value, self.frozen)

    def test_post94_primitive_not_claimed_as_old_host(self):
        value = copy.deepcopy(self.matrix)
        value['rows'][129]['old_host_available'] = True
        with self.assertRaises(ValueError):
            validate_matrix(value, self.frozen)

    def test_existing_opcode_semantics_not_assumed(self):
        value = copy.deepcopy(self.matrix)
        value['rows'][8]['signature_and_semantics'] = 'compatible'
        with self.assertRaises(ValueError):
            validate_matrix(value, self.frozen)

    def test_no_false_qualification(self):
        value = copy.deepcopy(self.plan)
        value['bootstrap_qualified'] = True
        with self.assertRaises(ValueError):
            validate_plan(value)

    def test_no_single_runtime_crossing(self):
        value = copy.deepcopy(self.plan)
        value['stages']['H']['own_host_runtime'] = 'Exact current runtime'
        with self.assertRaises(ValueError):
            validate_plan(value)

    def test_newer_target_not_implicitly_admitted(self):
        value = copy.deepcopy(self.plan)
        value['stages']['H']['emitted_target_identity']['primitive_abi'] = 'mlf-primitive-134-v9'
        with self.assertRaises(ValueError):
            validate_plan(value)

    def test_complete_manifest_gate_cannot_be_dropped(self):
        value = copy.deepcopy(self.plan)
        value['required_prototype_gates'].remove(
            'complete-original-manifest-scan-including-independent-oracle')
        with self.assertRaises(ValueError):
            validate_plan(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
