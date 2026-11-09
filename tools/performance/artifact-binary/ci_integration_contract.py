"""Exact four-file, three-owner CI-integration source successor.

All query-index and older contracts, manifests, deltas and evidence remain frozen.
Actual eight-fresh/fifty-one-reused generation and separate O0/O2 full typecheck-only
audits are recorded. No native runtime or full-CI qualification is claimed.
"""
from pathlib import Path
import copy
import hashlib
import os
import re
import stat
import types

INDEX_CONTRACT_SHA256 = '7e5dc443d3f8f0305122576fc58ae5dd87c4fdaa931630fdfb37e27164d23462'
INDEX_MANIFEST_SHA256 = '5289d668b8aae86409fca78e80e56f31e3a000c5f3a060f4dcf44a97a658b954'
INDEX_VALUE_SHA256 = '2b37c07dfda3bbde4ad779c454f39e7778c5194ccc8e6d3274fc93a262ed7137'
BASE_HEAD = 'd5e18cde20a6e0308a85fa219152363219c2ed6b'
BASE_TREE = '7f813ad30f6f0c8029f4a21a8b0a3c2c828837e4'
PARENT_INVENTORY_SHA256 = '34eab53906c266ccbd819f051df8da3fb315a36671523219f84b007f0adf8e94'
PARENT_REGISTRY_SHA256 = '24a3527efba157413cdae5657c28767f262120fc5493ec6b94e380411f27d011'
CURRENT_INVENTORY_SHA256 = '445572be92331b1ba280d7eef12174f4a9e337db1c30af18ea0abb1723679e69'
CURRENT_REGISTRY_SHA256 = '1d13d7f392c42a5a067faedc705015a5082ab6fb8e58c53b8b789bee068010f1'
PROVENANCE_VALUE_SHA256 = '69cd9ceeb7dd80c55447b3adba0fb11c28bcf30ea24a806881e48c09ab14c38a'
IDENTITIES = {'bootstrap/MLF/BuiltinPreludeData.hs': ('0e04f145d180c5b3b54f29bc4cb288ab59249be62ac58f346647df8c848f9679', '3840a53007599bed84eaabfac58b2d93423f61dadaa65d02e3c5c3eea65f08f9'), 'libraries/mlf-crates/Bootstrap/Crate.hs': ('2a5a614103afb126f8dc1ed7fe286ced827f9f87471eade176b1610a25768df1', 'e1248bc1a71625429b122f59f153cf7448d3c13d21764937bcb0c43e668b7ade'), 'libraries/mlf-crates/Bootstrap/OpenFragment.hs': ('b3d43f1a3a46b62107b0301e6278225c97dac4477c7c8bb21e981fc887933f4b', 'c1f6ee40041e9be3b8056bc1a9e03c539269cd1dcfec3ce69e717cfbf48948d7'), 'mlf.lock': ('79cb056a1456d4b3e94ef86d3dda7379b9614db2dbe8fae90965f8cdea77996e', '0323366b84ac8a85adcd5511f04ac296fbeaa3a77de707a217be62d1dd5b1f5b')}
NEW_IDENTITY = '208a79cd23693358d7624822110f2e44fd98cc9fd82270638c2ef08a0276564c'

