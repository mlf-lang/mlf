// Execute the workflow's shell routing with private fixtures and recording
// tools. The policy observes calls, environments and outcomes, not shell text.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {projectAdapterCommands} from './workflow-test-adapters.mjs';
import {releaseTestCase, releaseTestEvent} from './test-events.mjs';
import {parseWorkflow, readWorkflow, job, steps, commandStep, actionStep, paths, list, selected,
  render, clone, reformatted} from './workflow-model.mjs';
import {shellCalls, successfulCalls, requireFailurePropagation} from './workflow-shell.mjs';

const workflow = readWorkflow('ci');
const projected = value => {
  const copy = clone(value);
  for (const entry of Object.values(copy.jobs)) for (const step of steps(entry)) {
    if (step.run) step.run = projectAdapterCommands(step.run);
  }
  return copy;
};
const native = value => job(value,'native');
const command = (value, needle) => commandStep(native(value),needle);
const campaignStep = (value, group) => {
  const matches=steps(native(value)).filter(step=>/compiler-tests\b/.test(step.run || '') &&
    new RegExp('\\b'+group+'\\s+--manager\\b').test(step.run || ''));
  assert.equal(matches.length,1,'Exactly one hosted '+group+' campaign');return matches[0];
};
const sorted = calls => calls.map(call => JSON.stringify(call)).sort();
const argvCalls = (step, context = {}, options = {}) => successfulCalls(render(step.run,context), {shell:step.shell,...options});
const context = (matrix, outcomes = {}, cancelled = false) => ({matrix, cancelled:()=>cancelled,
  steps:Object.fromEntries(Object.entries(outcomes).map(([id,outcome]) => [id,{outcome}]))});
const inFixture = action => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'mlf-ci-routing-'));
  try { return action(root); } finally { fs.rmSync(root,{recursive:true,force:true}); }
};
const option = (argv, flag) => {
  assert.equal(argv.filter(value => value === flag).length,1,'One '+flag+' argument');
  return argv[argv.indexOf(flag)+1];
};
const positive = (value, label) => {
  const number = Number(value);
  assert.ok(Number.isSafeInteger(number) && number > 0, label + ' must be a positive integer');
  return number;
};
const enclosingSeconds = (value, step = {}) => {
  const jobSeconds = positive(native(value)['timeout-minutes'], 'Job timeout') * 60;
  const stepSeconds = step['timeout-minutes'] === undefined ? jobSeconds :
    positive(step['timeout-minutes'], 'Step timeout') * 60;
  assert.ok(stepSeconds <= jobSeconds, 'A step must fit within its job budget');
  return stepSeconds;
};
const guard = (argv, outerSeconds, requireOutputBound = false) => {
  assert.deepEqual(argv.slice(0,3),['python3','-B','tools/shared/resource_watchdog.py']);
  const bound = flag => positive(option(argv, flag), flag);
  const seconds = bound('--seconds');
  assert.ok(seconds < outerSeconds, 'The watchdog must finish before its enclosing timeout');
  assert.ok(bound('--rss-mib') <= bound('--address-space-mib'), 'RSS must fit within the address-space limit');
  bound('--disk-free-mib');
  if (requireOutputBound || argv.includes('--max-output-mib')) bound('--max-output-mib');
  return seconds;
};
const expectProducerQuery = query => {
  const good = {complete:true,producer_host:'GHC',typecheck_only:false};
  for (const [change, status] of [[{},0],[{complete:false},1],[{producer_host:'MLF'},1],[{typecheck_only:true},1]]) {
    const result=spawnSync('jq',['-e',query],{input:JSON.stringify({...good,...change}),encoding:'utf8'});
    assert.equal(result.status,status,result.stderr);
  }
};
const fixtureProgram = (root, name, variables=[]) => {
  const filename=path.join(root,'.mlf-build/shared-ghc/bin',name);
  fs.mkdirSync(path.dirname(filename),{recursive:true});
  fs.writeFileSync(filename, '#!/bin/bash\nprintf \'%s\\0\' "$(($# + 1))" '+name+' "$@" '+
    variables.map(variable=>'"${'+variable+'-}"').join(' ')+ ' >&3\n'+
    'if [ "$(printf \'%s\\037\' '+name+' "$@")" = "$MLF_WORKFLOW_FAIL_ARGUMENTS" ]; then exit 73; fi\n');
  fs.chmodSync(filename,0o755);
};

