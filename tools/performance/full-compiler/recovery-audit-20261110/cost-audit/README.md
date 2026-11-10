# Fresh compiler cost and necessity audit

Source: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. Restored plan:
`22b50be7014ede07db9e41d44cacf286c5ef6206`, revision 15. All 16 audited
source files were compared byte-for-byte with their frozen Git blobs; identities
are in `source-manifest.json`. This is a source-path audit plus a reconciliation
of preserved measurements, **not a new timing experiment or semantic gate**.
No compiler code or validation policy changed.

## Answer supported now

Repeated representation and checking work exists on the real fresh compilation
path. It is a plausible optimization target, but the available evidence does not
show that dispensable functionality dominates compilation. Do not equate every
check, proof witness or serialization with redundant work, or count overlapping
profile rows as independent cost. Optimize repeated work while retaining its
authority and observable behavior.

The current end-to-end result is still negative/incomplete: the full 90-module
MLF and split strategies hit their 600-second limits, and there is no completed
current MLF/GHC ratio. The F3 real 11-module ABBA cohort completed, retained every
sample, and did not support a speedup (candidate/base median 1.270493). Its 21.9%
local Graph-harness reduction does not establish compiler acceleration.

## 1. Extra audit switches are already off on the ordinary path

- `bootstrap/MLF/Entry/Emlf.hs:113–118,185–186`: plain `--compile-crate` passes
  `verifyAll=False`; `-Zincremental-verify-ich` explicitly enables verification.
- `libraries/mlf-crates/Bootstrap/CrateGraph.hs:153–169,225–236`: the extra cached
  fragment semantic audit is enabled only by `MLF_QUERY_SEMANTIC_AUDIT=1`.
- `libraries/mlf-crates/Bootstrap/QueryGraph.hs:854–865`: optional phase clocks
  require `MLF_QUERY_PROFILE=1`.

Turning these switches off cannot explain a new ordinary speedup when the
recorded ordinary runs already had them off. This does **not** mean the normal
language/compiler correctness checks are off.

## 2. A concrete second target-check boundary deserves measurement

The actual fresh path is `CrateSession.compileGraphLocked` → `CrateGraph.compile`
or `compileLoweredIn` → `runGroups` → `InferenceUnit.compileOpenGroup[Indexed]`.
It does not use the legacy `CrateSession.writeSourceRecord` experiment.

1. `InferenceUnit.compileGroupBody` calls `CompilerCore.finishCompilation`.
2. `CompilerCore.hs:49–77` generates and solves constraints, constructs evidence,
   elaborates the target, then runs `Checked.check`, compares its type with the
   inferred type, and checks source/target erasure equality.
3. `InferenceUnit.hs:343–381` extracts the datatype context and, when needed,
   removes the external-parameter `XLetRec` wrapper. It verifies parameter order
   and dependency schemes.
4. `InferenceUnit.hs:383–391` creates an open environment and runs `Open.check`
   on the resulting implementation, then checks declaration ownership.
5. `OpenFragment.hs:71–81` validates parameter types and runs
   `Check.inferDeclarationSpine` over that open implementation.

Thus much of the same target body is visited at two successive checked
boundaries. They are **not identical inputs**: closed target versus open body
under an extracted dependency environment. The second boundary also establishes
owned declarations. No saved measurement isolates its ordinary cost.

A possible later optimization is a checked projection that transfers the first
certificate into the exact open-fragment environment and preserves ownership,
error order, bottom/demand behavior and erasure checks. Merely deleting
`Open.check` is not such a projection. Existing `Open.fromChecked` splits lambda
parameters; it is not automatically equivalent to this external `XLetRec`
extraction and must not be substituted blindly. First measure this boundary and
prove a narrowly scoped certificate-transfer contract.

Demand detail: `X.Checked.check` obtains a type and a separately deferred
`Either` binding inventory (`X/Checked.hs:21–28`). CompilerCore consumes type
and erasure, but need not consume that declaration inventory. `Open.check`
consumes the open inventory and checks exported free variables, while the
fragment fingerprint and free-name fields are still lazy. Closing a clock at
`Right` weak-head normal form does not account for all later demand; stamping
can be charged to raw encoding. Do not attribute those wall windows as complete
checker CPU or add deeper forcing merely to tidy the measurement.

## 3. Not all graph validation is duplicate

`Constraint.hs:287–303` validates the generated graph; `solvePrepared:1255–1261`
then calls `Solver.prepare`, which validates its input again at
`Graph/Solver.hs:240–256`. This is a concrete same-graph boundary already noted
in the previous plan. Its selected second validation accounted for 799 of 89,395
ticks (about 0.894%) in the old instrumented prefix, not an ordinary CPU share.

Other validations surround graph expansion, unification, rebinding and changed
local graphs. An old certificate cannot cover a new graph. The old inherited
`denseValidation` share of 9.51% includes required work and overlapping callers;
it is not a 9.51% removable budget. An older private-driver validation-reuse
screen reported 0.2478% pooled wall improvement and failed its prespecified
0.5%/both-blocks-positive rule; that result is historical, not a current-path
performance claim. The present prepared elaboration path already
retains the finished solver (`CompilerCore.hs:60`, `Elaborate.hs:474–481`) rather
than unconditionally calling the legacy re-preparation entry.

## 4. Three different meanings of witness

