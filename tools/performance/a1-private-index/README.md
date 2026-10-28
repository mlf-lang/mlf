# A1 private-index admission: experimental reproduction

**Experimental, not an accepted optimization.** The retained cloud three-round
screen improved the P3 median by about **2.695%**, below its predeclared 5% screen,
and remained about **10.57× GHC**, not the requested ≤3× goal. Reproduce on one
machine; do not compare your wall times with that cloud host. This runner never
marks an optimization accepted, including when a new local screen passes.

## Supported environment

The Linux route uses the maintained collector with ordinary GHC 9.14.1. The
experimental native macOS route was exercised on Apple Silicon with Xcode
Command Line Tools and GHC 9.14.1. It applies the same platform-only builder
patch to both fixed producer snapshots and records the original and patched
hashes. Its Mach-O/dyld collector has platform-specific path and resolution
assumptions and is not an independently certified toolchain closure. Other macOS
installations may fail closed and require additional platform work.

On macOS, 5 GiB process-group RSS is sampled approximately every 100 ms and
exceeding it triggers termination. Short peaks may be missed; there is **no hard
6 GiB per-process address-space limit**. Host available memory is estimated as
`vm_stat` free + inactive + speculative pages, not Linux `MemAvailable`.
CPU affinity is not enforced, and `ru_maxrss` is recorded in bytes. These are
macOS experimental results, not Linux qualification. The collector and sampling
limits should be reviewed before relying on the measurements.

Python **3.11+**, Git, ordinary GHC **9.14.1** and a C toolchain are required.
The builder checks the installed `base`, `array`, `bytestring`, `text`,
`containers` and `directory` closure. Use a fresh output directory outside the
repository. Linux guards default to 5 GiB process-group RSS, 6 GiB per-process
address space, 3 GiB available memory, 4 GiB free disk, 16 GiB work-tree size,
and six hours per command. macOS uses the sampling and memory estimate described
above instead of the Linux RSS/address-space mechanisms. Every compiler command
is serial; do not run competing builds or benchmarks while measuring. The runner
does not create a VM, install tools, push, or run the cancelled native bootstrap.

## Run it

Use a checkout containing this runner and make both historical refs available
locally (for example, `git fetch --no-tags origin 875e483de49655030c4ffba1995b60610a50273a 5a89143ecbcaaef152a7e88331583660192e106d`).
No dirty working implementation is silently used: the runner creates exact
read-only-input-style source snapshots from the specified Git commits and
checks all published implementation pins. `--source-checkout` identifies the
repository holding those commits, not an alternate source overlay.

This fixed-ref experiment is **not the integrated-HEAD correctness gate**.
To check the current checkout, build its maintained O2 producer and run
`check_integrated.py --producer /absolute/producer --output /absolute/fresh/checks`.
The latter prepares one tiny fresh builtin fixture and runs the independent
finite A1 controls; it does not benchmark, select a historical ref, or establish
a speedup. The P1–P3 controls have their own current-producer runner in
`../crate-optimizations/`.

```sh
python3 -B tools/performance/a1-private-index/reproduce.py \
  --source-checkout "$PWD" \
  --base-ref 875e483de49655030c4ffba1995b60610a50273a \
  --candidate-ref 5a89143ecbcaaef152a7e88331583660192e106d \
  --work-dir /absolute/fresh/a1-reproduction \
  --ghc /absolute/path/to/ghc-9.14.1 \
  --cc /absolute/path/to/cc \
  --prepare-only
```

The script prints the completed preparation receipt path and SHA-256. Review
its results, then run the fixed campaign using that exact prepared directory:

```sh
python3 -B tools/performance/a1-private-index/reproduce.py \
  --work-dir /absolute/fresh/a1-reproduction \
  --run-campaign \
  --preparation-receipt /absolute/fresh/a1-reproduction/preparation.json \
  --preparation-sha256 THE_PRINTED_SHA256
```

Omit `--prepare-only` in the first command to perform both phases automatically.
`--run-campaign` requires a complete preparation receipt. It reauthenticates the
actual producers, inputs, controls and dependency files before and after every
leg. Do not move the work tree or alter scripts, fixtures, source snapshots,
compiler installations or prepared files between phases. There is no silent
resume, output replacement, target-cache reuse or favorable resampling. A failed
run retains its partial receipt/logs and stops. Diagnose it before starting a
separately named fresh experiment.

`--rss-mib`, `--address-space-mib`, `--host-available-mib`, `--disk-free-mib`,
`--max-work-gib` and `--command-timeout` override guard limits at preparation;
the preparation receipt fixes them for the later campaign. On macOS,
`--address-space-mib` is not enforced, as described above. They do not change
compiler options. The process-group guard covers ordinary inherited children;
it is not a security sandbox for deliberately escaped processes.

## Exactly what preparation does

1. Resolve the requested local Git refs and extract fresh separate P3/A1 source
   snapshots. Verify the fixed implementation source/config/host pins and the
   maintained package/shared-source/Cabal inventory/direct-import checks.
