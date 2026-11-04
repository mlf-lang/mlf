# Stage20: recursive captures of closed nominal-arrow helpers

The opt-in source route now admits ordinary recursive captures whose full closed
arrow contains Int/Bool or exact already-admitted DATA/SUM nominal leaves.
This is a source replay/planner extension. Runtime C/H and the public driver
remain byte-identical to accepted Stage19; ABI, limits, placement and fault
defaults do not change. This stage makes no new performance claim.

## Exact capture contract

The original ordinary `Reference` is carried unchanged, including its complete
type, identity, support relation and Access. Every nominal leaf must resolve to
the exact canonical declaration already published in the checked DATA/SUM
inventory, with its name, index and source path. Classification cannot select a
new family, unfold a recursive type, match by field shape or predict a Code,
origin, readiness state or stronger Down/below support from an arrow type.

Only a captured arrow containing a nominal leaf selects
`closed-admitted-callable-shared-view-captures/1`. Its evidence explicitly contains
`scalars`, `callables`, `nominals` and `views`, including empty arrays. Callable
rows retain the actual binder, complete type and every canonical occurrence.
Nominal leaves are type obligations, not extra physical captures. Ordinary
owners and complete lexical shared-view pairs remain distinct. With no such
captured arrow, earlier scalar-callable/direct-nominal evidence and generated
plans remain unchanged.

The bounds remain 64 captures including used self and each full view, with a
separate 32-external-capture limit for SUM arm factories. The existing single
closed monomorphic recursive group, eight-wrapper introduction bound, full
proof/type replay and outer-first substitutions are unchanged. Every annotation
application remains in the graph; Fill still targets the actual pending RHS.

This does not admit open, foreign or parameterized nominal leaves, higher-rank
arrows, bare Schemes, nominal generic arguments/scopes, mutual/generic/value
recursion or another recursive group. DATA field arrows still contain only
Int/Bool leaves. Recursive DATA, cross-family/callable SUM fields remain out of
scope. SUM case results remain Int: nominal-valued SUM cases are not added.

## Genuine sources and observed ownership

The two original sources import the same shared polymorphic `sharedId` and use
one recursive closure on Nil, Cons and the tail Nil. Their ordinary compiler
checks succeeded; the earlier capture boundary then rejected the helper before
native execution. Those complete captures and refusals remain preserved. New
full custody/projection/resolver replay matches both producer normalization
results exactly, including their two steps, checked Int type and erasure.

- `IntList -> Int`: a pending annotated helper examines its argument and calls
  the genuine shared Int view on its head. Both helper calls receive the same
  recursive-parameter application reference, already memoized to the original
  Cons owner. The helper coercion applications follow that existing chain;
  they are not removed or replaced by the bare Cons owner. Each helper returns a pending case thunk before its parameter is demanded.
- `Int -> Box`: the helper returns two distinct ready Boxes with separate pending
  shared-Int application fields. Each Box is returned before its field is
  projected and demanded. The helper parameter applications remain real owners;
  downstream Force follows them to the same pending bonus computation.

In both finite observations, initial Nil finishes before helper/bonus demand or
shared Int invocation. One helper owner memoizes to one closure invoked twice.
The bonus evaluates and memoizes once to 21; the total is 42. One original shared
RHS/body serves Bool, Int and Int, with complete lexical view identities. View
acquisition/allocation can precede demand. Concrete recursive/helper hosts do
not rebrand the captured generic origin as E0.

Fresh metadata and generated-code correspondence establish exact full types,
capture support and owner paths. Allocation, slot, invocation, field, memo and
handoff events corroborate the observed graph. There is no event exposing every
owner's Access field, nor individual traces for every retain/end-borrow/drop;
these checks do not claim such traces.

## Validation status

- Transport: 206 focused passes; broad regression: 358 passes and three existing
  optional legacy-artifact skips. Stage16 and Stage18 complete evidence goldens
  remain exact.
- Planner: 16 focused passes; combined regression: 124 passes without skips,
  including five older native fragments. Its default new-suite invocation has
  13 passes and three retained-artifact skips. Eight prior full plans and 32
  generated files remain byte-identical.
- Native matrix: both sources, coarse/groups and O0/O2 pass all eight conditions,
  with Int42, fault zero and seven balanced empty terminal ledgers. Both original
  coarse-O0 pairs were revalidated/reused; six missing pairs were launched.
  Complete O0/O2 reports agree. All 200 copied-report and 48 copied-structure
  corruption controls reject; these are evidence mutations, not runtime faults.
- A fixed fuel23 retain/destroy pair produces the same fault4 after Fill.
  Retain leaves 5,200 tracked bytes; explicit terminal destruction retires those
  same 5,200 bytes without changing the evaluation fault. This is not rollback.
- Four O0 ASan/UBSan conditions pass with LSan disabled. Complete reports equal
  ordinary runs without ignored work fields; 100 report and 24 structure
  controls pass. The native guard-work cap stays 67,108,864.

The separate fresh-source suite also passed both cases through fresh producer
builds, snapshots, checking/replay and native execution. All 16 recorded
processes exited zero without cleanup errors; both complete native reports are
JSON-exact to the original coarse-O0 reports, including every work field. Its
50 copied-report and 12 copied-structure controls reject. Outer elapsed times
were 124.8627s and 114.5677s, including compilation, not runtime benchmarks.
No extra fault pair was run. Exact-head CI remains a separate result.

The diagnostic capture itself is never arbitrary-JSON native authority. These
finite tests do not establish general MLF support, complete GC replacement,
Perceus equivalence or a performance improvement.

## Reproduce and CI

```sh
T=tools/experimental/resource-native/tests
python3 -B "$T/test_module_shared_transport.py"
python3 -B "$T/test_planner_v8_nominal_callable_captures.py"
python3 -B "$T/test_source_v8_nominal_callable_captures.py" \
  --ghc /absolute/path/to/ghc-9.14.1 --cc cc \
  --output /absolute/new/nominal-callable-source-output
```

The fresh runner performs two coarse CLI/build/capture/native cases, retaining
`nominal-callable-observations.json` per case; it adds no fault pair. Optional
retained artifacts exercise host replay/goldens separately, not fresh builds.

The workflow adds the new planner suite to the existing fragment job
and the two new source cases to the existing 20-minute nominal-capture job.
That job then has four cases and reuses one checksum-pinned official GHC setup.
Its old two cases, the separate 26-case/60-minute job, per-process limits and
all job caps remain unchanged. The earlier Stage19 nominal job took 6m56s,
including about 138s for setup and 267s for its two cases. That observation
supports trying this grouping; it is not a guarantee that four cases fit on
every runner. A cap overrun remains a failure, not permission to relax limits.
