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
// Record each direct Python call separately, including its evidence destination.
// A flattened argv stream would not distinguish split or merged invocations.
const directArguments = step => {
  const run = step.match(/^        run: \|\n([\s\S]*)$/m)?.[1];
  assert.ok(run, 'The direct step must have an explicit shell command');
  const script = run.replace(/^          /gm, '');
  assert.doesNotMatch(script, /\$\{\{/, 'Direct arguments must not vary by hidden workflow interpolation');
  const recorder = "unset MLF_CRC_TEST_EVIDENCE MLF_UTF8_TEST_EVIDENCE\npython3() { printf 'CALL\\0%s\\0%s\\0%s\\0' \"$#\" \"${MLF_CRC_TEST_EVIDENCE-}\" \"${MLF_UTF8_TEST_EVIDENCE-}\"; printf '%s\\0' \"$@\"; }\n";
  const result = spawnSync('bash', ['-euo', 'pipefail', '-c', recorder + script],
    {encoding: 'utf8', timeout: 5000});
  assert.equal(result.status, 0, result.stderr || String(result.error || 'Direct dispatch failed'));
  assert.equal(result.stderr, '', 'Direct dispatch must not emit diagnostics');
  assert.ok(result.stdout.endsWith('\0'), 'The direct commands must execute');
  const tokens = result.stdout.slice(0, -1).split('\0');
  const calls = [];
  for (let index = 0; index < tokens.length;) {
    assert.equal(tokens[index++], 'CALL', 'Every Python invocation has its own boundary');
    const argc = tokens[index++];
    assert.match(argc, /^[1-9][0-9]*$/, 'Canonical decimal argc');
    const count = Number(argc);
    assert.ok(Number.isSafeInteger(count) && count > 0 && count <= 64, 'Bounded exact argc');
    const evidence = tokens[index++];
    const utf8Evidence = tokens[index++];
    assert.ok(index + count <= tokens.length, 'Complete invocation arguments');
    calls.push({evidence, utf8Evidence, argv: tokens.slice(index, index + count)});
    index += count;
  }
  return calls;
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
  assert.match(producer, /python3 tools\/shared\/build.py --bootstrap-only --optimization '\$\{\{ matrix.optimization \}\}' --build-dir \.mlf-build\/shared-ghc\n/);
  assert.match(producer, /jq -e '\.complete == true and \.producer_host == "GHC" and \.typecheck_only == false' \.mlf-build\/shared-ghc\/receipt.json/);

  assert.match(producer, /^        id: shared_build$/m);
  const regeneration = commandStep('tools/shared/generate_builtin_evidence.py');
  assert.equal(regeneration.match(/^        if: (.+)$/m)?.[1], "failure() && steps.shared_build.outcome == 'failure' && ((matrix.optimization == '0' && matrix.suite == 'default') || (matrix.optimization == '2' && matrix.suite == 'all'))",
    'Only failed builds in one O0 and the O2 leg collect actual generation evidence');
  assert.match(regeneration, /^        timeout-minutes: 16$/m);
  const regenerationExpression = regeneration.match(/^        if: (.+)$/m)[1];
  const regenerationSelected = Function('matrix', 'failure', 'steps', `return (${regenerationExpression});`);
  for (const leg of legs) {
    for (const failed of [false, true]) for (const outcome of ['success', 'failure', 'skipped']) {
      assert.equal(regenerationSelected(leg, () => failed, {shared_build: {outcome}}),
        failed && outcome === 'failure' && (leg.suite === 'default' || leg.suite === 'all'));
    }
  }
  assert.match(regeneration, /resource_watchdog.py --seconds 900 --address-space-mib 6144 --rss-mib 5120 --max-output-mib 16 --disk-free-mib 4096 \.mlf-build\/builtin-generation-guard python3 -B tools\/shared\/generate_builtin_evidence.py --root "\$PWD" --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/builtin-generation-guard\/results --timeout 600\n/);
  assert.ok(steps.indexOf(producer) < steps.indexOf(regeneration), 'Generation follows the failed build');
  assert.ok(steps.indexOf(regeneration) < steps.indexOf(commandStep('tools/performance/crate-query-graph/verify.py')),
    'Generation does not replace or wrap later qualification gates');
  for (const flags of ['-B', '-O -B']) {
    assert.ok(job(text, 'metadata').includes('python3 ' + flags + ' tools/shared/test_generate_builtin_evidence.py\n'),
      'Keep normal and optimized generation refusal controls');
  }
  const toolchain = commandStep('https://downloads.haskell.org/~ghc/9.14.1/');
  assert.doesNotMatch(toolchain, /^        if:/m, 'Every producer has its own verified toolchain');
  assert.ok(toolchain.includes('python3 -B tools/release/cleanup-ghc-install.py --receipt .mlf-build/ghc-install-cleanup.json\n'),
    'Each shard verifies and removes only its pinned install inputs');
  const installedAt = toolchain.indexOf('make install)');
  const cleanupAt = toolchain.indexOf('python3 -B tools/release/cleanup-ghc-install.py');
  assert.ok(installedAt >= 0 && cleanupAt >= 0 && installedAt < cleanupAt,
    'Install-input cleanup follows successful installation');
  for (const flags of ['-B', '-O -B']) {
    assert.ok(job(text, 'metadata').includes('python3 ' + flags + ' tools/release/test-ghc-install-cleanup.py\n'),
      'Keep normal and optimized cleanup refusal controls');
  }
  const checkout = commandStep('uses: actions/checkout@');
  assert.doesNotMatch(checkout, /^        if:/m);
  assert.match(checkout, /fetch-depth: 0/);

  const direct = [
    'tools/release/test-suite-build-receipts.py',
    'tools/release/source-smoke.sh',
    'tools/shared/test_direct_bounded.py',
    'tools/shared/test_figure12_direct.py',
  ];
  // The ABI migration retains the frozen semantic algorithms behind explicit
  // adapters. Check each suite argument, since several now share one driver.
  const migrated = [
    'tools/performance/patricia/run_integrated.py --suite p123',
    'tools/performance/patricia/run_integrated.py --suite graph',
    'tools/performance/patricia/run_fingerprint.py',
    'tools/performance/map-policy/run_controls.py',
    'tools/performance/patricia/run_integrated.py --suite validation',
    'tools/performance/patricia/run_integrated.py --suite builtin',
    'tools/performance/patricia/run_file_controls.py',
    'tools/performance/patricia/run_controls.py',
    'tools/performance/patricia/run_native.py',
    'tools/performance/int64/run_llp64.py',
    'tools/performance/int64/run_controls.py',
  ];
  for (const command of migrated) {
    const lines = commandStep(command).split('\n').filter(line => line.includes(command));
    assert.equal(lines.length, 1, `One guarded command for ${command}`);
    assert.match(lines[0], /resource_watchdog.py --seconds 1800 --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 4096 /);
  }
  const mapPolicy = commandStep('tools/performance/map-policy/run_controls.py');
  assert.match(mapPolicy, /^        if: matrix.optimization == '2'$/m);
  assert.doesNotMatch(native, /tools\/performance\/patricia\/run_integrated\.py --suite map-balance/,
    'No obsolete shape-equality route alongside the explicit historical/current successor');
  const mapTest = 'tools/performance/map-policy/test_prepare_map_policy.py';
  const mapRun = 'tools/performance/map-policy/run_controls.py';
  const mapShell = mapPolicy.match(/^        run: \|\n([\s\S]*)$/m)?.[1].replace(/^          /gm, '').trim();
  assert.equal(mapShell, [
    'set -euo pipefail',
    'MAP_POLICY_SOURCE="$PWD" python3 -B ' + mapTest,
    'MAP_POLICY_SOURCE="$PWD" python3 -O -B ' + mapTest,
    'python3 -B tools/shared/resource_watchdog.py --seconds 1800 --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 4096 .mlf-build/map-balance-guard python3 -B ' + mapRun + ' --source "$PWD" --producer .mlf-build/shared-ghc --output .mlf-build/map-balance-controls',
  ].join('\n'), 'Exact source-bound map step, including both explicit source environments');
  assert.deepEqual(directArguments(mapPolicy), [
    {utf8Evidence: '', evidence: '', argv: ['-B', mapTest]},
    {utf8Evidence: '', evidence: '', argv: ['-O', '-B', mapTest]},
    {utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/resource_watchdog.py', '--seconds', '1800',
      '--address-space-mib', '6144', '--rss-mib', '5120', '--disk-free-mib', '4096',
      '.mlf-build/map-balance-guard', 'python3', '-B', mapRun, '--source', process.cwd(),
      '--producer', '.mlf-build/shared-ghc', '--output', '.mlf-build/map-balance-controls']},
  ], 'Exactly the two pure controls and one guarded actual Map successor');
  const numeric = commandStep('tools/performance/int64/run_controls.py');
  assert.match(numeric, /for suite in host native legacy; do/);
  assert.match(numeric, /run_controls.py --suite "\$suite" --producer \.mlf-build\/shared-ghc/);
  assert.match(commandStep('tools/performance/patricia/run_native.py'), /--mode standalone\n/);
  const graphChecks = [
    'tools/performance/crate-query-graph/verify.py',
    'tools/performance/crate-query-graph/source_checks.py',
  ];
  for (const command of graphChecks) {
    const step = commandStep(command);
    assert.match(step, /^        if: matrix.optimization == '2'$/m);
    assert.match(step, /resource_watchdog.py --seconds 600 --address-space-mib 6144 --rss-mib 5120 --max-output-mib 100 --disk-free-mib 4096 /);
  }
  const o2Only = [
    ...migrated,
    ...graphChecks,
    'python3 -B tools/performance/patricia/test_adapters.py',
    'python3 -O -B tools/performance/patricia/test_adapters.py',
    'tools/shared/test_source_context_cache.py',
    'tools/shared/test_artifact_binary.py',
    'tools/shared/test_recursive_managed.py',
    'tools/shared/test_guest_framework.py',
    'tools/shared/test_guest_state_laws.py',
  ];
  const binary = commandStep('tools/shared/test_artifact_binary.py');
  assert.match(binary, /^        if: matrix.optimization == '2'$/m);
  assert.match(binary, /set -euo pipefail/);
  assert.ok(binary.includes('python3 -B tools/shared/test_artifact_binary_modular.py\n'));
  assert.ok(binary.includes('python3 -O -B tools/shared/test_artifact_binary_modular.py\n'));
  assert.match(binary, /resource_watchdog.py --seconds 1800 --address-space-mib 6144 --rss-mib 5120 --max-output-mib 640 --disk-free-mib 4096 \.mlf-build\/artifact-binary-guard python3 -B tools\/shared\/test_artifact_binary.py --source-root "\$PWD" --build-receipt \.mlf-build\/shared-ghc\/receipt.json --clang clang --gc-prefix "\$PWD\/\.mlf-build\/io-action-gc" --partial-write-sink \/dev\/full --output \.mlf-build\/artifact-binary-guard\/results\n/);
  const gcPreparation = commandStep('cp "$archive" "$prefix/lib/libgc.a"');
  assert.ok(steps.indexOf(gcPreparation) < steps.indexOf(binary), 'GC preparation precedes binary native build');
  const framework = commandStep('tools/shared/test_framework_direct.py');
  assert.match(framework, /python3 tools\/shared\/test_framework_direct.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/framework-direct --suite '\$\{\{ matrix.suite \}\}' \$\{suite_args\[@\]\+"\$\{suite_args\[@\]\}"\}\n/);
  assert.doesNotMatch(native, /--frontend-timeout|--native-timeout/,
    'Direct per-mode defaults must come from the authenticated producer receipt');
  assert.doesNotMatch(native.replace(framework, ''), /--suite-timeout/,
    'Only the framework wrapper may receive the bounded suite override');
  assert.doesNotMatch(native, /\.mlf-build\/shared-ghc\/bin\/tuple-list\s*[|;]/,
    'Do not repeat the legacy TupleList run outside the exact wrapper oracle');
  const crc = commandStep('tools/shared/test_direct_bounded.py');
  assert.deepEqual(directArguments(crc), [
    {utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_crc_successor_entry.py']},
    {utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_crc_successor_entry.py']},
    {utf8Evidence: '', evidence: '.mlf-build/crc-supervisor-controls/normal',
      argv: ['-B', 'tools/shared/test_crc_process_supervisor.py']},
    {utf8Evidence: '', evidence: '.mlf-build/crc-supervisor-controls/optimized',
      argv: ['-O', '-B', 'tools/shared/test_crc_process_supervisor.py']},
    {utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_utf8_batch_contract.py']},
    {utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_utf8_batch_contract.py']},
    {utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_utf8_batch_worker.py']},
    {utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_utf8_batch_worker.py']},
    {utf8Evidence: '.mlf-build/utf8-supervisor-controls/normal', evidence: '', argv: ['-B', 'tools/shared/test_direct_bounded_entry.py']},
    {utf8Evidence: '.mlf-build/utf8-supervisor-controls/optimized', evidence: '', argv: ['-O', '-B', 'tools/shared/test_direct_bounded_entry.py']},
    {utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_direct_bounded.py',
      '--bin-dir', '.mlf-build/shared-ghc/bin',
      '--build-receipt', '.mlf-build/shared-ghc/receipt.json',
      '--output', '.mlf-build/direct-host-tests']},
  ], 'Exactly eleven ordered direct calls: four retained CRC controls, six UTF8/bounded controls and the authenticated composite successor');
  assert.doesNotMatch(native, /^\s*python3(?:\s+-B)?\s+tools\/shared\/test_direct\.py\b/m,
    'The legacy direct entry must not bypass the bounded successor');
  // Exact shell plus per-invocation argv checks: comments cannot replace an
  // execution, and merged/split calls or hidden shell routing cannot pass.
  const boundedShell = crc.match(/^        run: \|\n([\s\S]*)$/m)?.[1].replace(/^          /gm, '').trim();
  assert.equal(boundedShell, "set -euo pipefail\npython3 -B tools/shared/test_crc_successor_entry.py\npython3 -O -B tools/shared/test_crc_successor_entry.py\nMLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal python3 -B tools/shared/test_crc_process_supervisor.py\nMLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/optimized python3 -O -B tools/shared/test_crc_process_supervisor.py\npython3 -B tools/shared/test_utf8_batch_contract.py\npython3 -O -B tools/shared/test_utf8_batch_contract.py\npython3 -B tools/shared/test_utf8_batch_worker.py\npython3 -O -B tools/shared/test_utf8_batch_worker.py\nMLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py\nMLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/optimized python3 -O -B tools/shared/test_direct_bounded_entry.py\npython3 -B tools/shared/test_direct_bounded.py --bin-dir .mlf-build/shared-ghc/bin \\\n  --build-receipt .mlf-build/shared-ghc/receipt.json --output .mlf-build/direct-host-tests\n# The default/all framework gate executes this same no-argument\n# TupleList binary with its exact 305-observation completion oracle.",
    'Exact bounded direct shell and unchanged budgets');
  assert.doesNotMatch(native, /^\s*python3(?:\s+-B)?\s+tools\/shared\/test_direct_crc_successor\.py\b/m,
    'The standalone CRC entry cannot bypass UTF8 batching qualification');
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
  for (const suffix of ['**/stdout', '**/stderr', '**/*.json', '**/*.hs', '**/*.c', '**/*.h', '**/*.d']) {
    assert.ok(upload.includes('            .mlf-build/map-balance-controls/' + suffix + '\n'),
      'Retain actual Map commands, source closure, dependency and terminal evidence: ' + suffix);
  }
  for (const evidence of ['bounded-receipt.json', 'build.log', 'results/**/*.json',
                          'results/**/*.stdout', 'results/**/*.stderr']) {
    assert.ok(upload.includes('.mlf-build/artifact-binary-guard/' + evidence),
      'Keep binary build, target, and independent-oracle evidence: ' + evidence);
  }

  for (const path of ['.mlf-build/crc-supervisor-controls/', '.mlf-build/direct-host-tests/**/*.json',
                      '.mlf-build/direct-host-tests/**/*.stdout', '.mlf-build/direct-host-tests/**/*.stderr']) {
    assert.ok(upload.includes('            ' + path + '\n'), 'Preserve CRC cleanup and original suite evidence: ' + path);
  }
  for (const path of [".mlf-build/direct-host-tests/utf8-length/**/*.hs",".mlf-build/direct-host-tests/utf8-length/**/*.o",".mlf-build/direct-host-tests/utf8-length/**/*.hi",".mlf-build/direct-host-tests/utf8-length/**/*.d",".mlf-build/direct-host-tests/utf8-length/**/stdout",".mlf-build/direct-host-tests/utf8-length/**/stderr",".mlf-build/direct-host-tests/utf8-length-supervisor.json"]) {
    assert.ok(upload.includes('            ' + path + '\n'), 'Preserve selected UTF8 generated and supervisor evidence: ' + path);
  }
  assert.ok(upload.includes('            .mlf-build/utf8-supervisor-controls/\n'),
    'Preserve real UTF8 synthetic lifecycle evidence separately from CRC');
  assert.ok(upload.includes('            .mlf-build/ghc-install-cleanup.json\n'),
    'Retain exact cleanup scope, validation and refusal receipts');

  assert.ok(upload.includes('            .mlf-build/shared-ghc/ghc-info.txt\n'), 'Preserve the compiled toolchain metadata');
  assert.ok(upload.includes('            .mlf-build/shared-ghc/builtin-verification/\n'), 'Preserve the original failed builtin evidence');
  assert.ok(upload.includes('            .mlf-build/builtin-generation-guard/\n'), 'Preserve actual generator output and guards');
  for (const directory of ['native-library', 'stdlib-default-controls']) {
    for (const evidence of ['receipt.json', '*.stdout', '*.stderr']) {
      assert.ok(upload.includes('            .mlf-build/' + directory + '/' + evidence + '\n'),
        'Retain actual native-library command metadata and failure captures: ' + directory + '/' + evidence);
    }
  }
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
  ["Native failure evidence omitted: .mlf-build/native-library/receipt.json","            .mlf-build/native-library/receipt.json\n",""],
  ["Native failure evidence omitted: .mlf-build/native-library/*.stdout","            .mlf-build/native-library/*.stdout\n",""],
  ["Native failure evidence omitted: .mlf-build/native-library/*.stderr","            .mlf-build/native-library/*.stderr\n",""],
  ["Native failure evidence omitted: .mlf-build/stdlib-default-controls/receipt.json","            .mlf-build/stdlib-default-controls/receipt.json\n",""],
  ["Native failure evidence omitted: .mlf-build/stdlib-default-controls/*.stdout","            .mlf-build/stdlib-default-controls/*.stdout\n",""],
  ["Native failure evidence omitted: .mlf-build/stdlib-default-controls/*.stderr","            .mlf-build/stdlib-default-controls/*.stderr\n",""],
  ["UTF8 synthetic evidence omitted","            .mlf-build/utf8-supervisor-controls/\n",""],
  ["UTF8 normal evidence env omitted","MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal ",""],
  ["UTF8 optimized evidence env omitted","MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/optimized ",""],
  ["UTF8 evidence directories collide","MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/optimized ","MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal "],
  ["UTF8 evidence wrong variable","MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal ","OTHER_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal "],
  ["UTF8 evidence replaces CRC variable","MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal ","MLF_UTF8_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal "],
  ["UTF8 env injected into CRC call","          python3 -B tools/shared/test_crc_successor_entry.py\n","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_crc_successor_entry.py\n"],
  ["CRC env injected into UTF8 call","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py","          MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py"],
  ["UTF8 evidence attached to pure worker","          python3 -B tools/shared/test_utf8_batch_worker.py\n","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_utf8_batch_worker.py\n"],
  ["UTF8 evidence on wrong call","          python3 -O -B tools/shared/test_utf8_batch_worker.py\n          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py\n","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -O -B tools/shared/test_utf8_batch_worker.py\n          python3 -B tools/shared/test_direct_bounded_entry.py\n"],
  ["test_utf8_batch_contract.py normal omitted","          python3 -B tools/shared/test_utf8_batch_contract.py\n",""],
  ["test_utf8_batch_contract.py optimized omitted","          python3 -O -B tools/shared/test_utf8_batch_contract.py\n",""],
  ["test_utf8_batch_contract.py optimized duplicates normal","          python3 -O -B tools/shared/test_utf8_batch_contract.py\n","          python3 -B tools/shared/test_utf8_batch_contract.py\n"],
  ["test_utf8_batch_contract.py calls merged","          python3 -B tools/shared/test_utf8_batch_contract.py\n          python3 -O -B tools/shared/test_utf8_batch_contract.py\n","          python3 -B tools/shared/test_utf8_batch_contract.py -O -B tools/shared/test_utf8_batch_contract.py\n"],
  ["test_utf8_batch_contract.py order reversed","          python3 -B tools/shared/test_utf8_batch_contract.py\n          python3 -O -B tools/shared/test_utf8_batch_contract.py\n","          python3 -O -B tools/shared/test_utf8_batch_contract.py\n          python3 -B tools/shared/test_utf8_batch_contract.py\n"],
  ["test_utf8_batch_worker.py normal omitted","          python3 -B tools/shared/test_utf8_batch_worker.py\n",""],
  ["test_utf8_batch_worker.py optimized omitted","          python3 -O -B tools/shared/test_utf8_batch_worker.py\n",""],
  ["test_utf8_batch_worker.py optimized duplicates normal","          python3 -O -B tools/shared/test_utf8_batch_worker.py\n","          python3 -B tools/shared/test_utf8_batch_worker.py\n"],
  ["test_utf8_batch_worker.py calls merged","          python3 -B tools/shared/test_utf8_batch_worker.py\n          python3 -O -B tools/shared/test_utf8_batch_worker.py\n","          python3 -B tools/shared/test_utf8_batch_worker.py -O -B tools/shared/test_utf8_batch_worker.py\n"],
  ["test_utf8_batch_worker.py order reversed","          python3 -B tools/shared/test_utf8_batch_worker.py\n          python3 -O -B tools/shared/test_utf8_batch_worker.py\n","          python3 -O -B tools/shared/test_utf8_batch_worker.py\n          python3 -B tools/shared/test_utf8_batch_worker.py\n"],
  ["test_direct_bounded_entry.py normal omitted","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py\n",""],
  ["test_direct_bounded_entry.py optimized omitted","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/optimized python3 -O -B tools/shared/test_direct_bounded_entry.py\n",""],
  ["test_direct_bounded_entry.py optimized duplicates normal","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/optimized python3 -O -B tools/shared/test_direct_bounded_entry.py\n","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py\n"],
  ["test_direct_bounded_entry.py calls merged","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py\n          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/optimized python3 -O -B tools/shared/test_direct_bounded_entry.py\n","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py -O -B tools/shared/test_direct_bounded_entry.py\n"],
  ["test_direct_bounded_entry.py order reversed","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py\n          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/optimized python3 -O -B tools/shared/test_direct_bounded_entry.py\n","          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/optimized python3 -O -B tools/shared/test_direct_bounded_entry.py\n          MLF_UTF8_TEST_EVIDENCE=.mlf-build/utf8-supervisor-controls/normal python3 -B tools/shared/test_direct_bounded_entry.py\n"],
  ["Bounded successor replaced by standalone CRC","python3 -B tools/shared/test_direct_bounded.py --bin-dir","python3 -B tools/shared/test_direct_crc_successor.py --bin-dir"],
  ["Bounded direct extra routing token","python3 -B tools/shared/test_direct_bounded.py --bin-dir","python3 -B tools/shared/test_direct_bounded.py --worker --bin-dir"],
  ["Bounded direct shell route injected","          python3 -B tools/shared/test_direct_bounded.py --bin-dir","          true\n          python3 -B tools/shared/test_direct_bounded.py --bin-dir"],
  ["Bounded direct mocked by comment","          python3 -B tools/shared/test_direct_bounded.py --bin-dir","          # python3 -B tools/shared/test_direct_bounded.py --bin-dir"],
  ["UTF8 evidence omitted .mlf-build/direct-host-tests/utf8-length/**/*.hs","            .mlf-build/direct-host-tests/utf8-length/**/*.hs\n",""],
  ["UTF8 evidence omitted .mlf-build/direct-host-tests/utf8-length/**/*.o","            .mlf-build/direct-host-tests/utf8-length/**/*.o\n",""],
  ["UTF8 evidence omitted .mlf-build/direct-host-tests/utf8-length/**/*.hi","            .mlf-build/direct-host-tests/utf8-length/**/*.hi\n",""],
  ["UTF8 evidence omitted .mlf-build/direct-host-tests/utf8-length/**/*.d","            .mlf-build/direct-host-tests/utf8-length/**/*.d\n",""],
  ["UTF8 evidence omitted .mlf-build/direct-host-tests/utf8-length/**/stdout","            .mlf-build/direct-host-tests/utf8-length/**/stdout\n",""],
  ["UTF8 evidence omitted .mlf-build/direct-host-tests/utf8-length/**/stderr","            .mlf-build/direct-host-tests/utf8-length/**/stderr\n",""],
  ["UTF8 evidence omitted .mlf-build/direct-host-tests/utf8-length-supervisor.json","            .mlf-build/direct-host-tests/utf8-length-supervisor.json\n",""],
  ['Map normal pure controls omitted', '          MAP_POLICY_SOURCE="$PWD" python3 -B tools/performance/map-policy/test_prepare_map_policy.py\n', ''],
  ['Map optimized pure controls omitted', '          MAP_POLICY_SOURCE="$PWD" python3 -O -B tools/performance/map-policy/test_prepare_map_policy.py\n', ''],
  ['Map source environment omitted', 'MAP_POLICY_SOURCE="$PWD" python3 -B tools/performance/map-policy/test_prepare_map_policy.py', 'python3 -B tools/performance/map-policy/test_prepare_map_policy.py'],
  ['Map old shape route restored', 'tools/performance/map-policy/run_controls.py --source "$PWD"', 'tools/performance/patricia/run_integrated.py --suite map-balance'],
  ['Map source basis argument omitted', 'tools/performance/map-policy/run_controls.py --source "$PWD"', 'tools/performance/map-policy/run_controls.py'],
  ['Map wrong producer', 'tools/performance/map-policy/run_controls.py --source "$PWD" --producer .mlf-build/shared-ghc', 'tools/performance/map-policy/run_controls.py --source "$PWD" --producer .mlf-build/old-producer'],
  ['Map wrong output', 'tools/performance/map-policy/run_controls.py --source "$PWD" --producer .mlf-build/shared-ghc --output .mlf-build/map-balance-controls', 'tools/performance/map-policy/run_controls.py --source "$PWD" --producer .mlf-build/shared-ghc --output .mlf-build/other-map'],
  ['Map duplicate dispatch', '          MAP_POLICY_SOURCE="$PWD" python3 -B tools/performance/map-policy/test_prepare_map_policy.py\n', '          python3 -B tools/performance/map-policy/run_controls.py\n          MAP_POLICY_SOURCE="$PWD" python3 -B tools/performance/map-policy/test_prepare_map_policy.py\n'],
  ['Map C source evidence omitted', '            .mlf-build/map-balance-controls/**/*.c\n', ''],
  ['Map project header evidence omitted', '            .mlf-build/map-balance-controls/**/*.h\n', ''],
  ['Map dependency evidence omitted', '            .mlf-build/map-balance-controls/**/*.d\n', ''],
  ['Map target stdout evidence omitted', '            .mlf-build/map-balance-controls/**/stdout\n', ''],
  ['Map target stderr evidence omitted', '            .mlf-build/map-balance-controls/**/stderr\n', ''],
  ['Map terminal receipt evidence omitted', '            .mlf-build/map-balance-controls/**/*.json\n', ''],
  ["CRC calls merged without argv token loss","          python3 -B tools/shared/test_crc_successor_entry.py\n          python3 -O -B tools/shared/test_crc_successor_entry.py\n","          python3 -B tools/shared/test_crc_successor_entry.py -O -B tools/shared/test_crc_successor_entry.py\n"],
  ["CRC call split without argv token loss","          python3 -B tools/shared/test_crc_successor_entry.py\n","          python3 -B\n          python3 tools/shared/test_crc_successor_entry.py\n"],
  ["CRC evidence environment assigned to wrong call","          python3 -B tools/shared/test_crc_successor_entry.py\n          python3 -O -B tools/shared/test_crc_successor_entry.py\n          MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal python3 -B tools/shared/test_crc_process_supervisor.py\n","          MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal python3 -B tools/shared/test_crc_successor_entry.py\n          python3 -O -B tools/shared/test_crc_successor_entry.py\n          python3 -B tools/shared/test_crc_process_supervisor.py\n"],
  ["CRC successor replaced by legacy bypass","python3 -B tools/shared/test_direct_bounded.py --bin-dir","python3 -B tools/shared/test_direct.py --bin-dir"],
  ["CRC successor duplicated","          python3 -B tools/shared/test_direct_bounded.py --bin-dir","          python3 -B tools/shared/test_direct_bounded.py --bin-dir ignored\n          python3 -B tools/shared/test_direct_bounded.py --bin-dir"],
  ["CRC old route inserted","          python3 -B tools/shared/test_direct_bounded.py --bin-dir","          python3 tools/shared/test_direct.py --bin-dir ignored\n          python3 -B tools/shared/test_direct_bounded.py --bin-dir"],
  ["CRC normal entry controls omitted","          python3 -B tools/shared/test_crc_successor_entry.py\n",""],
  ["CRC optimized entry controls omitted","          python3 -O -B tools/shared/test_crc_successor_entry.py\n",""],
  ["CRC normal lifecycle controls omitted","          MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal python3 -B tools/shared/test_crc_process_supervisor.py\n",""],
  ["CRC optimized lifecycle controls omitted","          MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/optimized python3 -O -B tools/shared/test_crc_process_supervisor.py\n",""],
  ["CRC lifecycle optimization dropped","python3 -O -B tools/shared/test_crc_process_supervisor.py","python3 -B tools/shared/test_crc_process_supervisor.py"],
  ["CRC evidence environment omitted","MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal ",""],
  ["CRC evidence environment inactive","MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal ","OTHER_EVIDENCE=.mlf-build/crc-supervisor-controls/normal "],
  ["CRC evidence directories collide","MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/optimized ","MLF_CRC_TEST_EVIDENCE=.mlf-build/crc-supervisor-controls/normal "],
  ["CRC successor producer differs","--build-receipt .mlf-build/shared-ghc/receipt.json --output .mlf-build/direct-host-tests","--build-receipt .mlf-build/wrong/receipt.json --output .mlf-build/direct-host-tests"],
  ["CRC successor output differs","--output .mlf-build/direct-host-tests\n","--output .mlf-build/wrong-direct\n"],
  ["CRC lifecycle evidence omitted","            .mlf-build/crc-supervisor-controls/\n",""],
  ["CRC suite receipts omitted","            .mlf-build/direct-host-tests/**/*.json\n",""],
  ["CRC suite stdout omitted","            .mlf-build/direct-host-tests/**/*.stdout\n",""],
  ["CRC suite stderr omitted","            .mlf-build/direct-host-tests/**/*.stderr\n",""],
  ['generation compiler metadata omitted', '            .mlf-build/shared-ghc/ghc-info.txt\n', ''],
  ["producer diagnostic id omitted","        id: shared_build\n",""],
  ["generation failure condition relaxed","failure() && steps.shared_build.outcome == 'failure' && ((matrix.optimization == '0' && matrix.suite == 'default') || (matrix.optimization == '2' && matrix.suite == 'all'))","steps.shared_build.outcome == 'failure' && ((matrix.optimization == '0' && matrix.suite == 'default') || (matrix.optimization == '2' && matrix.suite == 'all'))"],
  ["generation O0 coverage changed","failure() && steps.shared_build.outcome == 'failure' && ((matrix.optimization == '0' && matrix.suite == 'default') || (matrix.optimization == '2' && matrix.suite == 'all'))","failure() && steps.shared_build.outcome == 'failure' && ((matrix.optimization == '0' && matrix.suite == 'direct') || (matrix.optimization == '2' && matrix.suite == 'all'))"],
  ["generation O2 omitted","failure() && steps.shared_build.outcome == 'failure' && ((matrix.optimization == '0' && matrix.suite == 'default') || (matrix.optimization == '2' && matrix.suite == 'all'))","failure() && steps.shared_build.outcome == 'failure' && ((matrix.optimization == '0' && matrix.suite == 'default') || (matrix.optimization == '2' && matrix.suite == 'framework'))"],
  ["generation command omitted","tools/shared/generate_builtin_evidence.py","tools/shared/omitted_builtin_evidence.py"],
  ["generation resource guard relaxed","--rss-mib 5120 --max-output-mib 16 --disk-free-mib 4096 .mlf-build/builtin-generation-guard","--rss-mib 6144 --max-output-mib 16 --disk-free-mib 4096 .mlf-build/builtin-generation-guard"],
  ["generation time allowance widened","--timeout 600\n","--timeout 601\n"],
  ["generation original evidence omitted","            .mlf-build/shared-ghc/builtin-verification/\n",""],
  ["generation real output omitted","            .mlf-build/builtin-generation-guard/\n",""],
  ["generation normal refusal controls omitted","          python3 -B tools/shared/test_generate_builtin_evidence.py\n",""],
  ["generation optimized refusal controls omitted","          python3 -O -B tools/shared/test_generate_builtin_evidence.py\n",""],
  ['missing shard', "          - optimization: '0'\n            suite: default\n", ''],
  ['duplicate shard', '            suite: default\n', '            suite: framework\n'],
  ['missing O2', "          - optimization: '2'\n", "          - optimization: '0'\n"],
  ['matrix exclusion', '        include:\n', '        exclude: []\n        include:\n'],
  ['outer bound changed', '    timeout-minutes: 120\n', '    timeout-minutes: 121\n'],
  ['fail-fast cancellation', '      fail-fast: false\n', '      fail-fast: true\n'],
  ['installation omitted before cleanup', '&& make install)', '&& true)'],
  ['premature install-input cleanup',
    '          (cd "$RUNNER_TEMP/ghc-9.14.1-x86_64-unknown-linux"',
    '          python3 -B tools/release/cleanup-ghc-install.py --receipt .mlf-build/ghc-install-cleanup.json\n          (cd "$RUNNER_TEMP/ghc-9.14.1-x86_64-unknown-linux"'],
  ['install-input cleanup omitted', 'python3 -B tools/release/cleanup-ghc-install.py --receipt', 'python3 -B tools/release/omitted-cleanup.py --receipt'],
  ['cleanup receipt argument omitted', '--receipt .mlf-build/ghc-install-cleanup.json', '--receipt .mlf-build/omitted-cleanup.json'],
  ['cleanup evidence omitted', '            .mlf-build/ghc-install-cleanup.json\n', ''],
  ['normal cleanup controls omitted', '          python3 -B tools/release/test-ghc-install-cleanup.py\n', ''],
  ['optimized cleanup controls omitted', '          python3 -O -B tools/release/test-ghc-install-cleanup.py\n', ''],
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
  ['direct budget override', 'python3 -B tools/shared/test_direct_bounded.py --bin-dir', 'python3 -B tools/shared/test_direct_bounded.py --suite-timeout 5400 --bin-dir'],
  ['Figure12 omitted', 'python3 tools/shared/test_figure12_direct.py', 'python3 tools/shared/omitted.py'],
  // Bind selector mutations to the named step, not the first unrelated O2 step.
  ['O2 guest omitted',
    "      - name: Check actual MLF mixed-framework source acceptance\n        if: matrix.optimization == '2'\n",
    "      - name: Check actual MLF mixed-framework source acceptance\n        if: false\n"],
  ['O2 graph fingerprints omitted',
    "      - name: Check query graph fingerprints and publication recovery\n        if: matrix.optimization == '2'\n",
    "      - name: Check query graph fingerprints and publication recovery\n        if: false\n"],
  ['O2 source graph omitted',
    "      - name: Check source query graph and lowered fallback\n        if: matrix.optimization == '2'\n",
    "      - name: Check source query graph and lowered fallback\n        if: false\n"],
  ['graph fingerprints command omitted', 'tools/performance/crate-query-graph/verify.py', 'tools/performance/crate-query-graph/omitted.py'],
  ['source graph command omitted', 'tools/performance/crate-query-graph/source_checks.py', 'tools/performance/crate-query-graph/omitted_source.py'],
  ['graph fingerprint resource guard relaxed', '--rss-mib 5120 --max-output-mib 100 --disk-free-mib 4096 .mlf-build/source-ich-guard', '--rss-mib 6144 --max-output-mib 100 --disk-free-mib 4096 .mlf-build/source-ich-guard'],
  ['source graph resource guard relaxed', '--rss-mib 5120 --max-output-mib 100 --disk-free-mib 4096 .mlf-build/source-graph-guard', '--rss-mib 6144 --max-output-mib 100 --disk-free-mib 4096 .mlf-build/source-graph-guard'],
  ['O2 source context omitted',
    "      - name: Check retained legacy query API contexts and codecs\n        if: matrix.optimization == '2'\n",
    "      - name: Check retained legacy query API contexts and codecs\n        if: false\n"],
  ['O2 artifact binary omitted',
    "      - name: Check binary artifact codecs and real native storage\n        if: matrix.optimization == '2'\n",
    "      - name: Check binary artifact codecs and real native storage\n        if: false\n"],
  ['binary output allowance widened', '--max-output-mib 640 --disk-free-mib 4096 .mlf-build/artifact-binary-guard', '--max-output-mib 641 --disk-free-mib 4096 .mlf-build/artifact-binary-guard'],
  ['binary modular normal controls omitted', '          python3 -B tools/shared/test_artifact_binary_modular.py\n', ''],
  ['binary modular optimized controls omitted', '          python3 -O -B tools/shared/test_artifact_binary_modular.py\n', ''],
  ['binary command omitted', 'tools/shared/test_artifact_binary.py', 'tools/shared/omitted_artifact_binary.py'],
  ['binary producer receipt omitted', '--build-receipt .mlf-build/shared-ghc/receipt.json --clang clang --gc-prefix "$PWD/.mlf-build/io-action-gc"', '--clang clang --gc-prefix "$PWD/.mlf-build/io-action-gc"'],
  ['binary native sink omitted', '--partial-write-sink /dev/full', ''],
  ['binary native dependencies omitted', '--gc-prefix "$PWD/.mlf-build/io-action-gc"', ''],
  ['binary resource guard relaxed', '--rss-mib 5120 --max-output-mib 640 --disk-free-mib 4096 .mlf-build/artifact-binary-guard', '--rss-mib 6144 --max-output-mib 640 --disk-free-mib 4096 .mlf-build/artifact-binary-guard'],
  ['binary evidence omitted', '            .mlf-build/artifact-binary-guard/results/**/*.json\n', ''],
  ['retained P123 omitted', 'run_integrated.py --suite p123', 'run_integrated.py --suite graph'],
  ['retained graph omitted', 'run_integrated.py --suite graph', 'run_integrated.py --suite builtin'],
  ['retained validation omitted', 'run_integrated.py --suite validation', 'run_integrated.py --suite builtin'],
  ['numeric native suite omitted', 'for suite in host native legacy; do', 'for suite in host legacy; do'],
  ['numeric selector ignored', '--suite "$suite"', '--suite host'],
  ['LLP64 controls omitted', 'tools/performance/int64/run_llp64.py', 'tools/performance/int64/omitted.py'],
  ['collection native route omitted', '--mode standalone\n', '--mode installed\n'],
  ['resource guard relaxed', '--rss-mib 5120 --disk-free-mib 4096 .mlf-build/patricia-focused-guard', '--rss-mib 6144 --disk-free-mib 4096 .mlf-build/patricia-focused-guard'],
  ['artifact collision', '-${{ matrix.suite }}\n', '\n'],
  ['aggregate missing matrix', 'needs: [metadata, native, windows-runtime', 'needs: [metadata, windows-runtime'],
  ['aggregate accepts skipped', '.result == "success"', '.result != "failure"'],
  ['PR matrix skipped', "if: github.event_name != 'workflow_dispatch' || !inputs.windows_runtime_only", "if: github.event_name == 'workflow_dispatch'"],
  ['nonblocking failures', '    timeout-minutes: 120\n', '    timeout-minutes: 120\n    continue-on-error: true\n'],
];
for (const [name, before, after] of controls) {
  assert.ok(workflow.includes(before), `Mutation ${name} must hit the actual workflow`);
  if (['O2 guest omitted', 'O2 graph fingerprints omitted', 'O2 source graph omitted',
       'O2 source context omitted', 'O2 artifact binary omitted'].includes(name)) {
    assert.equal(workflow.split(before).length, 2, `Mutation ${name} must select exactly one named step`);
  }
  const mutated = workflow.replace(before, after);
  assert.notEqual(mutated, workflow, `Mutation ${name} must change the actual workflow`);
  assert.throws(() => validate(mutated), undefined, `Reject ${name}`);
}
console.log(`Native O0/O2 CI partition and ${controls.length} mutation controls passed.`);
