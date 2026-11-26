# PR55 algorithmic optimizations

## Scope and baseline

This change integrates the ten requested optimizations into
`codex/pr55-algorithmic-optimizations`. The branch initially pointed to
`45ddd6da0f2488523fbf9f773a2bd83c5c78d1ea`; it was first advanced to the
observed PR55 head, `94e086c15c40aaf220c764f0e723cc3cfe627587`.

Three optimizations were already present at that head. They are retained and
tested, rather than counted as new implementations in this patch. Measurements
against `94e086c` therefore measure the additional changes. The row-accumulator
comparison against its older append implementation is labeled separately.

| # | Production path | Integration |
|---|---|---|
| 1 | `LLVM.Analysis.captureIndexed` | Retain upstream caller-dependent propagation and set-valued summaries; compare with an independent whole-table fixed point. |
| 2 | `LLVM.Analysis.letBodyDemands` and Codegen | Retain upstream lexical let-spine summaries; check each cached suffix and demand barrier. |
| 3 | `ArtifactStorage.sameBytes` | Use exact bulk byte equality through GHC, interpreter and native runtime implementations. Across crate jobs, reread each file and compare its current bytes with the published snapshot. |
| 4 | `Parser.operatorReferenceSpan` | Record token endpoints for infix and parenthesized operator references, including qualified and split tokens. |
| 5 | `Surface.normalizeRow` | Retain upstream cons/reverse construction; check complete patterns, RHS rewriting and Fresh state. |
| 6 | `Elaborate.boundsAtIndexedUsing` | Share structural postorder ranks within a solved context when strict descendants have unique incoming type edges; keep root-local DFS for shared DAGs. |
| 7 | `Graph.Solver.commonLocalBinderPath` | Align ancestor-path depths and return the existing common suffix with a linear walk. |
| 8 | `ImportedRoot.evidenceTemplate` | Compare stable first occurrences against the full quantified prefix using IntSet membership. |
| 9 | `CrateQuery.encodeType`, `encodeKind`, `encodePredicate` | Keep source types, kinds and predicates in a length-carrying builder until one final render. |
| 10 | `LLVM.Analysis.appendDemand` | Share ordered concatenation trees, cache flattened lexical aliases and filter later leaves with indexed identities without forcing future summaries. |

The generic parser `pWithSpan` remains available for general syntax ranges. The
new endpoint helper addresses the operator-reference hotspot without changing
the parser state representation. The quantified-bound optimization deliberately
uses the old traversal for graphs whose sharing invalidates a global rank.

## Preserved behavior

Demand summaries retain numeric name identity, the first occurrence's hint,
the original first-force order, and the complete/incomplete boundary. A leaf
supplied through the existing `EntryDemand` constructor retains its internal
duplicates. The implementation does not inspect a following summary merely to
produce the first name of the preceding one.

Independent review found both an empty-demand alias DAG that could expand
exponentially and a subtree-index lookup that could demand a later summary too
early. The final traversal shares flattened lexical alias leaves and delays each
leaf identity set until its names have been consumed. Regressions include 256
levels of let and default-case aliases, complete and incomplete summaries,
nested failing summaries and partially defined following leaves. Ordinary
concatenations traverse their structure once, plus indexed membership costs.
An alias chain whose demanded-name prefix keeps growing still materializes each
shared prefix; this is not a claim of linear work for every alias DAG.

Source query framing retains all constructor tags, ordered fields, quantifier
flags and Unicode scalar lengths. An initial builder version inspected a later
syntax node before an earlier failing field. The final builder forces the
current field length before matching the tail, restoring the previous first
diagnostic. Eight partial-input tests cover this ordering as well as complete
Unicode and nested-type byte comparisons.

Evidence-only imports still require every quantified binder, in canonical
first-occurrence order. Reordered or missing binders use the ordinary path and
preserve its result or diagnostic. Public import tests compare checked output
and identities with the ordinary graph route, including valid duplicate
occurrences and fallback cases.

## Byte equality and compatibility

`byteArrayEqual :: ByteArray -> ByteArray -> IO Bool` is appended as opcode
**137**. Existing opcodes **0–136** retain their meanings. The primitive ABI is
`mlf-primitive-138-v13`; the builtin interface is
`mlf-primitive/shared-haskell-v1/18`. The wire framing and schema layout do not
change. The explicit primitive contract and unknown-code boundary now cover
138 entries and reject code 138. The Lexer and shared-source manifest both
identify builtin interface version 18, including prepared-library schemas.

