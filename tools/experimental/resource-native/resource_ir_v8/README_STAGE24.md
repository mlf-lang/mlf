# Stage24: closed scalar captures in a generalized local let

Historical Stage24 qualification follows. [Stage25](README_STAGE25.md) extends the
generic primitive boundary and replaces the active suite's two old refusal slots;
the original inputs and results below remain historical evidence.

**Finite local qualification complete.** The two genuine Int/Bool source cases
pass the native matrix, sanitizers and final fresh-source suite. Focused native
guards, host checks and legacy reports also pass. The two unchanged generic
primitive examples reject at their exact pre-native boundaries. Exact-commit
CI remains pending. No default activation,
general capture, GC replacement or performance claim follows from this stage.

## Bounded source and resource change

An inferred, top-level generalized let may now capture ordinary closed intrinsic
Int/Bool values when its actual checked body, after the type prefix, is a direct
lambda. The source checker and planner agree on exact lexical binders, types and
occurrences. There are at most 64 explicit import bindings, including aliases as
separate bindings. The definition remains one shared body with complete use-site
vectors and actual checked proofs. No literal substitution, body cloning, eager
forcing, wrapper deletion or identity special case is introduced.

Open/rigid/higher-rank, Scheme/view, callable, nominal, nested or recursive
generalized captures remain excluded. Generic body primitive operations are not
added. The ordinary compiler checks, root type, erasure and outer-first proof
normalization remain authorities; the producer is unchanged. The diagnostic
capture remains evidence rather than an arbitrary JSON admission interface.

The IR `generalize.imports` map explicitly joins a new child name to an owned
parent value, exact intrinsic `^T` and `down` relation. The source must have
allocated unscoped concrete provenance, MONO access with no ticket/projection,
and proven Down support to the introduction authority, including same-home
support. Unknown, forced or foreign
callback provenance is insufficient. Every import independently retains the
original owner after begin and is dropped before seal; it is never itself the
sealed result. The parent survives. Full imported References enter placement
support, so an unsafe below-home choice falls back to coarse ownership rather
than inventing descent. The existing post-begin handle watermark detects a leaked
alias. No allocator, terminal cleanup policy or public ABI changes.

## Capture-only runtime rule

Only registered capture construction, stored-slot checking, read and adaptation
gain an alternative to the existing same-neutral-capsule/PROJECT rule. The new
branch requires the exact Code, capture name/position, intrinsic scalar Type,
CONCRETE origin, E0, capsule/activation0, MONO Access and matching physical
representation. Scalar describes a result descriptor, not readiness: the target
may be an unforced THUNK or APPLICATION. Its original node, Access and memo survive;
adaptation uses the existing null-projection identity Transport. Generic-owned
closed scalars still follow the old neutral/projected path.

This does not relax neutral argument, result, application, memo or Fill edges.
Global publication and transport helpers are unchanged. The packet has no new
per-introduction import whitelist. Source correspondence is a fresh static and
registered generated-Code obligation. Boundary/Coverage describes the full static
premise closure, including unused callbacks, not observed reachability or an
exhaustive native API acceptance set. Old no-import metadata remains exact. Symbolic callback captures still require
actual-origin checks at runtime; resource-checker acceptance is not a guarantee
that every arbitrary raw IR graph will pass every dynamic guard. This source
slice is narrower and its genuine cases are qualified separately.
See the explicit amendment in [CORE_CONTRACT.md](CORE_CONTRACT.md).

## Genuine inferred source cases

Both positive fixtures contain an unused SharedPoly import for the existing
capture route; its annotated `sharedId` is projected away. The local `k` and its
uses are unannotated, and there is no implemented identity-specific shortcut.

- `generic-closed-scalar`: pending `bonus = addInt 20 1`, then `k = \x -> bonus`.
  `addInt (k true) (k 0)` returns 42. Actual normalization is `/1` with zero steps.
