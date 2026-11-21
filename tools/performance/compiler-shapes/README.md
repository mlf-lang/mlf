# GHC / MLF compiler shape benchmark

This benchmark compiles **the same generated shared-Haskell source bytes** with GHC
and with GHC-hosted MLF, starting from fresh target outputs and ending at a native
executable. The standard matrix covers 25 program shapes at sizes 8, 32, 128,
1,024 and 8,192, with six paired builds per size. Its 125 cells schedule 1,500
native compilations. Each reported time is the median for one compiler, shape
and size.

It is **not** the C/MLF Benchmarks Game. The [native benchmark runner](../../bench/README.md)
builds and compares pinned application workloads through the package manager and
keeps its own runner contract; nothing here changes it. This suite generates its
own programs, has no application inputs, and reports per-shape compilation ratios
rather than workload gates.

The [21 November 2026 comparison](../../../docs/compiler-shapes-2026-11-21.md) reports elapsed time, peak memory and incomplete builds for the 25-shape standard matrix.

## Compile endpoint

The default measured endpoint is `crate-fused-v1`:

- `PRODUCER/bin/emlf --compile-crate-to-llvm-gc SPEC -o UNIT` (source to checked xMLF and LLVM in one invocation)
- `clang -O2 -Wno-override-module UNIT.ll runtime.o -lgc -lgmp -lm -lpthread -ldl`

This is the low-level crate route over a **bootstrap-only** producer
(`tools/shared/build.py --bootstrap-only --optimization 2`). It is **not** the
installed `emlf SOURCE -o OUTPUT` driver with its native standard library, so its
absolute times must not be presented as the installed compiler's performance.

The separate `emlf-source-v1` runner compares two authenticated public
installations with GHC. It measures the installed `emlf SOURCE -o OUTPUT`
command and verifies the executable for every leg. Run it on POSIX from the
repository root, with fresh installation and output directories.

```sh
# In each of the before and after worktrees
python3 -B tools/shared/build.py --build-dir "$PWD/.mlf-build/install"
# From the implementation worktree
python3 -B tools/performance/compiler-shapes/bench.py installed \
  --before /absolute/before/.mlf-build/install --after "$PWD/.mlf-build/install" \
  --output "$PWD/.mlf-build/installed-pairs"
```

This command records the compiler's own host identity. The public build
produces a GHC-hosted compiler with an installed native standard library. The
paired runner uses a separate schema and analyzer. Five workloads cover a
chain, wide fan-out, a recursive SCC, a four-module diamond and the compiler's
Unicode classifier. The latter uses its production source with a renamed module
so both compilers compile it as user code. Each sample starts with empty target
outputs or is a no-edit repeat of that lane's preceding build. GHC can reuse
user objects on the repeat. The installed MLF command recompiles user code. Pass `--diamond-edit` with a fresh output directory for a separate cohort that changes the shared leaf and checks the new result through both branches of the diamond.

`prepare.py` additionally requires the producer's own receipt to carry
`prepared_verification.kind == "empty"`, which is what a bootstrap-only build has.
A native installation cannot be passed off as this endpoint.

The default publishes the checked object, metadata and query cache, then passes
the retained checked root to the ordinary linker and LLVM backend. Its stage
names are `source-to-llvm` and `llvm-to-executable`. `matrix.json` supplies the
same default to `bench.py list/prepare/run/all` and the direct prepare/run tools.
The explicit `--endpoint crate-bootstrap-v1` option preserves the two-process
route: `--compile-crate` followed by `--crate-to-llvm-gc`, then the same Clang
link. Use that option in both preparation and execution when reproducing an old
cohort. Old setup files and recorded cohort labels are never silently changed;
an endpoint mismatch is rejected, and different endpoints cannot be pooled.
This is still a GHC-hosted bootstrap compiler, distinct from the installed
`emlf SOURCE -o OUTPUT` driver.
See the [default-entry integration study](../../../docs/default-fused-build-2026-11-15.md)
for package/cache regressions and a fresh paired growth comparison.