The action demands the left array and then the right array when executed,
checks their lengths, and compares their complete current contents. Constructing
or discarding an action does not force either operand. GHC retains both pinned
owners across the safe foreign call; native code follows the same IO ordering.
No hash or digest can substitute for exact equality. As with other mutable-array
operations, callers synchronize concurrent writes when they require a stable
snapshot; retained metadata arrays are private immutable snapshots.

The graph loader indexes canonical paths and admitted crate identities as it
walks dependencies in postorder. Within one ordinary link it passes the admitted
graph directly to object checking. Between jobs, a dependency can be replaced
at the same path, even with a file of the same length. Reuse therefore checks
the bytes read from the current file. For larger regular files the reader uses
the open file's observed length to size its buffer and still reads through EOF.

Generated LLVM requires `mlf_require_byte_array_equal_abi`, preventing linkage
against a runtime without the new primitive. The builtin Prelude was generated
from the actual checked producer and then independently regenerated and compared
by the normal build gate. All six maintained package locks were refreshed and
their locked plans checked. A real six-module prepared library was compiled,
reopened and admitted; its generated registry schema and artifact hashes were
checked against the manifest, including interface version 18.

The frozen artifact fixture was extended only with the new primitive's explicit
tree/graph roundtrips and the next rejected opcode. Its recorded hash was updated
for that reviewed append-only change.

## Validation

The final producer uses GHC 9.14.1 with `-O2`,
`-fstatic-argument-transformation`, `-fpedantic-bottoms` and `-fno-state-hack`.
The full build checks exhaustive patterns and records direct source resolution
for 142 shared modules and four GHC adapter modules. The shared MLF frontend check, compiler
identity check and exact builtin regeneration gate passed.

The integrated `tests/indexvec/Graphs.hs` program passed its existing graph,
query and package controls and all five new optimization modules:

- `OptimizationLLVM`: more than 12,000 expression comparisons, every lexical
  suffix, skewed/balanced demand orders, aliases and capture fixed points.
- `OptimizationInference`: all 64 four-node DAGs in both child orders with
  reachable candidate subsets, shared/repeated edges, sparse IDs, aliases,
  solved translations, 4,096 ancestor-path pairs and actual local unification.
- `OptimizationFrontend`: 1,578 parser prefix comparisons, infix/error states,
  normal source spans, and mixed/wide row normalization with exact Fresh state.
- `OptimizationCrates`: every source type/kind/predicate variant, Unicode and
  nested framing, first-error order and checked public import behavior.
- `OptimizationMetadata`: exact cache reuse, same-size modifications, changed
  lengths, restoration and missing-file rereads through `readInterfaceRetaining`.

Ormolu 0.9.0.0 compatibility passed **106/106** maintained/fixture pairs and
all five harness controls with an unchanged input snapshot. The primitive
qualification passed **224 commands**: 45 exact byte/mutation vectors on each
of GHC, interpreter, native O0 and native O2; four demand checks per lane; host
pinned-owner GC controls; and 12 direct native-runtime modes.

The compiler-shapes suite passed **200 tests**, including **152 contract tests**
and the new checks for matching each compiler with its own primitive ABI. The artifact admission
control suite passed **45 tests**. The three new shape generators additionally
passed **126 executions** at sizes 0, 1, 2, 3, 4 and 8 with signed Int64 edge
inputs, checked against an independent operation-by-operation Python oracle.

Two stale test-harness assumptions were corrected without changing production
behavior or weakening acceptance thresholds: the thunk-allocation detector now
recognizes the runtime's fused `.fill.N` and `mlf_thunk_new` names, and reduced
artifact-library coverage is tested at the production crate-planning boundary
that actually enforces it. Both original failures were reproduced on `94e086c`.

The maintained demand/force-order gate passed **79 interpreter cases and 158
native O0/O2 cases**, retaining every output/error oracle and allocation
threshold. Its three allocation-detector controls also passed. The final
producer was authenticated before and after the gate. The maintained concat
gate also passed its GHC checks, 45 interpreter cases, 90 native O0/O2 cases
and 24 direct runtime cases, including the updated primitive inventory.

## Production-helper measurements

These probes compile the same driver against the actual modules in two
checkouts. They measure CPU time in the named production operation. They are
not end-to-end compilation times or a claim that MLF compiles faster than GHC.
The baseline is `94e086c`, except for the separately labeled historical row
accumulator. GHC is 9.14.1; LLVM-analysis probes use O1, other groups use O2.
Groups are separate measurement windows and are not pooled.

