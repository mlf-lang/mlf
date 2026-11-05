# Verified context window: real Foundation study

## Result and decision

This candidate reduces duplicate source-query storage while retaining strict
record/key/context/raw admission. It is an explicit space-versus-read-cost
trade-off, not a claim that the new representation is faster.

| Complete cold cache directory | CACHE-3 / A | Same-binary CACHE-1 / B |
| --- | ---: | ---: |
| File contents, including all non-reachable files | 49,387,843 B | 104,698,792 B |
| Pathname allocation, including directories and locks | 50,651,136 B | 105,771,008 B |
| Active query records | 504 | 504 |
| Shared context files | 83 | 0 |

The reductions are **52.8286% logical** and **52.1125% allocated**. This does not
subtract old experiment inputs, retained previous runs, build objects, final
outputs or evidence from the workspace. No query-cache GC is included.

| Actual stage | A seconds | B seconds |
| --- | ---: | ---: |
| Warm first | 17.326310 | 16.015133 |
| Warm second | 16.379245 | 16.377485 |
| One source value changed | 17.024431 | 15.564088 |
| Warm after change | 16.975775 | 16.326217 |

Warm order was **A1, B1, B2, A2**. The mean difference was **+0.656469 s /
+4.0532% for A**. The changed path was also slower. One sequence is not a
distribution or significance test. A cold read/write was 51.031454 s, but there
was no old-format cold-compiler arm, so it is not a cold speedup comparison.
Materialization took 19.980050 s outside the timed comparison.

Earlier protected candidates observed +14.0579% and +11.2094% warm differences.
The second of those studies failed later in a measurement helper when the
outer guard atomically replaced its own receipt; it is not a complete PASS.
The current bounded retry fix only recognizes that exact guard temporary path,
restarts the entire sample, permits at most three attempts and otherwise fails
closed. This completed run needed no retry in any of its 68 samples.
Different builds and runs are **not** a controlled single-variable attribution
of the observed improvement.

## What was actually exercised

* All 14 `mlf-foundation` modules (204,977 source bytes), 28 internal import edges
  and the single external source import `MLF.Primitive`.
* A historically pinned **504-group** ordered population, checked independently
  of the current reports. The SCC histogram was 501 singletons, one pair and two
  groups of four. The canonical population-projection SHA is recorded in JSON.
* The ordinary CLI implementation `runEntry Entry.main` linked into the
  unchanged [FoundationStudy.hs](FoundationStudy.hs) helper. This is a qualified
  wrapper executable identity, **not** a claim that its bytes equal `emlf`.
* A cold CACHE-3 compilation followed by lossless CACHE-1 materialization using
  that **same executable**. B is not a historical compiler and does not measure
  a before/after compiler revision.
* Four warm CLI invocations, an in-place same-length Version literal change
  `0.3.0` to `0.3.1`, one changed invocation per arm, and one changed-warm
  invocation per arm: ten study stages, of which nine use the real CLI.
* Counts: cold 504/0; original warm 0/504; change 1/503; changed-warm 0/504
  (inferred/reused). All 503 unaffected active records remained byte/stat
  identical; old records were preserved rather than deleted.
* Complete formal interface/object bytes matched across arms for each source
  state. Nine untimed final/Version checks linked the actual full dependency
  closure and independently evaluated the unique Version string. One additional
  builtin command makes ten untimed study auxiliaries.
* Before the study, two separate controls validated the retained golden closure:
  original Version succeeds, and deliberately expecting the changed Version
  must fail with the exact mismatch diagnostic. An arbitrary nonzero exit is
  not a successful negative control.
* Four helper compile/link commands, those two Version precontrols, and the
  study runner constitute seven outer commands.
* After the change, complete A/B cache directories occupied **49,607,972 /
  105,046,105 logical bytes** and **50,872,320 / 106,123,264 allocated bytes**.
  Each retains one old Version record; all orphan content is counted.

