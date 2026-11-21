# Default retained-root builds, 2026-11-15

This change integrates the previously measured single-invocation crate compiler
into default complete package builds and `compiler-shapes`. It starts from the
uncommitted, qualified polymorphic-chain implementation after checkpoint
`590b8317`; the preceding study and its failed intermediate cohorts remain
unchanged. This task does not create another commit.

## Build behavior

The package manager still schedules library, target, emission, native object,
runtime, link and publication actions. A cold executable/test target now invokes
`--compile-crate-to-llvm-gc` once, requesting the ordinary codegen cache and an
invocation-owned report with `--codegen-cache DIR --query-report FILE`.

The target's checked metadata/object and retained LLVM/report are published in
the ordinary checksummed target artifact. Before handing that LLVM to the
emission cache, the manager checks the producing compiler identity, the current
root metadata/object digests and both retained file digests. Native object and
link actions retain their inputs, flags and independent cache boundaries. A
failed compile/emission action cannot publish a new executable.

Library actions continue to request checked artifacts only. No-edit target and
emission cache hits invoke no compiler. Checked-only artifacts and compilers
without the new cache protocol continue through the existing two-stage commands.
Feature discovery requires the new `--codegen-cache` option, so an earlier
compiler advertising only the uncached fused command is not misidentified.

Both cached CLI routes now use the same `PreparedCompiler` linking/admission
path. A development control initially found that the old disk-cache command
linked the full Prelude while the retained-root command used the admitted
prepared Prelude; equivalent programs therefore had different LLVM and cache
keys. The corrected CLI paths share exact input/optimized keys and LLVM bytes.
The public `CrateCodegen.emitFile*` library APIs remain unchanged.

The installed `emlf SOURCE -o OUTPUT` driver is separate and is not replaced by
this crate-driver change.

## Benchmark contract

`matrix.json` now owns `default_endpoint = crate-fused-v1`. All four `bench.py`
build/list entry points and the direct preparation/run scripts use that value.
Explicit `crate-bootstrap-v1` remains available; an old setup cannot silently
be consumed as a new endpoint. Existing historical cohort labels are preserved.

The experiment records its plan before final measurement in
`.mlf-build/default-fused-build-20261115/measurement-plan.json`. Preparation and
the primary run deliberately omit `--endpoint`, then check that the generated
plan names `crate-fused-v1`. The workload is the same unsigned polymorphic chain
at N=32,64,128,256,512, plus an empty baseline. Each compiler gets six fresh
compilations per cell, for 72 compilations and 216 independent executable output
checks. Paired order, source bytes, tool flags, fixed builtin artifacts and
resource guards follow the preceding study.

The comparison reports positive-size medians, OLS with an intercept and the
endpoint slope `(T512 - T32) / 480`. The three descriptive criteria are unchanged:
all positive medians and both slopes below paired GHC. A paired bootstrap interval
uses 10,000 draws and seed 20261115. A fresh measurement is reported as observed;
failures are retained and are not replaced. These finite-range results do not
establish an asymptotic complexity class.

Package-manager correctness is exercised separately from the compiler timing
cohort. The timing cohort measures the GHC-hosted crate compiler through Clang
to an executable, with fixed dependencies prepared outside timing. It does not
measure the package manager's complete wall time or qualify native self-hosting.

## Validation and results

All evidence below uses the authenticated `producer-v1` GHC 9.14.1 / `-O2`
build of the final compiler sources. Its builtin verification regenerated the
embedded image exactly, verified immutable inputs afterwards, and rewrote no
source file. The existing independent checking and runtime output gates remain
active.

| Validation | Result |
| --- | --- |
| Benchmark contract suite | 82 tests passed; before the default change, its new parser test failed at all six entry points |
| Default package controls | 30 checks passed, including two parallel cold targets, staged libraries, jobs 1/2 parity, shared-cache restoration, corruption repair, dependency edits, failed publication and real staged fallback |
| Polymorphic-chain CLI controls | Staged: 14 checks; fused: 20; fused with codegen cache/report: 36; all passed |
| Flat signed/inferred CLI controls | 26 checks each through the fused entry; all passed |
| Shared frontend and runtime controls | All 12 commands passed their expected-status/output checks, including the deliberately failing child-process case |
| Package smoke | Three cold/warm/dependency-change cases passed on both interpreter and LLVM |
| Existing complete package campaign | 79 reviewed executions, no aliases; all 22 resolver, 29 integration and 28 checked-release cases passed, plus scheduler and target-dependency checks |
| Native build runner | All 22 checks passed |
| Default endpoint shape regression | Six families at N=8 plus baseline; 42 compilations and 126 executable-output checks passed |
| Explicit two-stage shape regression | Same shape/control inventory; 42 compilations and 126 executable-output checks passed |
| Lock and whitespace | Updated `mlf.lock`, `--locked plan` and `git diff --check` passed |

