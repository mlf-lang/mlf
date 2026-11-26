// Policy is evaluated from parsed workflow values. Actionlint covers syntax;
// the native partition and macOS suites execute their actual shell commands.
import assert from 'node:assert/strict';
import {projectAdapterCommands} from './workflow-test-adapters.mjs';
import {releaseTestEvent} from './test-events.mjs';
import {readWorkflow, job, steps, actionSteps, actionStep, commandStep, list, paths,
  expression, selected, render, clone, reformatted} from './workflow-model.mjs';
import {successfulCalls} from './workflow-shell.mjs';

const suite = 'release-ci-policy';
let active;
const check = (name, action) => {
  active = 'release/ci/' + name;
  releaseTestEvent(suite, {start: active});
  action();
  releaseTestEvent(suite, {id: active, status: 'pass'});
  active = undefined;
};
process.on('uncaughtExceptionMonitor', error => {
  if (active) releaseTestEvent(suite, {id: active, status: 'fail', detail: String(error)});
});
const ci = readWorkflow('ci'), qualify = readWorkflow('native-qualification'), release = readWorkflow('platform-release');
const requiredJobs = ['metadata', 'native', 'windows-runtime', 'build-runner', 'async-runtime', 'async-language'];
const context = github => ({github, matrix: {optimization: '0', suite: 'routine', os: 'ubuntu-24.04'}});

check('concurrency', () => {
  const verify = workflow => {
    const concurrency = (inputs, github) => ({group: render(workflow.concurrency.group, {inputs, github}),
      cancel: expression(workflow.concurrency['cancel-in-progress'], {inputs, github})});
    const rehearsal = (ref, sha) => concurrency({validation_only:true, tag:''}, {ref, sha});
    const publishing = (tag, sha) => concurrency({validation_only:false, tag}, {ref:'refs/heads/main', sha});
    const old = rehearsal('refs/heads/feature', 'a'.repeat(40));
    const current = rehearsal('refs/heads/feature', 'b'.repeat(40));
    assert.deepEqual(old, current);
    assert.equal(current.cancel, true);
    assert.notEqual(current.group, rehearsal('refs/heads/another', 'b'.repeat(40)).group);
    assert.deepEqual(publishing('v0.3.0', 'a'.repeat(40)), publishing('v0.3.0', 'b'.repeat(40)));
    assert.equal(publishing('v0.3.0', 'a'.repeat(40)).cancel, false);
    assert.notEqual(publishing('v0.3.0', 'a'.repeat(40)).group, publishing('v0.4.0', 'a'.repeat(40)).group);
    assert.notEqual(current.group, publishing('v0.3.0', 'b'.repeat(40)).group);
    assert.notEqual(publishing('', 'a'.repeat(40)).group, publishing('', 'b'.repeat(40)).group);
  };
  verify(release); verify(reformatted(release));
  const changed = clone(release); changed.concurrency['cancel-in-progress'] = true;
  assert.throws(() => verify(changed));
});

