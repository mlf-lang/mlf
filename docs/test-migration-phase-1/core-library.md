# Phase 1 handoff for TupleList, Core, regex and int-set unions

Baseline `720dd649627fbf8b19c7447493a4fdf6fd05eb39`. The suites below are implemented, unverified. Every command in this handoff is for Phase 2. Use separate checkout-local build, report and cache directories for the baseline and candidate. Run with GHC 9.14.1 and the same Clang, GMP, GC, platform and job limits on each revision.

## TupleList

The default `tuple-list` executable currently runs the 105 IDs previously exposed through `--framework`. The ordered public IDs are in `tools/testing/tuple-list-active-contract.json`; the direct gate derives its counts from this inventory. This file contains no historical source hashes or migration counts. The recorded 305 old observations and their migration contract are archived in Git at `496dcae024cae1a93096d9bdb9d6b93e57359dc0`; see the [retirement and historical reproduction guide](../testing-history-retirement.md). They map to the cutover's 105 IDs because the grouped arity ID represents 201 observations. It covers three parser assertions for each arity from 2 to 64 and independent type and target checks after compilation at arities 2, 3, 15, 16, 63 and 64 under both syntax profiles. The parser-provenance, scope, erasure, independent target, negative-phase and diagnostic controls retain their original inputs and assertions.

The seven `*-runtime` IDs retain their own runtime results. Each preceding type ID and its runtime ID share one lazy compilation result for the identical source. Full registry execution should make seven compilation calls for these fourteen cases, compared with fourteen in the old opt-in registry and seven in the legacy default. Exact selection should force only its own fixture. The main module uses the shared options by default and accepts `--framework` and `--framework-list` as compatibility aliases. Its successful no-argument text retains `Tuple/list focused checks passed.`. Setting `MLF_TUPLE_LIST_REPORT` on that invocation also writes the JSON Lines report. The legacy module is recoverable at the pinned baseline. Routine CI can collect default text and the report in the same hosted `-O0` invocation instead of executing default and registry suites separately. The self-built release qualification path and independently specified interpreter/LLVM fixture retain distinct purposes.

Run the following on each checkout. Use the `--framework` selectors on the baseline when comparing registry results, and capture the baseline no-argument success lines separately to reconcile the 305 observations. On the candidate compare ordered inventory and results to the reviewed contract.

```sh
mkdir -p .mlf-build/phase2
python3 -B tools/shared/build.py --optimization 0 --build-dir "$PWD/.mlf-build/phase2/ghc-o0"
bin="$PWD/.mlf-build/phase2/ghc-o0/bin"
MLF_TUPLE_LIST_REPORT="$PWD/.mlf-build/phase2/tuple-list.jsonl" "$bin/tuple-list"
"$bin/tuple-list" --framework-list --format json > .mlf-build/phase2/tuple-inventory.jsonl
"$bin/tuple-list" --framework --exact tuple-list/focused/tuple-projection --format json
"$bin/tuple-list" --framework --exact tuple-list/focused/tuple-projection-runtime --format json
"$bin/tuple-list" --framework --exact tuple-list/focused/tuple-arities-2-through-64 --format json
bash tools/release/test-tuple-list.sh "$bin/emlf" "$PWD/.mlf-build/phase2/tuple-native"
```

`framework-direct` runs current framework, registry, CLI and producer checks
through [the maintained direct gate](../../tools/shared/test_framework_direct.py)
and [active ID contract](../../tools/testing/tuple-list-active-contract.json).
The Tuple/list migration and dated inventory audits have been removed from the
current tree and registries. Review them in the archived checkout described in
the [retirement guide](../testing-history-retirement.md).

Adding current cases updates only the active ID inventory and actual tests; it
does not rewrite the cutover or the 305-observation historical record. The Python
gate controls exercise this separation in a source archive without `.git` or
the historical audit files. Actual language semantics still require the compiled
suite above.

In a disposable candidate checkout, change the expected type for the projection leaf from `int` to `bool`, change the runtime result from `42` to `41`, then change a grouped arity AST expectation. Run the same exact selection after each separate mutation and require a failed case with its own ID. Restore each mutation before proceeding. Use a counter at `compileRuntime` and time the grouped parsing and compilation blocks separately in equivalent temporary instrumented builds. After provisioning an authenticated source-matching self-built candidate in the standard release layout, run `MLF_CI_SHARED_CANDIDATE=1 bash tools/release/qualify-tuple-list.sh`. Verify the marker, producer hashes, interpreter/LLVM outputs and release receipt in the same run.