| Operation and size | Baseline median | Candidate median | Observation |
|---|---:|---:|---|
| Exact metadata comparison, 8 MiB | 20.977 ms | 0.526 ms | 39.8× for comparison alone; file IO excluded. |
| Parse 4,096 operator bindings | 704.209 ms | 42.304 ms | 16.65× through production module parsing. |
| Source arrow encoding, 4,096 levels | 37.734 ms | 7.846 ms | 4.81×, complete output checksum preserved. |
| Source forall encoding, 2,048 levels | 31.801 ms | 10.166 ms | 3.13×. |
| Qualified source encoding, 2,048 levels | 22.852 ms | 6.601 ms | 3.46×. |
| Sparse quantified bounds, 2,048 | 865.734 ms | 8.986 ms | About 96×; allocation 3.625 GB → 18.826 MB. |
| Dense quantified bounds, 2,048 | 829.532 ms | 8.587 ms | About 97×. |
| Balanced ordered demands, 16,384 names | 1.169 s | 42.878 ms | About 27×; separate baseline/candidate windows. |
| Left-skewed ordered demands, 16,384 names | 17.08 s | 35.746 ms | About 478×; separate baseline/candidate windows. |
| Right-skewed ordered demands, 16,384 names | 38.44 s | 18.929 ms | About 2,030×; separate baseline/candidate windows. |

Some controls are neutral or slower. The complete evidence-import path at size
128 was effectively unchanged (856.017 ms → 856.233 ms), so the indexed
first-occurrence change is not presented as an observed end-to-end speedup.
The isolated 4,096-let summary control increased from 3.01 ms to 3.74 ms;
the 4,096-level fixed-prefix alias control increased from 17.02 ms to 18.65 ms.
Capture-chain controls were approximately unchanged. The common
binder-path probe improved substantially, but the candidate is measured in tens
of microseconds and excludes input construction; that ratio is not an overall
compiler result.

Raw repetitions, source identities, probe/executable identities and limitations
are in `tools/performance/pr55-optimizations/*-results.json`. The older
`frontend-results.json` also includes the historical append-accumulator
comparison; it is not a before/after PR55 row-normalization result.

## End-to-end compilation

The maintained `compiler-shapes/bench.py` harness is used with the
`crate-fused-v1` endpoint. Identical generated source is compiled to native
executables by the final GHC-hosted MLF compiler, an independently rebuilt
`94e086c` compiler, and GHC. Each compiler uses its own prepared builtin and
runtime; this setup happens outside the timed region. Cross-ABI substitution
is rejected by the harness. An earlier cohort using shared ABI inputs failed
and is excluded from performance claims. Executables are checked against independent output
oracles. This endpoint includes source-to-LLVM and LLVM-to-executable stages;
it is separate from an installed or self-hosted compiler campaign.

The selected families are `parenthesized_operator_sites`, `wide_pattern_rows`,
`ordered_worker_demands`, `forwarded_worker_capture`, `quotient_let_chain` and
`polymorphic_import_spine`. All 108 fresh compilations and 324 executable oracle
checks passed, followed by candidate and baseline provenance authentication.
The ratio of candidate/GHC median full compilation wall times was below one in
all 12 cells (0.122–0.439). Full wall time includes the common worker launcher,
source-to-LLVM and Clang/link; prepared dependencies are outside this interval.

At size 64, the candidate/reference median wall ratios were 0.851–0.972 across
all six families. At size 16, five observed medians were slower (1.024–1.125);
the capture family was approximately unchanged at 0.990. Three size-64 families
also used more peak build RSS than the baseline. Three repetitions and two sizes
do not establish an asymptotic growth result or eliminate timing noise. These
are reduced workloads, not a measurement of full self-host compilation.

Full compilation wall-time medians in seconds (three runs per cell):

