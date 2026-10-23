// Workflow syntax is separately checked by actionlint. These narrow contracts
// make the PR/main/release split and full coverage executable review assertions.
import fs from 'node:fs';
import assert from 'node:assert/strict';
const read = name => fs.readFileSync(`.github/workflows/${name}.yml`,'utf8');
const ci=read('ci'), qualify=read('native-qualification'), release=read('platform-release');
assert.match(ci,/push:\n    branches: \[main\]/);
assert.match(ci,/if: \(github.event_name == 'push'.*inputs.full_validation.*inputs.self_host/);
assert.match(ci,/uses: \.\/\.github\/workflows\/native-qualification.yml\n    with:\n      source: \$\{\{ github.sha \}\}\n      build_packages: false/);
assert.match(ci,/needs: \[metadata, native, windows-runtime, build-runner\]/);
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