## Running it

Run from the repository root. The default command builds a bootstrap-only GHC `-O2` producer and prepares the fixed inputs under the sweep directory. Supply `--producer DIR` for an existing bootstrap build, or `--setup FILE` to reuse a prepared setup.
The sweep runs one shape at a time, with a separate cohort for every size.
It records failures and resource limits alongside completed cells and continues
to the next cell. The command exits unsuccessfully if any selected cell failed.
The comparison table and its CSV are written to `WORKDIR/summary.md` and
`WORKDIR/summary.csv`.

Each cohort retains the whole tracked Git patch. The sweep verifies the
archive against its recorded byte count and SHA-256. When patches differ,
it replays them at the recorded revision in a temporary index. The revision,
shared measurement pins and all tracked file contents and modes must agree,
apart from edits, additions or deletions of regular UTF-8 prose files named
`README.md`, `CONTRIBUTING.md`, `CHANGELOG.md` at the project root or
`docs/*.md` directly under `docs`. A change to a measured file's pin still
fails the comparison even if its path matches a documentation name.

```sh
# Show the standard matrix or a filtered selection.
python3 tools/dev.py bench shapes list
python3 tools/dev.py bench shapes list --family wide_case --size 128

# Build, prepare and measure all 125 cells.
python3 tools/dev.py bench shapes

# Reuse the exact setup for a separate table.
python3 tools/dev.py bench shapes --workdir .mlf-build/selected-shapes \
  --setup .mlf-build/compiler-shapes/setup/setup.json \
  --family wide_case,dependency_diamonds --size 8,128
```

`--family` and `--size` each accept repeated values and replace their respective
defaults. Each cell uses six pairs unless you set `--repeats`. Add
`--prune-build-products` to a sweep to remove verified native executables and
GHC target objects from successful cells after checking them. The receipts,
sources and per-cell measurements remain available.

Fit the standard five-size point exponents offline with NumPy installed:

```sh
python3 tools/dev.py bench shapes growth docs/compiler-shapes-2026-11-21.csv
```

The command also accepts a sweep directory containing `summary.csv` and its
per-cell evidence. It prints CSV with one row per shape. Each fit uses six
paired builds at 8, 32, 128, 1,024 and 8,192 and estimates the nonnegative
offset and scale in `a + b*(n/nmax)^p` from those five medians. The
`met` and `higher` outcomes compare the unrounded MLF and GHC point
exponents. An estimate outside the fitter’s interior [0.101, 2.999] or a
zero growth scale yields `indeterminate`. Missing or failed standard cells
yield `incomplete`. The compiler columns identify the measured binary and
producer receipt. Published rows also supply its Git revision.

For a paired bootstrap interval, select the optional `baseline` and at least
three positive sizes of one family **in a single cohort**. The baseline runs once per
repetition at size zero. `--interleave-pairs` spreads sizes across rounds
while keeping the two compilers adjacent. `all` prepares, runs and analyzes a
cohort. A completed cohort can also be analyzed with `bench.py analyze`.

```sh
python3 -B tools/performance/compiler-shapes/bench.py all \
  --workdir .mlf-build/compiler-shapes --cohort wide-case-growth --interleave-pairs \
  --family baseline --family wide_case --size 8 --size 32 --size 128
python3 tools/performance/compiler-shapes/fit_growth.py \
  .mlf-build/compiler-shapes/cohorts/wide-case-growth --family wide_case
```

`fit_growth.py` requires NumPy. It reports per-size medians, OLS and endpoint
slopes in milliseconds per unit of shape size, and a fitted exponent in the
model `a + b*(n/nmax)^p`. Each of 2,000 bootstrap samples resamples adjacent
MLF/GHC pairs within each size. The estimates describe the measured size range.

