# Stage22: genuine higher-order shared-source qualification

**Local qualification complete:** both genuine source cases pass the finite
native, sanitizer and final fresh-source checks below. The fixed-fuel fault pair
covers A only. Exact Stage22 commit CI has not run; it remains separate.

This stage exercises already-admitted higher-order shared functions. It adds
source-specific tests and documentation, not a runtime, producer, planner, ABI,
allocator, default-policy or limit change. Its baseline is published Stage21,
commit `ffd18824c34d9ee0d3d08adc8148ac2047a6a23a`, tree
`b088d1a2bfe39d5908c621688a4962959882de35`. Publication identity and exact-commit
CI are distinct from the local qualification recorded here.

## Source boundary

Both fixtures import this real module:

```text
module SharedPoly (sharedApply) where
sharedApply : forall a b. (a -> b) -> a -> b
sharedApply f x = f x
```

The function argument is an ordinary term value. The complete shared type
coordinates remain scalar atoms, not closed arrow coordinates. This does not
extend the accepted type-argument domain, generic principals or recursive
capture policies. The [Stage21 restrictions](README_STAGE21.md) still apply.

Fresh ordinary K checking, module/resolver custody, projection, raw type-proof
replay, outer-first normalization, root/declaration/erasure checks and fresh IR8
resource/metadata checking remain mandatory. One original shared RHS is retained
with its annotation applications. All source lambdas and parameter wrappers
remain ordinary allocations/applications; no identity shortcut, cloning or
direct-C replacement is introduced.

The returned INSTANCE child captures the actual pending callable-parameter
wrapper. Its full projected arrow type, original owner, Down support and shared
origin remain checked through metadata, stored slots and guarded handoffs.
A concrete helper is not permission to relabel a captured shared origin as E0.
Public events do not expose every owner's Access or capsule, so they are not an
exhaustive per-owner trace proof.

## A: equal coordinates, completed locally

```text
import SharedPoly
let bonus = addInt 20 1 in
let helper : Int -> Int = \n -> addInt n bonus in
let gate : Bool -> Bool = \b -> b in
let partial : Int -> Int = sharedApply helper in
if sharedApply gate true then addInt (partial 0) (partial 0) else 0
```

The actual complete vectors are `[Int, Int]` and `[Bool, Bool]`. Both share one
RHS and its neutral memo. Each returned child is used after its creator returns
and retains the pending callable wrapper. The Int partial is memoized once and
reused for two calls; the same helper runs twice and the shared bonus once.
Ordinary annotation and parameter applications remain in that demand chain.
Equal coordinates do not test coordinate permutation sensitivity.

Completed observations:

- Four coarse/groups × O0/O2 conditions return Int42/fault0 with all seven live
  ledgers zero. The initial coarse/O0 pair was reused; three pairs were new.
  Complete O0/O2 reports match per placement, including every work field.
- Both O0 placements pass ASan/UBSan with LSan disabled. Their complete reports
  match the corresponding ordinary runs.
- Coarse work is 38,035,267, allocated bytes 45,112 and peak bytes 16,048.
  Groups work is 36,219,291, allocated bytes 48,440 and peak bytes 11,976.
  These are counters for this finite workload, not a timing benchmark or a
  general memory/performance conclusion.
- Fixed fuel 150, selected from the saved healthy execution before launching
  either fault call, stops at step 151 after the creator return. Both calls
  preserve the same 243-event healthy prefix. Default retain keeps 74 blocks /
  11,104 bytes; explicit terminal destruction retires exactly those blocks and
  bytes, without changing the evaluation. Six copied fault controls reject.
  There was no budget search, healthy retry or recursive-Fill claim.
- The earlier A-only fresh CLI pipeline passed eight clean child records.
  It predates the integrated two-case runner and remains intermediate evidence,
  not a substitute for the final default-suite results below.
- The integrated observer rejects 26 copied-report controls for each observed
  A report. Its 10 structural controls run on each placement plan and again in
  the fresh CLI, not independently for every optimization or sanitizer run.