The complete package campaign first built its native test executable with 13
checked-only library compilations and one fused target compilation, with no
second disk-to-LLVM compiler call. That first test execution then stopped in
`extraCases`: this invocation had omitted the documented `MLF_GC_PREFIX`
environment variable. The exact empty-prefix `canonicalPath` failure was
reproduced separately. Setting the already-installed BDWGC 8.2.12 prefix fixed
that probe. The corrected campaign reused every checked crate, the LLVM emission
and the program object without another compiler call; the explicit prefix selected
static GC, so the runtime and native link were rebuilt. The resulting executable
completed all 79 cases in a fresh campaign directory. The first failure and the
corrected run are both retained. No compiler/test source or expected result
was changed to obtain that pass.

The native self-bootstrap gate is separate: `./mlfpkg --locked build` could not
start because `.mlf-build/package-manager/mlfpkg` is absent. No native seed or
other dependency was installed. Thus this is a GHC-hosted compiler qualification,
including execution of its generated native package test program, **not** a
native compiler self-bootstrap qualification.

### Fresh unsigned polymorphic-chain growth

Preparation and execution omitted `--endpoint`; the stored plans confirm
`crate-fused-v1`. All 72 timed compilations and 216 executable-output checks
passed. Seconds below are six-run medians; N=0 is reported separately from the
positive-size slope calculations.

| Functions N | MLF seconds | GHC seconds | MLF lower time |
| ---: | ---: | ---: | ---: |
| 0 | 0.333330 | 0.509205 | 34.5% |
| 32 | 0.354665 | 0.553487 | 35.9% |
| 64 | 0.372775 | 0.563089 | 33.8% |
| 128 | 0.396095 | 0.571682 | 30.7% |
| 256 | 0.471965 | 0.677599 | 30.3% |
| 512 | 0.594946 | 0.799602 | 25.6% |

| Growth statistic, N=32..512 | MLF ms/function | GHC ms/function | MLF lower |
| --- | ---: | ---: | ---: |
| OLS with intercept | 0.503755 | 0.536579 | 6.1% |
| Endpoint `(T512-T32)/480` | 0.500585 | 0.512741 | 2.4% |

All three predeclared descriptive criteria pass: every positive-size median,
the OLS slope and the endpoint slope are lower than paired GHC. The paired
bootstrap 95% interval for **MLF minus GHC OLS slope** is
**[-0.732055, +0.010254] ms/function**. It includes zero, so this cohort does not
establish a statistically clear growth-rate advantage. It also does not establish
a different asymptotic complexity class. In particular, the small-size growth
segments are not uniformly flatter.

All samples remain in the analysis. GHC's N=512 samples range from 0.756444 to
1.458671 seconds; the slow sample was neither discarded nor replaced. There was
one predeclared primary measurement cohort, with no performance-driven rerun.
The archived earlier single-invocation cohort appears separately in the plot;
it is not pooled with current data or treated as a causal integration speedup.

![Fresh paired growth comparison](../.mlf-build/default-fused-build-20261115/comparison/chain-scaling.png)

Points are medians and the left-panel error bars span observed minima/maxima.
The right panel subtracts each current lane's N=32 median to expose growth.

### Reproduction and evidence

The serial campaign driver is
`.mlf-build/default-fused-build-20261115/run-measurements.py`; its recorded argv,
exit statuses and log digests are in `measurement-commands.json`. The preserved
plan is `measurement-plan.json`. The package controls can be replayed with:

```sh
python3 -B tools/shared/test_fused_package_build.py \
  --build-receipt .mlf-build/default-fused-build-20261115/producer-v1/receipt.json \
  --build-runner .mlf-build/default-fused-build-20261115/transport/mlf-build-runner \
  --output /absolute/fresh/package-controls
```

Principal evidence under `.mlf-build/default-fused-build-20261115/`:

- `producer-v1/receipt.json` and `producer-v1/builtin-verification/receipt.json`;
- `package-controls/receipt.json`, `chain-cached/receipt.json`, `direct-tests/receipt.json`;
- `native-packages/verification.json` (retained failed invocation),
  `gc-environment-repro.json`, and `native-packages-gc/verification.json` (complete);
- `default/cohorts/chain-final/{plan,receipt}.json`, both `regression-smoke` cohorts,
  and `comparison/chain-comparison.json`;
- `comparison/chain-scaling.{png,svg}` and `qualification.json`, which binds the
  final sources, producer, driver/report digests and current test evidence.

The initial dirty-tree snapshot is retained. Unrelated pre-existing files and
the preceding study are unchanged; no commit or push was made in this task.