`inferred_functions` removes the generated function signatures from
`flat_functions` and retains the annotated entry and IO harness. See the
[inferred-function study](../../../docs/compiler-inferred-functions-2026-11-15.md)
for its measured range and qualification.

`inferred_poly_functions` rotates identity, constant, application and composition
definitions without signatures. Every generated function is instantiated at both
`Int` and `Bool`; runtime-dependent branches have an independent closed-form
oracle. The entry/IO harness retains its annotations, as in the other families.
See the [polymorphic-function study](../../../docs/compiler-polymorphic-functions-2026-11-15.md)
for the before/after measurements and preserved type inventories.

`inferred_poly_chain` defines unsigned functions `f0 step y = step y` and
`fi step y = step (fprevious step y)`. The final function is used with both an
integer increment and a Boolean negation, so every layer is reachable at two
types. Its independent oracle checks the accumulated increment and negation
parity. The entry/IO harness retains its signatures.
See the [polymorphic-chain study](../../../docs/compiler-polymorphic-chain-2026-11-15.md)
for the separate endpoint results, slope criteria and qualification limits.

On a Mac whose shell cannot inspect processes (`/bin/ps` denied by a sandbox), the
measurement harness cannot sample the process group and refuses to run. Use the
pinned Linux environment instead of weakening a guard:

```sh
docker build -f tools/performance/compiler-shapes/linux-environment.dockerfile \
  -t mlf-compiler-shapes:9.14.1 tools/performance/compiler-shapes
docker run --rm -v "$PWD:/work" -w /work mlf-compiler-shapes:9.14.1 \
  bash -lc 'python3 tools/shared/build.py --bootstrap-only --optimization 2 \
    --build-dir .mlf-build/shared-ghc && \
    python3 -B tools/performance/compiler-shapes/bench.py prepare \
      --workdir .mlf-build/compiler-shapes --producer .mlf-build/shared-ghc --build-builtin && \
    python3 -B tools/performance/compiler-shapes/bench.py sweep \
      --workdir .mlf-build/compiler-shapes --setup .mlf-build/compiler-shapes/setup/setup.json'
```

The sweep also reports each compiler’s median sampled peak process-group RSS in
MiB. The resource monitor samples every 100 ms, so short-lived peaks may fall
between samples. For a type-depth experiment, pass `--family nested_poly_types`
and repeat `--size` with 4, 8, 16 and 32. That selection uses the standard runner.

## Matrix

The 25 families below make up the standard matrix. Each family has its own
size unit. For example, `n` counts case arms in `wide_case` and fields in
`wide_product`. Request `--family baseline` separately to include the minimal
size-zero program that reads and prints its argument.

| Family | Generated work |
| --- | --- |
| `flat_functions` | `n` annotated top-level functions summed in a balanced tree |
| `inferred_functions` | identical independent functions with their `n` signatures removed; entry/IO harness unchanged |
| `inferred_poly_functions` | unsigned independent identity/constant/application/composition functions; each used at `Int` and `Bool` with runtime-dependent branches |
| `dependency_chain` | `n` annotated functions in a strict chain |
| `inferred_chain` | the same chain with no signature on the generated functions |
| `inferred_poly_chain` | unsigned dependency chain applying a supplied step once per layer, used at both `Int` and `Bool` |
| `recursive_ring` | `n` functions in a mutually recursive cycle |
| `mono_calls` | `n` monomorphic constructor pack/unpack calls |
| `poly_calls` | the same calls through a rank-1 `forall` |
| `tree_chain` | `n` leaves in a left-deep constructor tree |
| `balanced_tree` | the same leaves in a balanced constructor tree |
| `literal_table` | a generated constructor table of `n` items |
| `higher_order_chain` | `n` nested higher-order compositions |
| `local_functions` | flat functions inside one local `let` |
| `wide_case` | a datatype with `n` constructors and a matching case arm for each constructor, selected by a runtime input clamped to the constructor range. An additional untimed invocation checks every arm in order |
| `class_instances` | `n` concrete wrapper types, each with an instance of the same class, all called through one constrained function |
| `dependency_diamonds` | `n` layers of branching and reconverging function dependencies, with one runtime path through each layer |
| `state_updates` | `n` ordered integer-array updates in `IO`, with the result read back at runtime |
| `captured_closures` | `n` closures capture runtime values, escape in a returned tree, and are applied in a separate consumer |
| `wide_product` | one constructor holds `n` integer fields, all destructured once and read with distinct positional weights |
| `rank2_arguments` | `n` call sites pass polymorphic functions to a rank-2 consumer that instantiates them at both `Int` and `Bool` |
| `irregular_literal_table` | two-field literal rows with deterministic irregular payloads and an order-sensitive checksum |
| `nested_poly_types` | `n` polymorphic boxes nest around the input before `n` projections return it |
| `rank2_callbacks` | `n` separately type-checked consumers each use a rank-2 callback at both `Int` and `Bool` |
| `decoder_pipeline` | `n` field reads validate against prior decoded state, with successful and malformed runtime inputs |

