// Fail closed on incomplete/filtered runs, weakened limits, stale inputs,
// missing measurement telemetry or an inconsistent native performance verdict.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
export const workloads = ['binary-trees','fannkuch-redux','fasta','k-nucleotide','mandelbrot','n-body','pidigits','regex-redux','reverse-complement','spectral-norm'].sort();
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const sameNames = (actual, expected) => assert.deepEqual([...actual].sort(), expected);
const finite = n => assert(Number.isFinite(n) && n >= 0, 'missing/invalid measurement');
const sha = h => assert(/^[0-9a-f]{64}$/.test(h), 'missing artifact digest');
function verifyRuntimeInputs(report, runtimes) {
  assert.deepEqual(report.runtimes, runtimes, 'compiler/runtime pairing');
  assert.notEqual(runtimes.baseline, runtimes.mlf, 'release baseline requires its bundled runtime');
  for (const runtime of Object.values(runtimes)) {
    assert.equal(fs.realpathSync(runtime), runtime);
    const directory = path.dirname(runtime);
    for (const name of fs.readdirSync(directory).filter(name => /\.[ch]$/.test(name))) {
      const file = path.join(directory, name);
      assert.equal(report.fingerprints[file], hash(file), `runtime input fingerprint: ${file}`);
    }
  }
}
function verifyRuntimeCompile(stage, source, object) {
  const command = stage.command;
  assert.ok(Array.isArray(command) && command.includes('-c'), 'missing runtime compile command');
  assert.deepEqual(command.filter(arg => arg.endsWith('.c')), [source], 'measured runtime source');
  const output = command.indexOf('-o');
  assert.ok(output !== -1 && path.basename(command[output + 1]) === object, 'runtime object output');
}
export function verify(report, manifest, runtimes) {
  verifyRuntimeInputs(report, runtimes);
  assert.equal(report.status, 'passed');
  assert.equal(report.implementation, 'MLF');
  assert.equal(report.runs, 7);
  assert.deepEqual(report.limits, {compilation:3,runtime:2});
  sameNames(manifest.workloads.map(w => w.name), workloads);
  sameNames(report.workload_selection, workloads);
  sameNames(report.benchmarks.map(w => w.benchmark), workloads);
  assert.equal(report.performance_checks.length, 20);
  for (const row of report.benchmarks) {
    assert.equal(row.input, manifest.workloads.find(w => w.name === row.benchmark).default_input);
    sha(row.stdin_sha256);
    sameNames(Object.keys(row.languages), ['baseline','c','mlf']);
    assert.equal(row.binary_samples.length, 7);
    for (const binary of row.binary_samples) for (const language of ['c','baseline','mlf']) {
      sha(binary[language].binary_sha256);
      if (language !== 'c') for (const file of ['program.ll','runtime.o','program.o']) sha(binary[language].artifacts_sha256[file]);
    }
    for (const language of ['c','baseline','mlf']) for (const dimension of ['compilation','runtime']) {
      const summary = row.languages[language][dimension];
      assert.equal(summary.samples.length, 7);
      const times = [];
      for (const [index, sample] of summary.samples.entries()) {
        finite(sample.wall_seconds); finite(sample.cpu_seconds);
        assert(sample.wall_seconds > 0);
        times.push(sample.wall_seconds);
        const processes = sample.stages ?? [sample];
        assert(processes.length > 0);
        if (language !== 'c' && dimension === 'compilation') {
          const runtime = processes.filter(stage => stage.phase === 'runtime');
          assert.equal(runtime.length, 1, 'one measured runtime compile');
          verifyRuntimeCompile(runtime[0], runtimes[language], 'runtime.o');
          const supervisor = processes.filter(stage => stage.phase === 'runtime-supervisor');
          const artifacts = row.binary_samples[index][language].artifacts_sha256;
          assert.equal(supervisor.length, Object.hasOwn(artifacts, 'runtime-supervisor.o') ? 1 : 0);
          if (supervisor.length) {
            const source = path.join(path.dirname(runtimes[language]), 'mlf_process_supervisor.c');
            sha(report.fingerprints[source]);
            sha(artifacts['runtime-supervisor.o']);
            verifyRuntimeCompile(supervisor[0], source, 'runtime-supervisor.o');
          }
        }
        for (const process of processes) {
          finite(process.wall_seconds); finite(process.cpu_seconds); finite(process.peak_rss_bytes);
          assert(process.peak_rss_bytes > 0);
          assert.equal(process.exit_code, 0);
          assert(!process.timed_out && !process.interrupted && !process.termination_signal);
        }
      }
      times.sort((a,b) => a-b);
      assert.equal(summary.median_wall_seconds, times[3]);
      assert.equal(summary.min_wall_seconds, times[0]);
      assert.equal(summary.max_wall_seconds, times[6]);
      finite(summary.median_absolute_deviation_seconds);
    }
    for (const dimension of ['compilation','runtime']) {
      const checks = report.performance_checks.filter(c => c.benchmark === row.benchmark && c.dimension === dimension);
      assert.equal(checks.length, 1);
      const check = checks[0], limit = dimension === 'compilation' ? 3 : 2;
      const ratio = row.languages.mlf[dimension].median_wall_seconds / row.languages.c[dimension].median_wall_seconds;
      assert.equal(check.maximum_ratio, limit);
      assert.equal(check.passed, true);
      finite(check.mlf_over_c);
      // The native verdict uses unrounded measurements. Recompute from the
      // serialized medians as a consistency check, without relaxing its limit.
      assert(check.mlf_over_c <= limit && ratio <= limit);
      assert(Math.abs(check.mlf_over_c - ratio) < 1e-6);
    }
  }
}
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  const [reportFile, manifestFile, candidate, baseline, clang, ...configs] = process.argv.slice(2);
  const report = JSON.parse(fs.readFileSync(reportFile));
  const runtimes = {
    mlf: fs.realpathSync('runtime/mlf_runtime.c'),
    baseline: fs.realpathSync(path.resolve(path.dirname(baseline), '../runtime/mlf_runtime.c')),
  };
  verify(report, JSON.parse(fs.readFileSync(manifestFile)), runtimes);
  for (const file of [candidate, baseline, clang]) assert.equal(report.fingerprints[fs.realpathSync(file)], hash(file));
  for (const [file, digest] of Object.entries(report.fingerprints)) assert.equal(hash(file), digest, `changed benchmark input: ${file}`);
  for (const directory of configs) {
    const file = path.join(directory, directory.endsWith('/backend') ? 'toolchain.json' : 'build.json');
    for (const [input, digest] of Object.entries(JSON.parse(fs.readFileSync(file)).sha256)) assert.equal(hash(input), digest, `changed backend input: ${input}`);
  }
  console.log('Complete ten-workload benchmark gate passed (7 samples, 3x compilation / 2x runtime).');
}
