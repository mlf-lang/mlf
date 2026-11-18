# Inferred chain: remaining growth and allocation experiments

This follow-up retains no additional compiler change. The unsigned monomorphic
`inferred_chain` shape remains open. The preceding fixed GHC comparison in
[the retained study](compiler-inferred-chain-2026-11-17.md) remains authoritative:
OLS slopes are 0.164411 ms/function for MLF and 0.158357 for GHC; the MLF
endpoint slope and the paired OLS interval also fail acceptance. No unchanged-source
GHC confirmation was rerun and no acceptance commit or push was made.

Evidence is under `.mlf-build/inferred-chain-remaining-growth-20261117`.
The preceding final audit (300 source pins and 496 evidence pins) and the
current producer were authenticated before the work and again at qualification.

## Fresh profile

Six profiling compiles (two each at N=0/256/1024) rebuild the current compiler
from empty profiling objects. Query phase timers are disabled; compiler flags
and F4 are preserved. Every interface, object and LLVM byte matches the
preceding ordinary cohort. Profile ticks/allocation are attribution evidence,
not acceptance timings. N=1024 minus N=0 shows:

| Owner, including helper work | Additional ms | Additional allocated MB |
| --- | ---: | ---: |
| OpenFragment.makePackage | 16.00 | 75.129 |
| QueryGraph.encodeHashed | 11.40 | 57.640 |
| CrateGraph.preparedValueCached | 5.95 | 21.758 |
| CrateGraph.preparedSyntax | 3.25 | 18.108 |

The whole profile also attributes 24.7 ms of additional ticks to GC. Total
allocation, sampled maximum live heap and sampled process RSS are different
measures; lowering one does not establish that the others improve.

## Isolated alternatives

- `packed-plan`: combine adjacent small entry fields and pairs of references,
  and process a current planner child without allocating an `EncodeOne` task.
- `framed-prepared`: reuse `CrateQuery.renderKey` for Prepared original/lowered
  member strings instead of repeatedly concatenating enclosing strings.
- `stream-packed`: separate pure field/byte generation from the per-byte IO loop.
  This replaces nested field continuations with a lazy byte stream.

Each prototype starts from the same authenticated compiler, independently of
other prototypes. Each screen uses one warmup plus six alternating measured
pairs at N=0/256/1024, fresh query/output directories and unchanged dependencies.
The boundary below is compiler-plus-Clang subprocess sum. It is not the formal
whole-worker boundary, and separate screens are not pooled.

| Candidate | N=0 before / after, s | N=256 before / after, s | N=1024 before / after, s |
| --- | ---: | ---: | ---: |
| packed-plan | 0.271684 / 0.269548 | 0.310894 / 0.307202 | 0.443887 / 0.442101 |
| framed-prepared | 0.259633 / 0.257755 | 0.297685 / 0.299612 | 0.428567 / 0.428551 |
| stream-packed | 0.258169 / 0.259633 | 0.303368 / 0.298104 | 0.421011 / 0.424766 |

Three separate alternating RTS pairs at N=0/1024 preserve `-s -F4`. At N=1024:

| Candidate | Allocated MB before / after | Max live MB before / after | Process RSS MB before / after |
| --- | ---: | ---: | ---: |
| packed-plan | 862.887 / 847.090 | 11.233 / 11.157 | 61.456 / 62.636 |
| framed-prepared | 862.889 / 878.001 | 11.233 / 11.256 | 61.456 / 61.538 |
| stream-packed | 862.888 / 916.586 | 11.233 / 12.543 | 61.456 / 64.700 |

`packed-plan` reduces cumulative allocation by 15,796,480 bytes (1.83%),
but its compiler-only median is 0.305590 -> 0.306040 seconds; the smaller
combined time does not establish a compiler speedup. Sampled live heap barely
changes and RSS rises. This is insufficient benefit for the extra special cases.
`framed-prepared` increases allocation by 15,111,616 bytes; `stream-packed`
increases it by 53,698,072 bytes and also increases live heap/RSS. Neither
establishes a useful large-case speed gain. All remain private experiments.

## Validation and scope

The two writer candidates each pass 5,104 offset/width/entry cases against
an unchanged generic writer, 186 full-wire/admission cases against a separate
original codec module, 10,920 existing field states, 65,280 existing byte states,
and the maintained artifact constructor/admission/base64/source/bounds controls.
The framing candidate passes the unchanged Prepared fixture (9,904 checks,
53 syntax variants), declaration cache controls and independent inferred-template
controls. The Prepared fixture uses the ordinary encoder as its exact oracle.

Across all screens: 126 successful compiles and 378 correct native outputs.
The 36 separate memory compiles and all screens preserve exact preceding
interface, object and LLVM bytes. The first writer test harness failed to
compile because its pattern used Prelude Either rather than Bootstrap.Types.Either;
the failed receipt and fixture are preserved, and the corrected fixture passes.
This is not counted as a passing first attempt or a compiler regression.

No compiler, builtin, lock, ABI or wire-format change is introduced by this
follow-up. Existing uncommitted work from the preceding inferred-chain study
is preserved. Native compiler self-bootstrap, installed CLI and previously
documented native-codec/QuerySnapshotProbe gaps remain outside qualification.
Finite-range fitted exponents are not an asymptotic complexity proof.

Next work remains on this shape and its object/index construction costs.
Another formal GHC cohort requires a justified retained change; these rejected
experiments do not authorize retrying the unchanged maintained compiler.
