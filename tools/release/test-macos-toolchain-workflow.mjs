// The path-filtered PR job checks actual macOS provenance without self-hosting.
// actionlint separately validates complete GitHub Actions syntax.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {projectAdapterCommands} from './workflow-test-adapters.mjs';
import {releaseTestCase, releaseTestEvent} from './test-events.mjs';
import { spawnSync } from 'node:child_process';
const workflowSource = fs.readFileSync('.github/workflows/macos-toolchain.yml', 'utf8');
const workflow = projectAdapterCommands(workflowSource);
const clangLibraryProof = String.raw`.toolchain.files | keys | any(test("/libclang-cpp(\\.[0-9]+)*\\.dylib$"))`;
const verify = text => {
  assert.match(text, /^  pull_request:\n    paths:\n/m);
  for (const path of ['.github/workflows/macos-toolchain.yml', 'tools/shared/build.py',
    'tools/shared/test_darwin_toolchain.py', 'tools/release/test-macos-toolchain-workflow.mjs']) {
    assert.ok(text.includes('      - ' + path + '\n'));
  }
  assert.match(text, /^  contents: read$/m);
  assert.match(text, /^    runs-on: macos-26$/m);
  assert.match(text, /^    timeout-minutes: 120$/m);
  assert.ok(text.includes('test "$(uname -m)" = arm64'));
  assert.ok(text.includes('brew install llvm@19 gmp pkg-config bdw-gc jq'));
  assert.ok(text.includes('841591f152085be605616682779341847d24fd56bd6d22ca61bb37ee32b50681 "$archive" | shasum -a 256 -c -'));
  for (const flags of ['-B', '-O -B']) {
    assert.ok(text.includes(`python3 ${flags} tools/shared/test_darwin_toolchain.py`));
    assert.ok(text.includes(`python3 ${flags} tools/shared/test_prepare_async_ghc.py`));
  }
  assert.ok(text.includes('python3 -B tools/shared/prepare_async_ghc.py --build-dir .mlf-build/async-ghc --clang clang --optimization 2\n'));
  assert.ok(text.includes(clangLibraryProof));
  assert.ok(text.includes('.runner_protocol_version == 1'));
  assert.ok(text.includes('        if: always()\n'));
  assert.equal((text.match(/^        if:/gm) || []).length, 1, 'Only artifact upload may be conditional within the job');
  for (const path of ['macos-toolchain/', 'async-ghc/async-tools.json', 'async-ghc/receipt.json',
    'async-ghc/*.stderr', 'async-ghc/*.stdout', 'async-ghc/*.log', 'async-ghc/builtin-verification/']) {
    assert.ok(text.includes('            .mlf-build/' + path + '\n'));
  }
  assert.doesNotMatch(text, /self_host|self-host|full_validation|continue-on-error|pull_request_target|secrets\.|set \+e|\|\| true/);
};
const suite = 'release-macos-toolchain-workflow';
const prefix = 'release/macos-toolchain-workflow/';
const cases = [
  ['workflow', () => {
    for (const adapter of ['python-shared-darwin-toolchain', 'python-shared-prepare-async-ghc']) {
      assert.ok(workflowSource.includes('tools/testing/run.py ' + adapter));
    }
    verify(workflow);
  }],
];
for (const required of ['runs-on: macos-26', 'contents: read', 'timeout-minutes: 120',
  'tools/shared/build.py', '841591f152085be605616682779341847d24fd56bd6d22ca61bb37ee32b50681',
  'python3 -B tools/shared/prepare_async_ghc.py', '.toolchain.files | keys',
  '.runner_protocol_version == 1', 'if: always()', '.mlf-build/async-ghc/*.stderr']) {
  cases.push(['required/' + encodeURIComponent(required),
    () => assert.throws(() => verify(workflow.replace(required, 'removed')))]);
}
cases.push(
  ['fail-open', () => assert.throws(() => verify(workflow + '\n    continue-on-error: true\n'))],
  ['no-self-host', () => assert.throws(() => verify(workflow + '\n    self_host: true\n'))],
  ['run-condition', () => assert.throws(() => verify(workflow.replace('        run: |', '        if: false\n        run: |')))],
  ['shell-failure', () => assert.throws(() => verify(workflow.replace('set -euo pipefail', 'set +e')))],
);
// The receipt hashes resolved files, which may have a versioned physical name.
for (const basename of ['libclang-cpp.dylib', 'libclang-cpp.19.dylib', 'libclang-cpp.19.1.7.dylib',
  'libclang-cpp.dylib.extra', 'libclang-cpp.fake.dylib', 'libclang-cpp.so', 'not-libclang-cpp.dylib']) {
  cases.push(['receipt/' + basename, () => {
    const result = spawnSync('jq', ['-e', clangLibraryProof], {
      input: JSON.stringify({toolchain: {files: {['/llvm/lib/' + basename]: 'hash'}}}), encoding: 'utf8',
    });
    assert.equal(result.error, undefined);
    assert.equal(result.status, /^libclang-cpp(?:\.[0-9]+)*\.dylib$/.test(basename) ? 0 : 1, basename);
  }]);
}
const exact = process.env.MLF_TEST_SUITE === suite ? process.env.MLF_TEST_EXACT : undefined;
const plan = cases.map(([label]) => prefix + label).filter(id => !exact || exact === id);
assert.ok(plan.length, 'Unknown macOS workflow case');
if (process.argv.includes('--framework-list')) {
  console.log(JSON.stringify(plan));
} else {
  releaseTestEvent(suite, {plan});
  for (const [label, action] of cases) {
    const id = prefix + label;
    if (!exact || exact === id) releaseTestCase(suite, id, action);
  }
  console.log('PASS macOS toolchain workflow: path scope, actual authenticated build, pinned GHC, bounded execution, failure evidence and no self-hosting.');
}