- `bool-scalar`: pending `flag = ltInt 20 21`, then `k = \x -> flag`. Two nested
  ordinary conditionals use `k 0` and `k true` and return 42. Normalization is `/1`
  with four exact steps. Source order is Int then Bool while canonical IR use
  declarations are Bool then Int; the observer joins full vectors and capture
  chains instead of zipping these orders.

Each actual bonus is a primitive THUNK in the native graph, despite the source
application syntax. A single direct generic closure captures that original pending
concrete node. Both calls use the same closure and return the same bonus node;
its primitive is computed/memoized once and reused. Fresh source/proof inventory,
IR import-copy facts, generated begin/retain/drop order, Code/Site/Env/Transport
and the full event graph are checked together. Public events do not expose every
owner Access or callback capsule, so they are not an exhaustive per-owner proof.

Two unchanged diagnostic fixtures remain intentional **pre-native refusals**:
`mixed-scalar` reaches generic `ifThenElse`, and `alias-scalar` reaches generic
`addInt`. They pass the new capture inventory but fail the unchanged generic
primitive allowlist at exact recorded paths with FRAGMENT. They are the next
capability gap, not successful source programs or renamed CAPTURE failures.

## Completed finite local checks

The first coarse/O0 Int/Bool runs each return 42/fault0 with all seven live memory
categories zero. Int:99 events, work2,968,725, allocated/freed10,024B, peak6,352B.
Bool:140 events, work4,946,662, allocated/freed13,368B, peak7,168B. No events are
omitted. Guard mask117440495 excludes projected transport bit4 and Fill bit24;
these runs use concrete identity capture transport and no Hole/Fill. This is not
exhaustive guard coverage, RSS or a timing comparison.

The genuine Int pair passes 49 controls per optimizer (34 copied-packet +15 runtime)
and Bool passes 70 (55+15). Complete O0/O2 guard reports match. Tests cover copied
wrong type/origin/Access/role/shape, the unchanged noncapture publication guard,
capture/transport work failures, post-retain failure, leaked import alias and a
balanced extra retain/drop. Fault8 controls keep diagnostic ownership until explicit
terminal destruction, which retires the exact retained amount:3,080B,4,792B or
3,416B depending on the frontier. Retain is not reported as zero live memory.

Two separate, host-checked synthetic fixtures extend the native boundary coverage:

- Pending Int APPLICATION:three retained aliases of one owner, two capture slots,
  unused third alias discharged and a transitive ordinary generic closure. Both
  views are demanded; the returned Int child is applied. O0/O2 each pass 46 controls
  (31+15), with healthy42 and the original pending owner retained.
- Ready Bool:the same alias pattern returns a Bool that is forced/dropped, followed
  by an explicitly synthetic Int42 marker. O0/O2 each pass 41 controls (26+15).
  The marker is not evidence of the Bool's truth value.

All synthetic O0/O2 reports match completely. These are raw IR fixtures, not
original-source qualification. Packet mutations may reject at earlier validation
stages; private copied-fact checks are not claims about public ABI entry points.
Known-valid registered references are assumed, not arbitrary-pointer/race safety.

The two sources, coarse/groups placement and O0/O2 form **eight ordinary
conditions**: two initial compile/run pairs are reused, and six pairs are new.
All return 42/fault0 with seven zero live ledger categories. Complete O0/O2 reports
match within each source/placement, including every work field. **Four O0
ASan/UBSan conditions**, one per source/placement, also pass with LSan disabled;
every full report equals its matching ordinary report. This finite check does not
claim exhaustive memory safety or leak-sanitizer qualification. Full graph observations pass all twelve retained reports without target reruns:
204 copied-report/84 structural controls for the ordinary matrix, and102/42
for sanitizers. These are checks of saved reports and source correspondence, not
extra native executions or independent guard-path coverage.

The existing O0/O2 standalone native suite passes 22 cases each with stress. All 44
complete reports match both Stage23 and Stage19, including work, events and terminal
destruction. The existing five native planner fragments also pass. The standalone
host suite passes 475 checks and the emitter suite passes 128. Host focused checks
pass 28 source/planner and 25 resource/import tests; existing resource/metadata
regression passes 300. The broad source/planner run initially has 346 passes and 4
skips; the available Stage20 golden and the native fragment test subsequently pass.
Two optional legacy event-artifact tests remain unexecuted, not counted as passes.

