# Checked bootstrap memory reduction — 2026-10-19

The root `emlf` target now uses the existing checked separate-compilation path;
`mlfpkg` retains source linking. Three alternating, completely cold native build
pairs reduced median sampled process-tree RSS **67.283899%**, from
**9,994,472,504 to 3,269,801,760 bytes**. The maximum candidate observation was
**3,275,260,344 bytes**, well below the 5,500,000,000-byte measurement budget and
the requested 7 GB runner capacity. No compiler, runtime, verifier, or test
implementation was changed.

This is a memory improvement with a measured local time regression: median
complete build time increased **38.657561%**, from **332.38s to 460.87s** on the
32 GiB development host. It is not a measured hosted speedup. Avoiding pressure
on a smaller runner may improve its elapsed time, but that requires hosted
measurements; the historical hour-long job has no phase data proving its cause.

## Cold paired measurements

| Measurement | Baseline samples | Median | Candidate samples | Median |
| --- | --- | ---: | --- | ---: |
| Complete build, seconds | 324.25, 403.17, 332.38 | 332.38 | 459.68, 470.15, 460.87 | 460.87 |
| MLF calls, seconds | 285.14, 363.41, 292.30 | 292.30 | 377.63, 382.84, 377.30 | 377.63 |
| All Clang calls, seconds | 33.09, 33.97, 34.40 | 33.97 | 32.57, 37.70, 31.71 | 32.57 |
| Maximum command RSS, bytes | 9755951104, 10180476928, 9772531712 | 9772531712 | 2612903936, 2612887552, 2626158592 | 2612903936 |
| Sampled tree + sampler RSS, bytes | 9811596736, 10233460032, 9994472504 | 9994472504 | 3253872408, 3269801760, 3275260344 | 3269801760 |

Complete wall-time ranges are 324.25–403.17s / 459.68–470.15s, with MAD
8.13s / 1.19s. Sampled aggregate RSS ranges are 9,811,596,736–10,233,460,032 /
3,253,872,408–3,275,260,344 bytes, with MAD 182,875,768 / 5,458,584 bytes.
Per-command RSS medians decreased 73.262774%. GB means decimal bytes; the
candidate aggregate median is approximately 3.05 GiB. Every sample, including
the slower second baseline, is retained in [summary.json](pairs/summary.json).

Pairs ran baseline/candidate, candidate/baseline, baseline/candidate, without
concurrent builds or tests. Both variants used the same published v0.1.1 native
compiler and package manager, runtime defaults (`GC_FREE_SPACE_DIVISOR=1`,
initial/max heap environment variables unset), compiler profile, and Clang `-O2`
flags. Each builds both native tools into a new directory, including fresh
runtime objects, LLVM compilation, and linking. Every native report is complete
and contains **zero cache hits**. The compiler/module/runtime C sources are
byte-identical; only the root manifest and corresponding native lock differ.
No warm-build shortcut or excluded compilation work produced this result.

Each sample keeps its readable build report, timing summary, host/context, and
RSS CSV. `raw-commands.tar.gz` losslessly retains full argv, raw time output,
native stdout/stderr, cache manifests, wrappers, and events. Its adjacent
`contents.json` hashes every member; every archive was extracted and verified
before redundant copied files were removed. `guard-tests/timing.tar.gz` retains
the resource-gate input reports. `SHA256SUMS` covers the final archive files.

The sampler records `/bin/ps` RSS for the helper and its live descendants every
500 ms, plus the sampler's RSS. Summing RSS can count shared pages repeatedly;
this is a conservative sampled aggregate, not a continuously observed peak or
a measurement of other runner services. Raw `*-rss.csv` and observation JSONs
are retained alongside each sample. `/usr/bin/time -lp` supplies complementary
command high-water RSS, faults, CPU times, exit statuses, and raw output.
The package-manager timing row includes its children: **do not add it to child
totals**, or sum high-water RSS from different times. Local measurements support
substantial headroom for a 7 GB runner; actual hosted resource use remains a
separate verification.

## Where the time and memory go

All native child compiler and Clang calls are serial. MLF compiler RSS, rather
than Clang RSS, dominates the monolithic baseline. Separate inference releases
one module's graph before starting the next process, instead of retaining the
whole compiler's inference graph. The final link checks typed objects and emits
one LLVM module; Clang still compiles and links the complete program normally.

| Invocation scope | Baseline median seconds | Candidate median seconds |
| --- | ---: | ---: |
| Module inference, checking, interface/object writing | — | 169.47 |
| Object reading, boundary checking, linked xMLF check, optimization, LLVM emission | — | 171.36 |
| Whole-source MLF through LLVM (both tools / only mlfpkg) | 292.30 | 36.80 |
| Fresh runtime C compilation | 0.95 | 0.72 |
| Clang LLVM compilation and linking | 32.94 | 31.93 |
| Orchestration and timing-wrapper remainder | 5.79 | 49.61 |

