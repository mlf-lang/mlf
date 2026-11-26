// Workflow syntax is separately checked by actionlint. These narrow contracts
// make the PR/main/release split and full coverage executable review assertions.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {projectAdapterCommands} from './workflow-test-adapters.mjs';
import {releaseTestEvent} from './test-events.mjs';

const suite = 'release-ci-policy';
let active;
const begin = name => {
  active = 'release/ci/' + name;
  releaseTestEvent(suite, {start: active});
};
const pass = () => {
  releaseTestEvent(suite, {id: active, status: 'pass'});
  active = undefined;
};
process.on('uncaughtExceptionMonitor', error => {
  if (active) releaseTestEvent(suite, {id: active, status: 'fail', detail: String(error)});
});

const read = name => projectAdapterCommands(fs.readFileSync(`.github/workflows/${name}.yml`,'utf8'));
const ci=read('ci'), qualify=read('native-qualification'), release=read('platform-release');
begin('concurrency');
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
pass();
begin('required-checks');
assert.doesNotMatch(qualify,/^\s*concurrency:/m, 'The reusable workflow must not collide with its caller');
assert.match(qualify,/MLF_TEST_BUILD_JOBS: '1'/);
assert.equal((qualify.match(/build-jobs: '1'/g) || []).length, 7, 'All qualification consumers remain serial');
assert.equal((qualify.match(/\.mlf-build\/prerequisites\/compiler-tests\/build-report.json/g) || []).length, 2, 'Both producers preserve authentic campaign-runner reports');
assert.match(ci,/push:\n    branches: \[main\]/);
assert.match(ci,/if: github.event_name == 'workflow_dispatch' && \(inputs.full_validation \|\| inputs.self_host\) && !inputs.windows_runtime_only/);
assert.doesNotMatch(ci,/if: \(github.event_name == 'push'.*inputs.full_validation.*inputs.self_host/);
assert.match(ci,/uses: \.\/\.github\/workflows\/native-qualification.yml\n    with:\n      source: \$\{\{ github.sha \}\}\n      build_packages: false/);
assert.match(ci,/needs: \[metadata, native, windows-runtime, build-runner, async-runtime, async-language\]/);
assert.match(ci,/length == 6 and all/);
const workflowJob = (workflow, name) => workflow.match(new RegExp(`^  ${name}:\\n[\\s\\S]*?(?=^  [a-z][a-z-]*:\\n|(?![\\s\\S]))`, 'm'))?.[0];
const ciJob = name => workflowJob(ci, name);
const runPrTests = "github.event_name != 'pull_request' || !contains(github.event.pull_request.labels.*.name, 'ci:skip')";
// Evaluate the workflow expressions for real PR event shapes, including labels added
// and removed from the same SHA while the original required checks are still active.
const evaluateRoute = (expression, github) => Function('github', 'inputs', 'contains', 'always',
  'return (' + expression.replaceAll('github.event.pull_request.labels.*.name',
    'github.event.pull_request.labels.map(label => label.name)') + ');')(
    github, {}, (values, name) => values.includes(name), () => true);
const routingCondition = job => {
  const expr = job.match(/^    if: >-\n((?:      [^\n]+\n)+)/m);
  return expr ? expr[1].trim() : job.match(/^    if: (.+)$/m)?.[1];
};
const render = (template, github) => template.replace(/\$\{\{ (.*?) \}\}/g,
  (_, expr) => expr.startsWith('matrix.') ? 'fixture' : String(evaluateRoute(expr, github)));
for (const [name, jobs] of [
  ['ci', ['metadata', 'native', 'build-runner', 'async-runtime', 'async-language', 'windows-runtime']],
  ['formatter-compatibility', ['formatter-compatibility']],
  ['macos-toolchain', ['provenance']],
  ['macos-dependencies', ['producer']],
]) {
  const workflow = read(name);
  assert.match(workflow, /^  pull_request:\n[\s\S]*?^    types: \[opened, synchronize, reopened, labeled, unlabeled\]$/m);
  assert.match(workflow, /^  cancel-in-progress: true$/m);
  const group = workflow.match(/^concurrency:\n(?:  #.*\n)*  group: (.+)$/m)[1];
  const event = (action, changed, labels, id=1) => ({
    event_name: 'pull_request', workflow: name, ref: 'refs/pull/55/merge', run_id: id,
    event: {action, ...(changed && {label:{name:changed}}), pull_request:{labels:labels.map(name => ({name}))}},
  });
  const revision = event('synchronize', null, []);
  const active = render(group, revision);
  const contexts = [
    [revision, true, true], [event('opened', null, []), true, true],
    [{...revision, event_name:'push', event:{}}, true, true],
    [{...revision, event_name:'merge_group', event:{}}, true, true],
    [event('labeled', 'ci:skip', ['ci:skip']), true, false],
    [event('unlabeled', 'ci:skip', []), true, true],
    [event('labeled', 'ci:async-parity', ['ci:async-parity']), name === 'ci', name === 'ci'],
    [event('unlabeled', 'ci:async-parity', []), name === 'ci', name === 'ci'],
    [event('labeled', 'documentation', ['documentation']), false, false],
    [event('unlabeled', 'documentation', ['ci:async-parity']), false, false],
    [event('unlabeled', 'documentation', ['ci:skip']), false, false],
  ];
  for (const [github, relevant, runsTests] of contexts) {
    assert.equal(render(group, github) === active, relevant, name + ' cancellation group');
    for (const id of jobs) {
      const job = workflowJob(workflow, id);
      assert.equal(evaluateRoute(routingCondition(job), github), runsTests, name + '/' + id);
      const title = job.match(/^    name: (.+)$/m)[1];
      assert.equal(render(title, github) === render(title, revision), relevant, id + ' check name');
    }
    if (name === 'ci') {
      const gate = ciJob('pr-gate');
      assert.equal(evaluateRoute(routingCondition(gate), github), relevant);
      assert.equal(render(gate.match(/^    name: (.+)$/m)[1], github) === 'PR gate', relevant);
    }
  }
  assert.notEqual(render(group, event('labeled', 'docs', ['docs'], 11)),
    render(group, event('unlabeled', 'docs', [], 12)));
}
const dependencyWorkflow = fs.readFileSync('.github/workflows/macos-dependencies.yml', 'utf8');
const requireDependencyArtifact = workflow => {
  const name = 'pinned-macos-dependency-hashes';
  const step = (job, action) => {
    const matches = job.split(/^      - /m).filter(candidate =>
      candidate.startsWith(`uses: actions/${action}-artifact@`) && candidate.includes(`          name: ${name}\n`));
    assert.equal(matches.length, 1, `One ${action} of the pinned macOS dependency hashes is required`);
    return matches[0];
  };
  const upload = step(workflowJob(workflow, 'producer'), 'upload');
  const paths = upload.match(/^          path: \|\n((?:            [^\n]+\n)+)/m)?.[1].trim().split(/\s+/);
  // A sibling upload path changes the archive root to their common parent.
  assert.deepEqual(paths?.sort(), ['closure.txt', 'files.sha256', 'homebrew-core-commit', 'installed.json']
    .map(file => `.mlf-build/macos-dependencies/${file}`), 'The hash artifact must contain four root-level input files');
  const consumer = workflowJob(workflow, 'consumer');
  assert.match(consumer, /^    needs: producer$/m);
  const download = step(consumer, 'download');
  const downloadPath = download.match(/^          path: ([^\n]+)$/m)?.[1];
  assert.ok(downloadPath && consumer.includes(`tools/testing/run.py macos-dependencies-verify -- ${downloadPath}\n`),
    'The verifier requires the artifact download directory');
};
requireDependencyArtifact(dependencyWorkflow);
assert.throws(() => requireDependencyArtifact(dependencyWorkflow.replace(
  '            .mlf-build/macos-dependencies/closure.txt\n',
  '            .mlf-build/test-framework/\n            .mlf-build/macos-dependencies/closure.txt\n')),
/The hash artifact must contain four root-level input files/);
assert.throws(() => requireDependencyArtifact(dependencyWorkflow.replace(
  '          path: .mlf-build/producer-dependencies\n', '          path: .mlf-build/wrong-download-root\n')),
/The verifier requires the artifact download directory/);
const gate = ciJob('pr-gate');
assert.ok(gate.includes("        if: github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'ci:skip')\n"));
assert.ok(gate.includes(`      - name: Require every merge check to succeed\n        if: ${runPrTests}\n`));
pass();
begin('history');
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
const historyPreparation = 'python3 -B tools/testing/prepare_history_refs.py';
const requirePreparedHistory = (text, consumer) => {
  const prepareAt = text.indexOf(historyPreparation);
  const consumeAt = text.indexOf(consumer);
  assert.ok(prepareAt >= 0 && consumeAt > prepareAt,
    'Pinned squash history must be prepared explicitly before historical consumers');
};
const releaseChecks = fs.readFileSync('tools/release/check.sh', 'utf8');
for (const [text, consumer] of [
  [releaseChecks, 'run benchmark-provenance'],
  [ciJob('native'), 'name: Install pinned direct-host GHC'],
]) {
  requirePreparedHistory(text, consumer);
  assert.throws(() => requirePreparedHistory(text.replace(historyPreparation, ''), consumer));
  assert.throws(() => requirePreparedHistory(text.replace(historyPreparation, '') + historyPreparation, consumer));
}
pass();
begin('hosted-guest');
assert.match(ciJob('native'), /python3 tools\/shared\/test_framework_direct.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/framework-direct/);
assert.match(ciJob('native'), /python3 tools\/shared\/test_figure12_direct.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json/);
assert.match(ciJob('native'), /\.mlf-build\/framework-direct\/\*\.json\*/);
assert.match(ciJob('native'), /name: Check actual MLF mixed-framework source acceptance\n\s+if: matrix.optimization == '2'\n\s+run: python3 tools\/shared\/test_guest_framework.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/guest-framework-source/);
assert.match(ciJob('native'), /\.mlf-build\/guest-framework-source\/\*\*\/\*\.json/);
assert.match(ciJob('native'), /name: Check actual-import guest Graph and Oracle laws\n\s+if: matrix.optimization == '2'\n\s+run: python3 tools\/shared\/test_guest_state_laws.py --build-receipt \.mlf-build\/shared-ghc\/receipt.json --output \.mlf-build\/guest-state-laws/);
assert.match(ciJob('native'), /\.mlf-build\/guest-state-laws\/\*\*\/\*\.json/);
assert.match(ciJob('native'), /\.mlf-build\/guest-state-laws\/\*\*\/\*\.log/);

assert.match(ciJob('native'), /\.mlf-build\/figure12-direct\/\*\.json/);

pass();
begin('resource-and-output-bounds');
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
  // C4's retained graph/transaction controls share this gate; keep their
  // additional source and extensionless diagnostic artifacts as well.
  for (const artifact of [
    '.mlf-build/a1-integrated-controls/**/stdout',
    '.mlf-build/a1-integrated-controls/**/stderr',
    '.mlf-build/a1-integrated-controls/**/*.hs',
  ]) assert.ok(workflow.includes('            ' + artifact + '\n'), 'C4 failure/evidence preservation: ' + artifact);
};
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
assert.throws(() => verifyFiniteGate(ciJob('native').replace(finiteGate, finiteGate.replace('--rss-mib 5120', '--rss-mib 99999'))));
assert.throws(() => verifyFiniteGate(ciJob('native').replace(finiteGate, finiteGate.replace('set -euo pipefail', 'set +e'))));
assert.throws(() => verifyFiniteGate(ciJob('native').replace('.mlf-build/a1-integrated-controls/**/stderr', 'discarded')));
assert.throws(() => verifyFiniteGate(ciJob('native').replace('.mlf-build/a1-integrated-controls/**/*.json', 'discarded')));
assert.throws(() => verifyFiniteGate(ciJob('native').replace('.mlf-build/f1-integrated-controls/**/*.json', 'discarded')));
assert.match(ciJob('native'), /f1-integrated-controls\/\*\*\/source\/Probe\.dump-\*/);
assert.match(ciJob('native'), /f1-integrated-controls\/actual-source\/Separate\.dump-\*/);

pass();
begin('async-platforms');
for (const name of ['build-runner','async-runtime','async-language']) {
  const job = ciJob(name);
  assert.ok(job, `Missing ${name} coverage`);
  assert.match(job,/github.event_name == 'push' \|\| github.event_name == 'workflow_dispatch'/);
  assert.match(job,/\["ubuntu-24.04", "macos-26"\]/);
  assert.match(job,/\|\| '\["ubuntu-24.04"\]'/);
}
assert.match(workflowJob(fs.readFileSync('.github/workflows/ci.yml', 'utf8'), 'build-runner'),
  /tools\/testing\/run[.]py native-build-tools\b/);
const asyncJob = ciJob('async-language');
assert.match(asyncJob,/fetch-depth: 0/);
assert.match(ci,/pull_request:\n    types: \[opened, synchronize, reopened, labeled, unlabeled\]/);
assert.match(fs.readFileSync('tools/release/async-change-scope.py','utf8'), /OPT_IN_LABEL = "ci:async-parity"/);
assert.match(asyncJob,/id: scope\n        run: python3 tools\/release\/async-change-scope.py/);
assert.match(asyncJob,/\.mlf-build\/async-change-scope\/decision.json/);
assert.match(asyncJob, /uses: \.\/\.github\/actions\/linux-ghc-bindist\n        if: steps.scope.outputs.required != 'false' && runner\.os == 'Linux'/);
for (const name of ['GHC-origin bootstrap and native parity dependencies', 'Install pinned GHC 9.14.1 for ordinary async parity', 'Test GHC async preparation controls', 'Build and authenticate GHC-origin async tools', 'Qualify typed completions and structured process tasks', 'Qualify checked async package interfaces and cache replay']) {
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
assert.doesNotMatch(asyncJob,/scripts\/bootstrap-async\.sh/);
for (const command of ['tools/shared/prepare_async_ghc.py','tests/fixtures/async-completion/check.sh','tools/release/test-async-process.sh','tools/release/test-async-task.sh','tools/release/test-async-package.sh']) {
  assert.ok(ciJob('async-language').includes(command), `Missing ${command}`);
}
pass();
begin('native-and-publishing');
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
pass();
console.log('PR/main/release workflow policy contracts passed.');
