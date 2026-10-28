// Independently execute the CI partition's actual selectors. This checks workflow
// coverage, not compiler results; wrapper/provenance controls check the assertions.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';

const workflow = fs.readFileSync('.github/workflows/ci.yml', 'utf8');
const job = (text, name) => {
  const block = text.match(new RegExp(`^  ${name}:\\n[\\s\\S]*?(?=^  [a-z][a-z-]*:\\n|(?![\\s\\S]))`, 'm'))?.[0];
  assert.ok(block, `Missing ${name} job`);
  return block;
};
const selected = (step, matrix) => {
  const expression = step.match(/^        if: (.+)$/m)?.[1];
  return expression === undefined || Function('matrix', `return (${expression});`)(matrix);
};
const frameworkArguments = (step, matrix) => {
  const run = step.match(/^        run: \|\n([\s\S]*)$/m)?.[1];
  assert.ok(run, 'The framework step must have an explicit shell command');
  const script = run.replace(/^          /gm, '')
    .replaceAll('${{ matrix.optimization }}', matrix.optimization)
    .replaceAll('${{ matrix.suite }}', matrix.suite);
  assert.doesNotMatch(script, /\$\{\{/, 'Resolve every framework workflow expression');
  // Execute the workflow's actual shell dispatch, replacing only Python with an
  // argv recorder. No compiler, authentication, or long-running suite is invoked.
  const result = spawnSync('bash', ['-euo', 'pipefail', '-c',
    `python3() { printf '%s\\0' "$@"; }\n${script}`], {encoding: 'utf8', timeout: 5000});
  assert.equal(result.status, 0, result.stderr || String(result.error || 'Framework dispatch failed'));
  assert.equal(result.stderr, '', 'Framework dispatch must not emit diagnostics');
  assert.ok(result.stdout.endsWith('\0'), 'The framework command must execute');
  return result.stdout.slice(0, -1).split('\0');
};
const validate = text => {
  const native = job(text, 'native');
  assert.match(native, /^    timeout-minutes: 120$/m, 'Every shard keeps the 120-minute outer bound');
  assert.match(native, /^      fail-fast: false$/m, 'One failure must not hide other shard evidence');
  assert.doesNotMatch(native, /continue-on-error/);
  assert.equal(native.match(/^    if: (.+)$/m)?.[1], "github.event_name != 'workflow_dispatch' || !inputs.windows_runtime_only",
    'No native leg may be skipped for a PR, merge queue, or main push');
  const matrix = native.match(/^      matrix:\n([\s\S]*?)(?=^    steps:\n)/m)?.[1];
  assert.ok(matrix, 'An explicit native matrix is required');
  const rows = [...matrix.matchAll(/^          - optimization: '([02])'\n            suite: (all|direct|default|framework)\n/gm)];
  assert.deepEqual(rows.map(row => ({optimization: row[1], suite: row[2]})), [
    {optimization: '2', suite: 'all'},
    {optimization: '0', suite: 'direct'},
    {optimization: '0', suite: 'default'},
    {optimization: '0', suite: 'framework'},
  ], 'Exactly one O2 all leg and three complementary O0 legs are required');
  let remainder = matrix.replace(/^        #.*\n/gm, '').replace(/^        include:\n/m, '');
  for (const row of rows) remainder = remainder.replace(row[0], '');
  assert.equal(remainder.trim(), '', 'No hidden matrix axis, exclusion, or extra leg');
  const legs = rows.map(row => ({optimization: row[1], suite: row[2]}));
  const steps = native.match(/^      - (?:name:|uses:)[\s\S]*?(?=^      - (?:name:|uses:)|(?![\s\S]))/gm) || [];
  const commandStep = command => {
    const matches = steps.filter(step => step.includes(command));
    assert.equal(matches.length, 1, `Exactly one invocation of ${command}`);
    return matches[0];
  };
  const producer = commandStep('python3 tools/shared/build.py');
  assert.doesNotMatch(producer, /^        if:/m, 'Every shard builds its own authenticated producer');
  assert.match(producer, /python3 tools\/shared\/build.py --optimization '\$\{\{ matrix.optimization \}\}' --build-dir \.mlf-build\/shared-ghc\n/);
  assert.match(producer, /jq -e '\.complete == true and \.producer_host == "GHC" and \.typecheck_only == false' \.mlf-build\/shared-ghc\/receipt.json/);
  const toolchain = commandStep('https://downloads.haskell.org/~ghc/9.14.1/');
  assert.doesNotMatch(toolchain, /^        if:/m, 'Every producer has its own verified toolchain');
  const checkout = commandStep('uses: actions/checkout@');
  assert.doesNotMatch(checkout, /^        if:/m);
  assert.match(checkout, /fetch-depth: 0/);

  const direct = [
    'tools/release/test-suite-build-receipts.py',
    'tools/release/source-smoke.sh',
    'tools/shared/test_direct.py',
    'tools/shared/test_figure12_direct.py',
  ];
  const o2Only = [
    'tools/performance/crate-optimizations/run_controls.py',
    'tools/performance/a1-private-index/check_integrated.py',
    'tools/performance/fingerprint-fusion/run_controls.py',
    'tools/shared/test_recursive_managed.py',
    'tools/shared/test_guest_framework.py',
    'tools/shared/test_guest_state_laws.py',
  ];
  const framework = commandStep('tools/shared/test_framework_direct.py');
  assert.match(framework, /python3 tools\/shared\/test_framework_direct.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/framework-direct --suite '\$\{\{ matrix.suite \}\}' "\$\{suite_args\[@\]\}"\n/);
  assert.doesNotMatch(native, /--frontend-timeout|--native-timeout/,
    'Direct per-mode defaults must come from the authenticated producer receipt');
  assert.doesNotMatch(native.replace(framework, ''), /--suite-timeout/,
    'Only the framework wrapper may receive the bounded suite override');
  assert.doesNotMatch(native, /\.mlf-build\/shared-ghc\/bin\/tuple-list\s*[|;]/,
    'Do not repeat the legacy TupleList run outside the exact wrapper oracle');
  const coverage = legs.map(leg => {
    const actual = [];
    for (const command of [...direct, ...o2Only]) {
      if (selected(commandStep(command), leg)) actual.push(command);
    }
    if (selected(framework, leg)) {
      assert.notEqual(leg.suite, 'direct', 'Direct shard cannot invoke the framework wrapper');
      const expectedArguments = ['tools/shared/test_framework_direct.py',
        '--build-receipt', '.mlf-build/shared-ghc/receipt.json',
        '--output', '.mlf-build/framework-direct', '--suite', leg.suite];
      if (leg.optimization === '0' && ['default', 'framework'].includes(leg.suite)) {
        expectedArguments.push('--suite-timeout', '5400');
      }
      assert.deepEqual(frameworkArguments(framework, leg), expectedArguments,
        `Only O0 default/framework get the existing 5400-second cap; O2 and direct arguments stay unchanged`);
      if (['all', 'default'].includes(leg.suite)) actual.push('tuple-default-305');
      if (['all', 'framework'].includes(leg.suite)) actual.push('tuple-framework-105');
    }
    const expected = leg.suite === 'all' ? [...direct, ...o2Only, 'tuple-default-305', 'tuple-framework-105']
      : leg.suite === 'direct' ? direct : [`tuple-${leg.suite}-${leg.suite === 'default' ? 305 : 105}`];
    assert.deepEqual(actual, expected, `Exact execution scope for O${leg.optimization} ${leg.suite}`);
    return actual;
  });
  assert.deepEqual(coverage.slice(1).flat().sort(), coverage[0].filter(name => !o2Only.includes(name)).sort(),
    'O0 shards must cover the complete prior O0 scope exactly once, with neither omissions nor duplicates');
  const upload = commandStep('uses: actions/upload-artifact@');
  assert.match(upload, /^        if: always\(\)$/m, 'Keep evidence for failed and timed-out shards');
  const artifact = upload.match(/^          name: (.+)$/m)?.[1];
  assert.ok(artifact);
  const artifactNames = legs.map(leg => artifact.replaceAll('${{ matrix.optimization }}', leg.optimization).replaceAll('${{ matrix.suite }}', leg.suite));
  assert.equal(new Set(artifactNames).size, legs.length, 'Matrix evidence artifacts must not collide');
  const gate = job(text, 'pr-gate');
  assert.match(gate, /^    if: always\(\) && github.event_name != 'workflow_dispatch'$/m);
  assert.match(gate, /^    needs: \[metadata, native, windows-runtime, build-runner, async-runtime, async-language\]$/m,
    'The aggregate must depend on the entire native matrix, not a selected shard');
  assert.match(gate, /jq -e 'length == 6 and all\(\.\[\]; \.result == "success"\)'/,
    'Skipped, cancelled, missing, or failed native matrix results must not pass');
};

validate(workflow);
const controls = [
  ['missing shard', "          - optimization: '0'\n            suite: default\n", ''],
  ['duplicate shard', '            suite: default\n', '            suite: framework\n'],
  ['missing O2', "          - optimization: '2'\n", "          - optimization: '0'\n"],
  ['matrix exclusion', '        include:\n', '        exclude: []\n        include:\n'],
  ['outer bound changed', '    timeout-minutes: 120\n', '    timeout-minutes: 121\n'],
  ['fail-fast cancellation', '      fail-fast: false\n', '      fail-fast: true\n'],
  ['producer skipped', '      - name: Build exact committed shared sources and direct test runners\n', "      - name: Build exact committed shared sources and direct test runners\n        if: matrix.optimization == '2'\n"],
  ['producer authentication removed', '.complete == true and .producer_host == "GHC" and .typecheck_only == false', '.complete == true'],
  ['direct coverage skipped', "if: matrix.suite == 'all' || matrix.suite == 'direct'", "if: matrix.suite == 'all'"],
  ['default/framework omitted', "if: matrix.suite != 'direct'", "if: matrix.suite == 'all'"],
  ['default/framework duplicated', "--suite '${{ matrix.suite }}'", '--suite all'],
  ['framework margin omitted', 'suite_args=(--suite-timeout 5400)', 'suite_args=()'],
  ['framework cap exceeded', 'suite_args=(--suite-timeout 5400)', 'suite_args=(--suite-timeout 5401)'],
  ['framework margin removed', 'suite_args=(--suite-timeout 5400)', 'suite_args=(--suite-timeout 4500)'],
  ['framework margin omitted by selector', "= '0:framework'", "= '0:default'"],
  ['default margin omitted by selector', "= '0:default'", "= '0:framework'"],
  ['O2 budget changed', "= '0:framework'", "= '2:all'"],
  ['all framework budgets changed', "if [ '${{ matrix.optimization }}:${{ matrix.suite }}' = '0:framework' ] || [ '${{ matrix.optimization }}:${{ matrix.suite }}' = '0:default' ]; then", 'if true; then'],
  ['direct budget override', 'python3 tools/shared/test_direct.py --bin-dir', 'python3 tools/shared/test_direct.py --suite-timeout 5400 --bin-dir'],
  ['Figure12 omitted', 'python3 tools/shared/test_figure12_direct.py', 'python3 tools/shared/omitted.py'],
  ['O2 guest omitted', "if: matrix.optimization == '2'", 'if: false'],
  ['artifact collision', '-${{ matrix.suite }}\n', '\n'],
  ['aggregate missing matrix', 'needs: [metadata, native, windows-runtime', 'needs: [metadata, windows-runtime'],
  ['aggregate accepts skipped', '.result == "success"', '.result != "failure"'],
  ['PR matrix skipped', "if: github.event_name != 'workflow_dispatch' || !inputs.windows_runtime_only", "if: github.event_name == 'workflow_dispatch'"],
  ['nonblocking failures', '    timeout-minutes: 120\n', '    timeout-minutes: 120\n    continue-on-error: true\n'],
];
for (const [name, before, after] of controls) {
  assert.ok(workflow.includes(before), `Mutation ${name} must hit the actual workflow`);
  assert.throws(() => validate(workflow.replace(before, after)), undefined, `Reject ${name}`);
}
console.log(`Native O0/O2 CI partition and ${controls.length} mutation controls passed.`);
