# A1 private-index experiment — not an accepted optimization

Published at the user's request for independent local testing. This branch does
**not** replace accepted P3. No <=3x result is claimed.

## What changed

The candidate combines A0 private whole-session reverse indexes with A1 direct
admission. A0 uses a paged-64 outer directory and immutable IntSet buckets behind
a sealed crate-file-owned entry. A1 validates/canonicalizes the same incoming
graph and initializes that representation directly, avoiding the old immutable
index build followed by import. The public Solver API is unchanged. All
independent graph/type/term/evidence/erasure checks remain. This is not inference
result caching or extra parallelism. `compileSpecFile` is the sole owner export.

The complete implementation, registrations and genuine regenerated locks are
included. The compiler has 123 registered shared modules. The benchmark is the
same separately frozen historical **14-module target**, not today's 15-module
crate. See [admission obligations](ADMISSION-PROOF.md) and
[finite control scope](../../../tools/performance/a1-private-index/CONTROL-SCOPE.md).

## Formal cloud measurements (2026-10-28)

Compiler subprocess wall seconds, in the predeclared execution order:

| Round | First | Second | Third |
|---|---|---|---|
| 1 | GHC 8.979014288 | P3 92.692393149 | A1 91.525555850 |
| 2 | A1 87.533069313 | GHC 8.282240412 | P3 89.958440899 |
| 3 | P3 89.911456895 | A1 87.533935668 | GHC 7.987367313 |

Medians: GHC **8.282240412 s**, P3 **89.958440899 s**, A1 **87.533935668 s**.
The whole A0+A1 candidate improves on P3 by **2.695139%**, remaining **10.568872x**
GHC. This is not an isolated admission measurement. The predeclared 5% improvement
minimum was not met: **performance acceptance rejected**, goal not met.
An earlier exploratory single pair suggested about 10.97%; it did not reproduce
and is excluded from these medians. No favorable resampling was used.

All six MLF legs inferred exactly 544 groups and reused zero, with identical
checked artifact bytes. Three GHC legs each compiled exactly 14 target modules,
reusing only the fixed 56 dependencies. Guards completed with empty owned-process
terminal states. [Exact samples](cloud-20261028/samples.json) include separate
CPU/RSS metrics and hashes identifying privately retained raw receipts;
[decision summary](cloud-20261028/result.json) records the unchanged outcome.
The original plan's SHA256 is
`261c661dbd522e0f07773817100094a53a0f3b191a47f22a0c16fcdd4da32099`.

Wall spans compiler subprocess launch to exit. Setup, copying, pre/post source
and artifact authentication are outside it. Child user/system CPU and maximum
individual-child RSS are separate metrics, not wall estimates or summed-tree
RSS. OS caches were not flushed: cold target means fresh target query/object
output, **not** cold OS page cache. GHC produces plain `-O2` objects; MLF produces
checked xMLF and query files. Disclose that endpoint asymmetry.

## Qualification and limits

The unchanged official build qualified this exact implementation using ordinary
GHC 9.14.1, O2, `-j1`, `-fpedantic-bottoms`, `-fno-state-hack`,
`-rtsopts=ignoreAll`: 123 inferred interfaces/syntax checks, 13 tools and builtin
verification. Independent controls passed 6 groups / 28 traces, 22 admission
cases, 9 parsed-file old/new byte comparisons and 4 sealed-interface negatives.
Actual changed inference (11) and crate (15) source sets compiled with all checks
and zero reuse. Three frontend modes, 86 provenance methods and five smoke checks
passed. Six maintained lock/locked-plan steps completed; four locks changed.

An earlier build was interrupted by executor loss, not user cancellation. The
first provenance run correctly rejected the old literal 121-module inventory;
the explicit two-module inventory amendment and entire suite rerun passed. Failed
attempts remain private evidence, not relabeled successes. The finite controls
are not a general semantic proof or native/self-hosting qualification.

The new portable wrapper's validation is separately stated in
[portable-validation.json](portable-validation.json). Its fresh-clone complete
preparation/campaign was **not** rerun end-to-end in the cloud. Do not confuse the
original campaign with a run of this newly packaged wrapper.

## Local reproduction

Use [runner instructions](../../../tools/performance/a1-private-index/README.md)
and this branch's `LOCAL-AGENT-PROMPT.md`. All frozen input and literal semantic
control sources are in Git; no private cloud path, binary or query-cache body is
required. Rebuild and compare all three implementations on the **same local host**.
Cross-host wall seconds are not an improvement comparison.

The runner supports an experimental native Apple Silicon macOS route in addition
to Linux. It uses the same platform-only builder adaptation for both producers.
Its 100 ms process-group RSS sampling can miss short peaks and does not enforce
a hard per-process address-space limit. The dyld/toolchain collector has platform
limitations and has not received independent platform qualification. See the
runner instructions for details; results remain experimental and do not accept
A1. Private local receipts and machine details are not published here.

## Evidence privacy

Raw execution records, machine identifiers, absolute cloud paths and detailed
host/toolchain metadata are deliberately **not published** in this branch. They
remain in the user's private Library and local recovery evidence. The full
historical archive is `mlf-crates-profile-20261028-v17.zip` (96,620,104 bytes),
SHA256 `13443786574bd4216b55c0105222e8d4f47b3bf5a25550f5bdcc8faf59d364e8`.
The archive, toolchains, binaries and target query-cache bodies are not in Git.
The published provenance JSON replaces only historical path metadata; literal
algorithm/test oracles are unchanged and independently hash-pinned.
