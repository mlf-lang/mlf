// Exercise the recovery workflow's actual tag guards in a disposable local
// repository. No GitHub access, tag pushes or release publication is performed.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync, spawnSync} from 'node:child_process';

const workflow = fs.readFileSync('.github/workflows/recover-release.yml', 'utf8');
const guards = [...workflow.matchAll(/^          (test "\$\(git rev-parse "refs\/tags\/.*\^\{commit\}"\)" = "\$SOURCE_COMMIT")$/gm)].map(match => match[1]);
assert.deepEqual(guards, [
  'test "$(git rev-parse "refs/tags/v$version^{commit}")" = "$SOURCE_COMMIT"',
  'test "$(git rev-parse "refs/tags/$RELEASE_TAG^{commit}")" = "$SOURCE_COMMIT"',
]);
assert.doesNotMatch(workflow, /git tag -a|git push origin/);
assert.ok(workflow.indexOf(guards[0]) < workflow.indexOf('  macos-package:'));
assert.ok(workflow.indexOf(guards[1]) < workflow.indexOf('gh release create'));
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mlf-release-tag-'));
const env = {...process.env, GIT_AUTHOR_NAME:'Tag test', GIT_AUTHOR_EMAIL:'test@example.invalid',
  GIT_COMMITTER_NAME:'Tag test', GIT_COMMITTER_EMAIL:'test@example.invalid'};
const git = (...args) => execFileSync('git', args, {cwd:directory,env,encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();
let checks = 0;
try {
  git('init', '-q');
  git('commit', '--allow-empty', '-qm', 'qualified source');
  const source = git('rev-parse', 'HEAD');
  git('commit', '--allow-empty', '-qm', 'different source');
  const other = git('rev-parse', 'HEAD');
  const check = (accepted, label) => {
    for (const guard of guards) {
      const result = spawnSync('bash', ['-euo', 'pipefail', '-c', guard], {
        cwd:directory, env:{...env, version:'0.3.0',RELEASE_TAG:'v0.3.0',SOURCE_COMMIT:source},
      });
      assert.equal(result.status === 0, accepted, label);
      checks++;
    }
  };
  check(false, 'Missing tag must fail in metadata and immediately before publishing');
  git('branch', 'v0.3.0', source);
  check(false, 'A branch with the tag name must not substitute for an existing tag');
  git('tag', 'v0.3.0', source);
  check(true, 'An exact lightweight tag is accepted');
  git('tag', '-d', 'v0.3.0');
  git('tag', '-a', 'v0.3.0', source, '-m', 'qualified tag');
  check(true, 'An exact annotated tag is accepted');
  git('tag', '-f', 'v0.3.0', other);
  check(false, 'A moved tag must fail, including the publication recheck');
} finally {
  fs.rmSync(directory, {recursive:true,force:true});
}
console.log(`${checks} recovery existing-tag guards passed.`);