The generator records each case's runtime inputs and independently computed
expected output in the plan. Both executables must produce the expected value
for every input.

## Measurement contract

- **Same source, both lanes.** Source bytes are hashed into the plan and re-checked
  immediately before every leg; GHC and MLF compile the identical file.
- **Fresh user target.** Every leg compiles in a new directory with a new private
  query cache. The plan asserts `fresh > 0`, `reused == 0` and that every group is
  uncached, and records the fresh group count.
- **Fixed inputs may be reused.** The checked builtin pair, the prebuilt
  `MLF.Primitive` host package, `runtime.o` and the toolchains are prepared once.
  `--build-builtin` produces the builtin pair through the public crate path; two
  independent preparations in this revision produced byte-identical
  `.mlfci`/`.mlfco` pairs.
- **Correctness is not relaxed.** Each MLF repetition is compared as raw
  `.mlfci`/`.mlfco` bytes against the first one in the cell, ordered query-group
  identities are compared, and every produced executable is run on all its recorded inputs
  with an exact stdout/stderr comparison.
- **One pipeline at a time, ordinary flags.** GHC runs
  `--make -j1 -O2 -fforce-recomp` with an isolated package DB; MLF runs the selected
  endpoint above; Clang runs plain `-O2`. All arguments are recorded in the plan and
  re-recorded per leg.
- **Order is frozen before samples.** Cells are shuffled with seed `20261031`. Each
  cell runs six paired rounds by default and alternates which compiler starts, so both
  within-cell and across-cell start positions are balanced.
- **Guards stay in place.** 90 s wall limit per leg, 512 MiB per-command output
  budget, 8 GiB aggregate cohort budget, 5 GiB free-disk floor, 3 GiB available
  memory floor, 5 GiB sampled process-group RSS ceiling, `RLIMIT_AS` on Linux.
  macOS has neither the hard address-space guarantee nor `/proc`, and sampling may
  miss short peaks. No target warming and no filesystem cache flushing is used.
- **Failures are kept.** A failed or guarded leg is recorded and stops that cell's
  remaining samples; it is never replaced. The analyzer refuses to publish a cohort
  that contains any failure.

## Result files

`--workdir W` holds `W/setup/`, `W/cohorts/<cohort>/` and `W/results/<label>/`:

| File | Content |
| --- | --- |
| `setup/setup.json` | endpoint profile, producer/driver/Clang paths, builtin pair identity, limits |
| `cohorts/<cohort>/plan.json` | schema, cohort, endpoint, source commit + dirty patch + untracked digests, toolchain identities, GHC/Clang/MLF arguments, cases with source hashes, frozen schedule, limits, claim limits |
| `cohorts/<cohort>/receipt.json` | one entry per executed leg: order, exit status, guard reason, raw wall/user/system, stage timings, fresh/reused counts, checked-output digests, correctness, failure list |
| `cohorts/<cohort>/legs/` | retained per-leg receipts, stdout/stderr, stages, query-cache inventory, sources, build products |
| `results/<label>/summary.json` | provenance, compatibility key, per-cell medians, ratios, stage medians, query footprint |
| `results/<label>/summary.csv` | the same cells as a flat table |
| `results/<label>/samples.csv` | every sample in execution order with its exit status and fresh/reused counts |
| `results/<label>/summary.md` | the human table and claim limits |

