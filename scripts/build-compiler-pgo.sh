#!/bin/sh
# Reproducible compiler construction through the native package manager.
set -eu
if [ "$#" -ne 3 ]; then
  echo 'build-compiler-pgo.sh NATIVE_SEED LLVM_PROFDATA FRESH_OUTPUT' >&2
  exit 64
fi
if [ -z "${MLF_PACKAGE_MANAGER:-}" ] || [ ! -x "$MLF_PACKAGE_MANAGER" ]; then
  echo 'Set MLF_PACKAGE_MANAGER to a native manager with --pgo-generate support.' >&2
  exit 64
fi
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
node - "$root" "$1" "$2" "$3" "$MLF_PACKAGE_MANAGER" "$0" <<'NODE'
'use strict';
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const {spawn} = require('child_process');
const [source, seedName, profdataName, outputName, managerName, scriptName] = process.argv.slice(2);
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const identified = file => ({path: fs.realpathSync(file), sha256: hash(file)});
const read = file => JSON.parse(fs.readFileSync(file));
const out = path.resolve(outputName);
let started = false;
const write = (name, data) => fs.writeFileSync(path.join(out, name), JSON.stringify(data, null, 2) + '\n');
async function run(name, executable, args, input, extra = {}) {
  const resultPath = path.join(out, name + '.stdout');
  const stdout = fs.openSync(resultPath, 'w'), stderr = fs.openSync(path.join(out, name + '.stderr'), 'w');
  const stdin = input ? fs.openSync(input, 'r') : null;
  const command = {executable, args, cwd: source, stdin: input || null, environment: extra, started: new Date().toISOString()};
  const child = spawn(executable, args, {cwd: source, env: {...process.env, ...extra}, stdio: [stdin === null ? 'ignore' : stdin, stdout, stderr]});
  write('state.json', {stage: name, pid: process.pid, child_pid: child.pid});
  const result = await new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('exit', (code, signal) => resolve({code, signal}));
  });
  fs.closeSync(stdout); fs.closeSync(stderr); if (stdin !== null) fs.closeSync(stdin);
  write(name + '-exit.json', {...command, ...result, finished: new Date().toISOString()});
  if (result.code !== 0) throw Error(name + ' failed; see ' + path.join(out, name + '.stderr'));
  return resultPath;
}
(async () => {
  if (fs.existsSync(out)) throw Error('Use a fresh output directory: ' + out);
  const seed = identified(seedName), manager = identified(managerName), profdata = identified(profdataName), script = identified(scriptName);
  fs.mkdirSync(out, {recursive: true}); started = true;
  const help = await run('manager-help', manager.path, ['--help']);
  if (!fs.readFileSync(help, 'utf8').includes('--pgo-generate')) throw Error('Native manager lacks PGO build support');
  const build = path.join(out, 'build');
  const baseArgs = ['--manifest', path.join(source, 'mlf-package.json'), '--compiler', seed.path,
    '--runtime', path.join(source, 'runtime/mlf_runtime.c'), '--timeout', '21600', '--build-dir', build];
  let packages;
  async function buildMode(name, options, targets = ['emlf']) {
    await run(name, manager.path, [...baseArgs, ...options, 'build', ...targets.flatMap(target => ['--target', target])]);
    const report = read(path.join(build, 'build-report.json'));
    if (!report.complete) throw Error('Incomplete build report: ' + name);
    if (packages && JSON.stringify(packages) !== JSON.stringify(report.packages)) throw Error('Package inputs changed during compiler construction');
    packages = report.packages;
    write(name + '-build-report.json', report);
    return report;
  }
  function nativeOutputs(report) {
    const files = {'LLVM emission': 'program.ll', 'LLVM object': 'program.o', 'runtime object': 'runtime.o', 'native link': 'program'};
    return Object.fromEntries(Object.entries(files).map(([kind, name]) => {
      const row = report.builds.find(entry => entry.kind === kind);
      if (!row) throw Error('Missing native build stage: ' + kind);
      return [kind, identified(path.join(build, 'cache', row.key, name))];
    }));
  }
  const ordinary = await buildMode('ordinary', [], ['emlf', 'mlfpkg']);
  fs.mkdirSync(path.join(out, 'ordinary'));
  fs.copyFileSync(path.join(build, 'bin/emlf'), path.join(out, 'ordinary/emlf'));
  const original = nativeOutputs(ordinary);
  const generated = await buildMode('generate', ['--pgo-generate', 'emlf']);
  const instrumentedOutputs = nativeOutputs(generated);
  if (original['LLVM emission'].sha256 !== instrumentedOutputs['LLVM emission'].sha256) throw Error('Instrumentation changed MLF emission');
  fs.mkdirSync(path.join(out, 'instrumented'));
  const instrumented = path.join(out, 'instrumented/emlf');
  fs.copyFileSync(path.join(build, 'bin/emlf'), instrumented);
  const names = ['choose-id', 'contextual-instance', 'identity', 'impredicative', 'io-hello', 'let-polymorphism', 'maybe', 'monad-io', 'monad-maybe', 'monad-state-do', 'multiparameter', 'partial-annotation', 'polymorphic-data', 'recursive-data', 'self-application'];
  const training = names.map(name => ({name, ...identified(path.join(source, 'examples', name + '.emlf'))}));
  const profiles = [];
  for (const round of ['first', 'second']) {
    const raw = path.join(out, round + '-raw'); fs.mkdirSync(raw);
    const inputs = [];
    for (const item of training) {
      if (hash(item.path) !== item.sha256) throw Error('Training source changed: ' + item.path);
      if (round === 'first') {
        const expected = await run('control-' + item.name, path.join(out, 'ordinary/emlf'), ['--emit-llvm'], item.path);
        item.llvm_sha256 = hash(expected);
      }
      const profile = path.join(raw, item.name + '.profraw');
      const actual = await run(round + '-' + item.name, instrumented, ['--emit-llvm'], item.path, {LLVM_PROFILE_FILE: profile});
      if (hash(actual) !== item.llvm_sha256) throw Error('Instrumented training output differs: ' + item.name);
      inputs.push(identified(profile));
    }
    const profile = path.join(out, round + '.profdata');
    await run(round + '-merge', profdata.path, ['merge', '-output=' + profile, ...inputs.map(entry => entry.path)]);
    const report = await buildMode(round + '-use', ['--pgo-target', 'emlf', '--pgo-use', profile]);
    const outputs = nativeOutputs(report);
    if (outputs['LLVM emission'].sha256 !== original['LLVM emission'].sha256) throw Error('Profile-use changed MLF emission');
    fs.mkdirSync(path.join(out, round));
    fs.copyFileSync(path.join(build, 'bin/emlf'), path.join(out, round, 'emlf'));
    profiles.push({profile: identified(profile), raw: inputs, outputs, binary: identified(path.join(out, round, 'emlf'))});
  }
  for (const key of Object.keys(profiles[0].outputs)) {
    if (profiles[0].outputs[key].sha256 !== profiles[1].outputs[key].sha256) throw Error('Repeated native production differs: ' + key);
  }
  if (profiles[0].profile.sha256 !== profiles[1].profile.sha256 || profiles[0].binary.sha256 !== profiles[1].binary.sha256) throw Error('Repeated profile or complete binary differs');
  await buildMode('selected', ['--pgo-target', 'emlf', '--pgo-use', profiles[0].profile.path]);
  for (const tool of [seed, manager, profdata, script]) if (hash(tool.path) !== tool.sha256) throw Error('Construction tool changed: ' + tool.path);
  for (const item of training) if (hash(item.path) !== item.sha256) throw Error('Training input changed: ' + item.path);
  write('provenance.json', {complete: true, source, seed, manager, profdata, script, training, profiles,
    selected_profile: profiles[0].profile, compiler: identified(path.join(build, 'bin/emlf')), package_manager: identified(path.join(build, 'bin/mlfpkg')),
    reproducibility: {profile: true, llvm: true, compiler_object: true, runtime_object: true, complete_binary: true},
    scope: 'Two fresh stdin-example training/profile/native-production runs. Native builds use genuine package cache keys and SHA-bound profile inputs. No benchmark training or compiler identity aliases. Fresh source self-hosting remains a separate required test.'});
  write('state.json', {complete: true, stage: 'ready', finished: new Date().toISOString()});
  console.log(path.join(build, 'bin/emlf'));
})().catch(error => {
  if (started) write('error.json', {message: error.message});
  console.error(error.stack); process.exitCode = 1;
});
NODE