- Instantiation proof: `Elaborate.hs:341–373` first tries equal-type reflexivity,
  then a checked direct correspondence. It calls `Solver.witness` only if the
  direct proof fails. `Solver.hs:1875–1887` expands and unifies to recover an
  image used to construct the explicit target proof. This is a semantic fallback,
  not an unconditional second solve. Its hit rate and separate cost remain
  unmeasured. The older October 30 15-module diagnostic recorded 176,557
  elaboration edges with zero witness fallbacks (all reflexivity/direct proof).
  That historical coverage does not establish current 90/11-module behavior or
  CPU cost, but argues against prioritizing witness from static complexity alone.
  See `docs/performance/validation-reuse-20261030.md` at the frozen commit.
- Builtin source witness: `BuiltinPreludeContext.hs:48–91` checks generated
  Prelude metadata and its target. `PreparedCompiler.hs:271–272` holds that
  preparation in a shared top-level value; it is not a per-SCC source-witness
  check. Installation still verifies the fixed images or takes full admission.
- Dictionary evidence: `CrateGraph.resolveRequests` serves actual finish
  requests. `SourceInference.hs:1665–1702` skips requests for protected roots,
  roots with no labels, or ready finishes. This does not justify removing class
  semantics or claiming evidence runs for every declaration.

## 5. Serialization has cost, but several hypothesized duplicates are absent

- `QueryGraph.hs:117–133`: `record` encodes and hashes once, then retains the
  immutable bytes for publication. Publication does not re-encode the raw AST.
- `CrateGraph.hs:313–326`: unchanged `KeepRawBody` plus identical references
  reuses the raw content digest unless explicit verification/audit asks for a
  recheck. Changed bodies/environments require a fresh address.
- `CrateGraph.hs:327–345`: exported contracts are encoded once; their digest and
  bytes are shared between finish receipts and Binding nodes.
- `QueryGraph.hs:722–769,835–846`: publishing writes staged encoded bytes;
  post-publication verification excludes the current pending set and checks
  retained payloads once per digest. It does not reread/hash every freshly
  written result again.

There is a real, narrower duplicate at initialization: `CrateGraph.hs:49–68`
records each imported contract/datatype first as an Input node and then as its
derived node, passing the same value through `G.record` twice. Both calls encode
and hash. This is not per-SCC whole-AST publication. The previous plan classified
remaining double encoding as low coverage; no new ordinary coverage estimate
was obtained here. Reusing the first encoding could retain both authority nodes
and edges, but does not yet justify an expensive producer experiment.

Every fresh fragment also takes `SourceInference.canonicalOpen`
(`1629–1636`): AST → bounded `Wire.GraphPlan` → graph materialization →
`finalSyntaxRun`. An unchanged result returns the original checked fragment;
a changed result is checked again. This is source-finalization representation
policy, not a lossless codec identity. Its demand, normalization and resource
limits must survive any fusion or representation improvement.

`OpenFragment.stamp` (`60–69`) separately renders context, parameters, body and
bindings into a semantic fingerprint, and `encodeBody` (`117–124`) places that
fingerprint alongside structured syntax. This is another concrete traversal to
measure, not proof that the fingerprint can be removed. It participates in
existing artifact/audit identity. Pretty traversal versus binary graph planning
should be separated in a new diagnosis.

CRC and SHA have different contracts. `Bitstream.hs:477–479` explicitly defines
CRC as corruption detection, not a content address or authentication substitute.
The retained old profile attributes 1.613% self ticks to one checksum worker;
this neither measures all serialization nor proves CRC is unnecessary.

## 6. What the preserved timings do and do not say

The old low-perturbation 120-second diagnostic closed 956 fresh groups. Closed
wall-demand windows were raw demand 91.768s, prepared record 4.654s, raw record
5.168s and finish 1.075s. They include GC and lazy residual demand, not exclusive
CPU. In particular raw demand includes inference, elaboration, target checking
and canonicalization; calling it all Solver work would be incorrect. Publication
was not reached, so its cost is not shown by this prefix.

The late profile points toward `solvePrepared` (34.34% inherited ticks), with
substantial graph/data-structure work, but GC (20.37%) and profiling overhead
(6.77%) materially affect it. Those figures cannot be turned into ordinary wall
savings. Raw profile and old binaries were not persisted remotely. Summaries
cannot recover missing detailed witness/checker counts.

## Next useful bounded experiment

Restore a qualified producer and fixed source/dependencies first. Then measure
the unchanged fresh path, with independent labels for constraint generation and
solve, target elaboration/proof fallback, first target check, open-fragment
admission, canonicalization, stamp demand, encoding/hash and publication. Keep
the established 780-fresh/0-reused and all three raw artifact oracles on the
11-module slice if that slice is selected. Diagnostics are not throughput
samples; no function is bypassed and no deleted check supplies a speed estimate.

Counter/clock design must respect laziness: do not force an entire AST at a new
boundary just to attribute time, hold it in a reporter, or sum nested windows.
If a profile is used, rebuild and requalify with its ABI and report the effect.
Ordinary GC statistics can describe whole-process managed-heap work but cannot
alone apportion these functions or explain C01's slow B retrospectively.

Rank a production candidate only after obtaining measured coverage and a
semantics-preserving mechanism. Preserve every outcome, including failed gates,
and continue to exclude native generation A/B and fixed-point campaigns.