The analyzer refuses a cohort whose plan lacks the schema-2 identity block, whose
digest does not match, whose schedule is missing or duplicated, whose timings are
not finite and non-negative, whose runs are qualification-only or guarded, whose
sources changed, and reports whose cohorts differ in endpoint, suite version,
repeat count, GHC/Clang identity, producer receipt, builtin pair or host. Cells
that appear in more than one cohort are listed and never combined.

Ledger paths are absolute because they pin the authenticated producer, toolchain
and per-leg commands, so re-analysis needs the same path mapping the cohort was
measured with — for example the same `-v "$PWD:/work" -w /work` container. Against
the recorded cohort, re-running `bench.py analyze` reproduced a byte-identical
`summary.md`.

Large build products stay in the evidence directory and in CI artifacts. The
repository does not contain them: `.mlf-build/` is ignored.

### Query storage evidence

Legacy cohorts retain the original one-`.mlfq`-per-fresh-group check and footprint
calculation. With `query-graph-v1`, group counts still come from the compiler's
actual `.queries` report, never from the number of result files. Binding,
Datatype and other graph nodes add results, and equal payloads share an address.

After timing, before the existing query-cache cleanup, the runner retains a
`query-graph-evidence.json` sidecar containing the exact UTF-8 query report and
base64 copies of the actual CURRENT and generation-index bytes. The ordinary
inventory records every result's measured SHA-256 and byte count. The analyzer
checks CURRENT's selected index, content addresses, graph closure and cycles,
the measured crate/compiler configuration, and the exact correspondence between
each fresh group's reported identity, sorted members,
`InferScc` node and raw payload SHA. It rejects reused groups, missing evidence,
missing or corrupt result inventories, and changes across repetitions. Existing
raw checked-output comparisons and executable oracles remain required.

`query_storage` labels the footprint: `legacy-mlfq` counts only `.mlfq` files;
`query-graph-v1` counts CURRENT, its generation index and all unique persisted
`.mlfqr` results, including initial or superseded-node results. Neither is a
group count or a measurement of cumulative disk traffic. Historical measurements
are not relabelled. Graph cohorts recorded before this sidecar cannot establish
the index mapping or closure and must be re-measured, not retroactively filled in.

## CI

- Every ordinary PR runs `python3 tools/dev.py check-tools`. The compiler-shape
  tests cover the matrix defaults, generated programs and oracles, graph evidence,
  schedule balance, sweep reports and cancellation without invoking a compiler.
  The GHC O2 job filters the standard matrix to size 8 for `flat_functions`,
  `recursive_ring`, `wide_case`, `class_instances`, `dependency_diamonds`,
  `state_updates`, `captured_closures`, `wide_product`, `rank2_arguments`,
  `irregular_literal_table`, `nested_poly_types`, `rank2_callbacks` and `decoder_pipeline`.
  Six paired builds per cell give 156 timed compilations in one cohort. CI
  uploads the available receipts and measurements even if a build fails.
- The manual `.github/workflows/compiler-shapes.yml` workflow runs the standard
  sweep. Dispatch inputs can filter families and sizes or set the repeat count.
  The job summary and uploaded CSV show the available results, including failed
  cells. The workflow prunes verified build products to save disk space.
- CI checks executable correctness and evidence integrity. Wall-clock medians
  from a shared runner are descriptive.

## Measured cohort: 2026-10-31