check('required-checks', () => {
  assert.equal(qualify.concurrency, undefined, 'Reusable workflow must not cancel its caller');
  assert.equal(String(qualify.env.MLF_TEST_BUILD_JOBS), '1');
  const consumers = Object.values(qualify.jobs).flatMap(entry => actionSteps(entry, './.github/actions/posix-qualification'));
  assert.equal(consumers.length, 7);
  for (const step of consumers) assert.equal(String(step.with['build-jobs']), '1');
  for (const name of ['mac-prerequisites','linux-candidate']) {
    const retained=actionSteps(job(qualify,name),'actions/upload-artifact').filter(step=>
      paths(step).includes('.mlf-build/prerequisites/compiler-tests/build-report.json'));
    assert.equal(retained.length,1,'Every platform retains its authenticated campaign-runner report');
    assert.equal(selected(retained[0],{success:()=>false,failure:()=>true}),true);
  }

  assert.deepEqual(ci.on.push.branches, ['main']);
  assert.equal(job(ci, 'qualification').uses, './.github/workflows/native-qualification.yml');
  assert.equal(job(ci, 'qualification').with.build_packages, false);
  assert.equal(render(job(ci, 'qualification').with.source, {github:{sha:'checked-source'}}), 'checked-source');
  for (const event_name of ['push', 'pull_request', 'workflow_dispatch']) {
    for (const full_validation of [false, true]) for (const self_host of [false, true]) {
      for (const windows_runtime_only of [false, true]) {
        assert.equal(selected(job(ci, 'qualification'), {github:{event_name}, inputs:{full_validation,self_host,windows_runtime_only}}),
          event_name === 'workflow_dispatch' && (full_validation || self_host) && !windows_runtime_only);
      }
    }
  }
  assert.equal(selected(job(ci,'pr-gate'),{github:{event_name:'workflow_dispatch',event:{}}}),false);
  const verifyRouting = (name, workflow, ids) => {
    assert.deepEqual(new Set(workflow.on.pull_request.types), new Set(['opened','synchronize','reopened','labeled','unlabeled']));
    assert.equal(workflow.concurrency['cancel-in-progress'], true);
    const event = (action, changed, labels, id=1) => ({event_name:'pull_request',workflow:name,
      ref:'refs/pull/55/merge',run_id:id,event:{action,...(changed && {label:{name:changed}}),pull_request:{labels:labels.map(name => ({name}))}}});
    const revision = event('synchronize', null, []);
    const baseline = render(workflow.concurrency.group, context(revision));
    const contexts = [
      [revision, true, true], [event('opened', null, []), true, true],
      [{...revision,event_name:'push',event:{}},true,true],
      [{...revision,event_name:'merge_group',event:{}},true,true],
      [event('labeled','ci:skip',['ci:skip']),true,false],
      [event('unlabeled','ci:skip',[]),true,true],
      [event('labeled','ci:async-parity',['ci:async-parity']),name==='ci',name==='ci'],
      [event('unlabeled','ci:async-parity',[]),name==='ci',name==='ci'],
      [event('labeled','documentation',['documentation']),false,false],
      [event('unlabeled','documentation',['ci:async-parity']),false,false],
      [event('unlabeled','documentation',['ci:skip']),false,false],
    ];
    for (const [github,relevant,runs] of contexts) {
      assert.equal(render(workflow.concurrency.group, context(github)) === baseline, relevant);
      for (const id of ids) {
        assert.equal(selected(job(workflow,id), context(github)), runs, name+'/'+id);
        assert.equal(render(job(workflow,id).name,context(github)) === render(job(workflow,id).name,context(revision)), relevant);
      }
      if (name === 'ci') {
        assert.equal(selected(job(workflow,'pr-gate'),context(github)),relevant);
        assert.equal(render(job(workflow,'pr-gate').name,context(github)) === 'PR gate', relevant);
      }
    }
    assert.notEqual(render(workflow.concurrency.group,context(event('labeled','docs',['docs'],11))),
      render(workflow.concurrency.group,context(event('unlabeled','docs',[],12))));
  };
  for (const [name,ids] of [['ci',requiredJobs],['formatter-compatibility',['formatter-compatibility']],
    ['macos-toolchain',['provenance']],['macos-dependencies',['producer']]]) {
    const workflow = readWorkflow(name);
    verifyRouting(name, workflow, ids); verifyRouting(name,reformatted(workflow),ids);
    const changed = clone(workflow); changed.concurrency.group = '${{ github.ref }}';
    assert.throws(() => verifyRouting(name,changed,ids));
  }
  const verifyDependencyArtifact = workflow => {
    const producer = job(workflow,'producer'), consumer = job(workflow,'consumer');
    const upload = actionSteps(producer,'actions/upload-artifact').filter(step => step.with.name === 'pinned-macos-dependency-hashes');
    const download = actionSteps(consumer,'actions/download-artifact').filter(step => step.with.name === 'pinned-macos-dependency-hashes');
    assert.equal(upload.length,1); assert.equal(download.length,1);
    assert.deepEqual(paths(upload[0]).sort(), ['closure.txt','files.sha256','homebrew-core-commit','installed.json']
      .map(file => '.mlf-build/macos-dependencies/'+file));
    assert.deepEqual(list(consumer.needs),['producer']);
    const calls = successfulCalls(commandStep(consumer,'tools/testing/run.py macos-dependencies-verify').run);
    assert.deepEqual(calls.map(call => call.argv),[['python3','-B','tools/testing/run.py','macos-dependencies-verify','--',download[0].with.path]]);
  };
  const deps = readWorkflow('macos-dependencies'); verifyDependencyArtifact(deps); verifyDependencyArtifact(reformatted(deps));
  const changed = clone(deps); actionStep(job(changed,'consumer'),'actions/download-artifact').with.path = '.mlf-build/wrong';
  assert.throws(() => verifyDependencyArtifact(changed));
});

