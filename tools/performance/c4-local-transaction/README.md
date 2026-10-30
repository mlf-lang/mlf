# C4 local fallback transaction: independent correctness controls

This directory makes the C4 controls reviewable and runnable from the repository.
It is **not a benchmark** and does not accept an optimization. The historical
roughly 3% scoped result was measured for C4 against P3 on another frozen cohort;
it is **not a measured speedup of the current PR #25 integration**. Do not add
independent optimization percentages or reuse old binaries/receipts as current
qualification. No native bootstrap, fixed-14 target, cache-warming campaign or
performance retry is launched by `run_controls.py`.

## Two oracle responsibilities

The integration-before reference is commit
`d3906cbaefc9d5965ee59bb87b6be8f730ec3204`. Its complete Graph, Solver and Constraint
algorithms are byte-identical to P3
`875e483de49655030c4ffba1995b60610a50273a`. The three local `Frozen*` modules are
the original independently frozen algorithms, with only the declared module and
internal Graph/Solver import renames. `manifest.json` records their literal
hashes and reversible substitutions. The full runner verifies the inverse
against the actual before source; focused mode checks the fixed inverse hashes,
never substitutes the candidate for the before source.

These modules intentionally use the **same current collections, Types and host
primitives** as the integration. This isolates the C4 change from earlier PR #25
changes, including generic `Map.unionWith`. It is not a claim that every imported
module is frozen P3. The full source contract pins all 179 registered shared,
host, configuration and builtin-verification inputs of the before checkout; the
candidate may change only the two exact reviewed C4 algorithm files and the
single generated builtin source-identity literal. The builtin semantic payload
must remain byte-identical after removing that token, and the maintained
producer independently checks fresh generation. The runner does not rewrite
any source or builtin.