There are 2 baseline MLF invocations and 48 candidate invocations (46 modules,
1 checked link, and the unchanged source-linked package manager). More process
starts, interface/object IO and repeated boundary verification cost time; the
aggregate observations do not isolate an exact causal share for each. Stage
medians need not sum to the enclosing median. [phase-breakdown.json](pairs/phase-breakdown.json)
records every sample's command scopes. These are ordinary executions, without
the diagnostic driver's extra phase forcing or graph checks.

## Checks and output identity

Each module still calls `Compiler.finishCompilation`, independently checks xMLF,
compares inferred types, and checks source erasure. Separate compilation also
checks its closed object payload, dependency-interface fingerprints, imported
schemes, datatype declarations, exports, object checksums, and module identities.
The linker rechecks objects and boundaries, grafts identities, and obtains its
opaque `CheckedTerm` through `Checked.check` on the complete linked term. Checked
witness constructors and module exports are untouched. See
[`Bootstrap.Separate`](../../../../bootstrap/Bootstrap/Separate.emlf) and
[`Compiler.finishCompilation`](../../../../bootstrap/Bootstrap/Compiler.emlf).

All three repetitions of each variant reproduce identical LLVM and native
executables. The candidate package manager is byte-identical to the seed;
its LLVM is also identical between strategies. Compiler bootstrap LLVM differs
between source linking and separate linking: module binding order and freshened
identities change generated names. Both have 18,601 LLVM functions, 7,104 globals,
and 755,100 lines; the constant string payloads are the same. This does not by
itself prove semantic equivalence, nor is numeric-ID normalization sufficient
to make the modules equal. Both original modules are retained in `llvm/`, with
structural observations in [comparison.json](llvm/comparison.json).
All six resulting compilers emit identical n-body validation LLVM.

All six native groups passed through the native package manager on the same
candidate and identical 426-file test-source snapshot. The strict
[verification audit](verification/audit.json) checks every native completion
flag, compiler/source identity, primary-log hash, and actual matrix row ledger.
It also verifies that the current checkout's test sources still match the
frozen inputs. The surrounding shell's progress labels are not a verification
oracle: the initial loop did not stop on a group failure, so this independent
audit was required before subsequent comparisons and measurements could run.

| Native group | Verified coverage |
| --- | --- |
| unit | 654 checks; independent Algorithm W over 6,712 closed terms; Figure 12 43/43 plus 36 supplementary checks; 57 harness tests |
| packages | 18 resolver tests and 19 integration cases |
| self-host | Fresh build, every cache decision a miss, identical compiler LLVM and binary fixed point |
| parity | 7,086 cases: 3,202 accepted, 3,884 rejected; 160 runtime executions; independent target/type oracle |
| backends | 552 rows × interpreter/LLVM in each of standard and compact-GC layouts; 500 shared fixtures |
| port | 26 rows × interpreter/LLVM in each layout, including independent reference, type/erasure and output checks |

All nine workloads emit **byte-identical LLVM in both layouts**, comparing the
stock baseline compiler with the candidate: [all 18 pairs](llvm/generated-equality.json).
Full generated LLVM, stderr and command/source hashes are retained in
`llvm/generated-workloads.tar.gz` and its member inventory. `verification/`
contains the native reports and primary logs, plus lossless diagnostic archives
with per-member hashes. Every diagnostic archive was extracted and checked.
`final-toolchain-audit.json` confirms the measured tools/libraries and selected
Clang/GC installations remained unchanged through correctness verification.
These are correctness and output-identity checks, not a new timed runtime gate.

## Resource gate and old target tags

The CI timing helper now rejects a measured command high-water above
`MLF_BOOTSTRAP_MAX_RSS_BYTES=5500000000` **before** exporting candidate paths to
subsequent steps. It retains raw evidence on failure. This per-command guard
is not an aggregate process-tree limit or a hard heap cap; the paired driver
also checks the sampled aggregate against 5.5 GB. A diagnostic value of `0`
disables the resource gate; explicit caller settings are respected.
`guard-tests/` retains accepted 5.5 GB, rejected 1-byte (exit 78), and diagnostic
zero-budget cases. The checks use retained real timing reports; compiler checks
are never disabled.

Separate builds keep divisor `1`. The workflow helper may build immutable old
release tags whose manifest still requests monolithic source linking; for those
it defaults to divisor `4` for more frequent collection and exports that policy
to later CI stages. It does not set a maximum heap size or change runtime source.
The seed-pair diagnostic driver explicitly defaults to divisor `1` and budget
`0`, preserving its historical conditions and retaining over-budget baselines.

All exploratory screens are retained in `screen/`, rather than selecting only
the favorable result. These five GC screens measure **only compiler source to
LLVM**, not the complete cold build boundary above:

