# GHC / MLF compiler shape benchmark

This benchmark compiles **the same generated shared-Haskell source bytes** with GHC
and with GHC-hosted MLF, starting from fresh target outputs and ending at a native
executable. It classifies where compile time goes for ten program shapes at three
sizes. It is a maintained repository benchmark: one entry point, a frozen schedule,
a machine-readable result format, and layered CI.

It is **not** the C/MLF Benchmarks Game. The [native benchmark runner](../bench/README.md)
builds and compares pinned application workloads through the package manager and
keeps its own runner contract; nothing here changes it. This suite generates its
own programs, has no application inputs, and reports per-shape compilation ratios
rather than workload gates.

## Compile endpoint

The measured endpoint is `crate-bootstrap-v1`:

- `PRODUCER/bin/emlf --compile-crate SPEC -o UNIT` (source to checked xMLF)
- `PRODUCER/bin/emlf --crate-to-llvm-gc UNIT.mlfci` (checked to LLVM)
- `clang -O2 -Wno-override-module UNIT.ll runtime.o -lgc -lgmp -lm -lpthread -ldl`

This is the low-level crate route over a **bootstrap-only** producer
(`tools/shared/build.py --bootstrap-only --optimization 2`). It is **not** the
installed `emlf SOURCE -o OUTPUT` driver with its native standard library, so its
absolute times must not be presented as the installed compiler's performance.

`matrix.json` also declares `emlf-source-v1` for that installed driver. It is
declared and unmeasured: this revision has no preparation path for it, so the entry
point refuses to select it. Once it exists, it is a **separate profile and a
separate cohort**; the analyzer rejects reports that mix endpoint profiles.

`prepare.py` additionally requires the producer's own receipt to carry
`prepared_verification.kind == "empty"`, which is what a bootstrap-only build has.
A native installation cannot be passed off as this endpoint.

## Running it

```sh
# What would run? Prints endpoint, matrix, families and the cell/compile counts.
python3 -B tools/performance/compiler-shapes/bench.py list
python3 -B tools/performance/compiler-shapes/bench.py list --matrix smoke

# Prepare fixed dependencies once, run one cohort, write the analysis.
python3 -B tools/performance/compiler-shapes/bench.py all \
  --workdir .mlf-build/compiler-shapes --cohort default-20261031 \
  --producer .mlf-build/shared-ghc --build-builtin

# Filters: families and sizes are repeatable; the baseline stays included.
python3 -B tools/performance/compiler-shapes/bench.py all \
  --workdir .mlf-build/shapes-512 --cohort flat-512 \
  --producer .mlf-build/shared-ghc --build-builtin \
  --family flat_functions --family local_functions --size 512

# Separate phases when a setup is reused or a run must be resumed by hand.
python3 -B tools/performance/compiler-shapes/bench.py prepare ...
python3 -B tools/performance/compiler-shapes/bench.py run --workdir W --cohort C ...
python3 -B tools/performance/compiler-shapes/bench.py analyze --workdir W --cohort C
```

`local_functions` is opt-in and never part of the default matrix. `--family` and
`--size` replace the matrix selection; they do not add to it.

On a Mac whose shell cannot inspect processes (`/bin/ps` denied by a sandbox), the
measurement harness cannot sample the process group and refuses to run. Use the
pinned Linux environment instead of weakening a guard:

```sh
docker build -f tools/performance/compiler-shapes/linux-environment.dockerfile \
  -t mlf-compiler-shapes:9.14.1 tools/performance/compiler-shapes
docker run --rm -v "$PWD:/work" -w /work mlf-compiler-shapes:9.14.1 \
  bash -lc 'python3 tools/shared/build.py --bootstrap-only --optimization 2 \
    --build-dir .mlf-build/shared-ghc && \
    python3 -B tools/performance/compiler-shapes/bench.py all \
      --workdir .mlf-build/compiler-shapes --cohort linux-20261031 \
      --producer .mlf-build/shared-ghc --build-builtin'
```

## Matrix

| Matrix | Content | Cells | Timed compilations |
| --- | --- | ---: | ---: |
| `default` | 10 shape families x sizes 8, 32, 128, plus one minimal baseline | 31 | 186 |
| `smoke` | 2 families at size 8, plus baseline (CI coverage) | 3 | 18 |

| Family | Generated work | Default |
| --- | --- | --- |
| `flat_functions` | `n` annotated top-level functions summed in a balanced tree | yes |
| `dependency_chain` | `n` annotated functions in a strict chain | yes |
| `inferred_chain` | the same chain with no signature on the generated functions | yes |
| `recursive_ring` | `n` functions in a mutually recursive cycle | yes |
| `mono_calls` | `n` monomorphic constructor pack/unpack calls | yes |
| `poly_calls` | the same calls through a rank-1 `forall` | yes |
| `tree_chain` | `n` leaves in a left-deep constructor tree | yes |
| `balanced_tree` | the same leaves in a balanced constructor tree | yes |
| `literal_table` | a generated constructor table of `n` items | yes |
| `higher_order_chain` | `n` nested higher-order compositions | yes |
| `local_functions` | flat functions inside one local `let` | no (opt-in) |
| `baseline` | reads argv and prints it | added by the matrix |

Every program is generated by `generate.py` and carries a closed-form expected
output for three inputs, including a negative one for the ring family.

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
  identities are compared, and every produced executable is run on all three inputs
  with an exact stdout/stderr comparison.
- **One pipeline at a time, ordinary flags.** GHC runs
  `--make -j1 -O2 -fforce-recomp` with an isolated package DB; MLF runs the three
  stages above; Clang runs plain `-O2`. All arguments are recorded in the plan and
  re-recorded per leg.
- **Order is frozen before samples.** Cells are shuffled with seed `20261031`. Each
  cell runs three paired rounds and alternates which compiler starts, so both
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

## CI

- Every ordinary PR runs `test_contract.py` (17 contract tests: refusals, schedule
  balance and matrix shape; no compiler needed) and
  the `smoke` matrix — 3 cells, 18 timed compilations — inside the existing
  GHC O2 job, uploading its results and raw receipts even on failure.
- The complete matrix is manual: `.github/workflows/compiler-shapes.yml`
  (`workflow_dispatch`) takes family, size, repeat and cohort inputs, runs the
  full default matrix by default, and always uploads plan, receipt, per-leg
  receipts, results and the human summary.
- There is no schedule and no automatic pass/fail on wall time. Three samples on a
  shared runner cannot resolve small differences, and a timing gate would reward
  noise.

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
