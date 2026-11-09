#!/usr/bin/env python3
"""Retain PR33's exact historical branch beside the current binary source chain.

These are source identity, reversible projection and adapter controls.
They do not qualify current compiler runtime behavior or performance.
"""
from pathlib import Path
import copy
import hashlib
import json
import sys
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PERFORMANCE = ROOT / 'tools/performance'
OWNER = 'libraries/mlf-crates/Bootstrap/CrateSession.hs'
MODULE = 'Bootstrap.CrateSession'

UPSTREAM = 'a250ec334b70b0e587c2dd6e894d111bf879c024'
UPSTREAM_PARENT = 'c5928b5be73cd78d194405e734aa012415570e1a'
RECORDED_PR29 = 'c0fffea2b4175797157ed81676d349541724a0b2'

PARENT_REGISTRY = (
    '3843ccebb5581db27d6ec385a7e8f403e07acb9856712e7db9aa5a1106af0538')
PRELUDE_REGISTRY = (
    '7ad764d9834e1b19c767287660164d0adc81cb6a31cd78a4ebef4198bdef5195')
PARENT_SESSION = (
    '1210cfc8605bb8e45fd6801661175f892ebeddef561afa097b3fa3eafdde3c37')
PRELUDE_SESSION = (
    '2bc7f098613df7d744601647ef3b7fa983e5daacfe95e0adc43bd657604032d0')
COMMON_SESSION = (
    '51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9')