## Core

The four physical partitions and compatibility `core` executable use one registry. `tests/Tests/CoreRegistry.emlf` maps the 746 reviewed legacy action labels to stable IDs in 35 families, with that order checked against the catalog and `tests/golden/unit-inventory.json`. This baseline already includes the amendments after the older 739-action inventory. The 13 substring IDs preserve the old predicates and contribute 13 to the full `substring-executed` metric without adding legacy execution rows. The HM oracle retains 6,712 prescribed terms, 1,712 exhaustive runs and 4,991 distinct runs among 5,000 seeded terms. The annotation corpus retains 126 programs. The grouped ID and named metric retain the independent oracle evidence. The int-set Core identity remains `core/int-set-unions/size-biased-set-unions-agree-with-independent-sorted-lists`.

All four partition-to-family mappings remain unchanged. Baseline `--list-families`, `--families` and compatibility executable `--from` use the registry. Use `--list`, `--exact`, `--tag`, `--format` and `--report` for normal framework selection. `--framework` and `--framework-list` are aliases. `MLF_TEST_CASE_REPORT` supplies a destination for family runs. `--framework-child` supports discovery or one exact worker action under the supervisor. Recoverable parser, type, module, graph, optimizer and library assertions run in process. IO actions with legacy fatal assertions and intentionally poisoned solver/runtime paths have supervised children. Each supervised action retains raw output, its validated child report, measurement data and `outcome.json`. The v1 process transport marks cleanup evidence unverified. It does not attest descendant cleanup. The parent still validates the exact partial partition case, metric and family reports and aggregates only the validated union. A partition's v1 coverage report is partial. An interrupted action leaves incomplete evidence and its status and raw diagnostics are available in its invocation directory.

Static counts predict 704 in-process and 55 supervised leaves in the full registry. This avoids 704 child starts compared with the old opt-in scheduler. The old direct-default path ran all actions in the partition process and had no child isolation at the case level, so count and measure the 55 added starts separately in that comparison. Focused families still build only their owning physical partition. One immutable helper serves the isolated leaves; the normal hosted path should reuse its campaign helper. Keep separate crate scratch roots and preserve the checked target and independent oracle calls.

Once the hosted compiler is built as above, provision the build runner and retain its path. Use the same build command in each checkout. The baseline `--framework-list` and `--framework` options remain usable for discovery and exact comparison.

```sh
bin="$PWD/.mlf-build/phase2/ghc-o0/bin"
export MLF_COMPILER="$bin/emlf" MLF_PACKAGE_MANAGER="$bin/mlfpkg"
export MLF_BUILD_RUNNER="$bin/mlf-build-runner"
clang -O2 -std=c11 -Wall -Wextra -Werror runtime/mlf_build_runner.c -o "$MLF_BUILD_RUNNER"
"$MLF_PACKAGE_MANAGER" --locked --compiler "$MLF_COMPILER" --manifest tests/mlf-package.json \
  --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --build-dir "$PWD/.mlf-build/phase2/suites" \
  build --target core-crates --target core-solver --target core-language --target core-modules \
  --target core --target regex --target int-set-unions
suites="$PWD/.mlf-build/phase2/suites/bin"
for shard in core-crates core-solver core-language core-modules; do
  "$suites/$shard" --framework-list --format json > ".mlf-build/phase2/$shard.inventory.jsonl"
done
"$suites/core-language" --framework --exact core/substring-adapter/prefix --format json
"$suites/core-language" --families core/substring-adapter core/guards
"$suites/core" --from 'example files'
"$bin/compiler-tests" select --family core/hm-oracle --family core/substring-adapter \
  --compiler "$MLF_COMPILER" --manager "$MLF_PACKAGE_MANAGER" --build-dir "$PWD/.mlf-build/phase2/core-focused"
"$bin/compiler-tests" unit --compiler "$MLF_COMPILER" --manager "$MLF_PACKAGE_MANAGER" \
  --build-dir "$PWD/.mlf-build/phase2/unit"
python3 -B tools/testing/run.py release-core-registry-controls
bash tools/release/verify-unit-evidence.sh .mlf-build/phase2/unit
```