check('hosted-guest', () => {
  const native = job(ci,'native');
  const upload = actionStep(native,'actions/upload-artifact');
  const expected = ['framework-direct/*.json*','guest-framework-source/**/*.json','guest-state-laws/**/*.json',
    'guest-state-laws/**/*.log','figure12-direct/*.json'];
  for (const path of expected) assert.ok(paths(upload).includes('.mlf-build/'+path));
  for (const adapter of ['guest-framework','guest-state-laws']) {
    const step = commandStep(native,'tools/testing/run.py '+adapter+' --');
    for (const optimization of ['0','2']) assert.equal(selected(step,{matrix:{optimization}}),optimization === '2');
  }
});
check('resource-and-output-bounds', () => {
  const upload = actionStep(job(ci,'native'),'actions/upload-artifact');
  for (const root of ['crate-optimization','a1-integrated','f1-integrated']) {
    assert.ok(paths(upload).includes(`.mlf-build/${root}-guard/`));
    for (const suffix of ['json','stdout','stderr']) assert.ok(paths(upload).includes(`.mlf-build/${root}-controls/**/*.${suffix}`));
  }
  for (const root of ['patricia-*','int64-*','llp64-*']) for (const suffix of ['**/*.json','**/stdout','**/stderr','**/*.hs']) {
    assert.ok(paths(upload).includes(`.mlf-build/${root}/${suffix}`));
  }
  for (const path of ['a1-integrated-controls/**/stdout','a1-integrated-controls/**/stderr','a1-integrated-controls/**/*.hs',
    'f1-integrated-controls/**/source/Probe.dump-*','f1-integrated-controls/actual-source/Separate.dump-*']) {
    assert.ok(paths(upload).includes('.mlf-build/'+path));
  }
});
check('async-platforms', () => {
  for (const name of ['build-runner','async-runtime','async-language']) {
    for (const event_name of ['pull_request','merge_group','push','workflow_dispatch']) {
      assert.deepEqual(expression(job(ci,name).strategy.matrix.os,{github:{event_name}}),
        event_name === 'push' || event_name === 'workflow_dispatch' ? ['ubuntu-24.04','macos-26'] : ['ubuntu-24.04']);
    }
  }
  commandStep(job(ci,'build-runner'),'tools/testing/run.py native-build-tools');
  const async = clone(job(ci,'async-language'));
  for (const step of async.steps) if (step.run) step.run = projectAdapterCommands(step.run);
  const scope = commandStep(async,'tools/release/async-change-scope.py');
  assert.ok(scope.id);
  assert.equal(String(actionStep(async,'actions/checkout').with['fetch-depth']),'0');
  const commands = ['tools/shared/prepare_async_ghc.py','tests/fixtures/async-completion/check.sh',
    'tools/release/test-async-process.sh','tools/release/test-async-task.sh','tools/release/test-async-package.sh'];
  for (const command of commands) {
    const step = commandStep(async,command);
    for (const required of ['true','',undefined,'unknown','false']) {
      assert.equal(selected(step,{steps:{[scope.id]:{outputs:{required}}}}),required !== 'false');
    }
  }
  const archive = actionStep(async,'./.github/actions/linux-ghc-bindist');
  for (const os of ['Linux','macOS']) for (const required of ['true','false','']) {
    assert.equal(selected(archive,{steps:{[scope.id]:{outputs:{required}}},runner:{os}}),os === 'Linux' && required !== 'false');
  }
  for (const name of ['build-runner','async-runtime','windows-runtime','native']) {
    assert.ok(!steps(job(ci,name)).some(step => (step.run || '').includes('async-change-scope')));
  }
});
check('native-and-publishing', () => {
  for (const workflow of [ci,qualify]) {
    assert.equal(workflow.permissions.contents,'read');
    for (const entry of Object.values(workflow.jobs)) {
      assert.ok(!entry['continue-on-error']);
      assert.ok(!entry.permissions || entry.permissions.contents !== 'write');
      for (const step of steps(entry)) assert.ok(!step['continue-on-error']);
    }
  }
  assert.deepEqual(job(qualify,'linux-tests').strategy.matrix.group,['unit','backends','parity','packages','self-host']);
  assert.deepEqual(job(qualify,'mac-tests').strategy.matrix.group,['backends','parity','packages','self-host']);
  for (const name of ['mac-port','mac-unit','linux-port','windows','benchmark-game','qualification-gate']) job(qualify,name);
  for (const value of [false,true]) {
    for (const name of ['mac-package','linux-package']) assert.equal(selected(job(qualify,name),{inputs:{build_packages:value}}),value);
    const windows = commandStep(job(qualify,'windows'),'package-windows.ps1');
    assert.equal(selected(windows,{inputs:{build_packages:value}}),value);
  }
  assert.equal(selected(job(qualify,'qualification-gate'),{failure:()=>true}),true);
  assert.equal(release.on.push,undefined);
  assert.equal(job(release,'qualification').uses,'./.github/workflows/native-qualification.yml');
  assert.equal(job(release,'qualification').with.build_packages,true);
  assert.deepEqual(list(job(release,'publish').needs),['metadata','qualification']);
});
console.log('PR/main/release workflow semantics passed.');