The first matrix invocation stopped before output creation or any target because
its local helper referenced a nonexistent inputs directory. Correcting only that
preflight root enabled the single successful matrix run. The first standalone
emitter test stopped before its tests on the intentionally changed production pin;
only the exact reviewed emitter-body pin was updated before its successful new run.
The independent observer review added seal Access, distinct view-owner and actual
Bool condition/selected-node checks after copied reports exposed those gaps. All
original failures and old reports remain; no production relaxation or hidden target
retry was used.

The final default portable suite completes four fresh producer builds/source
calls: both positive cases return42 with seven zero live categories, and both
negative cases reject before planning or native compilation. All four raw captures
are byte-identical to their retained originals, while the two complete native
reports equal the corresponding initial reports, including every work field.
The28 recorded processes are clean:26 exit0 and two outer CLI calls exit1 exactly
for the intended refusals. No subprocess cleanup escalates. Positive checks reject
51 copied-report/21 structural controls; refusal checks reject six altered diagnostic
controls. The original capture or binary is not substituted for these fresh calls.

## Reproduction and limits

Host-only checks do not launch a producer or native evaluator:

```sh
python3 -B -S tools/experimental/resource-native/tests/test_ir8_generic_imports.py
python3 -B tools/experimental/resource-native/tests/test_module_shared_generic_captures.py
python3 -B tools/experimental/resource-native/tests/test_planner_v8_generic_captures.py
```

The portable source suite is enabled after independent review. Its invocation is:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_generic_captures.py \
  --ghc /absolute/path/to/ghc-9.14.1 --cc cc --output /absolute/new/generic-source
```

Default `--case all` selects both positives and both exact refusals. Outputs are
outside the checkout and must not exist. Failures remain. The CLI default is still
coarse placement, fuel1,000,000 and retain-on-fault. Every original proof and fresh
source/build custody check remains; saved captures do not substitute for this run.

Reproduce the synthetic native guard inputs without running a source producer:

```sh
PYTHONHASHSEED=0 python3 -B tools/experimental/resource-native/tests/prepare_generic_capture_guard_fixtures.py \
  --output /absolute/new/generic-guard-fixtures
python3 -B tools/experimental/resource-native/tests/test_generic_capture_guards.py \
  --generated /absolute/new/generic-guard-fixtures/pending-int-application-aliases/generated \
  --output /absolute/new/generic-pending-guards --cc cc --expected-scalar 42 --require-pending
python3 -B tools/experimental/resource-native/tests/test_generic_capture_guards.py \
  --generated /absolute/new/generic-guard-fixtures/ready-bool-aliases/generated \
  --output /absolute/new/generic-ready-guards --cc cc --expected-scalar 42
```

The same guard runner accepts either genuine positive source case's generated
`native` directory, with `--require-pending`; those real sources test pending
THUNKs rather than the synthetic APPLICATION or READY paths.

All prior process/work limits remain. GHC builds:600wall/480CPU/8GiB. Capture:
180wall/120CPU/4GiB. Native compile:60wall/30CPU/1GiB; run30wall/20CPU/1GiB.
The version query alone retains `+RTS -xr32m -RTS` under10s/1GiB. Native guard
builds use60wall/30CPU/1GiB and runs60wall/40CPU/512MiB. The source wrapper retains
its1,500s deadline. No automatic retry or limit increase is introduced. Address-space
caps are not RSS measurements.

## CI scope

The workflow adds host import/source/planner checks and reproducible
synthetic guard fixtures to the existing suitable jobs. A separate20-minute source
job runs the four fresh cases and guards the two genuine generated pairs. It does
not append cases to the old26-case/60-minute job or change any old source job.
The job ceiling includes setup and is stricter than the portable deadline; neither
is a worst-case completion guarantee. Exact-commit CI is a separate pending result.
