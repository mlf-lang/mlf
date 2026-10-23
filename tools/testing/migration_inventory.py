#!/usr/bin/env python3
"""Static, read-only migration ledger audit. Never invokes a test/build driver.

The dated planning inventory is immutable. This ledger reviews roles, not execution
qualification. Every classification is bound to frozen source and owner excerpts.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = 'docs/testing-migration-inventory-20261023.json'
EXTERNAL = 'docs/testing-external-entrypoints-20261023.json'
LEDGER = 'tests/testing-migration-ledger.json'
BASELINE = '8a3e69b165765931c3ff762379a78db9659b2cd8'
FROZEN_INPUTS = {
    'docs/testing-migration-inventory-20261023.json': '106796a05c3f35504c0e5834929848e9b507d8456b2cb13d3379e17a86b47d3b',
    'docs/testing-external-entrypoints-20261023.json': 'd36d6439864d90080664344adcb038b653f64090b2287285b13ed3f72c99255d',
    'docs/testing-inventory-20261023.tsv': '9eda8926f8b878e45063f76063517db78d84f241aea290c4cefd7faf69db90bf',
    'docs/testing-external-entrypoints-20261023.tsv': '2f3c2afeba7b8def7bee960f559b3d13a311b22c128102652c920274ce646359',
}
COUNTEREXAMPLE = 'tests/fixtures/async-gate/counterexample/incorrect-quantifier.emlf'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read_json(path):
    return json.loads((ROOT / path).read_text())


class Sources:
    def __init__(self):
        self.cache = {}

    def raw(self, path):
        if path not in self.cache:
            self.cache[path] = subprocess.check_output(
                ['git', 'show', BASELINE + ':' + path], cwd=ROOT)
        return self.cache[path]

    def text(self, path):
        return self.raw(path).decode('utf-8')

    def evidence(self, path, needle=None, line=None):
        raw = self.raw(path)
        lines = raw.decode('utf-8').splitlines()
        if line is None:
            if needle:
                line = next((i + 1 for i, text in enumerate(lines) if needle in text), None)
                if line is None:
                    raise ValueError(f'No evidence for {needle!r} in {path}')
            else:
                line = next((i + 1 for i, text in enumerate(lines)
                             if re.match(r'^main\b|^int (?:w?main)|^# [A-Z]|^-- [A-Z]|^name:', text)), 1)
        return {'path': path, 'commit': BASELINE, 'sha256': digest(raw),
                'line': line, 'excerpt': '\n'.join(lines[line-1:line+2])}


# Reviewed script roles: classification is intentionally not inferred from a
# file extension, executable bit, or presence of `main`.
BUILD = set('bootstrap-linux.sh bootstrap-manager.ps1 bootstrap-manager.sh bootstrap-windows-release.ps1 build-program-windows.ps1 ensure-build-runner.sh prepare-qualification.sh shared-candidate.sh shared-port.sh package-windows.ps1 package.sh prepare-package-release.sh'.split())
PROVISION = set('activate-windows.ps1 download-artifact.sh fetch-seed.sh install.sh native-environment.sh setup-macos.sh setup-windows.ps1'.split())
UTILITY = set('command.sh qualification-jobs.sh time-command.sh time-stage.sh wait-for-priority-jobs.sh windows-common.ps1 summarize-bootstrap.sh measure-ci.mjs'.split())
GATES = set('check-benchmark-provenance.sh qualification-gate.sh verify-benchmarks.mjs verify-unit-evidence.sh'.split())
SCENARIOS = set('check.sh extended-pr-smoke.sh native-ci.sh pr-smoke-cli.sh pr-smoke-packages.sh pr-smoke.sh qualify-windows.ps1 run-benchmarks.sh smoke-windows.ps1 smoke.sh source-smoke.sh timed-bootstrap.sh'.split())
CONTRACTS = set('test-async-bootstrap.sh test-async-package.sh test-async-process.sh test-async-task.sh test-benchmark-gate.mjs test-ci-policy.mjs test-fetch-seed.sh test-package-publishing.sh test-pr-gate.sh test-pr-smoke-cli-watchdog.sh test-qualification-gate.sh test-qualification-jobs.sh test-release-tag.mjs test-setup-macos.sh test-shared-candidate.sh test-smoke-receipts.sh test-source-smoke-diagnostics.sh test-suite-build-receipts.py test-tuple-list.sh test-unit-evidence.sh test-windows-runtime.ps1'.split())
HELPERS = {
 'tests/native/binary_files.c': 'tests/Tests/CompilerTests.emlf',
 'tests/native/host_support.c': 'tests/Tests/CompilerTests.emlf',
 'tests/native/measurement_fixture.c': 'tests/Tests/BenchmarkSuite.emlf',
 'testing/Test/Runner.emlf': 'testing/Test/Runner.emlf',
 'testing/tools/Main.emlf': 'testing/tools/Test/Process.emlf',
 'tests/CheckTarget.emlf': 'tests/CheckTarget.emlf',
}
TUPLE_EXPECTATIONS = {
 'sameBoundary': 'fixed-expression-AST-before-owned-delimiter',
 'sameExpression': 'fixed-expression-AST', 'sameAnnotation': 'fixed-annotation-AST',
 'fixed-datatype-AST': 'fixed-datatype-field-AST',
 'parseDiagnostic': 'source-rejection-with-exact-diagnostic',
 'parse-rejection': 'source-parser-rejection',
 'accepted': 'inferred-type-independent-target-check-and-roundtrip',
 'checkResult': 'inferred-type-independent-target-check-and-roundtrip',
 'evaluates': 'inferred-type-independent-target-check-and-roundtrip',
 'runtime-evaluation': 'independent-runtime-value',
 'rejected': 'source-compilation-rejection',
 'moduleAccepted': 'module-compile-independent-type-check',
 'moduleRejected': 'module-compilation-rejection',
}


def classify(e, sources):
    p, kind = e['source'], e['entry_kind']
    name = Path(p).name
    if kind == 'reviewed-catalog-family':
        return ('family', 'tests/test-catalog.json', 'Original family evidence/alias/metric contract retained; this is not an extra leaf execution.')
    if kind.startswith('manifest-'):
        return ('manifest-facade', p, 'Manifest target binding retained; facade does not add a second execution of its implementation.')
    if kind == 'pinned-benchmark-workload':
        return ('benchmark-workload', 'benchmarks/manifest.json', 'Pinned workload, inputs and independent language provenance retained; samples are not inferred from source presence.')
    if kind == 'python-unittest-method':
        return ('authored-observation', p, 'Named unittest method retains its assertions and subtest variants; no execution result inferred.')
    if kind == 'source-authored-tuple-list-observation':
        helper = e['owner_provenance']['helper']
        return ('authored-observation', p, TUPLE_EXPECTATIONS[helper])
    if p == COUNTEREXAMPLE:
        return ('compile-only-counterexample', 'tests/fixtures/async-gate/check.sh', 'The gate deliberately accepts this bad interface to demonstrate quantifier unsoundness; NEVER execute it. Acceptance here is not a rejected negative fixture.')
    if kind in ('workflow-or-policy-entry', 'composite-action-or-policy-entry'):
        return ('ci-orchestration', p, 'Workflow/action owns provisioning, dispatch and artifact transport; individual run steps require their own contracts. Real publication is outside test execution.')
    if p in HELPERS:
        return ('execution-helper', HELPERS[p], 'Transport/runner/measurement helper, not an independent passing test. Its consumer owns assertions and lifecycle.')
    if p.startswith('bootstrap/tests/'):
        port = sources.text('tests/Tests/PortSuite.emlf')
        names = re.search(r'names = O.words "([^"]+)"', port).group(1).split()
        if Path(p).stem in names:
            return ('port-fixture', 'tests/Tests/PortSuite.emlf', 'Named in the 25-fixture Port matrix; prepared target, native output, expected bytes and independent references remain separate obligations.')
        return ('diagnostic-probe', p, 'Standalone stage/parser/graph diagnostic with a source main, not in the 25-fixture Port names list; retained separately, never counted as Port qualification.')
    if p.startswith('examples/'):
        return ('example-fixture', p, 'Example program; package/modules consumers may exercise it, but main alone does not register an independent test. Interactive snake is not auto-executed.')
    if p == 'tests/async-task/typecheck.emlf':
        return ('compile-check-fixture', p, 'Standalone task typing probe; not selected by the current task script modes. Retained without inventing runtime coverage.')
    if p == 'tests/native/runtime_force.c':
        return ('diagnostic-probe', p, 'Standalone force ABI assertion/failure-mode probe; current NativeABI suite explicitly selects runtime_inline_force.c, not this file. Retain without inventing active qualification.')
    if p.startswith('tests/async-'):
        directory = p.split('/')[1]
        owner = 'tools/release/test-' + directory + '.sh'
        if name.startswith(('opaque-', 'mixed-')):
            return ('rejection-fixture', owner, 'Driver requires opacity/type rejection, not execution or arbitrary nonzero process status.')
        return ('runtime-fixture', owner, 'Driver owns real interpreter/native parity and lifecycle observations; source is a fixture, not an umbrella pass.')
    if p.startswith(('tests/fixtures/async-gate/', 'tests/fixtures/async-completion/')):
        owner = '/'.join(p.split('/')[:3]) + '/check.sh'
        if p == owner:
            return ('scenario-driver', owner, 'Owns distinct compile, checker, negative diagnostic and runtime paths; representation proof and live-completion gate must not be merged.')
        if '/negative/' in p:
            return ('rejection-fixture', owner, 'Exact source-phase rejection contract is in the owning gate; runtime forbidden for negative source fixtures.')
        if '/positive/' in p:
            return ('compile-check-fixture', owner, 'Positive representation fixture is compiled and independently checked, not executed by the representation gate.')
        return ('runtime-fixture', owner, 'Runtime gate compares source/target/native observations according to this gate; expected output remains independent.')
    if p == 'tests/fixtures/tuple-list-runtime.emlf':
        return ('runtime-fixture', 'tools/release/test-tuple-list.sh', 'Same authored source has interpreter and native variants, with fixed expected output retained.')
    if p.startswith('tests/native/'):
        if name in ('async_completion_primitives.c', 'completion_cell_tests.c'):
            owner = 'tests/fixtures/async-completion/check.sh'
        elif name.startswith('windows_'):
            owner = 'tools/release/test-windows-runtime.ps1'
        else:
            owner = 'tests/Tests/NativeABI.emlf'
        return ('native-assertion-driver', owner, 'Native main contains mode-specific assertions or failure probes; owner checks status/diagnostics and variants. C main is not a single leaf ID.')
    if p.startswith('tests/Tests/') and name.endswith('Reference.emlf'):
        return ('independent-reference', 'tests/ReferencesMain.emlf', 'Independent reference program selected by references dispatcher; preserve algorithm and bytes, do not replace with candidate output.')
    if p.startswith('tests/') and p.endswith('.emlf'):
        return ('suite-driver', p, 'Source suite/dispatcher retains its authored actions; imported main and manifest facade must not execute the suite twice.')
    if p.startswith('scripts/') or name in BUILD and p.startswith('tools/release/'):
        return ('build-or-artifact-helper', p, 'Build/preparation/packaging produces authenticated artifacts, never an execution verdict; retain fresh-stage boundaries.')
    if p.startswith('tools/bench/'):
        if name == 'Main.emlf':
            return ('benchmark-driver', p, 'MLF benchmark engine owns oracles and sampling; all ten workloads and seven-sample policy remain obligations.')
        return ('build-or-artifact-helper', p, 'Benchmark backend/linker configuration is a prerequisite, not correctness or performance evidence.')
    if p.startswith('tools/profile/'):
        if name == 'test-measure-process-tree.py':
            return ('scenario-driver', p, 'The nine explicit unittest methods, not the file process exit alone, define regression coverage.')
        return ('diagnostic-tool', p, 'Opt-in profiling/measurement/build instrumentation. Measurements are diagnostic evidence, never an automatic qualification pass.')
    if p.startswith('tools/release/'):
        if name == 'publish-package-release.sh':
            return ('external-publication', 'tools/release/test-package-publishing.sh', 'Real GitHub release writes stay outside test adapters; publishing contracts are checked with mocked gh in the named test.')
        if name in PROVISION:
            owner = {'fetch-seed.sh':'test-fetch-seed.sh', 'setup-macos.sh':'test-setup-macos.sh', 'install.sh':'smoke.sh'}.get(name, name)
            return ('provisioning-helper', 'tools/release/' + owner, 'Real download/install/environment mutation is provisioning, not a passing case; contract tests use controlled destinations or mocks.')
        if name in UTILITY:
            return ('execution-helper', p, 'Scheduling/timing/environment/receipt utility; its side effect or elapsed time is not a test verdict.')
        if name in GATES:
            return ('evidence-validator', p, 'Validates provenance or complete prerequisite evidence; must fail closed, and is not a substitute for the original executions.')
        if name in SCENARIOS or name in CONTRACTS:
            return ('scenario-driver', p, 'Reviewed script owns explicit assertions and/or multiple child phases; leaf export and lifecycle migration remain required, not a whole-script pass.')
    raise ValueError('Unreviewed source: ' + p)


def build():
    for path, expected in FROZEN_INPUTS.items():
        if digest((ROOT / path).read_bytes()) != expected:
            raise ValueError('Frozen inventory changed: ' + path)
    inventory = read_json(INVENTORY)
    external = read_json(EXTERNAL)
    sources = Sources()
    unresolved = {e['id'] for e in inventory['unresolved_entries']}
    rows = []
    for e in inventory['entrypoints']:
        role, owner, rationale = classify(e, sources)
        evidence = [sources.evidence(e['source'], line=e['owner_provenance'].get('line'))]
        if owner != e['source']:
            evidence.append(sources.evidence(owner))
        if role == 'port-fixture':
            evidence.append(sources.evidence(owner, 'names = O.words'))
        if e['source'] == COUNTEREXAMPLE:
            evidence.append(sources.evidence(owner, '# It is NEVER executed.'))
        row = {'id': e['id'], 'source': e['source'], 'original_kind': e['entry_kind'],
               'role': role, 'owner': owner, 'target_adapter': e['adapter'],
               'phase': e['migration_phase'], 'review_status': 'source-role-reviewed',
               'was_unresolved': e['id'] in unresolved, 'rationale': rationale,
               'evidence': evidence, 'active_implementation': 'legacy',
               'execution_verified': False, 'contributes_independent_test_count': False}
        if role in ('rejection-fixture', 'compile-check-fixture', 'compile-only-counterexample'):
            row['execution_policy'] = 'FORBID_RUNTIME'
            row['allowed_operations'] = ['compile', 'type-check', 'inspect-diagnostics']
            row['forbidden_operations'] = ['interpret', 'native-execute']
        if role in ('external-publication', 'provisioning-helper'):
            row['test_invocation_policy'] = 'mock-or-isolated-contract-only'
        if e['entry_kind'] == 'source-authored-tuple-list-observation':
            row['implementation_source'] = 'tests/Tests/TupleList.emlf'
            row['active_implementation'] = 'legacy'
            row['opt_in_implementation'] = 'framework'
            row['opt_in_selector'] = '--framework'
            row['implementation_status'] = 'staged-opt-in-source-only-unexecuted'
            row['legacy_label'] = e['owner_provenance']['legacy_label']
            row['expectation_kind'] = TUPLE_EXPECTATIONS[e['owner_provenance']['helper']]
        rows.append(row)
    tuple_source = (ROOT / 'tests/Tests/TupleList.emlf').read_bytes()
    tuple_ids = re.findall(r'leaf \"(tuple-list/focused/[^\"]+)\"', tuple_source.decode())
    expected_tuple_ids = [e['id'] for e in rows if e['original_kind'] == 'source-authored-tuple-list-observation']
    if collections.Counter(tuple_ids) != collections.Counter(expected_tuple_ids):
        raise ValueError('Tuple registration multiset differs from frozen 90 observations')
    dispatcher = (ROOT / 'tests/TupleListMain.emlf').read_text()
    if ('Runner.run args TupleList.cases' not in dispatcher or
        'Cons "--framework" rest -> finish rest' not in dispatcher or
        '_ -> Legacy.main' not in dispatcher):
        raise ValueError('Tuple facade must retain legacy default and explicit framework opt-in')
    legacy = (ROOT / 'tests/Tests/TupleListLegacy.emlf').read_bytes()
    frozen_legacy = subprocess.check_output(['git', 'show', BASELINE + ':tests/TupleListMain.emlf'], cwd=ROOT)
    if legacy != frozen_legacy.replace(b'module TupleListMain where', b'module Tests.TupleListLegacy where', 1):
        raise ValueError('Tuple legacy implementation differs from frozen source')
    return {'schema_version': 1, 'kind': 'source-reviewed-migration-ledger',
            'source_commit': BASELINE, 'not_execution_evidence': True,
            'implementation_inputs': {'tests/Tests/TupleList.emlf': digest(tuple_source), 'tests/TupleListMain.emlf': digest(dispatcher.encode()), 'tests/Tests/TupleListLegacy.emlf': digest(legacy)},
            'qualification_complete': False,
            'scope': 'Frozen role/owner review only. Legacy means the frozen implementation; this ledger does not attest current-tree runtime migration.',
            'frozen_inputs': FROZEN_INPUTS,
            'counts': {'records': 577, 'families': 170, 'external_paths': 202, 'tuple_observations': 90, 'reviewed_previously_unresolved': 339, 'tracked_assets': 3486},
            'remaining_execution_obligations': ['Export dynamic/generated/internal assertion IDs without changing independent oracle or variant semantics.', 'Switch each actual dispatcher once, with leaf-level receipts and lifecycle validation.', 'Run authorized required platform/campaign acceptance against exact source/tool/config identities.'],
            'entries': rows,
            'external_paths': [{'path': e['path'], 'role': e['current_role'], 'owner': e['target_framework_owner'], 'target_id': e['target_id'], 'phase': e['phase'], 'git_blob_sha1': e['git_blob_sha1'], 'sha256': e['sha256']} for e in external['entries']],
            'asset_provenance': [{'path': a['path'], 'git_blob': a['git_object'], 'category': a['category'], 'frozen_classification_note': a['static_route']} for a in inventory['assets']]}


def validate(ledger):
    expected = build()
    # Exact comparison includes multisets, source excerpts, ownership, restrictions,
    # source hashes, immutable inputs and no-runtime-evidence flags. A count-only
    # comparison would accept replacing missing IDs with duplicates.
    if ledger != expected:
        for key in expected:
            if ledger.get(key) != expected[key]:
                raise ValueError('Migration ledger mismatch: ' + key)
        raise ValueError('Unexpected migration ledger fields')
    assert len(ledger['entries']) == 577
    assert len({e['id'] for e in ledger['entries']}) == 577
    assert sum(e['was_unresolved'] for e in ledger['entries']) == 339
    counts = collections.Counter(e['original_kind'] for e in ledger['entries'])
    assert counts['reviewed-catalog-family'] == 170
    assert counts['source-authored-tuple-list-observation'] == 90
    assert len(ledger['external_paths']) == len({e['path'] for e in ledger['external_paths']}) == 202
    assert len(ledger['asset_provenance']) == len({a['path'] for a in ledger['asset_provenance']}) == 3486
    fixtures = {a['path'] for a in ledger['asset_provenance']}
    assert {'test/fixtures/figure12-a8.emlf', 'tests/fixtures/figure12-a8.emlf'} <= fixtures
    return ledger['counts']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Regenerate reviewed static ledger only')
    args = parser.parse_args()
    if args.write:
        (ROOT / LEDGER).write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'static-role-review-valid', 'counts': validate(read_json(LEDGER)), 'execution_verified': False}))


if __name__ == '__main__':
    main()