2. On Linux run each snapshot's unaltered `tools/shared/build.py`; on macOS
   apply and record the same platform builder patch to both snapshots. Build with
   fixed `-O2` and the same GHC/CC. The builder retains its `-j1`, demand-preserving flags,
   exhaustive/inferred-interface auditing, exact source resolution,
   `-rtsopts=ignoreAll`, checked builtin verification and actual receipt inputs.
   Authenticate both complete producers with their unchanged maintained helper;
   their actual toolchain and installed dependency records must match.
3. Use authenticated P3 to compile the **frozen 54 provider source modules** in
   their six-package dependency order at one common local output location. The
   first foundation specification supplies a fresh builtin prefix; the normal
   `withPrelude`/`ensureBuiltin` path generates and checks that pair. There is no
   invented builtin-export CLI. The builtin pair must match the published,
   path-independent bytes. Each provider query report must show zero reuse.
4. Compile the literal independent `ValidateDependencies.hs` against copied,
   authenticated P3 implementation objects. Only its `Main` may compile. Reload
   and check all **seven** actual dependency objects, then require the independent
   malformed-object rejection. Provider bytes remain pinned and immutable.
5. Build the exact **70-module plain-GHC -O2 no-link closure** from the frozen
   fixture roots, with actual module/path resolution checked. Copy only the
   **56 non-target** `.hi`/`.o` pairs into the reusable directory. The initial
   14 target objects are explicitly excluded from reuse.
6. Run `run_controls.py` against the authentic registered A1 producer, including
   literal solver/session/admission controls, nine file cases comparing the
   unchanged public path with A1, and four privacy/rejection controls. Require
   its full input/output pins and successful inventory. P3 does not expose A1's
   private owner and is not falsely claimed to run those private controls.

Preparation performs **no frozen-target MLF inference**. Its GHC closure setup
is untimed and target objects from that setup are never reused. No native74 or
other native compiler bootstrap is launched.

## Fixed measurement contract

The nine legs are frozen before the first measurement:

| Round | Order |
|---|---|
| 1 | GHC → P3 → A1 |
| 2 | A1 → GHC → P3 |
| 3 | P3 → A1 → GHC |

- The target is the original **14 exact frozen modules**, not today's 15-module
  `mlf-crates` implementation. Target/provider fixtures and the actual 70-module
  GHC closure are hash-pinned by `fixtures/manifest.json`.
- GHC uses plain `-O2 --make -no-link -j1`. Every timed leg starts from a fresh
  object directory containing only the 56 checked reusable dependency pairs;
  it must compile exactly the 14 target modules and leave all dependency bytes
  unchanged. No producer-only demand flags are silently added to the GHC target
  comparison endpoint.
- Every P3/A1 leg starts with an **absent** query directory and must perform
  **544 fresh / 0 reused** groups, all `cached:false`. It checks the fixed ordered
  544 `{id,members}` oracle and actual newly written query-file count. The raw
  query report is retained; compiler-dependent `query_key` values are not used
  as an artifact equality oracle.
- Both sides use the **same local dependency paths**. Each `.mlfci` and `.mlfco`
  must be byte-for-byte equal to this run's first P3 output, including subsequent
  P3 legs. Cloud artifact hashes are historical context only: dependency paths
  are embedded in metadata. **No output normalization or path rewriting occurs.**
- Compiler wall is measured from process launch through exact-child `wait4`
  completion. Source copying, dependency preparation, producer authentication,
  object copying, input verification and postchecks are outside that boundary.
  CPU, maximum individual-child RSS, sampled aggregate process-group RSS and
  context switches are reported separately. Parent guard work is not called
  compiler CPU. OS caches are **not** flushed.
- The endpoints remain intentionally different: GHC produces ordinary objects
  without linking; MLF performs the complete checked xMLF crate path. Ratios
  apply only to this explicit frozen slice, not general runtime performance.

## Outputs and limits of the claim

`preparation.json` binds the sources, commits, producers, fixtures, safety limits,
controls and dependencies. Each preparation command has stdout, stderr and a
command receipt. `campaign/receipt.json` retains the predeclared order, every
leg's compiler wall/CPU/RSS, raw output hashes, checks, medians and same-machine
ratios. Per-leg directories retain the original checked artifacts, query reports,
specifications and GHC outputs. A failure is incomplete evidence, not a sample
that may be discarded to improve the median.

This is a **local frozen-performance reproduction with mandatory finite
controls**, not a complete local reexecution of compiler qualification. The
published cloud record separately reports registered-source 11+15 compilation,
frontend 86, smoke and six authentic lock/locked-plan checks. This runner does
not claim to rerun those campaigns, every platform, LLVM/native parity, or a
self-hosting fixed point. Additional local qualification should use the
maintained commands explicitly and report its own receipts; never restart the
cancelled native bootstrap as an implicit step.

The experiment remains unaccepted. Report an improvement below 5%, a ratio above
3×, failed checks, environment limitations and unchanged/negative results
plainly. Never substitute old cloud timings for a local baseline or describe a
Linux guest measurement as native macOS performance.