| Family | Size | Baseline `94e086c` | Candidate | GHC |
|---|---:|---:|---:|---:|
| `parenthesized_operator_sites` | 16 | 0.3124 | 0.3513 | 1.0090 |
| `parenthesized_operator_sites` | 64 | 0.3499 | 0.3260 | 0.9258 |
| `wide_pattern_rows` | 16 | 0.3345 | 0.3625 | 0.8916 |
| `wide_pattern_rows` | 64 | 0.5005 | 0.4260 | 0.9700 |
| `ordered_worker_demands` | 16 | 0.3124 | 0.3409 | 0.9505 |
| `ordered_worker_demands` | 64 | 0.3677 | 0.3574 | 0.9984 |
| `forwarded_worker_capture` | 16 | 0.3248 | 0.3215 | 1.0539 |
| `forwarded_worker_capture` | 64 | 0.4020 | 0.3755 | 3.0902 |
| `quotient_let_chain` | 16 | 0.2968 | 0.3108 | 0.9341 |
| `quotient_let_chain` | 64 | 0.3403 | 0.3129 | 0.9296 |
| `polymorphic_import_spine` | 16 | 0.2954 | 0.3026 | 1.0009 |
| `polymorphic_import_spine` | 64 | 0.3125 | 0.2991 | 1.1018 |

These are medians of total build time. The JSON also records each full sample
and separate source-to-LLVM and LLVM-to-executable phase medians; phase medians
need not sum to the total median.

The complete sample and stage-median table is recorded in
`tools/performance/pr55-optimizations/end-to-end-results.json`, separately from
the helper timings.

## Reproduction

Use the repository's required GHC 9.14.1, Clang, GMP and BDWGC toolchain. The
recorded native runs used Clang 19.1.7 and BDWGC 8.2.8. Each verifier/benchmark
requires a fresh output directory. The general probe runner below uses O2;
to reproduce the separately recorded LLVM-only O1 cohort, compile `LLVM.hs`
with the flags recorded in `llvm-results.json`.

```sh
git worktree add --detach ../mlf-pr55-baseline 94e086c15c40aaf220c764f0e723cc3cfe627587
python3 tools/shared/build.py --bootstrap-only --optimization 2 --build-dir .mlf-build/pr55-final
python3 tools/shared/test_formatter_compatibility.py --ghc ghc --ormolu ormolu --output .mlf-build/pr55-format-repro
python3 tools/shared/test_byte_array_equal.py --build-receipt .mlf-build/pr55-final/receipt.json --output .mlf-build/pr55-bytes-repro --clang clang
python3 tools/performance/pr55-optimizations/check_prepared_schema.py --producer .mlf-build/pr55-final --output .mlf-build/pr55-prepared-repro
python3 tools/shared/test_ready_total.py --compiler .mlf-build/pr55-final/bin/emlf --gc-prefix "$MLF_GC_PREFIX" --output .mlf-build/pr55-demands-repro
python3 tools/performance/pr55-optimizations/run.py --baseline ../mlf-pr55-baseline --group crates --group inference --group llvm --group frontend --repeats 5 --output .mlf-build/pr55-probes-repro
```

For the exact end-to-end baseline, start from the clean delivered candidate
commit and recreate its changes in a separate checkout whose HEAD remains
`94e086c`. The runner selects dirty HEAD as the reference, so this pins the
baseline even after later commits are added to the optimization branch. It
leaves the original checkout unchanged. Use fresh worktree/output paths.

```sh
candidate_revision=$(git rev-parse HEAD)
git worktree add --detach ../mlf-pr55-end-to-end 94e086c15c40aaf220c764f0e723cc3cfe627587
git diff --binary 94e086c15c40aaf220c764f0e723cc3cfe627587 "$candidate_revision" | git -C ../mlf-pr55-end-to-end apply --binary -
cd ../mlf-pr55-end-to-end
python3 tools/shared/build.py --bootstrap-only --optimization 2 --build-dir .mlf-build/pr55-reviewed
python3 tools/performance/compiler-shapes/bench.py prepare --workdir .mlf-build/pr55-reviewed-shapes --producer .mlf-build/pr55-reviewed --build-builtin --ghc "$(command -v ghc)" --clang "$(command -v clang)"
python3 tools/performance/compiler-shapes/bench.py run --workdir .mlf-build/pr55-reviewed-shapes --cohort integration-16-64 --family parenthesized_operator_sites,wide_pattern_rows,ordered_worker_demands,forwarded_worker_capture,quotient_let_chain,polymorphic_import_spine --size 16,64 --repeats 3 --interleave-pairs
python3 tools/performance/compiler-shapes/bench.py analyze --workdir .mlf-build/pr55-reviewed-shapes --cohort integration-16-64 --label integration-16-64
```

The default full native unit/backend/self-host campaign is not claimed by the
targeted checks above. The task board and the compact validation record live in
`docs/performance/pr55-optimizations/`.
