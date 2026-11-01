"""Reject stale/malformed source admission without weakening frozen oracles."""
import copy
import importlib.util
import unittest
import tempfile
from pathlib import Path
import source_contract as C

ROOT = Path(__file__).resolve().parents[3]


def load_projection(path):
    spec = importlib.util.spec_from_file_location('retained_owner_projection', path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


def retained_owner(raw=None):
    source = (ROOT / C.OWNER).read_bytes() if raw is None else raw
    source = load_projection(ROOT / 'tools/performance/source-context-read-reuse/source_contract.py').restore_previous_owner(source)
    diamond = load_projection(ROOT / 'tools/performance/source-context-projection-merge/source_contract.py')
    diamond.verify_diamond(source)
    source = diamond.to_left(source)
    scratch = load_projection(ROOT / 'tools/performance/query-key-scratch/source_contract.py')
    source = scratch.restore_previous_owner(source)
    context = load_projection(ROOT / 'tools/performance/source-query-context/source_contract.py')
    source = context.restore_previous_owner(source)
    # Match run_integrated.py's validation source-proof projection. Each
    # reviewed context layer checks its fixed manifest and complete before/
    # after hashes; runtime candidate sources and frozen V1 expectations stay
    # untouched. Require the current full chain, not heuristic token removal.
    adapters = load_projection(ROOT / 'tools/performance/patricia/adapt_oracles.py')
    source = adapters.without_sparse_contracts(source)
    for family in ('contract-context', 'datatype-context'):
        contract = load_projection(ROOT / 'tools/performance' / family / 'source_contract.py')
        source = contract.restore_previous_owner(source)
    source = adapters.without_rank_view(source)
    if source.count(b'IntMapTree Node') != 3:
        raise ValueError('three explicit Patricia owner type signatures')
    source = source.replace(b'IntMapTree Node', b'Map Int Node')
    C.restore_previous_owner(source)
    return source

class SourceContractTests(unittest.TestCase):
    def test_complete_source_inverse(self):
        source = retained_owner()
        restored = C.restore_previous_owner(source)
        self.assertEqual(C.sha(restored), C.OLD_OWNER_SHA)
        rebuilt = restored
        for edit in C.manifest()['edits']:
            self.assertEqual(rebuilt.count(edit['old'].encode()), 1)
            rebuilt = rebuilt.replace(edit['old'].encode(), edit['new'].encode())
        self.assertEqual(rebuilt, source)

    def test_manifest_mutation_is_not_new_expectation(self):
        raw = C.MANIFEST.read_bytes()
        for changed in [raw + b' ', b'{}', raw.replace(C.OLD_OWNER_SHA.encode(), b'0' * 64)]:
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                C.manifest(changed)

    def test_old_or_partly_changed_owner_rejected(self):
        source = retained_owner()
        old = C.restore_previous_owner(source)
        edit = C.manifest()['edits'][0]
        for changed in [old, source + b' ', source.replace(edit['new'].encode(), edit['old'].encode())]:
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                C.restore_previous_owner(changed)

    def test_dependency_extension_preserves_other_fields(self):
        before = {C.OWNER: C.OLD_OWNER_SHA, C.CONSTRAINT: C.CONSTRAINT_SHA, 'untouched': 'kept'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owner = root / C.OWNER
            owner.parent.mkdir(parents=True)
            owner.write_bytes(retained_owner())
            self.assertEqual(C.candidate_dependencies(before, root), {**before, C.OWNER: C.NEW_OWNER_SHA})
            for key in [C.OWNER, C.CONSTRAINT]:
                changed = copy.deepcopy(before); changed[key] = '0' * 64
                with self.subTest(key=key), self.assertRaises(ValueError):
                    C.candidate_dependencies(changed, root)


    def test_reviewed_projection_chain_and_order_are_pinned(self):
        source = (ROOT / C.OWNER).read_bytes()
        source = load_projection(ROOT / 'tools/performance/source-context-read-reuse/source_contract.py').restore_previous_owner(source)
        diamond = load_projection(ROOT / 'tools/performance/source-context-projection-merge/source_contract.py')
        common = diamond.verify_diamond(source)
        projection = load_projection(ROOT / 'tools/performance/full-compiler/source_contract.py')
        incoming = diamond.to_right(source)
        self.assertEqual(C.sha(incoming), projection.NEW_SHA)
        self.assertEqual(projection.restore_previous_owner(incoming), common)
        source = diamond.to_left(source)
        scratch = load_projection(ROOT / 'tools/performance/query-key-scratch/source_contract.py')
        self.assertEqual(C.sha(source), scratch.NEW_SHA)
        source = scratch.restore_previous_owner(source)
        context = load_projection(ROOT / 'tools/performance/source-query-context/source_contract.py')
        self.assertEqual(C.sha(source), context.NEW_SHA)
        source = context.restore_previous_owner(source)
        survivors = load_projection(ROOT / 'tools/performance/c3-survivors/source_contract.py')
        self.assertEqual(C.sha(source), survivors.NEW_SHA)
        source = survivors.restore_previous_owner(source)
        c3 = load_projection(ROOT / 'tools/performance/c3-delayed-index/source_contract.py')
        self.assertEqual(C.sha(source), c3.NEW_SHA)
        source = c3.restore_previous_owner(source)
        self.assertEqual(C.sha(source), '18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f')
        # These are the already-frozen session-delta before hashes, not new
        # expectations derived from the current owner.
        stages = (
            ('sparse-contracts', 'c97410642e2c86c7bc84436492a284c51291d617e1be0e262716275e5997a23d'),
            ('contract-context', '1d837ed6dfb21a54d78e491dc90b24c42e11e702bec53dd72d85f2f291d305b6'),
            ('datatype-context', 'da9727970cf184031b547c5c877a083a31d43bbaf03d4a1e647f7f49be38d88b'),
        )
        for family, _ in stages[1:]:
            contract = load_projection(ROOT / 'tools/performance' / family / 'source_contract.py')
            with self.subTest(out_of_order=family), self.assertRaises(ValueError):
                contract.restore_previous_owner(source)
        for family, expected in stages:
            contract = load_projection(ROOT / 'tools/performance' / family / 'source_contract.py')
            source = contract.restore_previous_owner(source)
            self.assertEqual(C.sha(source), expected)
        adapters = load_projection(ROOT / 'tools/performance/patricia/adapt_oracles.py')
        source = adapters.without_rank_view(source)
        self.assertEqual(source.count(b'IntMapTree Node'), 3)
        source = source.replace(b'IntMapTree Node', b'Map Int Node')
        self.assertEqual(C.sha(source), C.NEW_OWNER_SHA)
        self.assertEqual(source, retained_owner())

    def test_unknown_owner_edits_and_partial_projection_rejected(self):
        source = (ROOT / C.OWNER).read_bytes()
        adapters = load_projection(ROOT / 'tools/performance/patricia/adapt_oracles.py')
        partial = adapters.without_sparse_contracts(source)
        for changed in (source + b' ', source.replace(b'Rank.MapIndex Node', b'IntMapTree Node', 1), partial):
            self.assertNotEqual(changed, source)
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                retained_owner(changed)

    def test_context_projection_manifests_are_not_new_expectations(self):
        for family in ('query-key-scratch', 'source-query-context', 'sparse-contracts', 'contract-context', 'datatype-context'):
            original = ROOT / 'tools/performance' / family
            raw = (original / 'session-delta.json').read_bytes()
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                module = root / 'source_contract.py'
                module.write_bytes((original / 'source_contract.py').read_bytes())
                adapter = load_projection(module)
                self.assertEqual(adapter.HERE, root.resolve())
                for changed in (raw + b' ', b'{}', raw.replace(b'"new_sha256"', b'"not_the_owner"')):
                    self.assertNotEqual(changed, raw)
                    (root / 'session-delta.json').write_bytes(changed)
                    with self.subTest(family=family, size=len(changed)), self.assertRaises(ValueError):
                        adapter.manifest()


if __name__ == '__main__':
    unittest.main()
