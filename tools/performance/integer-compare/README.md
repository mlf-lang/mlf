# Small-Integer comparison (S2b)

The GHC host now compares the payloads of two small `Integer` constructors
directly. Both operands retain their original left-to-right demand. Every
other constructor pair calls the unchanged arbitrary-precision comparison
through a private `NOINLINE` helper. There is no range conversion, primitive
ABI change, or change to language `Int` semantics in this candidate.

The important distinction from S2a is the out-of-line fallback. Inlining the
generic comparison expanded big-integer branches into each hot lookup. The
ordinary S2b `Bootstrap.IntMap` object instead contains two direct machine
comparisons and calls the fallback for the other cases. Recompiling that
module with a Core dump produced exactly the same `__text` bytes as the
ordinary producer (16,248 bytes). This observation concerns actual optimized
code, not a source-level assumption. The host uses the GHC 9.14.1 `Integer`
representation and needs requalification when that toolchain changes.

## Discovery and fixed confirmation

The performance baseline is S1, commit
`841d4337d4b54c08d5fc18619c973d084d4b5990`. The subsequent source-snapshot
metadata repair `1569fa84` does not change its production compiler code.
Both ordinary producers use GHC 9.14.1 `-O2`, with the same
`-fpedantic-bottoms -fno-state-hack` options. Shape executables use serial,
ordinary Clang `-O2` and the retained fixed dependencies.

One four-leg block per shape gives the following exploratory medians. Each
side has two fresh native builds per shape, with three executable checks per
build. All twelve builds pass fresh/raw-byte checks, and all thirty-six
executable checks pass. These small discovery samples are not confirmation.

| n = 512 shape | Fresh groups | Before, seconds | S2b, seconds | Time reduction |
|---|---:|---:|---:|---:|
| Independent top-level functions | 515 | 4.685 | 4.418 | 5.70% |
| Inferred dependency chain | 515 | 5.243 | 5.327 | -1.59% |
| Local functions in one group | 3 | 4.721 | 4.570 | 3.19% |

The chain's observed slowdown is in source-to-checked work; it cannot be
attributed to Clang. We do not claim that every input shape improved. Two
separate real-target discovery blocks improved by 5.065% and 5.399%, which
qualified S2b for complete correctness gates and independent confirmation.

The primary task is the retained **15-module, 711-fresh / 0-reused** compiler
workload, frozen at `d96f67726599fa4e21f236462886106434c8e417`. Its endpoint
is checked MLF/xMLF, whereas the shape endpoint is a native executable. No
new GHC-versus-MLF ratio or generated-program runtime improvement is claimed.

The confirmation protocol was frozen before its first sample: six four-leg
blocks, ordered `ABBA ABBA BAAB BAAB BAAB ABBA` (seed 2026103102). Each leg
starts with an empty target query directory. It compares ordered inference
groups and both checked artifacts as raw bytes against the retained
independent reference. Hashes establish identities, not semantic equality.
No discovery timings enter this cohort; no samples are excluded or replaced.

For each block, average its two adjacent-pair log wall ratios B/A. The primary
ratio is the exponential of the mean of the six block effects. SciPy 1.18.1
provides the ordinary two-sided t interval, transformed back to a reduction
interval. The frozen rule requires a point reduction of at least 2%, a
positive nominal 95% lower bound, and positive point reductions in both
execution directions. The window ends at six blocks, without extensions.

**Accepted:** wall time reduction is **4.929%**, with a nominal 95% interval
of **3.664% to 6.177%**. ABBA and BAAB reductions are 4.241% and 5.611%.
All 24 legs pass freshness, ordered-group, raw-byte, and resource gates.
Descriptive wall medians are 70.637 / 67.036 seconds; user CPU medians are
67.725 / 64.157 seconds; system CPU medians are 1.881 / 1.859 seconds.
The median ratio is not the paired primary estimand.

These are conditional results for fixed binaries, inputs and one M1 Max Mac
session. Six blocks do not establish statistical independence, portability,
or a 95% guarantee over the entire candidate search. Timing rows, source and
binary identities, protocol hashes and control receipts are in
[result.json](result.json).

## Correctness and retained oracles

`run_controls.py` links its O2 probe against the actual ordinary producer
objects, then separately builds an O0 host closure. Each mode checks:

- 173,889 comparisons: 139 values squared, through nine public/host routes;
  all small/positive-big/negative-big constructor pairs, machine boundaries,
  and values up to magnitude 2^1024 are represented.
- 90 first-error observations, 18 partial-application observations and 36
  controlled divergence observations.
- 556 raw-tree lookups, including inconsistent sizes/order, and 12 tree
  demand controls.

The separate `Oracle.hs` uses Prelude `Integer` comparisons and the literal
old lookup specification. It is compiled at O0 with rewrite rules disabled
and interface pragmas omitted; expected results do not call candidate
helpers. Probe wrappers preserve the actual producer's optimization. The
ordinary producer is authenticated before and after the controls.

All complete retained gates passed before confirmation: validation reuse;
P1/P2/P3 selectors, collections, fingerprints and prefix controls; A1 private
index and integration; F1 arithmetic/rules/Core; map balance/raw-tree demand;
query encoding; and the complete C4 gate including all nine file cases.
The C4 run contains 30 commands. P1/P2 source-mutation preflights pass under
both ordinary Python and `python -O`; all 22 source-manifest tests pass.

The old semantic fixtures and oracle manifests are unchanged. The P1, P2
and C4 admission paths recognize only the exact reviewed host source and
recover the complete prior source hash. This source inverse is an identity
check, not a semantic proof: the independent scalar oracle remains required.
The boundary and oracle duties are documented in the adjacent P1/P2 audits.

Resource protection is unchanged: 5 GiB disk floor, 3 GiB estimated available
memory, 5 GiB sampled process-tree RSS, and a 600-second real-target limit.
On macOS the existing protection samples RSS; it does not enforce a hard
address-space limit. Setup, validation and evidence copying are outside
timed child execution and are not run concurrently with the next leg.

## Candidate ledger and reproduction

- An earlier INLINE-only comparison experiment left ordinary lookup
  instructions unchanged and was rejected before formal measurement.
- S2a exposed the small constructor case but inlined the generic fallback.
  Its ordinary lookup text was 18,176 bytes; shape discovery observed a
  4.34% chain slowdown. It was stopped before full-target or formal sampling.
  S2a data is retained and excluded from S2b's results.
- An extra equality branch in `Map.balance` was not implemented: diagnostic
  counts showed only about 7% equal, nontrivial child sizes. A cross-state
  group-contract cache remains deferred pending a cost and invalidation case.

The local evidence root is `.mlf-build/integer-compare-20261031`; the rejected
S2a evidence is `.mlf-build/compiler-groups-20261031`. The frozen configuration,
plan, raw command receipts and stdout/stderr remain there. The existing
`process-spawn/compare.py` runner and `process-spawn/analyze.py` statistical
implementation are reused. Plot legend labels were generalized before the
confirmation freeze; the statistical implementation was not changed.

Run focused controls with a fresh output directory:

```sh
python3 -B tools/performance/integer-compare/run_controls.py \
  --producer .mlf-build/integer-compare-20261031/producer \
  --output .mlf-build/integer-compare-controls-new
```

An initial manifest-test launcher named a nonexistent test file and ran no
tests; its failed receipt is retained. The corrected command passed all 22
tests before confirmation. The complete release checker still encounters
the pre-existing macOS Bash 3.2 empty-array failure in the native CI partition
test; this report does not claim that full release command passed.
