// Check workflow values and execute provenance routing. Step display names,
// YAML formatting and shell-local variable names are intentionally irrelevant.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {projectAdapterCommands} from './workflow-test-adapters.mjs';
import {releaseTestCase, releaseTestEvent} from './test-events.mjs';
import {readWorkflow, job, commandStep, actionStep, paths, clone, reformatted} from './workflow-model.mjs';
import {shellCalls, successfulCalls, requireFailurePropagation, shellCommand} from './workflow-shell.mjs';

const workflow = readWorkflow('macos-toolchain');
const provenance = value => job(value, 'provenance');
const install = value => commandStep(provenance(value), 'curl');
const build = value => commandStep(provenance(value), 'tools/shared/prepare_async_ghc.py');
const reject = (value, change) => {
  const changed = clone(value);
  change(changed);
  assert.throws(() => verify(changed));
};
const jqAccepts = (query, value) => {
  const result = spawnSync('jq', ['-e', query], {input: JSON.stringify(value), encoding: 'utf8'});
  assert.equal(result.error, undefined);
  assert.ok(result.status === 0 || result.status === 1, result.stderr);
  return result.status === 0;
};
const downloadOptions = {commands: ['curl'], stubs: String.raw`
shasum() {
  local input='' line
  while IFS= read -r line; do input="$input$line"$'\n'; done
  record shasum "$@" "$input"
}
tar() { record tar "$@"; exit 0; }
`};