function verifyPartition(value) {
  const entry = native(value);
  enclosingSeconds(value);
  assert.equal(entry.strategy['fail-fast'],false);
  assert.ok(!entry['continue-on-error']);
  // These retired public entrypoints bypass the bounded composite campaign.
  // Keep this narrow invocation policy; display text and comments are harmless.
  for (const step of entry.steps) assert.doesNotMatch(step.run || '',
    /^\s*python3?(?:\s+-[A-Za-z]+)*\s+['"]?tools\/shared\/test_direct(?:_crc_successor|_bounded)?\.py(?:['"]?)(?=\s|$)/m,
    'The native job must use the maintained composite direct-test entrypoint');

  assert.ok(Object.keys(entry.strategy.matrix).every(key=>['include','exclude'].includes(key)));
  assert.deepEqual(entry.strategy.matrix.exclude || [],[]);
  const legs=entry.strategy.matrix.include;
  assert.equal(legs.length,2);
  assert.deepEqual(legs.map(leg=>String(leg.optimization)).sort(),['0','2']);
  for (const leg of legs) assert.equal(typeof leg.suite,'string');
  for (const event_name of ['pull_request','push','workflow_dispatch']) for (const windows_runtime_only of [false,true]) {
    assert.equal(selected(entry,{github:{event_name,event:{pull_request:{labels:[]}}},inputs:{windows_runtime_only}}),
      event_name !== 'workflow_dispatch' || !windows_runtime_only);
  }
  const producer=command(value,'--bootstrap-only');
  const preparation=command(value,'tools/testing/prepare_history_refs.py');
  const install=command(value,'tools/release/cleanup-ghc-install.py');
  const regeneration=command(value,'tools/shared/generate_builtin_evidence.py');
  assert.ok(producer.id);
  enclosingSeconds(value,regeneration);
  const checkout=actionStep(entry,'actions/checkout');
  assert.equal(String(checkout.with['fetch-depth']),'0');
  assert.equal(checkout.if,undefined);
  assert.ok(entry.steps.indexOf(actionStep(entry,'./.github/actions/linux-ghc-bindist')) < entry.steps.indexOf(install));
  assert.ok(entry.steps.indexOf(producer) < entry.steps.indexOf(regeneration));
  assert.ok(entry.steps.indexOf(regeneration) < entry.steps.indexOf(command(value,'tools/performance/crate-query-graph/verify.py')));
  for (const leg of legs) {
    assert.equal(selected(producer,{matrix:leg}),true);
    assert.equal(selected(install,{matrix:leg}),true);
    const calls=argvCalls(producer,{matrix:leg},{commands:['python3','jq']});
    assert.equal(calls.length,2);
    assert.deepEqual(calls[0].argv,['python3','tools/shared/build.py','--bootstrap-only','--optimization',String(leg.optimization),'--build-dir','.mlf-build/shared-ghc']);
    assert.deepEqual([calls[1].argv[0],calls[1].argv[1],calls[1].argv[3]],['jq','-e','.mlf-build/shared-ghc/receipt.json']);
    expectProducerQuery(calls[1].argv[2]);
    requireFailurePropagation(render(producer.run,{matrix:leg}),{commands:['python3','jq']},calls);
    for (const failed of [false,true]) for (const outcome of ['success','failure','skipped']) {
      assert.equal(selected(regeneration,{...context(leg,{[producer.id]:outcome}),failure:()=>failed}),failed && outcome==='failure');
    }
  }
  const regenerationCalls=argvCalls(regeneration);
  assert.equal(regenerationCalls.length,1);
  const regenerationBudget=guard(regenerationCalls[0].argv,enclosingSeconds(value,regeneration),true);
  for (const [flag,expected] of [['--root',process.cwd()],['--build-receipt','.mlf-build/shared-ghc/receipt.json']]) {
    assert.equal(option(regenerationCalls[0].argv,flag),expected);
  }
  assert.ok(positive(option(regenerationCalls[0].argv,'--timeout'),'Generator timeout') < regenerationBudget,
    'Generation must finish before its watchdog');
  const routine=['tools/release/test-suite-build-receipts.py','tools/release/source-smoke.sh',
    'tools/shared/test_direct_candidate_successor.py','tools/shared/test_figure12_direct.py','tools/release/test-tuple-list.sh'];
  const optimized=['tools/performance/patricia/run_integrated.py --suite p123','tools/performance/patricia/run_integrated.py --suite graph',
    'tools/performance/patricia/run_integrated.py --suite validation','tools/performance/patricia/run_integrated.py --suite builtin',
    'tools/performance/patricia/run_fingerprint.py','tools/performance/map-policy/run_controls.py',
    'tools/performance/patricia/run_file_controls.py','tools/performance/patricia/run_controls.py','tools/performance/patricia/run_native.py',
    'tools/performance/int64/run_llp64.py','tools/performance/int64/run_controls.py','tools/performance/crate-query-graph/verify.py',
    'tools/performance/crate-query-graph/source_checks.py','tools/shared/test_source_context_cache.py','tools/shared/test_artifact_binary.py',
    'tools/shared/test_recursive_managed.py','tools/shared/test_guest_framework.py','tools/shared/test_guest_state_laws.py',
    'tools/shared/test_io_action_sharing.py','tools/shared/test_header_validation_adapter.py'];
  for (const leg of legs) {
    for (const name of routine) assert.equal(selected(command(value,name),{matrix:leg}),String(leg.optimization)==='0',name);
    for (const name of optimized) assert.equal(selected(command(value,name),{matrix:leg}),String(leg.optimization)==='2',name);
    const framework=command(value,'--output .mlf-build/framework-direct --suite '+(String(leg.optimization)==='0'?'all':'controls'));
    assert.equal(selected(framework,{matrix:leg}),true);
    const expected=['python3','tools/shared/test_framework_direct.py','--build-receipt','.mlf-build/shared-ghc/receipt.json',
      '--output','.mlf-build/framework-direct','--suite',String(leg.optimization)==='0'?'all':'controls'];
    const calls=argvCalls(framework,{matrix:leg});
    assert.equal(calls.length,1);
    const argv=[...calls[0].argv];
    if (String(leg.optimization)==='0') {
      assert.ok(positive(option(argv,'--suite-timeout'),'Framework timeout') < enclosingSeconds(value,framework),
        'The framework must finish before its enclosing timeout');
      argv.splice(argv.indexOf('--suite-timeout'),2);
    }
    assert.deepEqual(argv,expected);
    for (const other of legs.filter(other=>other!==leg)) assert.equal(selected(framework,{matrix:other}),false);
  }
  for (const script of ['tools/shared/test_artifact_binary_modular.py']) {
    const step=command(value,script);
    const calls=argvCalls(step);
    for (const flags of [['-B'],['-O','-B']]) assert.equal(calls.filter(call=>JSON.stringify(call.argv)===JSON.stringify(['python3',...flags,script])).length,1);
    for (const leg of legs) assert.equal(selected(step,{matrix:leg}),String(leg.optimization)==='2');
    assert.ok(entry.steps.indexOf(preparation) < entry.steps.indexOf(step));
    assert.ok(entry.steps.indexOf(step) < entry.steps.indexOf(install));
  }
  const metadata=job(value,'metadata');
  for (const script of ['tools/shared/test_generate_builtin_evidence.py','tools/release/test-ghc-install-cleanup.py']) {
    const calls=argvCalls(commandStep(metadata,script));
    assert.deepEqual(sorted(calls),sorted([['-B'],['-O','-B']].map(flags=>({argv:['python3',...flags,script]}))));
  }
  const campaign=command(value,'runtime/mlf_build_runner.c');
  const parity=campaignStep(value,'parity');
  const lifecycle=command(value,'--locked test --target lifecycle');
  const backends=campaignStep(value,'backends');
  const indexvec=command(value,'tests/indexvec/run.py');
  assert.ok(campaign.id && lifecycle.id);
  for (const leg of legs) for (const cancelled of [false,true]) for (const buildState of ['success','failure','skipped']) {
    for (const toolState of ['success','failure','skipped']) for (const lifecycleState of ['success','failure','skipped']) {
      const ctx=context(leg,{[producer.id]:buildState,[campaign.id]:toolState,[lifecycle.id]:lifecycleState},cancelled);
      const routine=String(leg.optimization)==='0' && !cancelled;
      assert.equal(selected(campaign,ctx),routine && buildState==='success');
      assert.equal(selected(parity,ctx),routine && toolState==='success');
      assert.equal(selected(lifecycle,ctx),routine && buildState==='success' && toolState==='success');
      assert.equal(selected(backends,ctx),routine && lifecycleState==='success');
      assert.equal(selected(actionStep(entry,'./.github/actions/prepare-backend-drivers'),ctx),routine && lifecycleState==='success');
      assert.equal(selected(indexvec,ctx),!cancelled && buildState==='success' && String(leg.optimization)==='2');
    }
  }
  assert.ok(entry.steps.indexOf(campaign)<entry.steps.indexOf(parity) && entry.steps.indexOf(parity)<entry.steps.indexOf(lifecycle) && entry.steps.indexOf(lifecycle)<entry.steps.indexOf(backends));
  assert.ok(entry.steps.indexOf(command(value,'tools/shared/test_figure12_direct.py'))<entry.steps.indexOf(lifecycle));
  for (const name of optimized) assert.ok(entry.steps.indexOf(command(value,name))<entry.steps.indexOf(indexvec));
  assert.ok(entry.steps.indexOf(command(value,'--suite controls'))<entry.steps.indexOf(indexvec));
  assert.ok(entry.steps.indexOf(command(value,'tools/shared/test_io_action_sharing.py'))<entry.steps.indexOf(command(value,'tools/shared/test_artifact_binary.py')));
  assert.deepEqual(argvCalls(indexvec).map(call=>call.argv),[['python3','-B','tests/indexvec/run.py','--compiler','.mlf-build/shared-ghc/bin/emlf','--output','.mlf-build/indexvec-controls']]);
  const upload=actionStep(entry,'actions/upload-artifact');
  assert.equal(upload.with['include-hidden-files'],true);
  assert.equal(selected(upload,{failure:()=>true,cancelled:()=>true,success:()=>false}),true);
  assert.equal(new Set(legs.map(matrix=>render(upload.with.name,{matrix}))).size,legs.length);
  assert.ok(paths(upload).length > 0, 'The upload must select evidence');
}

const directExpected = [

    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_crc_successor_entry.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_crc_successor_entry.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '.mlf-build/crc-supervisor-controls/normal',
      argv: ['-B', 'tools/shared/test_crc_process_supervisor.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '.mlf-build/crc-supervisor-controls/optimized',
      argv: ['-O', '-B', 'tools/shared/test_crc_process_supervisor.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_utf8_batch_contract.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_utf8_batch_contract.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_utf8_batch_worker.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_utf8_batch_worker.py']},
    {candidateEvidence: '', utf8Evidence: '.mlf-build/utf8-supervisor-controls/normal', evidence: '', argv: ['-B', 'tools/shared/test_direct_bounded_entry.py']},
    {candidateEvidence: '', utf8Evidence: '.mlf-build/utf8-supervisor-controls/optimized', evidence: '', argv: ['-O', '-B', 'tools/shared/test_direct_bounded_entry.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_candidate_batch_contract.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_candidate_batch_contract.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_candidate_batch_worker.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_candidate_batch_worker.py']},
    {candidateEvidence: '.mlf-build/candidate-supervisor-controls/normal', utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_direct_candidate_entry.py']},
    {candidateEvidence: '.mlf-build/candidate-supervisor-controls/optimized', utf8Evidence: '', evidence: '', argv: ['-O', '-B', 'tools/shared/test_direct_candidate_entry.py']},
    {candidateEvidence: '', utf8Evidence: '', evidence: '', argv: ['-B', 'tools/shared/test_direct_candidate_successor.py',
      '--bin-dir', '.mlf-build/shared-ghc/bin',
      '--build-receipt', '.mlf-build/shared-ghc/receipt.json',
      '--output', '.mlf-build/direct-host-tests']},
].map(({argv,evidence,utf8Evidence,candidateEvidence})=>({argv:['python3',...argv],MLF_CRC_TEST_EVIDENCE:evidence,
  MLF_UTF8_TEST_EVIDENCE:utf8Evidence,MLF_CANDIDATE_TEST_EVIDENCE:candidateEvidence}));
function verifyDirect(value) {
  const step=command(value,'tools/shared/test_direct_candidate_successor.py');
  const options={variables:['MLF_CRC_TEST_EVIDENCE','MLF_UTF8_TEST_EVIDENCE','MLF_CANDIDATE_TEST_EVIDENCE']};
  const calls=argvCalls(step,{},options);
  assert.deepEqual(sorted(calls),sorted(directExpected));
  assert.deepEqual(calls.at(-1),directExpected.at(-1),'The composite successor follows its pure controls');
  requireFailurePropagation(step.run,options,calls);
}
function verifyGuarded(value) {
  const names=['tools/performance/patricia/run_integrated.py --suite p123','tools/performance/patricia/run_integrated.py --suite graph',
    'tools/performance/patricia/run_integrated.py --suite validation','tools/performance/patricia/run_integrated.py --suite builtin',
    'tools/performance/patricia/run_fingerprint.py','tools/performance/patricia/run_file_controls.py',
    'tools/performance/patricia/run_controls.py','tools/performance/patricia/run_native.py','tools/performance/int64/run_llp64.py',
    'tools/performance/int64/run_controls.py','tools/performance/crate-query-graph/verify.py','tools/performance/crate-query-graph/source_checks.py',
    'tools/shared/test_artifact_binary.py'];
  for (const step of new Set(names.map(name=>command(value,name)))) {
    const options={stubs:'pkg-config() { printf "/fixture/lib\\n"; }\ntest() { return 0; }'};
    const calls=argvCalls(step,{},options);
    for (const name of names.filter(name=>step.run.includes(name))) {
      const [script,...tokens]=name.split(' ');
      const matches=calls.filter(call=>call.argv.includes(script) && tokens.every(token=>call.argv.includes(token)));
      assert.equal(matches.length,script==='tools/performance/int64/run_controls.py'?3:1,name);
      for (const call of matches) guard(call.argv,enclosingSeconds(value,step),
        script.includes('crate-query-graph') || script==='tools/shared/test_artifact_binary.py');
      if (script==='tools/performance/int64/run_controls.py') {
        assert.deepEqual(matches.map(call=>option(call.argv,'--suite')).sort(),['host','legacy','native']);
      }
      if (script==='tools/performance/patricia/run_native.py') assert.equal(option(matches[0].argv,'--mode'),'standalone');
      if (script==='tools/shared/test_artifact_binary.py') {
        for (const [flag,expected] of [['--source-root',process.cwd()],['--build-receipt','.mlf-build/shared-ghc/receipt.json'],
          ['--gc-prefix',process.cwd()+'/.mlf-build/io-action-gc'],['--partial-write-sink','/dev/full']]) assert.equal(option(matches[0].argv,flag),expected);
      }
    }
    requireFailurePropagation(step.run,options,calls);
  }
  const map=command(value,'tools/performance/map-policy/run_controls.py');
  const options={variables:['MAP_POLICY_SOURCE']};
  const calls=argvCalls(map,{},options);
  assert.equal(calls.length,3);
  assert.deepEqual(sorted(calls.slice(0,2)),sorted([['-B'],['-O','-B']].map(flags=>({argv:['python3',...flags,'tools/performance/map-policy/test_prepare_map_policy.py'],MAP_POLICY_SOURCE:process.cwd()}))));
  guard(calls[2].argv,enclosingSeconds(value,map));
  assert.equal(option(calls[2].argv,'--source'),process.cwd());
  assert.equal(option(calls[2].argv,'--producer'),'.mlf-build/shared-ghc');
  requireFailurePropagation(map.run,options,calls);
}
function verifyHeader(value) {
  inFixture(root=>{
    fs.mkdirSync(path.join(root,'.mlf-build'));
    const step=command(value,'tools/shared/test_header_validation_adapter.py');
    const variables=['HEADER_FIXTURE','HEADER_ORACLE','HEADER_HISTORY_SOURCE'];
    const options={cwd:root,variables,stubs:String.raw`
mkdir() { /bin/mkdir "$@"; }
git() { record git "$@" || return; printf 'frozen-header-oracle\n'; }
python3() {
  local original
  IFS= read -r original < "$HEADER_HISTORY_SOURCE"
  [ "$original" = frozen-header-oracle ]
  record python3 "$@"
}
`};
    const calls=argvCalls(step,{},options);
    assert.equal(calls.length,4);
    assert.deepEqual(calls[0].argv,['git','--no-replace-objects','cat-file','blob','dd5b4630a80803c19afdb219dba2dc4bffc3ea1b']);
    const environments={HEADER_FIXTURE:root+'/tools/shared/fixtures/native/HeaderValidationTests.hs',
      HEADER_ORACLE:root+'/tools/shared/fixtures/native/HeaderNamingOracle.hs',
      HEADER_HISTORY_SOURCE:root+'/.mlf-build/header-adapter-controls/history.hs'};
    const pure=[['-B'],['-O','-B']].map(flags=>({argv:['python3',...flags,'tools/shared/test_header_validation_adapter.py'],...environments}));
    assert.deepEqual(sorted(calls.slice(1,3)),sorted(pure));
    assert.deepEqual(calls[3],{argv:['python3','tools/shared/test_native_library.py','--build-receipt','.mlf-build/shared-ghc/receipt.json',
      '--output','.mlf-build/native-library','--clang','clang','--gc-prefix','.mlf-build/io-action-gc'],...environments});
    for (const call of calls) {
      fs.rmSync(path.join(root,'.mlf-build/header-adapter-controls'),{recursive:true,force:true});
      requireFailurePropagation(step.run,options,[call]);
    }
  });
}
function verifyInstall(value) {
  inFixture(root=>{
    const unpacked=path.join(root,'ghc-9.14.1-x86_64-unknown-linux');
    fs.mkdirSync(unpacked,{recursive:true}); fs.mkdirSync(path.join(root,'ghc/bin'),{recursive:true});
    fs.writeFileSync(path.join(unpacked,'configure'), '#!/bin/bash\nprintf \'%s\\0\' "$(($# + 1))" configure "$@" >&3\n');
    fs.chmodSync(path.join(unpacked,'configure'),0o755);
    fs.writeFileSync(path.join(root,'ghc/bin/ghc'),'#!/bin/bash\nprintf \'%s\\0\' "$(($# + 1))" ghc "$@" >&3\nprintf \'%s\\n\' "$FIXTURE_GHC_VERSION"\n');
    fs.chmodSync(path.join(root,'ghc/bin/ghc'),0o755);
    const step=command(value,'tools/release/cleanup-ghc-install.py');
    const options={cwd:root,env:{RUNNER_TEMP:root,GITHUB_PATH:path.join(root,'path'),FIXTURE_GHC_VERSION:'9.14.1'},commands:['sudo','tar','make','python3']};
    const calls=argvCalls(step,{},options);
    const installed=calls.findIndex(call=>JSON.stringify(call.argv)===JSON.stringify(['make','install']));
    const cleanup=calls.findIndex(call=>call.argv.includes('tools/release/cleanup-ghc-install.py'));
    assert.ok(installed>=0 && cleanup>installed,'Cleanup follows completed installation');
    const configured=calls.findIndex(call=>call.argv[0]==='configure');
    assert.ok(configured>=0 && configured<installed);
    assert.deepEqual(calls[configured].argv,['configure','--prefix='+root+'/ghc']);
    const version=calls.findIndex(call=>call.argv[0]==='ghc');
    assert.ok(version>installed && version<cleanup);
    assert.deepEqual(calls[version].argv,['ghc','--numeric-version']);
    const wrong=shellCalls(step.run,{...options,env:{...options.env,FIXTURE_GHC_VERSION:'9.12.2'}});
    assert.notEqual(wrong.status,0);
    assert.ok(!wrong.calls.some(call=>call.argv.includes('tools/release/cleanup-ghc-install.py')),
      'A wrong installed version must fail before cleanup');

    assert.deepEqual(calls[cleanup].argv,['python3','-B','tools/release/cleanup-ghc-install.py','--receipt','.mlf-build/ghc-install-cleanup.json']);
    requireFailurePropagation(step.run,options,[calls[installed],calls[cleanup]]);
  });
}
function verifyIo(value) {
  inFixture(root=>{
    fs.writeFileSync(path.join(root,'libgc.a'),'static-gc');
    const step=command(value,'tools/shared/test_io_action_sharing.py');
    enclosingSeconds(value,step);
    const options={cwd:root,commands:['sudo','cp','python3'],stubs:String.raw`
mkdir() { /bin/mkdir "$@"; }
cc() { record cc "$@" || return; printf '%s/libgc.a\n' "$PWD"; }
dpkg-query() { record dpkg-query "$@" || return; printf 'libgc-dev pinned-fixture\n'; }
`};
    const calls=argvCalls(step,{},options);
    const prefix=root+'/.mlf-build/io-action-gc';
    assert.deepEqual(calls.map(call=>call.argv),[
      ['sudo','apt-get','install','-y','libgc-dev'],
      ['cp','/usr/include/gc.h',prefix+'/include/gc.h'],
      ['cp','-R','/usr/include/gc',prefix+'/include/gc'],
      ['cc','-print-file-name=libgc.a'],
      ['cp',root+'/libgc.a',prefix+'/lib/libgc.a'],
      ['dpkg-query','-W','libgc-dev'],
      ['python3','-B','tools/shared/test_io_action_sharing.py','--build-receipt','.mlf-build/shared-ghc/receipt.json',
        '--output','.mlf-build/io-action-sharing','--clang','clang','--gc-prefix',prefix],
    ]);
    assert.equal(fs.readFileSync(path.join(prefix,'dependency-version.txt'),'utf8'),'libgc-dev pinned-fixture\n');
    requireFailurePropagation(step.run,options,calls);
  });
}
function verifyCampaignCalls(value) {
  inFixture(root=>{
    const variables=['MLF_BUILD_RUNNER','MLF_PACKAGE_MANAGER'];
    for (const name of ['compiler-tests','mlfpkg']) fixtureProgram(root,name,variables);
    fs.mkdirSync(path.join(root,'tools/release'),{recursive:true});
    fs.writeFileSync(path.join(root,'tools/release/native-environment.sh'),'# Environment setup is covered by its own controls.\n');
    for (const group of ['parity','backends']) {
      const step=campaignStep(value,group);
      const options={cwd:root,variables};
      const calls=argvCalls(step,{},options);
      const toolset=root+'/.mlf-build/shared-ghc/bin';
      const argv=['compiler-tests',group,'--manager',toolset+'/mlfpkg','--compiler',toolset+'/emlf',
        '--build-dir',root+'/.mlf-build/compiler-tests/'+group,'--cache-dir',root+'/.mlf-build/cache'];
      if (group==='parity') argv.push('--compiler-receipt',root+'/.mlf-build/shared-ghc/receipt.json');
      assert.deepEqual(calls,[{argv,MLF_BUILD_RUNNER:toolset+'/mlf-build-runner',MLF_PACKAGE_MANAGER:''}]);
      requireFailurePropagation(step.run,options,calls);
    }
    const step=command(value,'--locked test --target lifecycle');
    const options={cwd:root,variables};
    const calls=argvCalls(step,{},options);
    assert.equal(calls.length,1);
    const toolset=root+'/.mlf-build/shared-ghc/bin';
    assert.deepEqual(calls,[{argv:['mlfpkg','--manifest','testing/tools/mlf-package.json','--compiler',toolset+'/emlf',
      '--runtime',root+'/runtime/mlf_runtime.c','--build-dir',root+'/.mlf-build/compiler-tests/lifecycle',
      '--cache-dir',root+'/.mlf-build/cache','--locked','test','--target','lifecycle'],
      MLF_BUILD_RUNNER:toolset+'/mlf-build-runner',MLF_PACKAGE_MANAGER:toolset+'/mlfpkg'}]);
    requireFailurePropagation(step.run,options,calls);
  });
}
const qualificationAction = () => parseWorkflow(fs.readFileSync('.github/actions/posix-qualification/action.yml','utf8'));
const collectionStep = value => commandStep(value.runs,'tools/release/time-stage.sh evidence');
function verifyQualificationEvidence(value) {
  const step=collectionStep(value);
  const timer=fs.readFileSync('tools/release/time-stage.sh');
  inFixture(root=>{
    const put=(relative,content)=>{
      const target=path.join(root,relative);
      fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,content);
      return target;
    };
    fs.chmodSync(put('tools/release/time-stage.sh',timer),0o755);
    const files={'verification.json':'{"complete":true}\n','suite-build/bin/core-language':'retained executable\n'};
    for(const shard of ['core-crates','core-language','core-solver','core-modules']) {
      for(const suffix of ['inventory.json','cases.jsonl','coverage.jsonl','families.jsonl']) {
        files[shard+'.'+suffix]=JSON.stringify({shard,evidence:suffix})+'\n';
      }
    }
    for(const [name,content] of Object.entries(files)) put('.mlf-build/compiler-tests/unit/'+name,content);
    put('.mlf-build/compiler-tests/unit/intermediate.o','discard object\n');
    put('.mlf-build/compiler-tests/unit/scratch.hs','discard source\n');
    const result=spawnSync('/bin/bash',['--noprofile','--norc','-e','-o','pipefail','-c',step.run],{
      cwd:root,encoding:'utf8',timeout:10000,env:{PATH:process.env.PATH,TEST_GROUP:'unit'},
    });
    assert.equal(result.error,undefined);assert.equal(result.status,0,result.stderr);
    const destination=path.join(root,'.mlf-build/release-evidence/compiler-tests/unit');
    for(const [name,content] of Object.entries(files)) {
      const retained=path.join(destination,name);
      assert.ok(fs.existsSync(retained),'Retain qualification evidence: '+name);
      assert.equal(fs.readFileSync(retained,'utf8'),content,'Preserve evidence bytes: '+name);
    }
    for(const name of ['intermediate.o','scratch.hs']) assert.ok(!fs.existsSync(path.join(destination,name)));
  });
}
function verifyAggregate(value) {
  const gate=job(value,'pr-gate');
  const names=['metadata','native','windows-runtime','build-runner','async-runtime','async-language'];
  assert.deepEqual(new Set(list(gate.needs)),new Set(names));
  for (const skipped of [false,true]) {
    const github={event_name:'pull_request',event:{pull_request:{labels:skipped?[{name:'ci:skip'}]:[]}}};
    const candidates=gate.steps.filter(step=>selected(step,{github}));
    assert.equal(candidates.length,1);
    const statuses=['success','failure','cancelled','skipped','pending'];
    const execute=results=>{
      const result=spawnSync('/bin/bash',['-e','-c',candidates[0].run],{encoding:'utf8',timeout:5000,
        env:{PATH:process.env.PATH,GITHUB_STEP_SUMMARY:'/dev/null',...Object.fromEntries(
          Object.entries(candidates[0].env || {}).map(([name,value])=>[name,render(value,{needs:results})]))}});
      assert.equal(result.error,undefined);
      return result.status;
    };
    const good=Object.fromEntries(names.map(name=>[name,{result:skipped?'skipped':'success'}]));
    assert.equal(execute(good),0);
    for (const name of names) for (const status of statuses.filter(status=>status!==(skipped?'skipped':'success'))) {
      assert.notEqual(execute({...good,[name]:{result:status}}),0,name+' '+status);
    }
    const missing={...good};delete missing.native;assert.notEqual(execute(missing),0);
    assert.notEqual(execute({...good,unexpected:{result:skipped?'skipped':'success'}}),0);
  }
}
const validators=[verifyPartition,verifyDirect,verifyGuarded,verifyHeader,verifyInstall,verifyIo,verifyCampaignCalls,verifyAggregate];
const verify=value=>{for (const validate of validators) validate(projected(value));};
const mutate=(value,change,validate=verify)=>{const changed=clone(value);change(changed);assert.throws(()=>validate(changed));};
const findAdapter=(value,adapter)=>{
  const matches=steps(native(value)).filter(step=>new RegExp('tools/testing/run[.]py (?:--inherit-process-group )?'+adapter+'(?=\\s|$)').test(step.run || '') && (adapter!=='framework-direct' || step.run.includes('--suite all')));
  assert.equal(matches.length,1,'Exactly one adapter step: '+adapter);return matches[0];
};
const suite='release-native-ci-partition', prefix='release/native-ci-partition/';
const changeOption=(step,flag,replacement)=>{
  const token=`(?:"${flag}"|'${flag}'|${flag})`;
  const pattern=new RegExp(`(${token}\\s+)(?:"[^"\\n]*"|'[^'\\n]*'|[^\\s;]+)`,'g');
  step.run=step.run.replace(/\\\n/g,'').replace(pattern,(_,prefix)=>prefix+replacement);
};
const cases=[
  ['schedule',()=>verify(workflow)],
  ['qualification-evidence-transport',()=>verifyQualificationEvidence(qualificationAction())],
  ['mutation/qualification-discovery-deleted',()=>{
    const value=qualificationAction();
    collectionStep(value).run+="\nfind .mlf-build/release-evidence -name '*.inventory.json' -delete\n";
    assert.throws(()=>verifyQualificationEvidence(value),/Retain qualification evidence:/);
  }],
  ['equivalent-yaml-and-display-names',()=>verify(reformatted(workflow))],
  ['equivalent-shell-locals',()=>{
    const changed=clone(workflow);
    native(changed).strategy.matrix.exclude=[];
    const direct=findAdapter(changed,'direct-candidate');
    direct.run='# python3 -B tools/shared/test_direct.py is retired\n'+direct.run;
    for (const step of native(changed).steps) {
      for (const [before,after] of [['shared_build','host_compiler'],['hosted_campaign_tools','host_runner'],['native_lifecycle','lifecycle_checks']]) {
        if(step.id===before)step.id=after;
        if(typeof step.if==='string')step.if=step.if.replaceAll(before,after);
      }
      if(step.run)step.run=step.run.replaceAll('toolset','executables').replaceAll('$suite','$variant').replace('for suite in','for variant in')
        .replace(/(^|\s)prefix=/gm,'$1gcRoot=').replaceAll('$prefix','$gcRoot')
        .replace(/(^|\s)archive=/gm,'$1gcArchive=').replaceAll('$archive','$gcArchive');
    }
    // Independent pure checks may run in either order before the campaign.
    const lines=direct.run.split('\n');
    const pure=lines.map((line,index)=>line.includes('tools/testing/run.py python-shared-crc-successor-entry')?index:-1).filter(index=>index>=0);
    [lines[pure[0]],lines[pure[1]]]=[lines[pure[1]],lines[pure[0]]];direct.run=lines.join('\n');
    verify(changed);
  }],
  ['valid-policy-tuning-and-output-location',()=>{
    const value=projected(workflow);
    native(value)['timeout-minutes']-=1;
    const framework=command(value,'--suite all');
    const frameworkCall=argvCalls(framework)[0].argv;
    changeOption(framework,'--suite-timeout',String(Number(option(frameworkCall,'--suite-timeout'))+1));
    const binary=command(value,'tools/shared/test_artifact_binary.py');
    const binaryCall=argvCalls(binary,{},{stubs:'test() { return 0; }'})[0].argv;
    changeOption(binary,'--seconds',String(Number(option(binaryCall,'--seconds'))+1));
    changeOption(binary,'--rss-mib',String(Number(option(binaryCall,'--rss-mib'))-128));
    changeOption(binary,'--max-output-mib',String(Number(option(binaryCall,'--max-output-mib'))+1));
    const before=option(binaryCall,'--output'),after='.mlf-build/relocated-artifact-results';
    changeOption(binary,'--output',after);
    const upload=actionStep(native(value),'actions/upload-artifact');
    upload.with.path=[...paths(upload).filter(pattern=>!pattern.startsWith(before+'/')),after+'/**'].join('\n');
    verify(value);
  }],
  // A few invariant defects exercise the policy checks. Each baseline shell
  // validator already injects failures into the real commands it records.
  ['mutation/missing%20shard',()=>mutate(workflow,value=>native(value).strategy.matrix.include.pop())],
  ['mutation/nonblocking%20failures',()=>mutate(workflow,value=>native(value)['continue-on-error']=true)],
  ['mutation/skipped-campaign',()=>mutate(workflow,value=>findAdapter(value,'direct-candidate').if=false)],
  ['mutation/swallowed-failure',()=>{
    const value=projected(workflow),needle='tools/shared/test_direct_candidate_successor.py';
    const step=command(value,needle);
    step.run=step.run.replace(/\\\n\s*/g,' ');
    const line=step.run.split('\n').find(line=>line.includes(needle));
    assert.ok(line);
    step.run=step.run.replace(line,line+' || :');
    assert.throws(()=>verifyDirect(value));
  }],
  ['mutation/missing-budget',()=>mutate(workflow,value=>delete native(value)['timeout-minutes'])],
  ['mutation/artifact%20collision',()=>mutate(workflow,value=>actionStep(native(value),'actions/upload-artifact').with.name='shared')],
  ['mutation/artifact-success-only',()=>mutate(workflow,value=>actionStep(native(value),'actions/upload-artifact').if='success()')],
  ['mutation/aggregate%20missing%20matrix',()=>mutate(workflow,value=>job(value,'pr-gate').needs=job(value,'pr-gate').needs.filter(name=>name!=='native'))],
];
const exact=process.env.MLF_TEST_SUITE===suite?process.env.MLF_TEST_EXACT:undefined;
const chosen=cases.filter(([label])=>!exact||prefix+label===exact);
assert.ok(chosen.length,'Unknown CI partition case');
if(process.argv.includes('--framework-list')) console.log(JSON.stringify(chosen.map(([label])=>prefix+label)));
else {
  releaseTestEvent(suite,{plan:chosen.map(([label])=>prefix+label)});
  for(const [label,run] of chosen) releaseTestCase(suite,prefix+label,run);
  console.log(`Native CI behavioral partition: ${chosen.length} checks passed.`);
}