The existing A1 directory separately retains its complete historical P3
Graph/Solver/Constraint/**Map/IntMap/IntSet** oracles. Their literal identities are
checked here, but their dynamic gate belongs to the separate A1 integration
runner. Nothing in `a1-private-index/controls/` is changed or shadowed by this
runner. The old C4 `PublicControls` summary says A1-specific controls are not
applicable **to that module's C4 mechanism test**; this is not a claim that the
integrated PR lacks A1 or that its admission/privacy tests may be skipped.

## Fixed source inventory and coverage

All thirteen `controls/*.hs` files and the 216-case entrypoint retain the exact
recovered v10 bytes. `manifest.json` records each original evidence member and
hash. The small `TransactionMain.hs` is a new import-and-call wrapper. There is
no expectation regeneration from current candidate output.

| Executed entry | Required coverage |
| --- | --- |
| `PublicControls.main` | 12,000 validation cases; 5,616 unifications with success/rejection and both binder-premise outcomes; 400 renamed cases; 28 public traces with immutable retry; eight independently authored parsed-expression expectations; four authored permission cases; original graft/field controls |
| `C4TransactionControls.main` | 28 fixtures (18 authored + 10 coordinate variants), 19 successes / 9 rejections, 23 admitted exact compact projections; original 28 traces; both actual prepared drivers (56 each); boundary, scope, rigidity, kind, cycle, rollback, partial-demand and isolated restoration controls |
| `HeteroinputMain.hs` | Exactly 18 authored inputs × four fixed nonmonotone old-ID permutations × three coordinate systems = 216 executions; 156 successes / 60 rejections; 156 admitted; nonempty first/middle/last fresh-root positions on the admitted path itself |
| `FileControls.main`, full mode only | Nine fixed source-file cases, independently checked types/targets, exact errors, missing-file rejection, fresh query groups and whole `.mlfci/.mlfco` byte comparison between before and candidate |

The 216 executions are **not 216 independently designed topologies**. Every
variant obtains its complete result and exact first error afresh from the frozen
algorithm; candidate admission does not choose inputs or expected answers.

Graph node-tree shape, alias-tree shape, fresh counter and scope structure remain
physical comparisons. Only the new prepared transaction's reverse-index tree
shapes may differ: full ordered entries and independent BST/order/count/balance,
nonempty buckets, graph validation and final index audit remain mandatory.
Old public entrypoints retain their stricter original comparisons. The comparator
is tested against deliberately wrong sizes, members, graph shape, aliases,
counter and scopes. Failure/retry reuses the same immutable state. Finite tests
are not a proof for arbitrary forged prepared values or all partial Haskell
values; the production design's prepared-state and demand proofs remain necessary.

`TransactionControls.hs` from the older C3 experiment is deliberately absent.
It calls C3-only helpers and was not executed by the historical C4 full gate.
The present `TransactionOracle.hs` is a dependency of the unchanged public
controls; its presence does not claim execution of that C3 suite.

## Requirements and cheap checks

Python 3.11+, ordinary **GHC 9.14.1**, a C compiler and the maintained installed
package closure (`base`, `array`, `bytestring`, `text`, `containers`, `directory`)
are required for native control execution. Use the maintained ordinary O2
producer, not profiling/counting overlays. The guard helper is reused unchanged
from `../a1-private-index/helper.py`; source/object/toolchain authentication uses
each source checkout's maintained `tools/shared/test_direct.py`.

```sh
python3 -B tools/performance/c4-local-transaction/test_controls.py
```

This cheap test parses Python, verifies literal sources/inverses and exercises
synthetic positive/refusal cases for exact inventories, ordered matrix events,
typed summaries, identity-only changes and compile-argv mapping. It never runs
GHC, a producer or a target. It does **not** replace the native gates below.

## Full integration gate

Build separate before and candidate producers with the same toolchain. For the
low-level ordinary GHC producer the maintained explicit mode is:

```sh
# Run the appropriate checkout's script for each source snapshot.
python3 -B tools/shared/build.py --bootstrap-only --optimization 2 \
  --ghc /absolute/ghc-9.14.1 --cc /absolute/cc \
  --build-dir /absolute/fresh/producer
```

The default non-bootstrap-only builder also installs native standard-library
tools; that broader operation is not an implicit prerequisite of this control
runner. Any generated-source refresh must use the maintained pipeline and retain
its verification, rather than hand-authoring a successful receipt.

Prepare one fresh **current** canonical builtin pair through the ordinary crate
entrypoint, using the same common absolute prefix for both producers. The full
runner independently admits that actual disk pair against the committed current
literal and seven malformed/mismatch controls on **both** producers. Observed
pair hashes are used for immutability, not learned expected semantics. Historical
P3 builtin hashes are intentionally not substituted for the current representation.

```sh
python3 -B tools/performance/c4-local-transaction/run_controls.py \
  --source-base /absolute/before-source \
  --producer-base /absolute/before-producer \
  --source-candidate /absolute/candidate-source \
  --producer-candidate /absolute/candidate-producer \
  --builtin-prefix /absolute/common/builtin \
  --output /absolute/fresh/c4-full-controls
```

Output must be outside all source and producer trees. It must not exist, even as
a dangling symlink. Use a common output parent for cooperating runs: its unchanged
`SerialLock` serializes this runner. Do not run competing heavy jobs. Limits are
fixed at 5 GiB process-tree RSS, 6 GiB per-process address space on Linux, 3 GiB
host available memory, 4 GiB free disk, 16 GiB work size and six hours per command.
The shared helper's documented macOS qualifications remain limitations, not
Linux-equivalent resource enforcement or a newly tested platform claim.

Every ordinary `.hi/.o` is authenticated, physically copied and kept immutable;
only explicitly listed control modules and replacement Main may compile. Actual
compile log origins and original link argv are checked. The second layout build
must compile **only Main**. Original producers are authenticated again after all
controls. Command logs, failures, generated specs, raw query reports and actual
checked artifacts are retained. No failed output is deleted, resumed or replaced.
Query keys are implementation-dependent; complete ordered groups and actual raw
checked artifact bytes are compared without normalization.

## One-producer focused CI gate

An existing authenticated candidate producer is sufficient for the complete graph
control inventory, avoiding a second compiler build merely for CI:

```sh
python3 -B tools/performance/c4-local-transaction/run_controls.py \
  --focused-only \
  --source-candidate "$PWD" \
  --producer-candidate /absolute/current-o2-producer \
  --output "$RUNNER_TEMP/c4-focused-controls"
```

Optionally provide `--builtin-prefix` to run the current disk-builtin admission
too. Without it, the producer's maintained builtin verification is authenticated,
but this runner does not claim a separate supplied-pair admission. Focused mode
always executes PublicControls + C4 28 + all 216, including failures, rollback and
demand probes. It **does not** run the two-producer nine-file comparison, a fresh
544-group target or a performance cohort. Local full-gate evidence is separate.

## Receipts and claim boundaries

Full receipts have `format: c4-full-current-controls-v1`. Successful full admission
requires `complete`, `all_controls_passed`, `full_gate_passed`,
`focused_graph_gate_passed`, `nine_file_comparison_passed`,
`builtin_admission_passed` and `immutable_inputs_verified_after` all literally true,
with exactly nine completed `file_cases`.

Focused receipts use `c4-focused-current-controls-v1`: `complete` means only the
requested focused scope completed. `all_controls_passed`, `full_gate_passed` and
`nine_file_comparison_passed` remain false. Consumers must check the format/scope,
not a lone `complete` field. The receipt binds actual source roots, producer paths,
producer receipt hashes, source contracts, ordinary toolchain, common builtin
prefix, every command and input/output hashes. Process durations are incidental
guard records, **not performance samples**.

## Separate, bounded fixed-14 correctness qualification

Only after the **full two-producer gate** above completes, an explicit additional
command may qualify the original fixed module slice:

```sh
python3 -B tools/performance/c4-local-transaction/qualify_fixed14.py \
  --controls-receipt /absolute/completed/c4-full-controls/receipt.json \
  --output /absolute/fresh-disjoint/c4-fixed14-qualification
```

This separately authored runner consumes the actual full receipt, rechecks its
input/output and producer identities, and requires a fresh disjoint output tree.
The original 81-file fixture inventory and ordered 544-group projection remain
unchanged. It prepares common current dependencies, independently validates their
objects, and requires one fresh before inference and one fresh candidate inference:
**544 fresh / 0 reused each**, absent initial target caches, exact ordered groups
and actual whole checked-output byte equality. The supplied current builtin's full
literal/checked admission replaces only the inapplicable historical pair hash;
historical fixed-ref reproduction retains its original byte oracle.

The fresh cache directory must contain exactly the 544 distinct lowercase SHA256
report keys named `<query_key>.mlfq`, plus exactly two source-defined sidecars:
`query-key.new` and `.lock` (546 files total). The directory and every entry are
checked with `lstat`: no symlink, subdirectory, device, FIFO or arbitrary extra
file is admitted. The lock file must be empty. `query-key.new` must hash to the
**last ordered report key** on that same side. The actual `--compile-crate` entry
in `bootstrap/MLF/Entry/Emlf.hs` calls `CrateSession.compileSpecFile`. Both that
sealed-session route and the separate public `CrateQuery.hs` route write this
scratch file before each digest/cache publication and never remove it. Their
enclosing lock operation creates `.lock`, and the host releases it by close without writes
or unlink. Empty lock contents do not prove lock ownership or process termination;
the unchanged process runner still supplies the normal-exit/descendant guard.
Compiler-dependent query keys need not match across before/candidate. No cache
entry is deleted or normalized to make an inventory pass.

Provider, target and final GHC native launch requests/completions are saved before
their postchecks, with separate `native_launch_requested`, `native_completed`,
`phase` and `postchecks_complete`
fields. A successful native command followed by a failed cache/artifact check
therefore remains visibly executed but **unqualified**, not an empty target list
or an accepted sample. The initial integration attempt exposed the old harness's
incorrect total-directory-count assumption after a normal before execution;
that failed attempt is retained and must not be resumed or relabelled successful.
An initial launch request does not prove that a child started: the unchanged
runner may refuse on its pre-launch resource guard. The actual command receipt
and successful completion are recorded separately.

Its GHC control checks the frozen closure/dependency reuse boundary, requiring
14 freshly compiled targets and 56 unchanged reusable dependency modules. These
are bounded correctness checks, **not a new timing cohort or speedup estimate**.
The command is not implicitly executed by either focused or full controls.

The controls receipt pins this entire directory, including documentation and
qualification scripts. **Do not edit it or write subsequent test results here
after the full gate begins.** Put all actual receipts, logs and later reports in
fresh external directories; do not refresh pins to conceal a change.

The existing A1 integration gate, other PR gates and required CI remain separate
responsibilities. These finite checks do not establish full compiler,
native-platform or self-hosting qualification. Large historical evidence,
toolchains, binaries, objects and target caches are intentionally not committed.
