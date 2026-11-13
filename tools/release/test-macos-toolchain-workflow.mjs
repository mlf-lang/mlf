// PRs keep cheap native link checks; expensive GHC parity requires explicit opt-in.
// actionlint separately validates complete GitHub Actions syntax.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
const workflow = fs.readFileSync('.github/workflows/macos-toolchain.yml', 'utf8');
const ci = fs.readFileSync('.github/workflows/ci.yml', 'utf8');
const parityStart = ci.indexOf('      - name: Qualify typed completions and structured process tasks');
const parityEnd = ci.indexOf('      - uses: actions/upload-artifact@', parityStart);
const paritySteps = ci.slice(parityStart, parityEnd).replaceAll("        if: steps.scope.outputs.required != 'false'\n", '');
const scopeGuard = "steps.scope.outputs.required == 'true'";
const scopeStep = '      - name: Decide whether expensive async parity was explicitly requested\n' +
  '        id: scope\n' +
  '        run: python3 tools/release/async-change-scope.py --output .mlf-build/macos-toolchain/async-scope.json\n';
const expensiveSteps = [
  'Install pinned official GHC 9.14.1',
  'Build and authenticate actual GHC-origin async tools',
  'Qualify typed completions and structured process tasks',
  'Qualify checked async package interfaces and cache replay',
];
const parityArtifacts = [...ci.slice(parityEnd).matchAll(/^            (\.mlf-build\/async-(?:completion-gate|process-parity|task-parity|package-parity)\/[^\n]+)$/gm)].map(match => match[0]);
const clangLibraryProof = String.raw`.toolchain.files | keys | any(test("/libclang-cpp(\\.[0-9]+)*\\.dylib$"))`;
const probeName = '      - name: Verify diagnostic-free native completion links\n';
const ghcName = '      - name: Install pinned official GHC 9.14.1\n';
const probeCommands = [
  'clang -O2 -std=c11 -Wall -Wextra -Werror "${cflags[@]}" -c runtime/mlf_runtime.c -o "$output/runtime.o" > "$output/runtime.stdout" 2> "$output/runtime.stderr"',
  'clang -O2 -std=c11 -Wall -Wextra -Werror "${cflags[@]}" "tests/native/$native.c" "$output/runtime.o" "${libs[@]}" -o "$output/$native" > "$output/$native.link.stdout" 2> "$output/$native.link.stderr"',
  '"$output/$native" > "$output/$native.execute.stdout" 2> "$output/$native.execute.stderr"',
];
const verify = text => {
  assert.ok(text.replaceAll(`        if: ${scopeGuard}\n`, '').includes(paritySteps), 'Run the same ordinary async parity commands and assertions as main');
  assert.ok(text.includes(scopeStep), 'Reuse the ordinary async opt-in selector and preserve its decision receipt');
  assert.ok(text.indexOf(scopeStep) < text.indexOf(ghcName), 'Decide opt-in before installing or building GHC tools');
  for (const name of expensiveSteps) {
    const step = text.split(`      - name: ${name}\n`)[1]?.split(/\n      - (?:name|uses):/)[0];
    assert.ok(step, name);
    assert.equal(step.match(/^        if: (.*)$/m)?.[1], scopeGuard, `${name} must fail closed without explicit opt-in`);
  }
  assert.ok(text.indexOf('      - name: Build and authenticate actual GHC-origin async tools') < text.indexOf('      - name: Qualify typed completions'), 'Authenticate before parity');
  assert.ok(parityArtifacts.length > 0);
  for (const artifact of parityArtifacts) assert.ok(text.includes(artifact), artifact);
  const probe = text.match(/      - name: Verify diagnostic-free native completion links\n([\s\S]*?)(?=      - name:)/)?.[1];
  assert.ok(probe, 'Native completion probe must be present');
  for (const command of probeCommands) assert.ok(probe.includes(command), command);
  assert.ok(text.indexOf(probeName) < text.indexOf(ghcName), 'Probe must precede expensive GHC installation');
  assert.match(text, /^  pull_request:\n    types: \[opened, synchronize, reopened, labeled, unlabeled\]\n    paths:\n/m);
  assert.match(text, /^  workflow_dispatch:$/m, 'Manual dispatch retains full parity');
  for (const path of ['.github/workflows/macos-toolchain.yml', 'tools/shared/build.py',
    '.github/workflows/ci.yml', 'tests/native/completion_cell_tests.c',
    'tests/native/async_completion_primitives.c', 'runtime/mlf_runtime.c',
    'tools/shared/test_darwin_toolchain.py', 'tools/release/test-macos-toolchain-workflow.mjs',
    'tools/release/async-change-scope.py', 'tools/release/test-async-change-scope.py']) {
    assert.ok(text.includes('      - ' + path + '\n'));
  }
  assert.match(text, /^  contents: read$/m);
  assert.match(text, /^    runs-on: macos-26$/m);
  assert.match(text, /^    timeout-minutes: 360$/m);
  assert.ok(text.includes('test "$(uname -m)" = arm64'));
  assert.ok(text.includes('brew install llvm@19 gmp pkg-config bdw-gc jq'));
  for (const required of ["echo 'MACOSX_DEPLOYMENT_TARGET=26.0' >> \"$GITHUB_ENV\"",
    'for native in completion_cell_tests async_completion_primitives; do',
    'libs+=("$MLF_GC_PREFIX/lib/libgc.a" -lm -lpthread)',
    'test ! -s "$output/runtime.stderr"', 'test ! -s "$output/$native.link.stderr"',
    'test ! -s "$output/$native.execute.stderr"']) assert.ok(text.includes(required), required);
  assert.ok(text.includes('841591f152085be605616682779341847d24fd56bd6d22ca61bb37ee32b50681 "$archive" | shasum -a 256 -c -'));
  for (const flags of ['-B', '-O -B']) {
    assert.ok(text.includes(`python3 ${flags} tools/shared/test_darwin_toolchain.py`));
    assert.ok(text.includes(`python3 ${flags} tools/shared/test_prepare_async_ghc.py`));
  }
  assert.ok(text.includes('python3 -B tools/shared/prepare_async_ghc.py --build-dir .mlf-build/async-ghc --clang clang\n'));
  assert.ok(text.includes(clangLibraryProof));
  assert.ok(text.includes('.runner_protocol_version == 1'));
  assert.ok(text.includes('        if: always()\n'));
  assert.equal((text.match(/^\s+if:/gm) || []).length, expensiveSteps.length + 1, 'Only expensive opt-in steps and artifact upload may be conditional');
  for (const path of ['macos-toolchain/', 'async-ghc/async-tools.json', 'async-ghc/receipt.json',
    'async-ghc/*.stderr', 'async-ghc/*.stdout', 'async-ghc/*.log', 'async-ghc/builtin-verification/']) {
    assert.ok(text.includes('            .mlf-build/' + path + '\n'));
  }
  assert.doesNotMatch(text, /self_host|self-host|full_validation|continue-on-error|pull_request_target|secrets\.|set \+e|\|\| true/);
};
verify(workflow);
// Evaluate the actual guarded expression, including a missing selector output.
const evaluateScopeGuard = Function('steps', `return (${scopeGuard});`);
for (const [required, expected] of [['true', true], ['false', false], ['', false], [undefined, false]]) {
  assert.equal(evaluateScopeGuard({scope: {outputs: {required}}}), expected);
}
for (const name of expensiveSteps) {
  for (const replacement of ['', '        if: true\n', "        if: steps.scope.outputs.required != 'false'\n"]) {
    const original = `      - name: ${name}\n        if: ${scopeGuard}\n`;
    assert.throws(() => verify(workflow.replace(original, `      - name: ${name}\n${replacement}`)), name);
  }
}
for (const required of [scopeStep, 'labeled, unlabeled', '  workflow_dispatch:\n',
  '      - tools/release/async-change-scope.py\n', '      - tools/release/test-async-change-scope.py\n']) {
  assert.throws(() => verify(workflow.replace(required, 'removed')));
}
assert.throws(() => verify(workflow.replace(scopeStep, '').replace(ghcName, ghcName + scopeStep)));
for (const required of ['runs-on: macos-26', 'contents: read', 'timeout-minutes: 360',
  'MACOSX_DEPLOYMENT_TARGET=26.0', 'test ! -s "$output/$native.link.stderr"',
  'test ! -s "$output/$native.execute.stderr"', 'libs+=("$MLF_GC_PREFIX/lib/libgc.a" -lm -lpthread)',
  'tools/shared/build.py', '841591f152085be605616682779341847d24fd56bd6d22ca61bb37ee32b50681',
  'python3 -B tools/shared/prepare_async_ghc.py', '.toolchain.files | keys',
  '.runner_protocol_version == 1', 'if: always()', '.mlf-build/async-ghc/*.stderr']) {
  assert.throws(() => verify(workflow.replace(required, 'removed')));
}
for (const required of ['EMLF="$compiler" tests/fixtures/async-completion/check.sh',
  'tools/release/test-async-process.sh "$compiler"', 'tools/release/test-async-task.sh "$compiler"',
  'tools/release/test-async-package.sh "$compiler" "$manager"', ...parityArtifacts]) {
  assert.throws(() => verify(workflow.replace(required, 'removed')));
}
for (const command of probeCommands) {
  assert.throws(() => verify(workflow.replace(command, 'removed')));
}
const probeStep = workflow.match(/      - name: Verify diagnostic-free native completion links\n[\s\S]*?(?=      - name:)/)[0];
const reordered = workflow.replace(probeStep, '').replace('      - name: Exercise resolver', probeStep + '      - name: Exercise resolver');
assert.throws(() => verify(reordered));
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
console.log('PASS macOS toolchain workflow: cheap PR probes, explicit expensive-parity opt-in, manual coverage, pinned GHC, bounded execution, failure evidence and no self-hosting.');
