// Workflow syntax is separately checked by actionlint. These narrow contracts
// make the PR/main/release split and full coverage executable review assertions.
import fs from 'node:fs';
import assert from 'node:assert/strict';
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
for (const name of ['build-runner','async-runtime','async-language']) {
  const job = ciJob(name);
  assert.ok(job, `Missing ${name} coverage`);
  assert.match(job,/github.event_name == 'push' \|\| github.event_name == 'workflow_dispatch'/);
  assert.match(job,/\["ubuntu-24.04", "macos-26"\]/);
  assert.match(job,/\|\| '\["ubuntu-24.04"\]'/);
}
assert.match(ciJob('build-runner'),/process-supervisor-tests/);
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
