#!/usr/bin/env python3
"""Pure adapter-edge controls; no Git, contract construction or compilation."""
from pathlib import Path
import copy
import hashlib
import json
import types
import unittest

import reconciliation_contract as C

HERE = Path(__file__).resolve().parent
OLD = b"LIVE_SESSION_HEADER = 'module Bootstrap.CrateSession (compileSpecFile, compileSpecFileWithPrelude, compileSpecFileWithVerification, compileSpecFileUsingInstaller) where {'"
NEW = b"LIVE_SESSION_HEADER = 'module Bootstrap.CrateSession (compileSpecFile, compileSpecFileWithPrelude, compileSpecFileWithVerification, compileSpecFileUsingInstaller,\\n    CompiledCrate, compiledObject, compiledInterfaces, compileSpecFileRetainedUsingInstaller) where {'"

COLD_CRATES = NEW.replace(
    b'compiledInterfaces, compileSpecFileRetainedUsingInstaller)',
    b'compiledInterfaces, compiledMetadata, PlanInputs(..), compilerImageDigest,\\n'
    b'    compileSpecFileRetainedUsingInstaller, compileSpecFileRetainedInPlan)')
BEFORE_COLD = '92871acb93f9c742910b6dfb224bda86e292d2214718be50fdb172b434f65820'
AFTER_COLD = 'e5ad567b3baecc736190708899cd2579b142a2ec2cd576efcbf5e0f985b52781'


def before_cold_crates(raw):
    if hashlib.sha256(raw).hexdigest() != AFTER_COLD or raw.count(COLD_CRATES) != 1 or NEW in raw:
        raise ValueError('unexpected cold-crates adapter bytes')
    previous = raw.replace(COLD_CRATES, NEW)
    if hashlib.sha256(previous).hexdigest() != BEFORE_COLD or previous.replace(NEW, COLD_CRATES) != raw:
        raise ValueError('historical adapter inverse')
    return previous


def fixtures():
    live = json.loads((HERE / 'pr43-reconciliation-migration.json').read_bytes())
    spec = C.adapter_endpoint(live)
    current = before_cold_crates((HERE.parent / 'patricia/adapt_oracles.py').read_bytes())
    prior = copy.deepcopy(spec)
    del prior['adapter_successor']
    del prior['maintenance']['patricia/adapt_oracles.py']
    prior_raw = (json.dumps(prior, indent=2, sort_keys=True) + '\n').encode()
    # Independent fixed hashes in the tests and validator authenticate both
    # reconstructed old inputs; candidates cannot define their own predecessor.
    old_source = current.replace(NEW, OLD)
    return spec, prior_raw, old_source, current


