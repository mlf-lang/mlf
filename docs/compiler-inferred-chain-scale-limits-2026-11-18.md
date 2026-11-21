# Inferred chain: larger-size boundary and fixed marks, 2026-11-18

No compiler change is retained. The current shape remains `inferred_chain`
(unsigned monomorphic dependency chain), and its original acceptance result
remains five of six checks. The fitted-exponent confidence gate is still open.
The [current-source formal cohort](compiler-inferred-chain-metadata-2026-11-17.md)
is unchanged; these experiments neither replace it nor supply extra samples to it.
Evidence is under `.mlf-build/inferred-chain-large-scale-20261118`.

## Extended-scale diagnostic

Using the unchanged authenticated metadata-receipt producer, the existing
`compiler-shapes` harness scheduled four alternating pairs at N0/1024/2048/4096/8192,
40 source-to-executable compiles at the same `crate-fused-v1` endpoint. Resource
limits and the rule to retain a failure and skip that case's remaining legs
were fixed before running.

The cohort completed with 18 successful compiles and 54 independently checked
native outputs. MLF at N2048, N4096 and N8192 failed with exactly
`cyclic/deep query graph`; 19 remaining scheduled legs were skipped by the
original failure rule. No time, RSS, work-directory or disk guard fired for
these failures. They are not timing samples, and no larger-range fit is made.

This is the existing logical query-graph depth contract, not a newly introduced
compiler regression. The [earlier two-stage report](compiler-two-stage-phases-2026-11-15.md)
already recorded the same guard at N1536/2048. Each source dependency contributes
multiple query nodes, so the logical graph reaches its limit before the source
contains 4096 functions. `QueryGraph.visit` memoizes longest suffix heights and
checks the 4096 bound in both lexical root orders. Existing independent tests
accept 4096 nodes and reject 4097, including when an already completed tail
would otherwise conceal the longer path.

The planned larger-size profiles were not executed: there are no accepted MLF
reference outputs at those sizes. The failed commands, receipts and exact
diagnostics are retained. Supporting longer chains would require a deliberate
cache-contract/validation change, rather than increasing a benchmark limit.
This investigation preserves all existing limits and formats.

## Fixed-cardinality marks experiment

Inspection found that `resolveClosure` allocates a growable `IndexVec.Builder`
for marks even though it already knows the exact number of graph nodes. A private
shadow changes only that table to `FixedBuilder` with `fixedFilled`, `fixedGet`
and `fixedSet`. It retains the same indexed graph, traversal, height memoization,
read order, stale/dangling/cycle diagnostics and depth boundary. No root source,
primitive ABI, builtin identity, lockfile or cache schema changed. Generations
retain the correct hash of their own compiler binary; all independently decoded
query rows match across the two compilers.

The shadow passes current declaration/query cache controls, 1,032 ordered SCC
and reach comparisons with graph/package controls, exact legacy/v2 query
roundtrips, 4096/4097 checks in both key orders, referenced/codec work budgets,
and cold/warm publication with all failpoints and retained-payload/generation
hash checks. Fixtures are built using coherent `ghc --make` source closures and
Core lint. One initial driver attempt compiled/linked the existing Graphs fixture
successfully but was marked failed because the runner rejects any stderr and
GHC emitted default `x-partial` warnings for its existing head/tail uses. A separate
driver suppresses only that warning; the initial receipt remains intact.

One warmup plus six alternating measured pairs at each N0/256/1024 yield 42
diagnostic compiles and 126 correct native outputs. Interface, object and LLVM
bytes exactly match the existing reference. These are compiler-plus-Clang
subprocess measurements; the compiler segment is reported separately.

| Size | Compiler before / candidate (ms) | Compiler + Clang before / candidate (ms) |
| ---: | ---: | ---: |
| 0 | 131.083 / 129.254 | 274.484 / 273.695 |
| 256 | 175.056 / 178.454 | 318.445 / 317.159 |
| 1024 | 310.557 / 312.330 | 454.755 / 455.793 |

Three separate RTS-instrumented pairs at N0/1024 give the following N1024 medians
in bytes. Instrumented times are excluded, and all artifacts/LLVM remain exact.

| Measurement | Before | Candidate |
| --- | ---: | ---: |
| Total allocation | 848,839,944 | 849,641,296 |
| Maximum live heap | 10,609,600 | 10,609,624 |
| GC copied | 90,754,176 | 91,009,080 |
| Individual peak RSS | 60,866,560 | 60,751,872 |

Reject this private candidate. Replacing the growable header looks simpler at
source level, but this build allocates about 0.8 MB more and has no peak-live
improvement. The N256 and N1024 compiler medians regress. There is no justified
root implementation to put through a new formal GHC acceptance cohort; do not
repeat this unchanged candidate or its screen.

## Continuing boundary

No acceptance commit/push or next-shape transition occurred. The maintained
compiler and preexisting edits remain unchanged. Native compiler self-bootstrap
and installed CLI qualification gaps are unchanged. Finite fitted exponents
must not be presented as proofs of asymptotic complexity, and the existing depth
limit restricts extrapolation beyond the accepted measurement range.

Continue with larger growing construction costs in the same shape. The preceding
authenticated fresh profile attributes about 18.7 ms / 70.0 MB of growth to
`OpenFragment.makePackage` and 13.25 ms / 54.25 MB to `QueryGraph.encodeHashed1`.
Revisit the unimplemented shared-body model as a possible way to reduce repeated
construction; its earlier byte/node estimates are hypotheses, not speed claims.
Any new representation needs exact reconstruction, identity, admission-limit,
cache compatibility and native-output controls before adoption.

## Evidence receipts

- `diagnostic/plan.json`: `836319f7bc462adef122ff9f845eede77e5d6d3eb17f8c84eb79374334271fd7`
- `diagnostic/receipt.json`: `17dca3c452764fe020a0eca0ec1c79a754e3f6437f1d54c66ba40ad771aa609e`
- `diagnostic-command.json`: `202ec943f46d6df47d1b3e34b02ed3454df955e974b24360457d3a49ae4fecca`
- `diagnostic-classification.json`: `b6e400139559620d7a1c89d24291317c9e1c1cc08fc946aa9bef4c1dd5292ca3`
- `fixed-marks/receipt.json`: `c4d446a3d0e42c30fdfa2277640c8fdf91884cecd1ae158c1eb3671c5671a583`
- `fixed-marks-controls/receipt.json`: `7331c67a559c5e208abd0d0353a8811ce7107d43ad1236b26b3623334163f1c2`
- `control-driver-diagnostic.json`: `b8ddf5ce13132f99107faa3a81491f6aba99d8a35dd38c9af1d9a89bbe41d627`
- `fixed-marks-controls-qualified/receipt.json`: `9cf02b3c3c855f70624aad717de4e5e377bbd8aed944afc7d084e3bd02a54374`
- `fixed-marks-screen/receipt.json`: `b4475fa567b1bfbb05ad7e13f558e82d6a47cdb4a5e2473cc76d9dcf10387e57`
- `fixed-marks-memory/receipt.json`: `596e987be3c9f2b72041ee488f597e69949c2608583afafd5020bfe863996390`
- `fixed-marks-decision.json`: `96e4654cdb48b18bb11a0ed9bd3f21d5391139734f6446535df6e8ee1496275d`
