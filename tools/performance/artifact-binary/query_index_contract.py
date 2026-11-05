"""Exact QueryGraph dictionary-index source successor of the immutable root edge.

This three-file edge binds genuine generation with authenticated object reuse.
All ancestor manifests, deltas, failed-wrapper and recovery evidence are frozen.
Source projection is not runtime equivalence or full toolchain qualification.
"""
from pathlib import Path
import copy
import hashlib
import os
import re
import stat
import types

ROOTS_CONTRACT_SHA256 = '65402542a1e0b0fa58bfc1a11d25b2adf4951582eac56c58149a8405ef2918aa'
ROOTS_MANIFEST_SHA256 = '153cb1b7a10f473cebed5c60256481b00b70591c65f1e1c13926314434ff08f5'
ROOTS_VALUE_SHA256 = "60817957fd858410f766b45a23271d3e99f4410cab2e9a46e1d28433531c9bf5"
BASE_HEAD = '9ef905033caa654ca07507d8b5ac2363f3207269'
BASE_TREE = '5688ecefcfce0eaa9f79a4ddf39d122f35d8195a'
PARENT_INVENTORY_SHA256 = '0e19351adb45a3a71841f946a174505656299a8774a0f497333feebf23b730b7'
PARENT_REGISTRY_SHA256 = '0bc8a2934cc7b41d2d71e4ede119c4273dbe33bda79175253196939004790b93'
CURRENT_INVENTORY_SHA256 = "34eab53906c266ccbd819f051df8da3fb315a36671523219f84b007f0adf8e94"
CURRENT_REGISTRY_SHA256 = "24a3527efba157413cdae5657c28767f262120fc5493ec6b94e380411f27d011"
PROVENANCE_VALUE_SHA256 = "a7fb5ec76df013bb398e595fd5dc14294dcdd0be8be92664f6a373200dea19a5"
IDENTITIES = {"bootstrap/MLF/BuiltinPreludeData.hs": ("cec037c459cd0ef0eb057c1593268adf115492feb14d69f4dddcf0be3d860a36", "0e04f145d180c5b3b54f29bc4cb288ab59249be62ac58f346647df8c848f9679"), "libraries/mlf-crates/Bootstrap/QueryGraph.hs": ("e20aa382dfbaa0d3422d7d18b6417ffac5d511c897e7f949569ffa4b263f4990", "0a872320d3e59ce85db09fa5c04e3d168b4c172560396a8875e0a83ba47ff040"), "mlf.lock": ("3a845410aa2cd8cad95ab421e25d8d0dd0d045627a75ea675b3effd82e49f040", "79cb056a1456d4b3e94ef86d3dda7379b9614db2dbe8fae90965f8cdea77996e")}
NEW_IDENTITY = "0516e68cb23805681ee62d0aab4cc2f4ae6395b69acc68c0a5c1d558526cba58"

LITERAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
CHANGED_PATHS = set(IDENTITIES)
CHANGED_MODULES = {'Bootstrap.QueryGraph': 'libraries/mlf-crates/Bootstrap/QueryGraph.hs',
                   'MLF.BuiltinPreludeData': LITERAL}
MANIFEST_NAME = 'query-index-migration.json'
PROVENANCE_NAME = 'query-index-provenance.json'
FORMAT = 'query-index-source-migration-v1'
VIEW_FORMAT = 'query-graph-with-writer-builtin-open-release-package-roots-and-query-index-source-v1'
SCOPE = 'Source identity and reversible projection only; no new runtime or generation qualification.'


def read_implementation(path):
    """Bounded regular-file reader; never follow a file link or block on a FIFO."""
    descriptor = None
    try:
        if path.is_symlink():
            raise ValueError('source implementation symlink')
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                             getattr(os, 'O_NONBLOCK', 0))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise ValueError('source implementation regular-file / byte bound')
        raw = os.read(descriptor, 65537)
        if len(raw) > 65536:
            raise ValueError('source implementation grew past byte bound')
        return raw
    except OSError as error:
        raise ValueError('source implementation read failed') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


