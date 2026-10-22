# Shared native test artifacts and reviewed reductions

The working tree based on cb16a87fcceb9d0d4c1a37aaffb322beb809e780 passed all six native test groups on
2026-10-21. The actual serial, locked root test command exited 0; each group has
a complete report with matching source and tool hashes. The compiler is unchanged
byte for byte (4d7f426223f2c840fe8ab66b21a231f761d7def80f4c9ddfeb43a11dc7ce2d36); the manager is 3893bcf3a41e702efd7190f46bb96bd8fd39c0349aed4e116a7e1ee44799d2f1.
These changes are uncommitted and have not been published as a new release.
The [machine record](shared-test-artifacts.json) binds the 3203-file immutable
snapshot, source inventories, logs, reports, cache controls and preservation checks.

| Root group | Previous seconds | Current seconds | Observed change |
| --- | ---: | ---: | ---: |
| unit | 1322.1 | 880.8 | -33.4% |
| packages | 231.0 | 224.2 | -3.0% |
| self-host | 566.7 | 538.7 | -4.9% |
| parity | 536.4 | 518.5 | -3.3% |
| backends | 1358.3 | 1216.6 | -10.4% |
| port | 4222.8 | 3649.9 | -13.6% |
| Complete serial test command | 8239.1 | 7030.1 | -14.7% |

The current complete command took **117m 10.1s**;
port took **60m 49.9s**. Both drivers retain source-frontend LLVM identical to the baseline; their
artifacts are reused between backend and port groups. These group timers include target
builds and preparation as well as execution. Initial native tool building
(353.9 seconds) is outside the complete
test-command timer. A dedicated driver preflight also ran before the complete
command; all earlier compiler/test jobs and diagnostics had ended. This is one observation per revision
on the same 10-core M1 Max / 32 GiB host. The final run explicitly reused genuine
verified build artifacts from earlier work; it is not an empty-cache comparison.

The [individual execution timings](shared-test-execution-times.json) contain
all **2400 checked backend paths** across 575 backend rows and 25 port rows,
each on two backends and two layouts. There are 2364 measured child executions;
36 LLVM target-rejection paths stop before native execution and retain their
diagnostics with null timers. Each measured row retains its label, wall/CPU time,
peak RSS and actual status, including prescribed negative tests. These timers
exclude preparation, LLVM emission/linking and reference programs; unit assertions
are included in their group timer rather than instrumented individually.

Root libraries and nested test targets now use an explicit shared checked store.
The two source-frontend driver LLVM artifacts use that store with complete
source/tool identities, preserving the established interpreter performance. Each build directory retains its own reports and logs.
Content/tool identities, recursive dependency proofs, file checksums and per-key
process locks control reuse. Prelude and inference queries remain in the shared
store after deleting a producing build directory. Nested bootstrap libraries
report zero inferred groups. The full self-host group instead used its own new
store: 2097 bootstrap, 359 package-tool and 24 entry groups were inferred, with
zero reused groups or outer artifacts. It reproduced the complete LLVM and native
bytes. Candidate discovery uses a copied, source-checked producer build report,
so equal binaries elsewhere in the store cannot select the wrong LLVM input.

Port compiled and independently checked **25 targets
once**, with 25 preparation misses and
0 hits in the full run. Both layouts consumed those
same checked bytes. Twenty-two targets also match both old layouts exactly;
OptimizerQueries, Target and StateTypes differ only with the reviewed smaller
inputs. Every layout reran interpreter/LLVM execution, native emission and ABI
linking, IO/output checks, six independent reference programs and regenerated
inference-source equality. The matrix still has 25 rows per layout. The normal
port parent had a sampled peak RSS of 847.4
MiB; preparation had 7517.4 MiB. These
are two-second, per-process samples, not aggregate memory or exact peaks.
The port interpreter children account for 2183.3 seconds, and native
program execution for 27.9 seconds. The other
1438.7 seconds include preparation, references, target emission,
linking and supervision; they are not a pure compilation timer.

The warm control reused 25/25 checked targets. Corrupting a target
and then its check receipt each caused one genuine rebuild and 24 hits; the
original bytes and artifact stamp were restored by real compilation. These
controls deliberately failed at an invalid collection policy before matrix
execution, and their incomplete group reports are not qualification evidence.
Two concurrent builds in separate directories shared one genuine producer per
artifact key and ran equal binaries. A separate source edit was rejected by the
self-host producer guard before any next-stage build. The release-profile helper
passed 8 positive/negative controls using explicitly labeled
projections of the actual completed native report; it preserves both profiles'
preparation provenance and rejects conflicting target bytes or evidence.

The [coverage decisions](../tests/coverage-overlap.md#smaller-witnesses-and-exact-execution-sharing)
list all **17 implemented reductions**. Logical HM coverage remains 6712 cases,
represented by 6703 unit executions. Figure 12 keeps all 43 labels with 41 distinct
executions and all 36 controls. Parity retains all 7086 frozen rows, with 7075
primary acceptance/rejection compilations and 11 explicit aliases (nine HM, two
Figure 12). Its 80 CLI interpreter runs and 80 CLI LLVM source-generation paths
still compile and execute separately; 7075 is the primary case count, not a count
of every frontend invocation. No alias receives a fabricated output or exit file.
The 686 core checks, 58 harness methods, 18 resolver checks and 29 package
integration cases passed. Deep, GC, spill, stack, counter and benchmark regressions
remain; the audit's 18 unconfirmed candidates were not reduced.

Failed and performance-rejected intermediate runs remain recorded. R2's unannotated port entry grew
an expensive inference graph and exited on a stack guard; concrete entry/helper
types resolved it. R3 exposed ambiguous same-binary artifacts during self-host
discovery; its actual producer already matched the fresh build, and the producer
report selection fix passed both the dedicated diagnostic and the complete run.
R4 exposed a 1.6–2.4x interpreter regression with crate-linked drivers on
byte-identical targets. Source-frontend LLVM for both drivers exactly reproduces
the baseline, and its genuine artifacts are now shared. R4 completed naturally
and is excluded from performance acceptance; concurrent diagnostics during its
later execution are recorded. R5 emitted real LLVM but its nonempty check misread the capture helper return
value. R6 checks the actual file; a dedicated fault-injected preflight verified
both complete driver cache/build/link paths and baseline LLVM/native byte
equality before the final full command. Its deliberate entry failure is not
qualification evidence. No rejected run is relabeled as final validation.

All 2712 historical paths match this task's starting snapshot. Five older
provenance-portability edits already existed in commit 55267e0; the original
retirement manifest's other 2707 hashes also match. All 72 benchmark pins,
independent Snake, frozen parity archive and independent checker sources remain.
No GHC, Cabal or Python invocation was observed. No new Windows/Linux execution
or cross-runner cache restoration is claimed. Cold preparation still calls
compileFile once per distinct port fixture; reuse removes the second-layout and
warm-run repetition, not every cross-fixture frontend cost.
