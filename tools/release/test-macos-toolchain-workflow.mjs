// The path-filtered PR job checks actual macOS provenance without self-hosting.
// actionlint separately validates complete GitHub Actions syntax.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
const workflow = fs.readFileSync('.github/workflows/macos-toolchain.yml', 'utf8');
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
  assert.ok(text.includes('python3 -B tools/shared/prepare_async_ghc.py --build-dir .mlf-build/async-ghc --clang clang\n'));
  assert.ok(text.includes(clangLibraryProof));
  assert.ok(text.includes('.runner_protocol_version == 1'));
  assert.ok(text.includes('        if: always()\n'));
  assert.equal((text.match(/^\s+if:/gm) || []).length, 1, 'Only artifact upload may be conditional');
  for (const path of ['macos-toolchain/', 'async-ghc/async-tools.json', 'async-ghc/receipt.json',
    'async-ghc/*.stderr', 'async-ghc/*.stdout', 'async-ghc/*.log', 'async-ghc/builtin-verification/']) {
    assert.ok(text.includes('            .mlf-build/' + path + '\n'));
  }
  assert.doesNotMatch(text, /self_host|self-host|full_validation|continue-on-error|pull_request_target|secrets\.|set \+e|\|\| true/);
};
verify(workflow);
for (const required of ['runs-on: macos-26', 'contents: read', 'timeout-minutes: 120',
  'tools/shared/build.py', '841591f152085be605616682779341847d24fd56bd6d22ca61bb37ee32b50681',
  'python3 -B tools/shared/prepare_async_ghc.py', '.toolchain.files | keys',
  '.runner_protocol_version == 1', 'if: always()', '.mlf-build/async-ghc/*.stderr']) {
  assert.throws(() => verify(workflow.replace(required, 'removed')));
}
assert.throws(() => verify(workflow + '\n    continue-on-error: true\n'));
assert.throws(() => verify(workflow + '\n    self_host: true\n'));
assert.throws(() => verify(workflow.replace('        run: |', '        if: false\n        run: |')));
assert.throws(() => verify(workflow.replace('set -euo pipefail', 'set +e')));
// The receipt hashes resolved files, which may have a versioned physical name.
for (const basename of ['libclang-cpp.dylib', 'libclang-cpp.19.dylib', 'libclang-cpp.19.1.7.dylib',
  'libclang-cpp.dylib.extra', 'libclang-cpp.fake.dylib', 'libclang-cpp.so', 'not-libclang-cpp.dylib']) {
  const result = spawnSync('jq', ['-e', clangLibraryProof], {
    input: JSON.stringify({toolchain: {files: {['/llvm/lib/' + basename]: 'hash'}}}), encoding: 'utf8',
  });
  assert.equal(result.error, undefined);
  assert.equal(result.status, /^libclang-cpp(?:\.[0-9]+)*\.dylib$/.test(basename) ? 0 : 1, basename);
}
console.log('PASS macOS toolchain workflow: path scope, actual authenticated build, pinned GHC, bounded execution, failure evidence and no self-hosting.');