_roots_path = Path(__file__).resolve().parent / 'open_package_roots_contract.py'
_roots_raw = read_implementation(_roots_path)
if hashlib.sha256(_roots_raw).hexdigest() != ROOTS_CONTRACT_SHA256:
    raise ValueError('fixed predecessor package-roots contract implementation SHA')
_ROOTS = types.ModuleType('fixed_query_index_predecessor_package_roots_contract')
_ROOTS.__file__ = str(_roots_path)
exec(compile(_roots_raw, str(_roots_path), 'exec'), _ROOTS.__dict__)
CURRENT_FIELDS = _ROOTS.CURRENT_FIELDS | {'query_index_successor'}


def _materialize(predecessor, successor):
    value = copy.deepcopy(predecessor)
    value['format'] = VIEW_FORMAT
    value['source_base_head'], value['source_base_tree'] = successor['base_head'], successor['base_tree']
    value['query_index_successor'] = copy.deepcopy(successor)
    for path, row in successor['transition']['deltas'].items():
        value['current_files'][path] = row['new']
    for name, path in CHANGED_MODULES.items():
        value['current_registry'][name] = successor['transition']['deltas'][path]['new']
    value['current_inventory_sha256'] = successor['current_inventory_sha256']
    value['current_registry_sha256'] = successor['current_registry_sha256']
    return value