The current [Core descriptor contract](../../tests/golden/core-registry-contract.json)
is checked against the [current catalog](../../tests/test-catalog.json) by
`release-core-registry-controls`. Executable discovery and actual case reports
are checked by `Tests.CompilerTests` and `verify-unit-evidence.sh`. The retired
source-transcription audit is available only in the historical checkout; it is
not a prerequisite for these checks.

For baseline exact selection, first provide `--work-dir "$PWD/.mlf-build/phase2/core-process" --host-tool "$PWD/.mlf-build/phase2/host-support"` after `--framework`, with `host-support` built by `clang -O2 -std=c11 -Wall -Wextra -Werror tests/native/host_support.c -o .mlf-build/phase2/host-support`. Interrupt a full candidate run after observing its first start event and check the absence of a complete summary. In a disposable checkout, change the `prefix` substring expectation and run `core-language --families core/substring-adapter`. Require failure and observable later substring cases. Compare package build receipts and child launch counts for the full and focused commands, and time setup and run phases separately. Requalify the same aggregate with the source-bound self-built release tools after the hosted comparison. Validate the older v1 partial coverage contracts and check isolation startup cost on each required POSIX platform.

The standalone recursive-inference checks now use the shared runner. The typeclass compatibility entry selects the same class IDs. The combined module entry preserves twelve existing Core IDs, the canonical query ID and one registry inventory check. The inventory source is also independently runnable as a single case without executing Core actions. Execute on both revisions with the hosted compiler and all source roots, then compare retained selections and results.

```sh
roots=$(jq -r '.source_roots[] | select(. != "host/ghc") | "-i " + .' shared-sources.json)
mkdir -p "$PWD/.mlf-build/phase2/recursive"
export MLF_TEST_WORK="$PWD/.mlf-build/phase2/recursive"
"$MLF_COMPILER" $roots -i tests/recursive-inference --run tests/recursive-inference/RecursiveInventoryDiscovery.emlf
"$MLF_COMPILER" $roots -i tests/recursive-inference --run tests/recursive-inference/RecursiveModuleCompatibility.emlf
"$MLF_COMPILER" $roots -i tests/recursive-inference --run tests/recursive-inference/TypeclassCompatibility.emlf
```

## Regex and int-set unions

`regex` preserves all 56 IDs from `tests/golden/unit-inventory.json` through the normal framework. They include 17 generated invalid-pattern cases in the original counted metric and the separately authored nested-empty repetition rejection. Expected offsets, counts, boundary cases and replacements remain independent. Seven repeated immutable pattern compilations and the repeated 200-character subject share preparation. Full passing regex execution is expected to reduce 59 compile calls to 52. Coverage counts attempted/passed registry actions and still records `invalid-patterns-executed = 17` on a full success. The legacy success line stays available in text mode.

`int-set-unions` retains `int-set/union-sorted-list`, ordering its 360 prescribed inputs, deduplicating to 276 distinct sorted-list oracle comparisons and checking balancing. Core uses the same action without the old `toLegacy` exit adapter. The standalone executable keeps its distinct CLI selection obligation. Share only immutable stimulus construction, with no expected reduction in oracle calls.

Use the `suites` built above. On the baseline the direct regex executable supports the full run only. The candidate adds standard discovery, exact selection and JSON reporting. Record a baseline full run by setting `MLF_TEST_COVERAGE_REPORT` on the command; verify the complete candidate JSON Lines and coverage reports separately.

```sh
MLF_TEST_COVERAGE_REPORT="$PWD/.mlf-build/phase2/regex.coverage.jsonl" "$suites/regex"
"$suites/regex" --list --format json > .mlf-build/phase2/regex.inventory.jsonl
"$suites/regex" --exact regex/invalid/reversed-range --format json
"$suites/regex" --exact regex/match/later-alternative --format json
"$suites/regex" --report "$PWD/.mlf-build/phase2/regex.jsonl"
"$suites/int-set-unions" --list --format json
"$suites/int-set-unions" --exact int-set/union-sorted-list --format json
"$suites/int-set-unions"
"$suites/core-solver" --families core/int-set-unions
```