class AdapterSuccessorTests(unittest.TestCase):
    def check(self, values, tree='eec52972c0028a7f1d20da0ac15f867664c2c918'):
        return C.validate_adapter_successor(*values, tree, types.SimpleNamespace(strict_json=json.loads))

    def test_exact_frozen_endpoint_and_single_reversible_edit(self):
        values = fixtures(); spec, prior_raw, old, current = values
        self.assertEqual(C.ADAPTER_BASE, '08a08aa98c01f4f07b6efb01a250a0d86f387811')
        self.assertEqual(C.ADAPTER_PATH, 'patricia/adapt_oracles.py')
        self.assertEqual(C.ADAPTER_OLD_DECLARATION, OLD)
        self.assertEqual(C.ADAPTER_NEW_DECLARATION, NEW)
        self.assertEqual(hashlib.sha256(prior_raw).hexdigest(), '82b9b045993ff9ac2d14a5b67dbfd35288004a79ae08303a1047f81de438d009')
        self.assertEqual(hashlib.sha256(old).hexdigest(), '45ce4b0fac779be59272e1a9ae377115c1c91a7e03f6acf77588c41aea40af0e')
        self.assertEqual(current, old.replace(OLD, NEW))
        self.assertEqual(self.check(values), json.loads(prior_raw))
        self.assertEqual(spec['maintenance']['patricia/adapt_oracles.py'],
                         ['45ce4b0fac779be59272e1a9ae377115c1c91a7e03f6acf77588c41aea40af0e', hashlib.sha256(current).hexdigest()])

    def test_rejects_wrong_tree_and_historical_bytes(self):
        with self.assertRaises(ValueError): self.check(fixtures(), '0' * 40)
        for index in (1, 2):
            values = list(fixtures()); values[index] += b' '
            with self.subTest(index=index), self.assertRaises(ValueError): self.check(values)

    def test_rejects_stale_duplicate_missing_and_nonheader_current_edits(self):
        original = fixtures()
        current = original[3]
        variants = [original[2], current + b' ', current + NEW,
                    current.replace(NEW, b''), current.replace(NEW, NEW.replace(b'CompiledCrate, ', b'')),
                    current.replace(NEW, NEW.replace(b'\\n    ', b' ')),
                    current.replace(b'binary_contract(root).live_registry(root)', b'pass')]
        for raw in variants:
            values = list(original); values[3] = raw
            with self.subTest(source=hashlib.sha256(raw).hexdigest()), self.assertRaises(ValueError): self.check(values)

    def test_rejects_extra_paths_broken_endpoints_and_unrelated_metadata(self):
        for mutation in ('missing', 'extra', 'old', 'new', 'top-first', 'top-new',
                         'base', 'tree', 'manifest', 'production', 'other-maintenance', 'other-field'):
            values = list(fixtures()); spec = values[0]; edge = spec['adapter_successor']
            name = 'patricia/adapt_oracles.py'
            if mutation == 'missing': del edge['maintenance'][name]
            elif mutation == 'extra': edge['maintenance']['patricia/run_integrated.py'] = edge['maintenance'][name][:]
            elif mutation == 'old': edge['maintenance'][name][0] = '0' * 64
            elif mutation == 'new': edge['maintenance'][name][1] = '0' * 64
            elif mutation == 'top-first': spec['maintenance'][name][0] = '0' * 64
            elif mutation == 'top-new': spec['maintenance'][name][1] = '0' * 64
            elif mutation == 'base': edge['predecessor'] = '0' * 40
            elif mutation == 'tree': edge['predecessor_tree'] = '0' * 40
            elif mutation == 'manifest': edge['predecessor_manifest_sha256'] = '0' * 64
            elif mutation == 'production': spec['changes']['libraries/mlf-crates/Bootstrap/CrateSession.hs'][1] = '0' * 64
            elif mutation == 'other-maintenance': spec['maintenance']['patricia/test_adapters.py'][1] = '0' * 64
            else: spec['unexpected'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.check(values)

    def test_restore_maintenance_delegates_only_exact_complete_old_bytes(self):
        spec, _, old, current = fixtures()
        calls = []
        expected_path = Path('/fixed-predecessor/tools/performance')
        def read_file(directory, name):
            self.assertEqual(directory, expected_path)
            self.assertEqual(name, 'patricia/adapt_oracles.py')
            return old
        def restore(raw, name):
            calls.append((raw, name))
            return b'earliest authenticated oracle'
        # Exercise the real method without its constructor, archives or Git.
        contract = object.__new__(C.Contract)
        contract.archived = Path('/fixed-predecessor')
        contract.maintenance = spec['maintenance']
        contract.core = types.SimpleNamespace(read_file=read_file)
        contract.previous = types.SimpleNamespace(restore_maintenance=restore)
        self.assertEqual(contract.restore_maintenance(current, C.ADAPTER_PATH), b'earliest authenticated oracle')
        self.assertEqual(calls, [(old, 'patricia/adapt_oracles.py')])
        for wrong in (old, current + b' '):
            calls.clear()
            with self.assertRaisesRegex(ValueError, 'maintenance source identity'):
                contract.restore_maintenance(wrong, C.ADAPTER_PATH)
            self.assertEqual(calls, [])
        contract.core = types.SimpleNamespace(read_file=lambda *args: old + b' ')
        with self.assertRaisesRegex(ValueError, 'maintenance source identity'):
            contract.restore_maintenance(current, C.ADAPTER_PATH)
        self.assertEqual(calls, [])

    def test_live_literal_matches_actual_owner_without_changing_legacy_role(self):
        path = HERE.parent / 'patricia/adapt_oracles.py'
        adapter = types.ModuleType('pure_header_adapter')
        adapter.__file__ = str(path)
        # Loading definitions does not call binary_contract or prepare.
        exec(compile(path.read_bytes(), str(path), 'exec'), adapter.__dict__)
        expected = ('module Bootstrap.CrateSession (compileSpecFile, compileSpecFileWithPrelude, '
                    'compileSpecFileWithVerification, compileSpecFileUsingInstaller,\n'
                    '    CompiledCrate, compiledObject, compiledInterfaces, compileSpecFileRetainedUsingInstaller) where {')
        declaration = ("LIVE_SESSION_HEADER = '" + expected.replace('\n', '\\n') + "'").encode()
        self.assertEqual(declaration, NEW)
        live = path.read_bytes()
        previous = before_cold_crates(live)
        self.assertEqual(previous.replace(NEW, COLD_CRATES), live)
        for bad in (previous, live + b' ', live + COLD_CRATES, live.replace(COLD_CRATES, b'')):
            with self.subTest(sha=hashlib.sha256(bad).hexdigest()), self.assertRaises(ValueError):
                before_cold_crates(bad)
        expected = COLD_CRATES.removeprefix(b"LIVE_SESSION_HEADER = '").removesuffix(b"'").decode().replace('\\n', '\n')
        self.assertEqual(adapter.LIVE_SESSION_HEADER, expected)
        owner = (HERE.parents[2] / 'libraries/mlf-crates/Bootstrap/CrateSession.hs').read_bytes()
        self.assertEqual(owner.count(expected.encode()), 1)
        legacy = b'module Bootstrap.CrateSession (compileSpecFile) where {'
        self.assertNotIn(legacy, owner)
        runner = (HERE.parent / 'patricia/run_integrated.py').read_bytes()
        self.assertIn(b"b'" + legacy + b"'", runner)
        self.assertIn(b"if name=='V1SessionUnderTest' else", runner)


if __name__ == '__main__':
    unittest.main()
