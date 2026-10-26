# Compiler experiment results — 2026-10-26

These are **historical research measurements**, not qualification of a newly
packaged checkout. The ordinary compiler/default Prelude policy remains unchanged.
The opt-in installed-Prelude experiment uses whole-root inference and full checking;
it does not cache user programs or replace benchmark algorithms.

## Application compilation

GHC 9.14.1-hosted producers, identical restored toolchain/environment; Clang 19.1.7.
C retains the repository's `-O3` flags; both MLF routes use `-O2
-Wno-override-module`. Each application compilation uses a fresh directory and
fresh runtime object. Required descriptor authentication, artifact read/hash/pack,
checking/inference, LLVM emission and native compile/link are included.
One-time Prelude installation and compiler/harness construction are separate.

| Frozen workload | Ordinary MLF (s) | Installed Prelude (s) | C (s) | Installed / C |
|---|---:|---:|---:|---:|
| n-body | 21.453278 | 3.016566 | 0.113859 | 26.49× |
| binary-trees | 20.733679 | 1.939988 | 0.085687 | 22.64× |
| pidigits | 20.090593 | 1.786051 | 0.097059 | 18.40× |

These are medians of **three fixed measured rounds**, after one excluded warmup
per label/workload. Corresponding paired geometric-mean ordinary/installed
speedups were 7.05×, 10.47× and 11.05×. This small descriptive experiment supplies
no confidence interval. **None meets the compilation target of ≤3× C.** No
runtime-speed benchmark was performed; the ≤2× C runtime target is not established.
Do not combine these figures with older machines, native-hosted producers, or
other fresh-runtime versus installed-runtime scopes.

The frontend and fresh runtime compilation overlap, followed by LLVM/link.
Installed-route median frontend/runtime/LLVM-link seconds were respectively:
`1.952/1.335/1.068`, `1.342/1.385/0.537`, and `1.193/1.283/0.500`.
These medians are **not additive**. Subtracting the runtime median does not produce
a measured prebuilt-runtime result.

## Fixed correctness and measurement protocol

Use unchanged sources, fixtures, algorithms and flags in `benchmarks/manifest.json`
and each workload's `PROVENANCE.md`. First build C/ordinary/installed once per
workload and run existing checks: n-body `[0,1,1000]`, binary-trees `[0,7,10]`,
pidigits `[1,10,27,30]`. All nine builds and 30 executions passed. Then use new
build directories for warmup order C/ordinary/installed and three measured orders:
C/ordinary/installed, ordinary/installed/C, installed/C/ordinary. After every
build, run that exact executable at the pinned fixture input outside compile timing.
The completed experiment contains **45 builds and 66 successful oracle executions**.
Use existing independent oracles; preserve floating tolerance and integer whitespace
rules rather than inventing a stricter C formatting requirement.

n-body and pidigits produced byte-identical ordinary/installed LLVM and native
binaries. Binary-trees did not: installed declarations precede user data and change
constructor numbers. The first byte-exact cohort stopped and remains **failed**.
An independent complete typed constructor identity/layout/use-point audit found
only the consistent tag bijection, with no other LLVM changes. A separate three-input
native diagnostic passed. A new, explicitly versioned cohort allowed **only that
frozen pair of raw artifact hashes**, not arbitrary tag alignment; all new oracles
ran again. No failed-cohort or diagnostic timing samples were pooled.

## Provenance and reproduction limits

The compact companion evidence manifest records the producer source commit, tool versions, all three
rounds, policy and audit digests. Large scratch receipts, toolchains, snapshots,
binaries and generated LLVM are deliberately not vendored. Those hashes identify
retained research evidence; they are not a portable runnable harness by themselves.
For a new checkout, follow
[`tools/experimental/installed-prelude/README.md`](../tools/experimental/installed-prelude/README.md)
for authenticated fresh producer/build/install and smoke tests, then apply the
fixed protocol above with fresh provenance. Its LLVM-only output mode rejects
fallback; this is experimental admission, not a change to ordinary fallback semantics.

Historical native compiler A/B fixed-point qualification did **not** complete
(the stored attempt failed at native-B). These results are GHC-hosted compiler
measurements, not a successful self-hosted/native compiler release claim. Successful
native *application* tests do not repair that distinct failure. Before publishing
new final-tree qualification, record fresh Hello/Unicode O0/O2 and n-body1000 O2
native gates against the exact final source/build; older scratch passes are not
substitutes. No default switch or general principal-type equivalence is claimed.