All raw and final results, source versions, captures and failed attempts were
retained locally. Large artifacts and machine-specific qualification receipts
are not embedded in this repository; their hashes identify the retained evidence
but are not a substitute for those bytes or independent public reproduction. Independent terminal review reread the complete current
154,654,077 cache-content bytes, all reconstructed keys/contexts, formal output
oracles, source/producer closed sets and command captures.

## Reproduction contract, not a one-click benchmark

[results-20261102.json](results-20261102.json) contains exact input and executable
identities, stage times/counts, full directory accounting and evidence hashes.
The Haskell helper is published byte-for-byte from the completed run.
The original [inner runner](reference-run-foundation.py) and
[qualification launcher](reference-qualification.py) are included byte-for-byte
as **fixed-environment reference source**, not portable entry points. Their
identities are recorded too.

The two reference Python files intentionally preserve their original absolute
bindings, draft-era comments and execution protocol. Their completed status comes
from the receipts, not from editing a historical source comment. Do not run them
as repository defaults. The local launchers are **not presented as portable
repository commands**:
they bind a specific authenticated producer, private resource root and historical
golden dependency closure. In particular, golden interfaces contain dependency
paths; copying them and silently rewriting paths or hashes is not reproduction.
This reference protocol intentionally does not replace those constraints with
an unchecked new launcher. The earlier portable
[64-group runner](../source-context-read-reuse/run_workload64.py) remains a
separate smaller fixture, not a substitute for this real package population.

To reproduce the Foundation protocol in another environment:

1. Authenticate a fresh producer built from the candidate's exact owners and
   source registry; keep original producer/source integrity checks before and
   after. Qualify the helper against those real objects, not copied stale ones.
2. Pin the 14 inputs and the independent ordered population; supply a genuinely
   qualified golden interface/object **dependency closure**. Execute both exact
   Version precontrols before measurement. Missing/unqualified goldens must fail.
3. Use one private fresh work root and the same absolute source paths for both
   arms. Preserve the ten-stage order, all nine CLI and ten auxiliary checks,
   the same-length sole source mutation, full raw/final semantics, and complete
   physical accounting including locks, directories, old records and staging.
4. Use a maintained external resource guard and serialize the experiment.
   The original outer limits were 1800 s, AS 6 GiB, tree RSS 5 GiB, whole-root
   logical **and** pathname allocation 8 GiB, free disk 4 GiB and available
   memory 3 GiB. Helper builds/precontrols were each 120 s, the inner study
   900 s, and each study command/auxiliary 300 s.
5. Reserve 448 MiB for all study categories plus 2 MiB terminal metadata before
   launch. The 448 MiB category checks are before/after samples, not a proved
   instantaneous hard limit. Do not delete intermediate output, shrink the
   population, retry selected timings, relax limits or credit hoped-for
   compression to make an execution pass.

The complete study categories ended at **282,235,763 logical /
284,954,624 allocated bytes**, before terminal receipts. The original guard
finished in **350.266407 s**, exit 0 with kernel no-child confirmation, peak
sampled tree RSS **491,651,072 B**, and peak sampled whole-root allocation
**8,399,691,776 B**. This includes experiment overhead and is not an A/B timing.

## Functional and deployment boundary

The current producer passed all 18 maintained build commands and builtin
regeneration. Strict Python contracts passed **232 checks** (70 Patricia,
34 A1, 7 validation-reuse and 5 full-compiler, each normal and `-O`).
The maintained runtime fixture passed **40 controls**, including prior legacy,
corruption, same-process invalidation, live-owner lock probes and directory
publication cases; the new eight-entry/MRU and actual raw/final checks preserve
the original semantic refusals.

The read window is per owned invocation, starts empty, and holds at most eight
verified entries—not eight bounded-size blobs. All per-record admission and
PreparedRaw validation remain. Cooperative process locking is a prerequisite;
exceptions/crashes, non-cooperating mutation, thread-level mutual exclusion,
Windows locking and retained heap bounds were not newly qualified.

The local source is the upstream `c5928b5b` / PR29 `a0330773` composition plus
the strictly layered publication, canonical-key-parts and read-window changes.
The prior published CI is not evidence for this later candidate. Exact-head
hosted CI and normal review remain separate merge gates. No PR was merged or
approved by this study.