Source `b81f9b0ad10d81c3b12275b59e5d37502a653ddf` (clean tree), cohort
`linux-default-20261031`, endpoint `crate-bootstrap-v1`, GHC 9.14.1, Clang 18.1.3,
Linux 6.12.76-linuxkit aarch64 (Docker Desktop VM on the Apple M1 Max host that ran
the earlier windows), one pipeline at a time. **31 cells, 186 timed compilations,
558 executable oracle runs, 0 failures.** All 93 MLF builds reported fresh target
groups with zero reused groups, and every repetition matched the first checked
output byte for byte.

Seconds are three-sample medians; the ratio is `MLF median / GHC median`. Group
counts are the fresh target groups recorded by the compiler.

| Family | Fresh groups 8/32/128 | GHC 8/32/128 | MLF 8/32/128 | MLF/GHC 8/32/128 |
| --- | --- | --- | --- | --- |
| `flat_functions` | 11/35/131 | 0.494/0.463/0.577 | 1.207/1.418/2.241 | 2.44/3.06/3.89 |
| `dependency_chain` | 11/35/131 | 0.454/0.465/0.505 | 1.218/1.623/2.114 | 2.68/3.49/4.18 |
| `inferred_chain` | 11/35/131 | 0.460/0.450/0.564 | 1.315/1.645/2.835 | 2.86/3.65/5.03 |
| `recursive_ring` | 4/4/4 | 0.443/0.508/0.571 | 1.127/1.285/1.898 | 2.55/2.53/3.33 |
| `mono_calls` | 5/5/5 | 0.444/0.469/0.654 | 1.157/1.226/1.491 | 2.61/2.61/2.28 |
| `poly_calls` | 5/5/5 | 0.479/0.481/0.666 | 1.242/1.236/1.542 | 2.60/2.57/2.32 |
| `tree_chain` | 4/4/4 | 0.456/0.475/0.636 | 1.171/1.222/1.781 | 2.57/2.57/2.80 |
| `balanced_tree` | 4/4/4 | 0.508/0.460/0.562 | 1.171/1.237/1.547 | 2.31/2.69/2.75 |
| `literal_table` | 5/5/5 | 0.464/0.431/0.490 | 1.176/1.165/1.255 | 2.54/2.70/2.56 |
| `higher_order_chain` | 6/6/6 | 0.459/0.439/0.486 | 1.173/1.187/1.362 | 2.56/2.70/2.80 |
| `baseline` (n=0) | 3 | 0.445 | 1.133 | 2.55 |

MLF is slower in all 30 shaped cells and in the baseline. Ratios span 2.28 to 5.03;
the per-size mean is 2.57 at n=8, 2.86 at n=32 and 3.19 at n=128.

Where the MLF time sits (medians, seconds):

| Cell | Source to checked | Checked to LLVM | LLVM to executable |
| --- | ---: | ---: | ---: |
| `baseline` (3 groups) | 0.458 | 0.452 | 0.185 |
| `flat_functions` n=128 (131) | 1.398 | 0.525 | 0.287 |
| `dependency_chain` n=128 (131) | 1.353 | 0.515 | 0.219 |
| `inferred_chain` n=128 (131) | 2.035 | 0.546 | 0.223 |
| `tree_chain` n=128 (4) | 0.683 | 0.662 | 0.406 |
| `recursive_ring` n=128 (4) | 0.791 | 0.544 | 0.535 |

### What this cohort shows

1. **A fixed floor dominates small programs.** The three-group baseline needs
   1.133 s against GHC's 0.445 s. Its checked-to-LLVM stage alone takes 0.452 s, so
   a program that does nothing still pays roughly 0.45 s there and about 0.69 s more
   than GHC in total. The n=8 cells sit only 0.02-0.18 s above that floor.