class Contract(_ROOTS.Contract):
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        if not isinstance(manifest_sha256, str) or re.fullmatch('[0-9a-f]{64}', manifest_sha256) is None:
            raise ValueError('explicit query-index manifest SHA required')
        self._index_manifest_sha256 = manifest_sha256
        self._initializing_index = True
        super().__init__(directory, ROOTS_MANIFEST_SHA256, history_root, source_root=source_root)
        self._initializing_index = False
        self.manifest_sha256 = manifest_sha256
        self.package_roots_metadata_paths = self.metadata_paths
        names = set(self.metadata_paths) | {'query_index_contract.py', MANIFEST_NAME, PROVENANCE_NAME}
        names.update(row['file'] for row in self.value['query_index_successor']['transition']['deltas'].values())
        self.metadata_paths = tuple(sorted(names))

    def _validate_index_successor(self, successor):
        c = self._core
        c.require(type(successor) is dict and set(successor) == {
            'format', 'roots_contract_sha256', 'roots_manifest_sha256', 'roots_value_sha256',
            'base_head', 'base_tree', 'module_count', 'primitive_count', 'file_count',
            'parent_registry_sha256', 'parent_inventory_sha256', 'current_registry_sha256',
            'current_inventory_sha256', 'transition', 'evidence', 'qualification_scope'
        }, 'query-index manifest fields')
        expected = {
            'format': FORMAT, 'roots_contract_sha256': ROOTS_CONTRACT_SHA256,
            'roots_manifest_sha256': ROOTS_MANIFEST_SHA256, 'roots_value_sha256': ROOTS_VALUE_SHA256,
            'base_head': BASE_HEAD, 'base_tree': BASE_TREE,
            'parent_registry_sha256': PARENT_REGISTRY_SHA256,
            'parent_inventory_sha256': PARENT_INVENTORY_SHA256,
            'current_registry_sha256': CURRENT_REGISTRY_SHA256,
            'current_inventory_sha256': CURRENT_INVENTORY_SHA256, 'qualification_scope': SCOPE
        }
        c.require(all(successor[key] == value for key, value in expected.items()) and
                  all(type(successor[key]) is int and successor[key] == value
                      for key, value in [('module_count', 135), ('primitive_count', 132), ('file_count', 196)]),
                  'query-index identity / unchanged counts / scope')
        edge = successor['transition']
        c.require(type(edge) is dict and set(edge) == {'changed_paths', 'added_paths', 'deltas'} and
                  edge['changed_paths'] == sorted(CHANGED_PATHS) and edge['added_paths'] == [] and
                  type(edge['deltas']) is dict and set(edge['deltas']) == CHANGED_PATHS,
                  'exact three-file query-index transition')
        for path, row in edge['deltas'].items():
            c.require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                      c.is_sha(row['sha256']) and (row['old'], row['new']) == IDENTITIES[path],
                      'query-index delta identity')
        evidence = successor['evidence']
        c.require(type(evidence) is dict and set(evidence) == {'file', 'sha256'} and
                  evidence['file'] == PROVENANCE_NAME and c.is_sha(evidence['sha256']),
                  'query-index evidence reference')

    def _validate_manifest(self):
        c = self._core
        initializing = getattr(self, '_initializing_index', False)
        if initializing:
            _ROOTS.Contract._validate_manifest(self)
            raw = c.read_file(self.directory, MANIFEST_NAME, c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == self._index_manifest_sha256, 'fixed query-index manifest SHA')
            successor = c.strict_json(raw)
            self._validate_index_successor(successor)
            self.value = _materialize(self.value, successor)
            self._initializing_index = False
        v = self.value
        c.require(type(v) is dict and set(v) == CURRENT_FIELDS and v['format'] == VIEW_FORMAT,
                  'query-index current view fields')
        successor = v['query_index_successor']
        self._validate_index_successor(successor)
        c.hash_map(v['current_files'], 'query-index current files')
        c.hash_map(v['current_registry'], 'query-index current registry')
        c.require(CHANGED_PATHS <= set(v['current_files']) and
                  set(CHANGED_MODULES) <= set(v['current_registry']), 'query-index owner inventory')
        predecessor = copy.deepcopy(v)
        del predecessor['query_index_successor']
        predecessor['format'] = _ROOTS.VIEW_FORMAT
        predecessor['source_base_head'], predecessor['source_base_tree'] = _ROOTS.BASE_HEAD, _ROOTS.BASE_TREE
        for path, row in successor['transition']['deltas'].items():
            predecessor['current_files'][path] = row['old']
        for name, path in CHANGED_MODULES.items():
            predecessor['current_registry'][name] = IDENTITIES[path][0]
        predecessor['current_inventory_sha256'] = PARENT_INVENTORY_SHA256
        predecessor['current_registry_sha256'] = PARENT_REGISTRY_SHA256
        c.require(c.canonical_sha(predecessor) == ROOTS_VALUE_SHA256, 'complete unchanged predecessor package-roots value')
        trial = object.__new__(_ROOTS.Contract)
        trial._core, trial.frozen_value, trial.value = c, self.frozen_value, predecessor
        _ROOTS.Contract._validate_manifest(trial)
        c.require(v == _materialize(predecessor, successor) and
                  c.canonical_sha(v['current_files']) == CURRENT_INVENTORY_SHA256 and
                  c.canonical_sha(v['current_registry']) == CURRENT_REGISTRY_SHA256 and
                  all(v['current_files'][path] == v['current_registry'][name]
                      for name, path in v['module_paths'].items()),
                  'exact complete query-index current source identity')
        self._validate_rows(successor['transition']['deltas'], CHANGED_PATHS,
                            predecessor['current_files'], v['current_files'], 'query-index-deltas/')
        self.package_roots_value = predecessor
        self.open_release_value = trial.open_release_value
        self.builtin_value, self.writer_value, self.graph_value = trial.builtin_value, trial.writer_value, trial.graph_value
        if initializing:
            reference = successor['evidence']
            raw = c.read_file(self.directory, reference['file'], c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == reference['sha256'], 'fixed query-index evidence SHA')
            self.query_index_generation_evidence = c.strict_json(raw)
            self._validate_index_provenance_record(self.query_index_generation_evidence)

    def _validate_index_provenance_record(self, value):
        # This is a new actual-generation summary, never a rewritten old receipt.
        c = self._core
        c.require(type(value) is dict and c.canonical_sha(value) == PROVENANCE_VALUE_SHA256,
                  'complete reviewed actual query-index generation summary')
        source, comparison = value['source'], value['comparison']
        c.require(source['base_head'] == BASE_HEAD and source['base_tree'] == BASE_TREE and
                  source['identity'] == 'builtin-source-v1:' + NEW_IDENTITY and
                  c.canonical_sha(source['identity_inputs']) == NEW_IDENTITY and
                  comparison['old']['sha256'] == IDENTITIES[LITERAL][0] and
                  comparison['generated']['sha256'] == IDENTITIES[LITERAL][1],
                  'actual generation evidence / query-index source edge')
        c.require(all(self.value['current_files'][row['path']] == row['sha256']
                      for row in source['compiled_sources'].values()) and
                  all(self.value['current_files'][path] == row['sha256']
                      for path, row in source['overlay'].items()),
                  'actual compiled source and overlay binding')
        collector, terminal = value['collector'], value['terminal']
        c.require(collector == {
            'generation_only': True, 'generation_body_complete': True,
            'wrapper_complete': True, 'full_compiler_build': False, 'optimization': '2',
            'fresh_compilation_count': 6, 'reused_compilation_count': 53,
            'total_compilation_closure': 59, 'nongenerated_module_count': 54},
            'actual six fresh and fifty-three reused generation closure')
        fresh, reused = value['fresh_modules'], value['reused_modules']
        c.require(fresh == ['Bootstrap.QueryGraph', 'Bootstrap.CrateArtifact',
                           'Bootstrap.BuiltinPreludeContext', 'Bootstrap.BuiltinPreludeLiteral',
                           'MLF.Entry.BuiltinPrelude', 'Main'] and
                  len(reused) == len(set(reused)) == 53 and
                  set(fresh).isdisjoint(reused) and
                  set(fresh + reused) == set(source['compiled_sources']) == set(value['object_inputs']),
                  'complete actual source and object partition')
        c.require(all(row['origin'] == ('fresh' if name in fresh else 'authenticated-parent-generation')
                      for name, row in value['object_inputs'].items()) and
                  set(value['c_objects']) == {'host.o', 'supervisor.o'} and
                  terminal['complete'] is True and terminal['actual_command_exits'] == [0] * 8 and
                  all(terminal[key] is True for key in ('authenticated_inputs_unchanged',
                      'frozen_source_unchanged', 'all_prior_history_unchanged',
                      'original_three_locks_reacquired')),
                  'actual link inputs and independent clean terminal verification')
        c.require(len(value['commands']) == 8 and
                  value['commands'][-1]['label'] == 'fresh-literal' and
                  value['commands'][-1]['argv'] == ['GENERATION/builtin-prelude', source['identity']] and
                  value['commands'][-1]['stdout'] == comparison['generated'] and
                  all(row['exit_code'] == 0 for row in value['commands']) and
                  comparison['identity_only'] is True and
                  comparison['comparison_is_evidence_not_generation_substitute'] is True and
                  all(row['complete'] is True and row['exit_code'] == 0 and
                      row['reason'] is None and row['cleanup_kernel_wait_no_children'] is True
                      for row in value['guards'].values()) and
                  set(value['guards']) == {'whole', 'root', 'phase', 'stage'},
                  'actual stdout, original eight successful commands and four terminal guards')

    def _validate_roots_provenance_record(self, value):
        # During ancestor initialization ROOTS validates its own old value.
        # Afterwards use the authenticated old value, not the changed QueryGraph.
        if getattr(self, '_initializing_index', False):
            return _ROOTS.Contract._validate_roots_provenance_record(self, value)
        return self._roots_proxy()._validate_roots_provenance_record(value)

    def _roots_proxy(self):
        trial = object.__new__(_ROOTS.Contract)
        trial._core, trial.directory = self._core, self.directory
        trial.frozen_value, trial.value = self.frozen_value, self.package_roots_value
        trial.open_release_value = self.open_release_value
        trial.builtin_value = self.builtin_value
        trial.writer_value, trial.graph_value = self.writer_value, self.graph_value
        return trial

    def _to_roots(self, raw, path):
        c = self._core
        c.require(path in self.value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.value['current_files'][path], 'full query-index current path SHA: ' + path)
        rows = self.value['query_index_successor']['transition']['deltas']
        return self._apply(raw, path, rows, True) if path in rows else raw

    def _from_roots(self, raw, path):
        c = self._core
        c.require(path in self.package_roots_value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.package_roots_value['current_files'][path], 'full predecessor package-roots path SHA: ' + path)
        rows = self.value['query_index_successor']['transition']['deltas']
        return self._apply(raw, path, rows, False) if path in rows else raw

    def _to_open(self, raw, path):
        return self._roots_proxy()._to_open(self._to_roots(raw, path), path)

    def _from_open(self, raw, path):
        return self._from_roots(self._roots_proxy()._from_open(raw, path), path)

    def _to_builtin(self, raw, path):
        return self._roots_proxy()._to_builtin(self._to_roots(raw, path), path)

    def _to_writer(self, raw, path):
        return self._roots_proxy()._to_writer(self._to_roots(raw, path), path)

    def _to_frozen(self, raw, path):
        return self._roots_proxy()._to_frozen(self._to_roots(raw, path), path)

    def _from_frozen(self, raw, path):
        return self._from_roots(self._roots_proxy()._from_frozen(raw, path), path)

    def _validate_index_literal(self, predecessor_raw, current_raw):
        c = self._core
        c.require(type(predecessor_raw) is bytes and c.sha(predecessor_raw) == IDENTITIES[LITERAL][0] and
                  type(current_raw) is bytes, 'exact predecessor package-roots literal')
        matches = list(re.finditer(rb'builtin-source-v1:([0-9a-f]{64})', predecessor_raw))
        c.require(len(matches) == 1 and matches[0].span(1) == (776, 840) and
                  matches[0].group(1) == _ROOTS.NEW_IDENTITY.encode('ascii') and
                  len(predecessor_raw) == 2219103 and
                  current_raw == predecessor_raw[:776] + NEW_IDENTITY.encode('ascii') + predecessor_raw[840:],
                  'literal changed beyond actual generation identity-only delta')

    def _validate_index_lock(self, predecessor_raw, current_raw):
        c = self._core
        c.require(type(predecessor_raw) is bytes and c.sha(predecessor_raw) == IDENTITIES['mlf.lock'][0],
                  'exact predecessor package-roots lock')
        expected = c.strict_json(predecessor_raw)
        seen = set()
        for package in expected['packages']:
            for name, digest in package['sources'].items():
                path = c.lock_path(package['path'], name)
                if path in CHANGED_PATHS - {'mlf.lock'}:
                    c.require(path not in seen and digest == IDENTITIES[path][0], 'unique predecessor lock owner')
                    package['sources'][name] = IDENTITIES[path][1]
                    seen.add(path)
        c.require(seen == CHANGED_PATHS - {'mlf.lock'} and c.strict_json(current_raw) == expected,
                  'lock changed beyond exactly two source hashes')

    def _validate_metadata_transition(self, frozen, current):
        c = self._core
        c.require(type(current) is dict and CHANGED_PATHS <= set(current), 'query-index metadata inputs')
        predecessor = dict(current)
        for path in CHANGED_PATHS:
            predecessor[path] = self._to_roots(current[path], path)
        self._validate_index_literal(predecessor[LITERAL], current[LITERAL])
        self._validate_index_lock(predecessor['mlf.lock'], current['mlf.lock'])
        self._roots_proxy()._validate_metadata_transition(frozen, predecessor)
