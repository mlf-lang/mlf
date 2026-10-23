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
export function verify(report, manifest) {
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
      for (const sample of summary.samples) {
        finite(sample.wall_seconds); finite(sample.cpu_seconds);
        assert(sample.wall_seconds > 0);
        times.push(sample.wall_seconds);
        const processes = sample.stages ?? [sample];
        assert(processes.length > 0);
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
  verify(report, JSON.parse(fs.readFileSync(manifestFile)));
  for (const file of [candidate, baseline, clang]) assert.equal(report.fingerprints[fs.realpathSync(file)], hash(file));
  for (const [file, digest] of Object.entries(report.fingerprints)) assert.equal(hash(file), digest, `changed benchmark input: ${file}`);
  for (const directory of configs) {
    const file = path.join(directory, directory.endsWith('/backend') ? 'toolchain.json' : 'build.json');
    for (const [input, digest] of Object.entries(JSON.parse(fs.readFileSync(file)).sha256)) assert.equal(hash(input), digest, `changed backend input: ${input}`);
  }
  console.log('Complete ten-workload benchmark gate passed (7 samples, 3x compilation / 2x runtime).');
}
