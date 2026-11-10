# Read-action fusion experiment

Status: O0/O2 semantic gate passed. The ordinary owner-codegen gate and all
performance samples remain pending. There is no speedup or full-compiler claim.

Baseline is exact `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`, independent of the
small parent-placement experiment. Only `libraries/mlf-inference/Bootstrap/Graph.hs`
changes. Its baseline SHA-256 is
`9df4833f55f0826181f8e1e974dc0672753e9462de0d134f64fc3f8c6f6e8a7f`, and its candidate
SHA-256 is `fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3`.

## Exact source mechanism

`transform.py` expands 54 saturated internal uses of
`readDense low array identity` into `readSTArray array (identity - low)`.
All three arguments at every site are already-bound variables, used once.
`sites.json` records each original/transformed span, line and containing function.
Reversing only those spans restores exact baseline bytes.

The public readDense definition remains unchanged, as do all write helpers and
write calls, primitive implementations, compiler flags, and the original parent
replay. No partial application, shared-action binding or new strictness operation
is introduced. No pragma is added: shared-haskell-v1 accepts only its approved
LANGUAGE extension prologue, not GHC INLINE pragmas.

## Why inspect this

An authenticated ordinary O2 Graph object still has actual callers of readDense,
whose wrapper allocates 56 bytes for an index thunk and an ST action closure.
The host primitive's pure/bind wrapper has already optimized away. Expansion may
let the caller's existing action consumption eliminate the Graph wrapper, but
source expansion alone does not establish this. The public helper may remain in
the object even when every internal caller changes. Code-generation review must
follow the actual callers and check that closure construction did not just move
or acquire another symbol name.

Profiling-prefix allocation counts are not ordinary invocation counts and must
not be multiplied by 56 to predict a compiler speedup. An ordinary GHC result is
also not evidence of native MLF performance.

## Demand contract

The shared interpreter constructs RSTAction with unevaluated operands
(`Bootstrap/Runtime.hs`, runtimePrimitive). Execution in performState and
performWorld validates the array before the index, snapshots the current cell,
and does not demand the cell payload. Native `mlf_st_read_array` follows the same
array/index/snapshot order. The existing native runtime ST fixture explicitly
checks lazy operands, repeated shared actions and snapshots before mutation.
Those sources were inspected; no native A/B or fixed-point suite was run.
The parser lowers `a <= b` as `not (ltInt b a)`, matching Host.Base.leInt;
therefore the parent interval value is demanded before the ancestor start in
that comparison. The read-demand oracle follows this existing order.

The transformation leaves the subtraction in the same action operand and uses
the same imported primitive and subtraction operator. It neither precomputes an
index with seq nor duplicates an argument or a shared action. The extra controls
call actual changed denseContains/denseKind paths, not the unchanged readDense
helper. They check action construction, array/index/cell error order, negative
and wide offsets, short arrays, lazy unused holes and cached kinds, and repeated
execution of one shared read action across a write.

## Semantic gate and remaining work

The prepared runner authenticates the frozen ordinary producer; makes reversible
LegacyGraph/CandidateGraph module copies; rebuilds both C objects with original
commands and requires byte equality; and uses baseline dependency objects. It
preserves ordinary pedantic demand flags. One outer 240-second resource scope
covers both O0/O2 builds, all controls and postchecks; nested commands do not
start a session or reset the budget. It must be called under the sprint outer
lock, from this checkout, using absolute producer/source/output paths.

The reused finite gate includes 12,000 exact validations, 5,616 public complete
graph outcomes, 480 signed-Int64/sparse layouts, and 26 placement-demand/alias
cases. Twenty-one new read-demand controls and 120 complete valid normalization
graphs are additional and passed at O0 and O2.
One fresh gate ran successfully in 41.017 seconds under the shared 240-second
scope. Both O0/O2 runs passed all seven exact control-output lines. Original
input pins, borrowed objects, C byte equality and producer reauthentication all
passed. There were no surviving descendants, and both locks were free.
The 120 normalization comparisons do not establish every normal* branch was hit.

`results.json` contains only a safe summary and receipt hashes. Full raw local
receipts, tool/object tables, binaries and build logs are not committed and have
not been remotely persisted; their hashes do not restore those bytes.

Any subsequent ordinary owner-object check or short sample needs separate
coordinator admission after the semantic gate. No full producer is planned here.