INTEGRATION_BASE = {'head': 'a250ec334b70b0e587c2dd6e894d111bf879c024', 'tree': '63400c29c679ffc5e1a67b46ebbde12c5f81ddf4'}
FRESH_MODULES = ['Bootstrap.OpenFragment', 'Bootstrap.CrateArtifact', 'Bootstrap.InferenceUnit', 'Bootstrap.SourceInference', 'Bootstrap.BuiltinPreludeContext', 'Bootstrap.BuiltinPreludeLiteral', 'MLF.Entry.BuiltinPrelude', 'Main']
GENERATION_LABELS = ['compile-Bootstrap-OpenFragment', 'compile-Bootstrap-CrateArtifact', 'compile-Bootstrap-InferenceUnit', 'compile-Bootstrap-SourceInference', 'compile-Bootstrap-BuiltinPreludeContext', 'compile-Bootstrap-BuiltinPreludeLiteral', 'compile-MLF-Entry-BuiltinPrelude', 'compile-Main', 'link-generator', 'fresh-literal']
GUARD_NAMES = ['phase', 'root', 'terminal_phase', 'terminal_root', 'terminal_whole', 'whole']
TERMINAL_TRUE_FIELDS = ['complete', 'all_prior_history_unchanged', 'authenticated_inputs_unchanged', 'old_failed_attempt_unchanged', 'published_source_unchanged', 'original_three_locks_verified_by_bootstrap']
TOOLCHAIN_REFERENCE = {'format': 'authenticated-complete-toolchain-inventory-reference-v1', 'representation': 'Complete-inventory commitment to the preserved authenticated preparation receipt, not a copied public per-file inventory.', 'file_count': 1926, 'inventory_sha256': 'b6aa43d2399f722b788e24660078a450a2c3c97958bf2824cb34097e3c0bc52e', 'receipt': {'bytes': 4076023, 'sha256': '99d365c9100efea8c2a7cff673fd4a350f25ba151201898bd517ea773d9233b2', 'mode': 420}, 'inventory_field': 'toolchain_inputs', 'ghc': {'label': 'GHC_EXECUTABLE', 'version': '9.14.1', 'input': {'bytes': 736, 'mode': 493, 'sha256': '6b0b015104f88cb39030a2e2613dcda21ad449260183ff50d6ebec8a49efe711'}}}
CI_SOURCE_CHANGES = ['libraries/mlf-crates/Bootstrap/OpenFragment.hs', 'libraries/mlf-crates/Bootstrap/Crate.hs']
CI_SIGNATURE = b'  restoreFinals8 :: [] PackageFinalFields8 -> [] XTerm ->\n    Either String ([] ((,) String Fragment));\n'
CI_OPEN_ANCHOR = b'  restoreFinals8 prepared bodies = case prepared of {'
CI_INLINE = b'                   else case (case witness of {\n                     Just ((,) checked encoded) -> case Literal.checkedCrateObject checked encoded of {\n                       Right object -> Right object; Left _ -> Artifact.builtinPrelude\n                     };\n                     Nothing -> Artifact.builtinPrelude\n                   }) of {'
CI_CALL = b'                   else case builtinForInstall witness of {'
CI_HELPER = b'  builtinForInstall witness = case witness of {\n    Just ((,) checked encoded) -> case Literal.checkedCrateObject checked encoded of {\n      Right object -> Right object;\n      Left _ -> Artifact.builtinPrelude\n    };\n    Nothing -> Artifact.builtinPrelude\n  };\n'
CI_HELPER_ANCHOR = b'  withPrelude = withPreludeUsing ensureBuiltin;'

LITERAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
CHANGED_PATHS = set(IDENTITIES)
CHANGED_MODULES = {'MLF.BuiltinPreludeData': 'bootstrap/MLF/BuiltinPreludeData.hs', 'Bootstrap.Crate': 'libraries/mlf-crates/Bootstrap/Crate.hs', 'Bootstrap.OpenFragment': 'libraries/mlf-crates/Bootstrap/OpenFragment.hs'}
MANIFEST_NAME = 'ci-integration-migration.json'
PROVENANCE_NAME = 'ci-integration-provenance.json'
FORMAT = 'ci-integration-source-migration-v1'
VIEW_FORMAT = 'query-graph-with-writer-builtin-open-release-package-roots-query-index-and-ci-integration-source-v1'
SCOPE = 'Source identity and reversible projection with pinned actual generation and O0/O2 full typecheck-only evidence; no native runtime or full-CI qualification.'


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


_index_path = Path(__file__).resolve().parent / 'query_index_contract.py'
_index_raw = read_implementation(_index_path)
if hashlib.sha256(_index_raw).hexdigest() != INDEX_CONTRACT_SHA256:
    raise ValueError('fixed predecessor query-index contract implementation SHA')
_INDEX = types.ModuleType('fixed_ci_integration_predecessor_query_index_contract')
_INDEX.__file__ = str(_index_path)
exec(compile(_index_raw, str(_index_path), 'exec'), _INDEX.__dict__)
CURRENT_FIELDS = _INDEX.CURRENT_FIELDS | {'ci_integration_successor'}