UPSTREAM_FILES = {
    'README.md':
        'c8706440395c8c7183fa1e19e4de6db54c8401302037f153afe89d2b803935bf',
    'results.json':
        'f6e6bfb858592fde5ac43ebaf29a42fb2eed05f9506801aef8209d3155c4b8a1',
    'source-migration.json':
        '4acb3a90757a375a423fda9db6eda022597f350d34090ca8f4712a478fa594f5',
    'source_contract.py':
        '7d75d46eb2bd3193f220698b3aeecac6848d3f0aac6b45bfedf8cc1366aac3a9',
}
RETAINED_ADAPTERS = {
    'a1-private-index/test_current.py':
        '49afb999c95477e458bd9c349cac3a560586cc29c93eec57e7d0d26046f9a776',
    'c3-delayed-index/run_controls.py':
        '3f289707a3f69bc78876bb9b3e9c27782ed2208b04d101dc03c4ead55ed620a8',
    'patricia/adapt_oracles.py':
        '45ce4b0fac779be59272e1a9ae377115c1c91a7e03f6acf77588c41aea40af0e',
    'patricia/run_integrated.py':
        '6cf6343a81b11f81c4f18c85f6e522a892a5e4cb194ca8d27316e4b8dd807a56',
    'patricia/source_migration.py':
        'e8f77e1eed83994b3b41d2906bdc41b46274119fafa63a1336902f233c7e7830',
    'patricia/test_adapters.py':
        'dd58bad7a75a80d6bc947abda2136ba60fafc078d6a5426d1afa3b42675982f1',
    'validation-reuse/test_contract.py':
        '72550841f8e04ca6e5ab6540f7771ae4b5809a5e7fb5e840d63d64599586625c',
}
FIXTURES = {
    # Exact upstream addition, including independently altered linked witness.
    'tools/shared/fixtures/item4/BuiltinArtifact.hs':
        '9aeac2ef85916721c43931941b9cf1fd435d9f4202a5ff6674b2fbd463fd25d5',
    # Exact PR29 fixture, retaining its binary/v7 and receipt-inventory coverage.
    'tools/shared/fixtures/item4/SourceSCC.hs':
        '68189ccf78a90b52c28a3173b6729b3b1cd82f74083b49c45da86003539718ff',
}
CHANGED_MODULES = {
    'Bootstrap.BuiltinPreludeContext',
    'Bootstrap.BuiltinPreludeLiteral',
    'Bootstrap.Crate',
    'Bootstrap.CrateSession',
    'MLF.BuiltinPreludeData',
    'MLF.Entry.BuiltinPrelude',
    'MLF.Entry.Emlf',
    'MLF.PreparedCompiler',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('retained crate Prelude branch: ' + message)


def checked_bytes(raw, expected, label):
    require(type(raw) is bytes and sha(raw) == expected, label)
    return raw


def read_pinned(path, expected):
    return checked_bytes(path.read_bytes(), expected, str(path))


def load_module(path, name, expected=None):
    raw = path.read_bytes()
    if expected is not None:
        checked_bytes(raw, expected, str(path))
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


def registry_sha(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return sha(raw)


def forward_session(parent, manifest):
    """Construct only the fixed historical PR33 session, never a live owner."""
    checked_bytes(parent, PARENT_SESSION, 'exact PR25 session before forward')
    result = parent
    for edit in manifest['session_edits']:
        old, new = edit['old'].encode(), edit['new'].encode()
        require(result.count(old) == 1, 'unique historical forward block')
        result = result.replace(old, new, 1)
    return checked_bytes(
        result, PRELUDE_SESSION, 'complete historical prepared25 session')


class CratePreludeBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Authenticate everything before loading the preserved implementations.
        for name, digest in UPSTREAM_FILES.items():
            read_pinned(HERE / name, digest)
        for name, digest in RETAINED_ADAPTERS.items():
            read_pinned(PERFORMANCE / name, digest)
        for name, digest in FIXTURES.items():
            read_pinned(ROOT / name, digest)

        cls.prelude = load_module(
            HERE / 'source_contract.py', 'retained_crate_prelude',
            UPSTREAM_FILES['source_contract.py'])
        cls.migration = load_module(
            PERFORMANCE / 'patricia/source_migration.py',
            'retained_prelude_binary_migration',
            RETAINED_ADAPTERS['patricia/source_migration.py'])
        cls.graph = load_module(
            PERFORMANCE / 'patricia/adapt_oracles.py',
            'retained_prelude_graph_adapter',
            RETAINED_ADAPTERS['patricia/adapt_oracles.py'])
        cls.driver = load_module(
            PERFORMANCE / 'c3-delayed-index/run_controls.py',
            'retained_prelude_private_driver',
            RETAINED_ADAPTERS['c3-delayed-index/run_controls.py'])

        cls.binary = cls.migration.binary_contract(source_root=ROOT)
        cls.live_registry = cls.binary.live_registry(ROOT)
        cls.binary.require_registry(cls.live_registry, 'current')
        cls.live_owner = (ROOT / OWNER).read_bytes()
        cls.prebinary_registry = cls.binary.registry_to_parent(
            cls.live_registry, cls.binary.added_source_bytes(ROOT))
        cls.prebinary_owner = cls.binary.project_owner(cls.live_owner, MODULE)

        cls.read_window = cls.migration.read_window_contract()
        cls.key_parts = cls.migration.key_parts_contract()
        cls.publication = cls.migration.publication_contract()
        cls.memo = cls.migration.memo_contract()
        cls.diamond = cls.migration.diamond_contract()

        registry = cls.prebinary_registry
        owner = cls.prebinary_owner
        for stage in (cls.read_window, cls.key_parts, cls.publication):
            registry = stage.registry_to_parent(registry)
            owner = stage.project_owner(owner, MODULE)
        registry = cls.memo.registry_to_parent(registry)
        owner = cls.memo.restore_previous_owner(owner, MODULE)

        cls.diamond_registry = registry
        cls.diamond_owner = owner
        cls.common_owner = cls.diamond.verify_diamond(owner)
        cls.parent_registry = cls.diamond.registry_to_parent(registry, 'right')
        cls.parent_owner = cls.diamond.to_right(owner)
        cls.branch_manifest = cls.prelude.manifest()
        cls.branch_registry = cls.prelude.advance_registry(cls.parent_registry)
        cls.branch_owner = forward_session(cls.parent_owner, cls.branch_manifest)

    def test_upstream_evidence_and_all_retained_files_are_exact(self):
        for name, digest in UPSTREAM_FILES.items():
            self.assertEqual(sha((HERE / name).read_bytes()), digest)
        for name, digest in RETAINED_ADAPTERS.items():
            self.assertEqual(sha((PERFORMANCE / name).read_bytes()), digest)
        for name, digest in FIXTURES.items():
            self.assertEqual(sha((ROOT / name).read_bytes()), digest)

        evidence = json.loads((HERE / 'results.json').read_bytes())
        self.assertEqual(evidence['pr25_head'], UPSTREAM_PARENT)
        self.assertEqual(evidence['pr29_head'], RECORDED_PR29)
        self.assertEqual(self.branch_manifest['parent'], UPSTREAM_PARENT)
        self.assertEqual(self.branch_manifest['module_count'], 128)
        self.assertEqual(
            set(self.branch_manifest['changed_sources']), CHANGED_MODULES)

    def test_actual_live_chain_meets_exact_upstream_parent(self):
        self.assertEqual(len(self.live_registry), 135)
        self.assertEqual(len(self.prebinary_registry), 128)
        self.assertEqual(len(self.parent_registry), 128)
        self.assertEqual(registry_sha(self.parent_registry), PARENT_REGISTRY)
        self.assertEqual(sha(self.parent_owner), PARENT_SESSION)
        self.assertEqual(sha(self.common_owner), COMMON_SESSION)

        base = json.loads(
            (PERFORMANCE / 'patricia/source-migration.json').read_bytes()
        )['old_sources']
        self.assertEqual(
            self.migration.migrate_to_read_window(base),
            self.prebinary_registry)
        self.assertEqual(
            self.migration.migrate(base), self.live_registry)

        full = self.diamond.contract('full-compiler')
        self.assertEqual(
            full.restore_previous_owner(self.parent_owner),
            self.common_owner)

    def test_branch_registry_has_exact_eight_owner_scope(self):
        self.assertEqual(registry_sha(self.branch_registry), PRELUDE_REGISTRY)
        self.assertEqual(len(self.branch_registry), 128)
        self.assertEqual(set(self.branch_registry), set(self.parent_registry))
        changed = {
            name for name in self.parent_registry
            if self.parent_registry[name] != self.branch_registry[name]
        }
        self.assertEqual(changed, CHANGED_MODULES)
        self.assertEqual(len(set(self.parent_registry) - changed), 120)
        for name, row in self.branch_manifest['changed_sources'].items():
            self.assertEqual(self.parent_registry[name], row['old'])
            self.assertEqual(self.branch_registry[name], row['new'])

    def test_branch_registry_rejects_mixed_repeated_and_unknown_sources(self):
        invalid = [
            dict(self.branch_registry),
            dict(self.live_registry),
            dict(self.prebinary_registry),
            {**self.parent_registry, 'Unexpected.Owner': '0' * 64},
        ]
        missing = dict(self.parent_registry)
        missing.pop(next(iter(missing)))
        invalid.append(missing)
        for name in self.parent_registry:
            altered = dict(self.parent_registry)
            altered[name] = '0' * 64
            invalid.append(altered)
        for name in CHANGED_MODULES:
            mixed = dict(self.parent_registry)
            mixed[name] = self.branch_registry[name]
            invalid.append(mixed)
        for index, registry in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(ValueError):
                self.prelude.advance_registry(registry)

    def test_branch_session_forward_inverse_and_common_ancestor(self):
        self.assertEqual(sha(self.branch_owner), PRELUDE_SESSION)
        restored = self.prelude.restore_session(self.branch_owner)
        self.assertEqual(restored, self.parent_owner)
        self.assertEqual(
            forward_session(restored, self.branch_manifest), self.branch_owner)
        self.assertEqual(
            self.diamond.contract('full-compiler').restore_previous_owner(
                restored),
            self.common_owner)

    def test_branch_session_rejects_live_prior_partial_and_corrupt_bytes(self):
        invalid = [
            self.live_owner,
            self.prebinary_owner,
            self.parent_owner,
            self.branch_owner + b' ',
            self.branch_owner[:-1],
        ]
        for edit in self.branch_manifest['session_edits']:
            new = edit['new'].encode()
            invalid.extend([
                self.branch_owner.replace(new, b'', 1),
                self.branch_owner + new,
            ])
        for index, raw in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(ValueError):
                self.prelude.restore_session(raw)

        for raw in (self.live_owner + b' ', self.branch_owner, self.parent_owner):
            with self.subTest(live_candidate=sha(raw)):
                with self.assertRaises(ValueError):
                    self.binary.project_owner(raw, MODULE)

    def test_pinned_metadata_cannot_define_replacement_expectations(self):
        original = (HERE / 'source-migration.json').read_bytes()
        changed = copy.deepcopy(self.branch_manifest)
        changed['parent_registry'] = '0' * 64
        for raw in (original + b' ', b'{}', json.dumps(changed).encode()):
            fake = types.SimpleNamespace(read_bytes=lambda raw=raw: raw)
            with patch.object(self.prelude, 'MANIFEST', fake):
                with self.assertRaises(ValueError):
                    self.prelude.manifest()

        for name, digest in UPSTREAM_FILES.items():
            original = (HERE / name).read_bytes()
            with self.subTest(file=name), self.assertRaises(ValueError):
                checked_bytes(original + b' ', digest, name)

    def test_even_in_memory_delta_corruption_fails_complete_roundtrip(self):
        for field in ('old', 'new'):
            damaged = copy.deepcopy(self.branch_manifest)
            damaged['session_edits'][0][field] += '\n'
            with patch.object(self.prelude, 'manifest', return_value=damaged):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.prelude.restore_session(self.branch_owner)

        damaged = copy.deepcopy(self.branch_manifest)
        damaged['session_edits'].pop()
        with patch.object(self.prelude, 'manifest', return_value=damaged):
            with self.assertRaises(ValueError):
                self.prelude.restore_session(self.branch_owner)

        for field in ('old', 'new'):
            damaged = copy.deepcopy(self.branch_manifest)
            damaged['changed_sources']['Bootstrap.Crate'][field] = '0' * 64
            with patch.object(self.prelude, 'manifest', return_value=damaged):
                with self.subTest(registry_field=field):
                    with self.assertRaises(ValueError):
                        self.prelude.advance_registry(self.parent_registry)

    def test_live_and_historical_private_headers_keep_distinct_roles(self):
        live_header = self.graph.LIVE_SESSION_HEADER.encode()
        old_header = self.driver.LEGACY_OWNER_HEADER
        self.assertEqual(self.live_owner.count(live_header), 1)
        self.assertEqual(self.parent_owner.count(old_header), 1)

        for role, raw, header in (
                ('CandidateSession', self.live_owner, live_header),
                ('LegacySession', self.parent_owner, old_header)):
            changed = self.driver.adapt_private_owner(raw, role, live_header)
            replacement = ('module ' + role + ' where {').encode()
            self.assertEqual(changed, raw.replace(header, replacement, 1))
            self.assertEqual(changed.replace(replacement, header, 1), raw)

        for role, raw in (
                ('CandidateSession', self.parent_owner),
                ('LegacySession', self.live_owner),
                ('CandidateSession', self.branch_owner),
                ('LegacySession', self.branch_owner)):
            with self.subTest(role=role, owner=sha(raw)):
                with self.assertRaises(RuntimeError):
                    self.driver.adapt_private_owner(raw, role, live_header)

        for export in (
                b', compileSpecFileWithPrelude',
                b', compileSpecFileWithVerification',
                b', compileSpecFileUsingInstaller'):
            malformed = self.live_owner.replace(
                live_header, live_header.replace(export, b''), 1)
            with self.subTest(missing=export):
                with self.assertRaises(RuntimeError):
                    self.driver.adapt_private_owner(
                        malformed, 'CandidateSession', live_header)


if __name__ == '__main__':
    unittest.main(verbosity=2)