2. **Growth follows fresh group count, not constructor or call shape.** The three
   chain/flat families reach 131 groups at n=128 and their source-to-checked stage
   rises to 1.35-2.04 s, while their checked-to-LLVM stage stays at 0.52-0.55 s.
   Families that stay at 4-6 groups remain near 1.1-1.5 s regardless of n, and their
   ratios stay in the 2.3-2.8 band.
3. **Derived marginal cost, exploratory.** Subtracting the baseline's
   source-to-checked median and dividing by the extra groups gives roughly 7 ms per
   group for `flat_functions` and `dependency_chain`, and 12 ms for
   `inferred_chain`. This is arithmetic on medians of one window, not an isolated
   per-group measurement.
4. **Retained query footprint scales the same way.** 0.53 MB at 3 groups,
   1.56 MB at 11, 17.0 MB at 131 for `flat_functions`, and 36.3 MB at 131 for
   `inferred_chain`. That is retained `.mlfq` bytes, not measured cumulative disk
   traffic, so it is evidence of representation size rather than a timing
   attribution.
5. **Big single groups still cost.** `tree_chain` and `recursive_ring` keep 4 groups
   but grow to 1.78 s and 1.90 s at n=128, and their checked-to-LLVM and link
   stages grow with the one large group (0.66 s and 0.54 s respectively). Per-group
   overhead is therefore not the only effect in the matrix.

### Next candidates, not conclusions

- **Per-group cache publication.** The source-to-checked stage carries nearly all of
  the group-count slope, and `CrateQuery.writeCache` currently launches a supervised
  `/bin/mv` per publication, which a 131-group program reaches at least 131 times.
  A candidate must preserve publication failures, first-error order, key semantics,
  supervision and rollback; this cohort does not prove that process launch is the
  cost or how much a change would save.
- **Repeated per-group preparation and serialization.** The 36.3 MB footprint at 131
  inferred groups and the 12 ms per-group slope deserve inspection of the
  self-contained query context. Neither the checks nor the target's fresh work may
  be removed to make a number smaller.
- **The fixed checked-to-LLVM cost.** A near-constant 0.45-0.55 s regardless of
  program shape is worth its own entry-point comparison, including the installed
  `emlf SOURCE` driver in a separate cohort.

### What this cohort cannot tell you

- It is one host inside a virtualised Linux container, run once. It is not a general
  "MLF is N times slower" claim, and it does not replace the earlier macOS window.
- Three samples per cell are a spread description, not a confidence interval. Six
  cells show GHC spreads above 25% (up to 64% for `flat_functions` n=128), so
  small ratio differences, including the 2.28-2.32 readings for `mono_calls` and
  `poly_calls` at n=128, are not resolvable.
- Three sizes do not establish asymptotics, and per-stage medians are separate
  medians that need not sum to the whole-run median.
- It measures the bootstrap crate route only. Absolute times, and the size of the
  fixed floor, are endpoint-specific.

## Earlier exploratory window

The 2026-10-31 macOS screen (10 families x 8/32/128 plus a separate 5-family
512 window, `fffb66a3`) was produced before this benchmark had a schema-2 identity
block. Its receipts remain in the ignored local experiment directory and its numbers
stay in the project history; the current analyzer refuses that older format rather
than relabelling it. Those windows and this cohort are separate cohorts and are
never pooled.

A first full-matrix attempt at `7c395e04` stopped at leg 149 on the aggregate
evidence budget, which was still sized for the older 41-cell windows. Its 148
retained legs are kept locally as an aborted cohort, carry `complete: false` with
their original records, and are excluded from every result above.


Explicit `--size` values may range from 1 through 8192. A larger requested size
is a qualification attempt, not a promise that every compiler shape supports
it: preserve compiler depth-limit failures in the receipt and report them.
`bench.py run --setup PATH` uses that existing setup (and still authenticates
its producer and endpoint). For the disk-entry phase diagnostic, see
[`MLF_CRATE_PROFILE`](../../../docs/crate-compilation.md#profiling-the-disk-to-llvm-entry).