def _materialize(predecessor, successor):
    value = copy.deepcopy(predecessor)
    value['format'] = VIEW_FORMAT
    value['source_base_head'], value['source_base_tree'] = successor['base_head'], successor['base_tree']
    value['ci_integration_successor'] = copy.deepcopy(successor)
    for path, row in successor['transition']['deltas'].items():
        value['current_files'][path] = row['new']
    for name, path in CHANGED_MODULES.items():
        value['current_registry'][name] = successor['transition']['deltas'][path]['new']
    value['current_inventory_sha256'] = successor['current_inventory_sha256']
    value['current_registry_sha256'] = successor['current_registry_sha256']
    return value


class Contract(_INDEX.Contract):
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        if not isinstance(manifest_sha256, str) or re.fullmatch('[0-9a-f]{64}', manifest_sha256) is None:
            raise ValueError('explicit ci-integration manifest SHA required')
        self._ci_manifest_sha256 = manifest_sha256
        self._initializing_ci = True
        super().__init__(directory, INDEX_MANIFEST_SHA256, history_root, source_root=source_root)
        self._initializing_ci = False
        self.manifest_sha256 = manifest_sha256
        self.query_index_metadata_paths = self.metadata_paths
        names = set(self.metadata_paths) | {'ci_integration_contract.py', MANIFEST_NAME, PROVENANCE_NAME}
        names.update(row['file'] for row in self.value['ci_integration_successor']['transition']['deltas'].values())
        self.metadata_paths = tuple(sorted(names))

    def _validate_ci_successor(self, successor):
        c = self._core
        c.require(type(successor) is dict and set(successor) == {
            'format', 'index_contract_sha256', 'index_manifest_sha256', 'index_value_sha256',
            'base_head', 'base_tree', 'integration_base', 'module_count', 'primitive_count', 'file_count',
            'parent_registry_sha256', 'parent_inventory_sha256', 'current_registry_sha256',
            'current_inventory_sha256', 'transition', 'evidence', 'qualification_scope'
        }, 'ci-integration manifest fields')
        expected = {
            'format': FORMAT, 'index_contract_sha256': INDEX_CONTRACT_SHA256,
            'index_manifest_sha256': INDEX_MANIFEST_SHA256, 'index_value_sha256': INDEX_VALUE_SHA256,
            'base_head': BASE_HEAD, 'base_tree': BASE_TREE,
            'integration_base': INTEGRATION_BASE,
            'parent_registry_sha256': PARENT_REGISTRY_SHA256,
            'parent_inventory_sha256': PARENT_INVENTORY_SHA256,
            'current_registry_sha256': CURRENT_REGISTRY_SHA256,
            'current_inventory_sha256': CURRENT_INVENTORY_SHA256, 'qualification_scope': SCOPE
        }
        c.require(all(successor[key] == value for key, value in expected.items()) and
                  all(type(successor[key]) is int and successor[key] == value
                      for key, value in [('module_count', 135), ('primitive_count', 132), ('file_count', 196)]),
                  'ci-integration identity / unchanged counts / scope')
        edge = successor['transition']
        c.require(type(edge) is dict and set(edge) == {'changed_paths', 'added_paths', 'deltas'} and
                  edge['changed_paths'] == sorted(CHANGED_PATHS) and edge['added_paths'] == [] and
                  type(edge['deltas']) is dict and set(edge['deltas']) == CHANGED_PATHS,
                  'exact four-file ci-integration transition')
        for path, row in edge['deltas'].items():
            c.require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                      c.is_sha(row['sha256']) and (row['old'], row['new']) == IDENTITIES[path],
                      'ci-integration delta identity')
        evidence = successor['evidence']
        c.require(type(evidence) is dict and set(evidence) == {'file', 'sha256'} and
                  evidence['file'] == PROVENANCE_NAME and c.is_sha(evidence['sha256']),
                  'ci-integration evidence reference')

    def _validate_manifest(self):
        c = self._core
        initializing = getattr(self, '_initializing_ci', False)
        if initializing:
            _INDEX.Contract._validate_manifest(self)
            raw = c.read_file(self.directory, MANIFEST_NAME, c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == self._ci_manifest_sha256, 'fixed ci-integration manifest SHA')
            successor = c.strict_json(raw)
            self._validate_ci_successor(successor)
            self.value = _materialize(self.value, successor)
            self._initializing_ci = False
        v = self.value
        c.require(type(v) is dict and set(v) == CURRENT_FIELDS and v['format'] == VIEW_FORMAT,
                  'ci-integration current view fields')
        successor = v['ci_integration_successor']
        self._validate_ci_successor(successor)
        c.hash_map(v['current_files'], 'ci-integration current files')
        c.hash_map(v['current_registry'], 'ci-integration current registry')
        c.require(CHANGED_PATHS <= set(v['current_files']) and
                  set(CHANGED_MODULES) <= set(v['current_registry']), 'ci-integration owner inventory')
        predecessor = copy.deepcopy(v)
        del predecessor['ci_integration_successor']
        predecessor['format'] = _INDEX.VIEW_FORMAT
        predecessor['source_base_head'], predecessor['source_base_tree'] = _INDEX.BASE_HEAD, _INDEX.BASE_TREE
        for path, row in successor['transition']['deltas'].items():
            predecessor['current_files'][path] = row['old']
        for name, path in CHANGED_MODULES.items():
            predecessor['current_registry'][name] = IDENTITIES[path][0]
        predecessor['current_inventory_sha256'] = PARENT_INVENTORY_SHA256
        predecessor['current_registry_sha256'] = PARENT_REGISTRY_SHA256
        c.require(c.canonical_sha(predecessor) == INDEX_VALUE_SHA256, 'complete unchanged predecessor query-index value')
        trial = object.__new__(_INDEX.Contract)
        trial._core, trial.frozen_value, trial.value = c, self.frozen_value, predecessor
        _INDEX.Contract._validate_manifest(trial)
        c.require(v == _materialize(predecessor, successor) and
                  c.canonical_sha(v['current_files']) == CURRENT_INVENTORY_SHA256 and
                  c.canonical_sha(v['current_registry']) == CURRENT_REGISTRY_SHA256 and
                  all(v['current_files'][path] == v['current_registry'][name]
                      for name, path in v['module_paths'].items()),
                  'exact complete ci-integration current source identity')
        self._validate_rows(successor['transition']['deltas'], CHANGED_PATHS,
                            predecessor['current_files'], v['current_files'], 'ci-integration-deltas/')
        self.query_index_value = predecessor
        self.package_roots_value = trial.package_roots_value
        self.open_release_value = trial.open_release_value
        self.builtin_value, self.writer_value, self.graph_value = trial.builtin_value, trial.writer_value, trial.graph_value
        if initializing:
            reference = successor['evidence']
            raw = c.read_file(self.directory, reference['file'], c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == reference['sha256'], 'fixed ci-integration evidence SHA')
            self.ci_integration_generation_evidence = c.strict_json(raw)
            self._validate_ci_provenance_record(self.ci_integration_generation_evidence)


    def _validate_ci_provenance_record(self, value):
        c = self._core
        c.require(type(value) is dict and c.canonical_sha(value) == PROVENANCE_VALUE_SHA256,
                  'complete reviewed actual CI-integration provenance')
        s, comparison = value['source'], value['comparison']
        c.require(s['base_head'] == BASE_HEAD and s['base_tree'] == BASE_TREE
                  and s['integration_base'] == INTEGRATION_BASE
                  and s['parent_value_sha256'] == INDEX_VALUE_SHA256
                  and s['identity'] == 'builtin-source-v1:' + NEW_IDENTITY
                  and c.canonical_sha(s['identity_inputs']) == NEW_IDENTITY
                  and comparison['old']['sha256'] == IDENTITIES[LITERAL][0]
                  and comparison['generated']['sha256'] == IDENTITIES[LITERAL][1],
                  'actual generation/source edge identity')
        c.require(set(s['overlay']) == CHANGED_PATHS
                  and s['production_changed_paths'] == sorted(CHANGED_PATHS)
                  and all(self.value['current_files'][p] == row['sha256']
                          for p, row in s['overlay'].items())
                  and all(self.value['current_files'][row['path']] == row['sha256']
                          for row in s['compiled_sources'].values())
                  and s['qualified_production_inventory_sha256'] == CURRENT_INVENTORY_SHA256,
                  'actual source/overlay/full production binding')
        c.require(value['collector'] == {
            'generation_body_complete': True, 'wrapper_complete': True,
            'full_compiler_build': False, 'optimization': '2',
            'fresh_compilation_count': 8, 'reused_compilation_count': 51,
            'total_compilation_closure': 59, 'nongenerated_module_count': 54,
            'generation_command_count': 10}, 'actual generator subsection counts and scope')
        fresh, reused = value['fresh_modules'], value['reused_modules']
        c.require(fresh == FRESH_MODULES and len(reused) == len(set(reused)) == 51
                  and set(fresh).isdisjoint(reused)
                  and set(fresh + reused) == set(s['compiled_sources']) == set(value['object_inputs'])
                  and 'Bootstrap.QueryGraph' in reused
                  and 'Bootstrap.Crate' not in s['compiled_sources']
                  and 'Bootstrap.Crate' not in s['identity_inputs']['modules']
                  and len(s['identity_inputs']['modules']) == 54,
                  'actual eight fresh/fifty-one reused partition')
        c.require(all(row['origin'] ==
                      ('fresh' if name in fresh else 'authenticated-parent-generation')
                      for name, row in value['object_inputs'].items()),
                  'actual object origins')
        commands = value['commands']
        c.require([row['label'] for row in commands] == GENERATION_LABELS
                  and len(commands) == 10
                  and all(row['complete'] is True and row['exit_code'] == 0
                          and row['reason'] is None and row['terminal_live_descendants'] == []
                          for row in commands)
                  and commands[-1]['argv'] == ['GENERATION/builtin-prelude', s['identity']]
                  and commands[-1]['stdout'] == comparison['generated']
                  and comparison['identity_only'] is True
                  and comparison['comparison_is_evidence_not_generation_substitute'] is True,
                  'ten actual generator commands and complete stdout')
        c.require(value['toolchain_inputs'] == TOOLCHAIN_REFERENCE
                  and value['toolchain_inputs']['receipt'] == value['preparation_receipt'],
                  'exact authenticated complete-toolchain inventory commitment')
        c.require(value['controls']['complete'] is True and value['controls']['methods'] == 7
                  and set(value['type_audits']) == {'0', '2'},
                  'controls and separate actual type audits')
        for mode, audit in value['type_audits'].items():
            c.require(audit['complete'] is True and audit['typecheck_only'] is True
                      and (audit['resolved_shared'], audit['inferred_shared'],
                           audit['resolved_host']) == (135, 135, 4)
                      and audit['objects_empty'] is True and audit['bin_empty'] is True
                      and audit['builtin_verification'] is None
                      and audit['command']['label'] == 'run-build'
                      and audit['command']['complete'] is True
                      and audit['command']['exit_code'] == 0,
                      'separate full typecheck-only audit ' + mode)
        c.require(value['qualification'] == {
            'runtime_equivalence': False, 'full_compiler_build': False,
            'native_runtime': False, 'full_ci': False, 'typecheck_only_modes': ['0', '2']},
            'actual full typecheck-only success, no native runtime/full-CI claim')
        c.require(all(value['terminal'][k] is True for k in TERMINAL_TRUE_FIELDS)
                  and set(value['guards']) == set(GUARD_NAMES)
                  and all(row['complete'] is True and row['exit_code'] == 0
                          and row['reason'] is None and row['remaining_descendants'] == []
                          and row['cleanup_errors'] == []
                          and row['cleanup_kernel_wait_no_children'] is True
                          for row in value['guards'].values()),
                  'actual independent terminal and clean guards')
        c.require(all(value['preservation'][k] is True for k in (
            'failed_attempt_stock_unchanged', 'published_source_unchanged',
            'all_prior_history_unchanged', 'authenticated_inputs_unchanged',
            'source_final_unchanged')), 'unchanged old evidence and qualified source')

    def _validate_index_provenance_record(self, value):
        # During ancestor initialization INDEX validates its own old value.
        # Afterwards use the authenticated old value, not the changed CI-integration sources.
        if getattr(self, '_initializing_ci', False):
            return _INDEX.Contract._validate_index_provenance_record(self, value)
        return self._index_proxy()._validate_index_provenance_record(value)

    def _index_proxy(self):
        trial = object.__new__(_INDEX.Contract)
        trial._core, trial.directory = self._core, self.directory
        trial.frozen_value, trial.value = self.frozen_value, self.query_index_value
        trial.package_roots_value = self.package_roots_value
        trial.open_release_value = self.open_release_value
        trial.builtin_value = self.builtin_value
        trial.writer_value, trial.graph_value = self.writer_value, self.graph_value
        return trial

    def _to_index(self, raw, path):
        c = self._core
        c.require(path in self.value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.value['current_files'][path], 'full ci-integration current path SHA: ' + path)
        rows = self.value['ci_integration_successor']['transition']['deltas']
        return self._apply(raw, path, rows, True) if path in rows else raw

    def _from_index(self, raw, path):
        c = self._core
        c.require(path in self.query_index_value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.query_index_value['current_files'][path], 'full predecessor query-index path SHA: ' + path)
        rows = self.value['ci_integration_successor']['transition']['deltas']
        return self._apply(raw, path, rows, False) if path in rows else raw


    def _to_roots(self, raw, path):
        return self._index_proxy()._to_roots(self._to_index(raw, path), path)

    def _from_roots(self, raw, path):
        return self._from_index(self._index_proxy()._from_roots(raw, path), path)

    def _to_open(self, raw, path):
        return self._index_proxy()._to_open(self._to_index(raw, path), path)

    def _from_open(self, raw, path):
        return self._from_index(self._index_proxy()._from_open(raw, path), path)

    def _to_builtin(self, raw, path):
        return self._index_proxy()._to_builtin(self._to_index(raw, path), path)

    def _to_writer(self, raw, path):
        return self._index_proxy()._to_writer(self._to_index(raw, path), path)

    def _to_frozen(self, raw, path):
        return self._index_proxy()._to_frozen(self._to_index(raw, path), path)

    def _from_frozen(self, raw, path):
        return self._from_index(self._index_proxy()._from_frozen(raw, path), path)


    def _validate_ci_sources(self, predecessor, current):
        c = self._core
        for path in CI_SOURCE_CHANGES:
            old, new = predecessor[path], current[path]
            c.require(type(old) is bytes and c.sha(old) == IDENTITIES[path][0]
                      and type(new) is bytes, 'exact CI-integration source inputs')
            if path.endswith('/OpenFragment.hs'):
                c.require(old.count(CI_OPEN_ANCHOR) == 1 and CI_SIGNATURE not in old
                          and new == old.replace(CI_OPEN_ANCHOR, CI_SIGNATURE + CI_OPEN_ANCHOR, 1),
                          'exact approved two-line restoreFinals8 signature')
            else:
                c.require(old.count(CI_INLINE) == 1 and old.count(CI_HELPER_ANCHOR) == 1
                          and new == old.replace(CI_INLINE, CI_CALL, 1).replace(
                              CI_HELPER_ANCHOR, CI_HELPER + CI_HELPER_ANCHOR, 1),
                          'exact PR33 helper extraction preserving binary writer')

    def _validate_ci_literal(self, predecessor_raw, current_raw):
        c = self._core
        c.require(type(predecessor_raw) is bytes and c.sha(predecessor_raw) == IDENTITIES[LITERAL][0] and
                  type(current_raw) is bytes, 'exact predecessor query-index literal')
        matches = list(re.finditer(rb'builtin-source-v1:([0-9a-f]{64})', predecessor_raw))
        c.require(len(matches) == 1 and matches[0].span(1) == (776, 840) and
                  matches[0].group(1) == _INDEX.NEW_IDENTITY.encode('ascii') and
                  len(predecessor_raw) == 2219103 and
                  current_raw == predecessor_raw[:776] + NEW_IDENTITY.encode('ascii') + predecessor_raw[840:],
                  'literal changed beyond actual generation identity-only delta')

    def _validate_ci_lock(self, predecessor_raw, current_raw):
        c = self._core
        c.require(type(predecessor_raw) is bytes and c.sha(predecessor_raw) == IDENTITIES['mlf.lock'][0],
                  'exact predecessor query-index lock')
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
                  'lock changed beyond exactly three source hashes')

    def _validate_metadata_transition(self, frozen, current):
        c = self._core
        c.require(type(current) is dict and CHANGED_PATHS <= set(current), 'ci-integration metadata inputs')
        predecessor = dict(current)
        for path in CHANGED_PATHS:
            predecessor[path] = self._to_index(current[path], path)
        self._validate_ci_sources(predecessor, current)
        self._validate_ci_literal(predecessor[LITERAL], current[LITERAL])
        self._validate_ci_lock(predecessor['mlf.lock'], current['mlf.lock'])
        self._index_proxy()._validate_metadata_transition(frozen, predecessor)