| Screen | Wall seconds | Command RSS bytes | Result |
| --- | ---: | ---: | --- |
| Divisor 2, default initial heap | 295.73 | 6676086784 | Insufficient headroom |
| Divisor 3, default initial heap | 321.94 | 5663506432 | Above 5.5 GB budget |
| Divisor 4, default initial heap | 363.60 | 5125832704 | Legacy fallback candidate |
| Divisor 3, 64 MiB initial heap | 366.82 | 5589729280 | Above budget; slower |
| Divisor 4, 64 MiB initial heap | 387.91 | 5217779712 | No improvement |

Every screen emits the same baseline LLVM hash. An additional exploratory
**both-tools-separate** full cold build took 476.32s at a 2,523,725,824-byte
maximum command RSS; its patch and native reports are retained too. It was not
selected: the final candidate leaves the package manager source-linked, whose
memory already fits, and preserves its exact executable identity. Single screens
are exploratory observations, not paired evidence of a speedup.

A subsequent **full cold legacy source build**, with the caller GC policy unset,
verified automatic divisor `4`, the default 5.5 GB gate, and successful policy
export. It took **447.12s**, peaked at **5,152,686,080 bytes per command**, had no
cache hits, and reproduced both baseline LLVM modules and release binaries
exactly. [Legacy evidence](legacy/audit.json) includes raw commands and timing.
This is a single compatibility validation, not an aggregate-RSS measurement or
a paired speed comparison. [Resource-gate cases](guard-tests/cases.json) also
record explicit exit statuses for accepted 5.5 GB, rejected 1-byte (78), and
diagnostic zero-budget settings.

## Exact inputs and reproduction

Baseline source is clean commit `39daab5af1051160ed48f229552e8fcbaf709acb`.
Candidate is that commit plus [candidate.patch](candidate.patch), containing
only the native manifest/lock change. `pairs/context.json` contains hashes of
all tracked frozen files, both source snapshots and patches, selected seed
metadata, measured driver/tool hashes, order, and GC policy. `context.json`
retains the initial source/seed inventory; `toolchain-audit.json` confirms the
Clang, GMP, pkg-config, and static GC identities remained unchanged.

| Artifact | SHA-256 |
| --- | --- |
| Seed / baseline compiler | `36816b701ad373d28e16f4dbeba0d3548921cbf36e4b4ca0816b1b53d558e9b6` |
| Candidate compiler | `d207c9a8988f9163c3ded6f9eca13f10452bfcf6e7ac93ea42a73924822b0bc6` |
| Seed / both package managers | `3ad5f14b10258a54ab144e73cbcb40d4c286d9eae5dcc6278adab6c5e8ff4f68` |
| Baseline compiler LLVM | `40d04cfb94852792ca9413f4bad06435b1936ccc0154bed5069c1e1f53b6270d` |
| Candidate compiler LLVM | `6681b744a867617156f6e8caf4a91c3a1c6f28ecd0d51a3f36f98051f9e701dd` |
| Both package-manager LLVM | `4d690c2c80397b00673f2f218a3ce87cbbe052240d70f72d095540cdf6b5e015` |

Host: Apple M1 Max, 32 GiB, macOS 26.6.2; Clang 23.1.3, GMP 6.3.0,
pkgconf 3.0.7, BDWGC 8.2.12. Time resolution is 0.01s. Tool hashes and host
snapshots are retained, rather than inferred from version strings. The candidate
is a stock native module build, distinct from the older PGO performance binary.
No new nine-workload runtime/performance gate is claimed by this bootstrap report.

From an implementation checkout, create two frozen worktrees and apply the
archived manifest patch only to the candidate. Download and verify the published
v0.1.1 native package first. Then run the current driver and its sibling release
scripts (the exact measured versions are also archived in `drivers/`):

```sh
git worktree add --detach /absolute/path/baseline 39daab5af1051160ed48f229552e8fcbaf709acb
git worktree add --detach /absolute/path/candidate 39daab5af1051160ed48f229552e8fcbaf709acb
git -C /absolute/path/candidate apply /absolute/path/to/this/report/candidate.patch
export PATH="/absolute/path/to/llvm/bin:$PATH"
export MLF_GC_PREFIX=/absolute/path/to/bdw-gc
node tools/profile/bootstrap-memory-pairs.cjs \
  /absolute/path/to/mlf-0.1.1-macos-arm64 \
  /absolute/path/baseline /absolute/path/candidate \
  /absolute/path/fresh-memory-pairs
```

Build and all checks execute through the native MLF compiler/package manager;
Node records identities, samples RSS and audits reports. No GHC, Cabal, Python,
or subagents are involved. Run native verification serially from the candidate:

```sh
set -eu
compiler=/absolute/path/fresh-memory-pairs/3-candidate/bin/emlf
manager=/absolute/path/fresh-memory-pairs/3-candidate/bin/mlfpkg
cd /absolute/path/candidate
for group in unit packages self-host parity backends port; do
  "$manager" compiler-test "$group" --compiler "$compiler" \
    --build-dir "/absolute/path/fresh-verification/$group"
done
```