The graph contains no Hole/Fill. Its 26 applicable guard bits have mask
117440511; this does not claim coverage of Fill guard 24 or all runtime paths.

## B: opposite coordinates, completed locally

```text
import SharedPoly
let bonus = addInt 20 1 in
let helper : Bool -> Int = \b -> if b then bonus else 0 in
let gate : Int -> Bool = \n -> ltInt n 1 in
let partial : Bool -> Int = sharedApply helper in
if sharedApply gate 0 then addInt (partial true) (partial true) else 0
```

Fresh checking and independent replay retain full vectors `[Bool, Int]` and
`[Int, Bool]`, normalization `/1` and four steps. These distinct coordinates
make order observable, unlike A. The actual native observer also checks their
ordered use environments, pending callable wrappers and reused partial. The
same helper is called twice, while bonus21 is evaluated once.

- All four coarse/groups × O0/O2 conditions return Int42/fault0 with seven zero
  live ledgers. Initial coarse/O0 was reused; three pairs were new. Complete
  reports, including work, are O0/O2-equal within each placement.
- Both O0 placements pass ASan/UBSan with LSan disabled. Their complete reports
  equal the matching ordinary runs.
- Coarse work is 43,862,447, allocated bytes 48,368 and peak bytes 16,856.
  Groups work is 41,651,314, allocated bytes 51,904 and peak bytes 12,248.
  These workload counters are not a timing or general performance claim.
- Each observed B report rejects 33 copied-report controls. Its 13 structural
  controls run on both placement plans and the fresh CLI, not separately per
  optimization or sanitizer. No B fault pair was run.

The first B support-build attempt was interrupted before any GHC or source
producer launched. Its incomplete support result remains preserved. After its
existing 900-second deadline expired, a separate fresh output was used for the
completed capture/replay; the old attempt was not overwritten or called a pass.

## Final default two-case source suite

The integrated runner defaults to both cases. Its final fresh invocation passes
16 child records, all exit zero with empty stderr and clean cleanup. Each raw
capture is byte-for-byte equal to its earlier checked A01/Bcross02 capture.
A uses normalization `/1` with two ordered Int steps; B uses `/1` with four.
Both complete native reports equal initial coarse/O0 byte-for-byte, including
work 38,035,267 for A and 43,862,447 for B.

The fresh suite rejects A's 26 report / 10 structure controls and B's 33 / 13.
The observer joins actual source binders, full vectors, Code/site records,
stored callable captures and memo/call events without hardcoded identities.
Both nonrecursive graphs exercise the 26 applicable guard bits, excluding Fill.
Structural checks validate plans and source correspondence; they are not extra
native executions or evidence for every possible runtime path.

## Reproduce and CI

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_higher_order_shared.py \
  --ghc /absolute/path/to/ghc-9.14.1 --cc cc \
  --output /absolute/new/higher-order-shared-source-output
```

The runner builds the shared producer and checks fresh source bytes through the
normal CLI. `--case all` is the default; `--case shared-apply` or
`--case shared-apply-cross` selects one case. Each writes inputs under
`output/<case>/inputs` and CLI evidence under `output/<case>/<case>`, including
capture, plan, generated/native files and `higher-order-shared-observations.json`.
The top-level `results.json` contains both case results for the default run.
Historical JSON is not native authority.

CI adds only a separate `ir8-higher-order-shared-source` job with a 20-minute
ceiling, the same checksum-pinned official GHC setup and unchanged process
limits. The 26-case/60-minute source job, four-case/20-minute nominal-capture job
and Stage21 nominal-shared/20-minute job remain byte-for-byte unchanged. Failure
evidence is uploaded. The job ceiling is not a worst-case completion guarantee.

This remains a bounded default-off experiment. No closed-arrow shared type
arguments, general MLF acceptance, GC replacement, Perceus equivalence or speed
improvement is claimed.