In disposable checkouts, change the match offset for `regex/match/later-alternative` and introduce a discrepancy in the int-set reference comparison. Require the focused cases to fail and a full regex invocation to continue reporting later cases before returning nonzero. Compare pattern compile counts and immutable setup time separately from execution. Re-run the framework CLI contract in the unit campaign for exact, unknown and nonmatching selectors.

## Receipt adapters for host and query controls

These entries support discovery and stable exact selection. The focused report covers the requested ID. Specialized evidence retains the setup commands and subprocesses that were needed to reach it.

| Entry | Coverage retained | Expected focused saving |
| --- | --- | --- |
| `shared-host-adapter` | Optimization, argument, locale, filesystem, cancellation and deliberate failure observations. The `--gc-root` cases retain platform compiler availability. | Only the selected fixture binary is built, and each binary is reused by its existing full-mode observations. |
| `recursive-saved-crate` | Six exact, source-bound direct-module and saved/reloaded crate comparisons, including independent target and rejection oracles. | Builds one harness and executes one fixture pair. The builtin directory stays private to this invocation and is shared across the six fixtures in full mode. |
| `query-graph-acceptance` | Existing `--case`, `--smoke`, recovery, and unfinished resume procedures, with source and binary identities. | One authored control and its original independent rebuilds or recovery steps. |
| `source-query-api` | Existing graph, source, named source-change versions, copied-definition, session transaction and optional cross-executable formal observations. | Runs only the selected family or the selected version lineage. Earlier versions in the same lineage still establish the incremental state. |
| `source-context-cache` | Forty full command IDs and the existing 29-command legacy mode, including independent live owner/lock probes, cold/warm cache oracles, and the concurrent pair. | Runs the phase's dependency chain. A lock-probe or concurrent control keeps both processes, a warm phase keeps its earlier cold run, and an unrelated cold, memo or window chain is omitted. |

For Phase 2, use writable fresh subdirectories and existing source-matching GHC build receipts. Inspect both the framework report and producer receipts or sealed stdout, including prerequisites and observed failure status. The exact compiler/process counts and runtime savings remain unmeasured. If a prerequisite or a post-run oracle fails before a selected verdict is established, expect the outer command to fail and the selected case to remain incomplete.

```sh
runner=tools/testing/run.py
mkdir -p .mlf-build/phase2/receipts
python3 -B "$runner" shared-host-adapter --list
python3 -B "$runner" shared-host-adapter --exact shared-host/contracts-O0 -- \
  "$(command -v ghc)" --output .mlf-build/phase2/receipts/shared-host-one
python3 -B "$runner" recursive-saved-crate --list
python3 -B "$runner" recursive-saved-crate --exact recursive-saved-crate/cross-module-recursion-infers-unsigned-cycle -- \
  --compiler-build .mlf-build/phase2/ghc-o0 --build-dir .mlf-build/phase2/receipts/crate-one
python3 -B "$runner" query-graph-acceptance --list
python3 -B "$runner" query-graph-acceptance --exact query-graph-acceptance/body -- \
  .mlf-build/phase2/ghc-o0/bin/emlf .mlf-build/phase2/receipts/query-one
python3 -B "$runner" source-query-api --list
python3 -B "$runner" source-query-api --exact source-query-api/source-change-body-1 -- \
  .mlf-build/phase2/ghc-o2/receipt.json .mlf-build/phase2/receipts/source-query-one
python3 -B "$runner" source-context-cache --list
python3 -B "$runner" source-context-cache --exact source-context-cache/lock-after-session -- \
  --build-receipt .mlf-build/phase2/ghc-o0/receipt.json --output .mlf-build/phase2/receipts/context-one
```

Repeat the execution commands without `--exact` in fresh output directories. Use `--gc-root GC_PREFIX` with the shared-host list and execution on the provisioned native runner. Include `--interface BUILT_OBJECT` with the source-query list and execution in the existing cross-executable rehearsal. Run the source-context qualification inside its established outer resource guard. Compare grouped-oracle setup and elapsed time separately from the underlying probe, maintaining their existing process and cache freshness boundaries.
