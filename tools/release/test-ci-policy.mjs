// Workflow syntax is separately checked by actionlint. These narrow contracts
// make the PR/main/release split and full coverage executable review assertions.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import './test-native-ci-partition.mjs';
const read = name => fs.readFileSync(`.github/workflows/${name}.yml`,'utf8');
const ci=read('ci'), qualify=read('native-qualification'), release=read('platform-release');
const concurrency = release.match(/^concurrency:\n(?:  #.*\n)*  group: \$\{\{ (.*) \}\}\n  cancel-in-progress: \$\{\{ (.*) \}\}$/m);
assert.ok(concurrency, 'Release/rehearsal concurrency must be explicit');
assert.equal(concurrency[1], "inputs.validation_only && format('platform-validation-{0}', github.ref) || format('platform-release-{0}', inputs.tag || github.sha)");
assert.equal(concurrency[2], 'inputs.validation_only');
// These asserted expressions use syntax shared by Actions and JavaScript.
// Evaluate the actual workflow values, not a separately maintained policy model.
const evaluateConcurrency = (inputs, github) => {
  const format = (pattern, value) => pattern.replace('{0}', value);
  return {
    group: Function('inputs', 'github', 'format', `return (${concurrency[1]});`)(inputs, github, format),
    cancel: Function('inputs', `return (${concurrency[2]});`)(inputs),
  };
};
const rehearsal = (ref, sha) => evaluateConcurrency({validation_only:true,tag:''},{ref,sha});
const publishing = (tag, sha) => evaluateConcurrency({validation_only:false,tag},{ref:'refs/heads/main',sha});
const oldRehearsal = rehearsal('refs/heads/feature', 'a'.repeat(40));
const newRehearsal = rehearsal('refs/heads/feature', 'b'.repeat(40));
assert.deepEqual(oldRehearsal, newRehearsal, 'New commits must supersede stale same-branch rehearsals');
assert.equal(newRehearsal.cancel, true);
assert.notEqual(newRehearsal.group, rehearsal('refs/heads/another', 'b'.repeat(40)).group);
assert.deepEqual(publishing('v0.3.0', 'a'.repeat(40)), publishing('v0.3.0', 'b'.repeat(40)));
assert.equal(publishing('v0.3.0', 'a'.repeat(40)).cancel, false);
assert.notEqual(publishing('v0.3.0', 'a'.repeat(40)).group, publishing('v0.4.0', 'a'.repeat(40)).group);
assert.notEqual(newRehearsal.group, publishing('v0.3.0', 'b'.repeat(40)).group);
assert.deepEqual(publishing('', 'a'.repeat(40)), {group:`platform-release-${'a'.repeat(40)}`,cancel:false});
assert.notEqual(publishing('', 'a'.repeat(40)).group, publishing('', 'b'.repeat(40)).group);
assert.match(ci,/concurrency:\n  group: ci-\$\{\{ github.workflow \}\}-\$\{\{ github.ref \}\}\n  cancel-in-progress: true/);
assert.doesNotMatch(qualify,/^\s*concurrency:/m, 'The reusable workflow must not collide with its caller');
assert.match(qualify,/MLF_TEST_BUILD_JOBS: '1'/);
assert.equal((qualify.match(/build-jobs: '1'/g) || []).length, 7, 'All qualification consumers remain serial');
assert.equal((qualify.match(/\.mlf-build\/prerequisites\/compiler-tests\/build-report.json/g) || []).length, 2, 'Both producers preserve authentic campaign-runner reports');
assert.match(ci,/push:\n    branches: \[main\]/);
assert.match(ci,/if: \(github.event_name == 'push'.*inputs.full_validation.*inputs.self_host/);
assert.match(ci,/uses: \.\/\.github\/workflows\/native-qualification.yml\n    with:\n      source: \$\{\{ github.sha \}\}\n      build_packages: false/);
assert.match(ci,/needs: \[metadata, native, windows-runtime, build-runner, async-runtime, async-language\]/);
assert.match(ci,/length == 6 and all/);
const ciJob = name => ci.match(new RegExp(`^  ${name}:\\n[\\s\\S]*?(?=^  [a-z][a-z-]*:\\n|(?![\\s\\S]))`, 'm'))?.[0];
assert.match(ciJob('metadata'), /fetch-depth: 0/, 'Historical migration audits require full Git history');
const requireHistoricalCheckouts = workflow => {
  const jobs = workflow.match(/^  [a-z][a-z-]*:\n[\s\S]*?(?=^  [a-z][a-z-]*:\n|(?![\s\S]))/gm) || [];
  for (const job of jobs) {
    if (job.includes('tools/release/check.sh') || job.includes('tools/shared/test_framework_direct.py')) {
      assert.match(job, /fetch-depth: 0/, 'Historical audits require a full-history checkout in their own job');
    }
  }
};
for (const workflow of [ci, qualify, release, read('recover-release')]) {
  requireHistoricalCheckouts(workflow);
  assert.throws(() => requireHistoricalCheckouts(workflow.replaceAll('fetch-depth: 0', 'fetch-depth: 1')));
}
assert.match(ciJob('native'), /python3 tools\/shared\/test_framework_direct.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/framework-direct/);
assert.match(ciJob('native'), /python3 tools\/shared\/test_figure12_direct.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json/);
assert.match(ciJob('native'), /\.mlf-build\/framework-direct\/\*\.json\*/);
assert.match(ciJob('native'), /name: Check actual MLF mixed-framework source acceptance\n\s+if: matrix.optimization == '2'\n\s+run: python3 tools\/shared\/test_guest_framework.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/guest-framework-source/);
assert.match(ciJob('native'), /\.mlf-build\/guest-framework-source\/\*\*\/\*\.json/);
assert.match(ciJob('native'), /name: Check actual-import guest Graph and Oracle laws\n\s+if: matrix.optimization == '2'\n\s+run: python3 tools\/shared\/test_guest_state_laws.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/guest-state-laws/);
assert.match(ciJob('native'), /\.mlf-build\/guest-state-laws\/\*\*\/\*\.json/);
assert.match(ciJob('native'), /\.mlf-build\/guest-state-laws\/\*\*\/\*\.log/);

assert.match(ciJob('native'), /\.mlf-build\/figure12-direct\/\*\.json/);

// The integrated source gate is not the separate fixed-ref timing runner.
const finiteGate = `      - name: Check finite P1-P3, A1 and F1 correctness
        if: matrix.optimization == '2'
        run: |
          set -euo pipefail
          python3 -B tools/shared/resource_watchdog.py --seconds 1800 --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 4096 .mlf-build/crate-optimization-guard python3 -B tools/performance/patricia/run_integrated.py --suite p123 --producer .mlf-build/shared-ghc --output .mlf-build/crate-optimization-controls
          python3 -B tools/shared/resource_watchdog.py --seconds 1800 --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 4096 .mlf-build/a1-integrated-guard python3 -B tools/performance/patricia/run_integrated.py --suite graph --producer .mlf-build/shared-ghc --output .mlf-build/a1-integrated-controls
          python3 -B tools/shared/resource_watchdog.py --seconds 1800 --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 4096 .mlf-build/f1-integrated-guard python3 -B tools/performance/patricia/run_fingerprint.py --producer .mlf-build/shared-ghc --output .mlf-build/f1-integrated-controls
`;
const verifyFiniteGate = workflow => {
  assert.ok(workflow.includes(finiteGate), 'Current-source P1-P3/A1/F1 gate, bounds and failure propagation must remain exact');
  for (const root of ['crate-optimization', 'a1-integrated', 'f1-integrated']) {
    assert.ok(workflow.includes(`            .mlf-build/${root}-guard/\n`));
    for (const suffix of ['json', 'stdout', 'stderr']) {
      assert.ok(workflow.includes(`            .mlf-build/${root}-controls/**/*.${suffix}\n`));
    }
  }
};
// C4's full retained graph/transaction controls now run in the explicit ABI
// adapter's graph suite inside this finite gate. Preserve its evidence too.
const c4Gate = finiteGate;
const verifyC4Gate = workflow => {
  assert.ok(workflow.includes(c4Gate), 'Exact O2 C4 graph gate with unchanged resource bounds');
  for (const artifact of [
    '.mlf-build/a1-integrated-guard/',
    '.mlf-build/a1-integrated-controls/**/*.json',
    '.mlf-build/a1-integrated-controls/**/stdout',
    '.mlf-build/a1-integrated-controls/**/stderr',
    '.mlf-build/a1-integrated-controls/**/*.hs',
  ]) assert.ok(workflow.includes('            ' + artifact + '\n'), 'C4 failure/evidence preservation: ' + artifact);
};
verifyC4Gate(ciJob('native'));
assert.throws(() => verifyC4Gate(ciJob('native').replace(c4Gate, '')));
assert.throws(() => verifyC4Gate(ciJob('native').replace(c4Gate, c4Gate.replace("if: matrix.optimization == '2'", 'if: false'))));
assert.throws(() => verifyC4Gate(ciJob('native').replace(c4Gate, c4Gate.replace('--rss-mib 5120', '--rss-mib 99999'))));
assert.throws(() => verifyC4Gate(ciJob('native').replace(c4Gate, c4Gate.replace('set -euo pipefail', 'set +e'))));
assert.throws(() => verifyC4Gate(ciJob('native').replace('.mlf-build/a1-integrated-controls/**/stderr', 'discarded')));
const verifyNumericEvidence = workflow => {
  for (const root of ['patricia-*', 'int64-*', 'llp64-*']) {
    for (const suffix of ['**/*.json', '**/stdout', '**/stderr', '**/*.hs']) {
      assert.ok(workflow.includes(`            .mlf-build/${root}/${suffix}\n`),
        `Keep numeric/collection failure evidence: ${root}/${suffix}`);
    }
  }
};
verifyNumericEvidence(ciJob('native'));
assert.throws(() => verifyNumericEvidence(ciJob('native').replace('.mlf-build/llp64-*/**/stderr', 'discarded')));

verifyFiniteGate(ciJob('native'));
assert.throws(() => verifyFiniteGate(ciJob('native').replace(finiteGate, '')));
assert.throws(() => verifyFiniteGate(ciJob('native').replace(finiteGate, finiteGate.replace("if: matrix.optimization == '2'", 'if: false'))));
assert.throws(() => verifyFiniteGate(ciJob('native').replace(finiteGate, finiteGate.replace('set -euo pipefail', 'set +e'))));
assert.throws(() => verifyFiniteGate(ciJob('native').replace('.mlf-build/a1-integrated-controls/**/*.json', 'discarded')));
assert.throws(() => verifyFiniteGate(ciJob('native').replace('.mlf-build/f1-integrated-controls/**/*.json', 'discarded')));
assert.match(ciJob('native'), /f1-integrated-controls\/\*\*\/source\/Probe\.dump-\*/);
assert.match(ciJob('native'), /f1-integrated-controls\/actual-source\/Separate\.dump-\*/);

for (const name of ['build-runner','async-runtime','async-language']) {
  const job = ciJob(name);
  assert.ok(job, `Missing ${name} coverage`);
  assert.match(job,/github.event_name == 'push' \|\| github.event_name == 'workflow_dispatch'/);
  assert.match(job,/\["ubuntu-24.04", "macos-26"\]/);
  assert.match(job,/\|\| '\["ubuntu-24.04"\]'/);
}
assert.match(ciJob('build-runner'),/process-supervisor-tests/);
const asyncJob = ciJob('async-language');
assert.match(asyncJob,/fetch-depth: 0/);
assert.match(ci,/pull_request:\n    types: \[opened, synchronize, reopened, labeled, unlabeled\]/);
assert.match(fs.readFileSync('tools/release/async-change-scope.py','utf8'), /OPT_IN_LABEL = "ci:async-parity"/);
assert.match(asyncJob,/id: scope\n        run: python3 tools\/release\/async-change-scope.py/);
assert.match(asyncJob,/\.mlf-build\/async-change-scope\/decision.json/);
assert.equal((asyncJob.match(/if: steps.scope.outputs.required != 'false'/g) || []).length, 5);
for (const name of ['Native bootstrap and parity dependencies', 'Fetch verified native seed', 'Bootstrap released seed through frozen bridge to shared native tools', 'Qualify typed completions and structured process tasks', 'Qualify checked async package interfaces and cache replay']) {
  assert.ok(asyncJob.includes(`- name: ${name}\n        if: steps.scope.outputs.required != 'false'\n`));
}
// Only a positive false output skips the expensive steps; unknown/missing
// decisions never opt out. A failed selector still fails this required job.
const selectionExpression = asyncJob.match(/if: (steps.scope.outputs.required != 'false')/)[1];
for (const required of ['true', '', undefined, 'unknown']) {
  assert.equal(Function('steps', `return (${selectionExpression});`)({scope:{outputs:{required}}}), true);
}
assert.equal(Function('steps', `return (${selectionExpression});`)({scope:{outputs:{required:'false'}}}), false);
for (const name of ['build-runner', 'async-runtime', 'windows-runtime', 'native']) {
  assert.doesNotMatch(ciJob(name), /steps\.scope|async-change-scope/, `${name} must stay unconditional`);
}
for (const command of ['scripts/bootstrap-async.sh','tests/fixtures/async-completion/check.sh','tools/release/test-async-process.sh','tools/release/test-async-task.sh','tools/release/test-async-package.sh']) {
  assert.ok(ciJob('async-language').includes(command), `Missing ${command}`);
}
assert.doesNotMatch(ci,/contents: write|continue-on-error/);
assert.doesNotMatch(qualify,/contents: write|continue-on-error/);
assert.match(qualify,/group: \[unit, backends, parity, packages, self-host\]/);
assert.match(qualify,/group: \[backends, parity, packages, self-host\]/);
for (const group of ['mac-port','mac-unit','linux-port','windows','benchmark-game','qualification-gate']) assert.match(qualify,new RegExp(`^  ${group}:$`,'m'));
for (const group of ['mac-package','linux-package']) assert.match(qualify,new RegExp(`  ${group}:\\n    if: inputs.build_packages`));
assert.match(qualify,/name: Package and relocate Windows SDK\n        if: inputs.build_packages/);
assert.match(qualify,/name: Complete qualification gate\n    if: always\(\)/);
assert.match(qualify,/if: always\(\)\n        uses: actions\/upload-artifact/);
assert.doesNotMatch(release,/^  push:/m);
assert.match(release,/uses: \.\/\.github\/workflows\/native-qualification.yml\n    with:\n      source:.*\n      build_packages: true/);
assert.match(release,/needs: \[metadata, qualification\]/);
assert.doesNotMatch(release,/git tag -a|git push origin/);
const runner=fs.readFileSync('tools/release/run-benchmarks.sh','utf8');
assert.match(runner,/"\$output\/results" 7 "\$clang" 3 2 \\\n/);
assert.match(runner,/test "\$status" -eq 0/);
assert.match(runner,/shared-candidate.sh verify/g);
console.log('PR/main/release workflow policy contracts passed.');