const verify = value => {
  for (const path of ['.github/workflows/macos-toolchain.yml', 'tools/shared/build.py',
    'tools/shared/test_darwin_toolchain.py', 'tools/release/test-macos-toolchain-workflow.mjs']) {
    assert.ok(value.on.pull_request.paths.includes(path));
  }
  assert.equal(value.on.pull_request_target, undefined);
  assert.equal(value.permissions.contents, 'read');
  const native = provenance(value);
  assert.equal(native['runs-on'], 'macos-26');
  assert.equal(native['timeout-minutes'], 120);
  assert.ok(!native['continue-on-error']);
  const upload = actionStep(native, 'actions/upload-artifact');
  assert.equal(upload.if, 'always()');
  for (const step of native.steps) {
    assert.ok(!step['continue-on-error']);
    if (step !== upload) assert.equal(step.if, undefined, 'Provenance steps must run unconditionally');
  }
  for (const path of ['macos-toolchain/', 'async-ghc/async-tools.json', 'async-ghc/receipt.json',
    'async-ghc/*.stderr', 'async-ghc/*.stdout', 'async-ghc/*.log', 'async-ghc/builtin-verification/']) {
    assert.ok(paths(upload).includes('.mlf-build/' + path));
  }
  const dependencies=commandStep(native,'brew install');
  const dependencyOptions={env:{GITHUB_PATH:'/dev/null',GITHUB_ENV:'/dev/null',FIXTURE_ARCH:'arm64'},stubs:String.raw`
uname() { printf '%s\n' "$FIXTURE_ARCH"; }
brew() {
  record brew "$@" || return
  if [ "$1" = --prefix ]; then printf '/fixture/%s\n' "$2"; fi
}
`};
  const dependencyCalls=successfulCalls(dependencies.run,dependencyOptions);
  assert.deepEqual(dependencyCalls.map(call=>call.argv),[
    ['brew','install','llvm@19','gmp','pkg-config','bdw-gc','jq'],
    ['brew','--prefix','llvm@19'],['brew','--prefix','bdw-gc'],
  ]);
  requireFailurePropagation(dependencies.run,dependencyOptions,[dependencyCalls[0]]);
  const wrongArchitecture=shellCalls(dependencies.run,{...dependencyOptions,
    env:{...dependencyOptions.env,FIXTURE_ARCH:'x86_64'}});
  assert.notEqual(wrongArchitecture.status,0);
  assert.deepEqual(wrongArchitecture.calls,[],'Wrong architecture must stop before installation');
  const controls = successfulCalls(projectAdapterCommands(commandStep(native,
    'tools/testing/run.py python-shared-darwin-toolchain').run), {
    stubs: 'tee() { while IFS= read -r line; do :; done; }',
  });
  assert.deepEqual(controls.map(call => call.argv), [
    ['python3', '-B', 'tools/shared/test_darwin_toolchain.py'],
    ['python3', '-O', '-B', 'tools/shared/test_darwin_toolchain.py'],
    ['python3', '-B', 'tools/shared/test_prepare_async_ghc.py'],
    ['python3', '-O', '-B', 'tools/shared/test_prepare_async_ghc.py'],
  ]);
  const download = successfulCalls(install(value).run, downloadOptions);
  assert.deepEqual(download.map(call => call.argv), [
    ['curl', '-fsSL', 'https://downloads.haskell.org/~ghc/9.14.1/ghc-9.14.1-aarch64-apple-darwin.tar.xz',
      '-o', '/workflow-test/ghc-9.14.1.tar.xz'],
    ['shasum', '-a', '256', '-c', '-',
      '841591f152085be605616682779341847d24fd56bd6d22ca61bb37ee32b50681  /workflow-test/ghc-9.14.1.tar.xz\n'],
    ['tar', '-xJf', '/workflow-test/ghc-9.14.1.tar.xz', '-C', '/workflow-test'],
  ]);
  requireFailurePropagation(install(value).run, downloadOptions, download.slice(0, 2));
  const options = {commands: ['python3', 'jq']};
  const calls = successfulCalls(build(value).run, options);
  assert.equal(calls.length, 4, 'Build plus three receipt verifications must execute');
  assert.deepEqual(calls[0].argv, ['python3', '-B', 'tools/shared/prepare_async_ghc.py',
    '--build-dir', '.mlf-build/async-ghc', '--clang', 'clang', '--optimization', '2']);
  for (const [index, path] of [[1, 'receipt.json'], [2, 'receipt.json'], [3, 'async-tools.json']]) {
    assert.deepEqual([calls[index].argv[0], calls[index].argv[1], calls[index].argv[3]],
      ['jq', '-e', '.mlf-build/async-ghc/' + path]);
  }
  const producer = {complete: true, producer_host: 'GHC', typecheck_only: false, optimization: '2'};
  assert.equal(jqAccepts(calls[1].argv[2], producer), true);
  for (const wrong of [{complete: false}, {producer_host: 'MLF'}, {typecheck_only: true}, {optimization: '0'}]) {
    assert.equal(jqAccepts(calls[1].argv[2], {...producer, ...wrong}), false);
  }
  const tools = {complete: true, producer_host: 'GHC', runner_protocol_version: 1};
  assert.equal(jqAccepts(calls[3].argv[2], tools), true);
  for (const wrong of [{complete: false}, {producer_host: 'MLF'}, {runner_protocol_version: 2}]) {
    assert.equal(jqAccepts(calls[3].argv[2], {...tools, ...wrong}), false);
  }
  for (const basename of ['libclang-cpp.dylib', 'libclang-cpp.19.dylib', 'libclang-cpp.19.1.7.dylib',
    'libclang-cpp.dylib.extra', 'libclang-cpp.fake.dylib', 'libclang-cpp.so', 'not-libclang-cpp.dylib']) {
    assert.equal(jqAccepts(calls[2].argv[2], {toolchain: {files: {['/llvm/lib/' + basename]: 'hash'}}}),
      /^libclang-cpp(?:\.[0-9]+)*\.dylib$/.test(basename), basename);
  }
  requireFailurePropagation(build(value).run, options, calls);
};
const suite = 'release-macos-toolchain-workflow';
const prefix = 'release/macos-toolchain-workflow/';
const cases = [
  ['workflow', () => verify(workflow)],
  ['equivalent-yaml-and-display-names', () => verify(reformatted(workflow))],
  ['equivalent-shell-locals-and-receipt-predicate', () => {
    const changed = clone(workflow);
    install(changed).run = install(changed).run.replaceAll('archive', 'tarball').replaceAll('distribution', 'bindist');
    build(changed).run = build(changed).run.replace('.complete == true and .producer_host == "GHC"',
      '.producer_host == "GHC" and .complete');
    verify(changed);
  }],
  ['required/runs-on%3A%20macos-26', () => reject(workflow, value => provenance(value)['runs-on'] = 'ubuntu-24.04')],
  ['required/contents%3A%20read', () => reject(workflow, value => value.permissions.contents = 'write')],
  ['required/timeout-minutes%3A%20120', () => reject(workflow, value => provenance(value)['timeout-minutes'] = 121)],
  ['required/path-scope', () => reject(workflow, value => value.on.pull_request.paths.pop())],
  ['required/841591f152085be605616682779341847d24fd56bd6d22ca61bb37ee32b50681', () => reject(workflow, value => install(value).run = install(value).run.replaceAll('841591f', '0000000'))],
  ['required/if%3A%20always()', () => reject(workflow, value => actionStep(provenance(value), 'actions/upload-artifact').if = 'success()')],
  ['required/.mlf-build%2Fasync-ghc%2F*.stderr', () => reject(workflow, value => {
    const upload = actionStep(provenance(value), 'actions/upload-artifact');
    upload.with.path = paths(upload).filter(path => !path.endsWith('*.stderr')).join('\n');
  })],
  ['fail-open', () => reject(workflow, value => provenance(value)['continue-on-error'] = true)],
  ['run-condition', () => reject(workflow, value => build(value).if = false)],
  ['shell-failure', () => reject(workflow, value => {
    const calls=successfulCalls(build(value).run,{commands:['python3','jq']});
    build(value).run='set +e\n'+calls.map(call=>shellCommand(call.argv)).join('\n')+'\ntrue';
  })],
];
for (const [label, alter] of [
  ['commented-provenance-command', line => '# ' + line],
  ['conditional-provenance-command', line => `if false; then\n${line}\nfi`],
  ['swallowed-provenance-failure', line => line + ' || :'],
]) {
  cases.push([label, () => {
    for (const identify of [install, build]) {
      const isInstall=identify===install;
      const calls=successfulCalls(identify(workflow).run,isInstall?downloadOptions:{commands:['python3','jq']});
      const lines=calls.map(({argv})=>argv[0]==='shasum'
        ? shellCommand(['printf','%s',argv.at(-1)])+' | '+shellCommand(argv.slice(0,-1))
        : shellCommand(argv));
      for (const index of isInstall?[1]:[0,1,2,3]) reject(workflow,value=>{
        identify(value).run=lines.map((line,offset)=>index===offset?alter(line):line).join('\n');
      });
    }
  }]);
}
const exact = process.env.MLF_TEST_SUITE === suite ? process.env.MLF_TEST_EXACT : undefined;
const plan = cases.map(([label]) => prefix + label).filter(id => !exact || exact === id);
assert.ok(plan.length, 'Unknown macOS workflow case');
if (process.argv.includes('--framework-list')) console.log(JSON.stringify(plan));
else {
  releaseTestEvent(suite, {plan});
  for (const [label, action] of cases) if (!exact || exact === prefix + label) releaseTestCase(suite, prefix + label, action);
  console.log(`macOS workflow semantics: ${plan.length} checks passed.`);
}
