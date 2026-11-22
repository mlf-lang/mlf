# Figure 12, parity corpus and direct language checks

Baseline `720dd649627fbf8b19c7447493a4fdf6fd05eb39`. Phase 1 used source and manifest inspection. All commands below are for Phase 2.

For the candidate commands, run from the candidate root. These variables keep the GHC producer, native executable builds, and receipts local to each checkout.

```sh
P2="$PWD/.mlf-build/phase2-language"
HOST="$P2/ghc"
mkdir -p "$P2"
python3 -B tools/shared/build.py --bootstrap-only --optimization 0 --build-dir "$HOST"
clang -O2 -std=c11 -Wall -Wextra -Werror runtime/mlf_build_runner.c -o "$HOST/bin/mlf-build-runner"
export MLF_BUILD_RUNNER="$HOST/bin/mlf-build-runner"
```

## Figure 12

The native `figure12` target maps 43 expression labels in 34 paper rows to `figure12/paper/<label>`. It keeps A8 as a documented difference between the paper and the compiler, with the phase and protected-type diagnostic validated. The 36 supplementary checks map to 29 `figure12/assumption/<index>`, four semantic `figure12/type/...` and three `figure12/repair/<label>` IDs. The labels, expressions, result types, diagnostic checks, and erasure oracle come from the existing fixtures. `A12.1` shares with `A10.1`, and `E3a` shares with `A12.2`. An exact selection can run either alias on its own. Full native runs retain the historical coverage ledger, alias edges, metrics and completion lines. There is one native registry behind the no-argument, list and selected forms.

The authenticated direct GHC adapter adds its independent free-name visitor's four positive and nine phase-boundary rejection controls to the 79 corresponding suite cases. Its `figure12-direct/` prefix identifies the distinct hosted producer and oracle adapter. It retains the exact inventory digest authorization for both the old and registered fixture sources, the GHC object and transport authentication checks, and raw capture and verification receipts. It replaces 79 per-control/inspection child launches with one case batch. The batch shares 41 distinct paper compilations across the 43 labels and preserves individual timeouts. Native PR smoke uses the 16 independent and backend checks of its own registry and drops its duplicate run of the native Figure 12 campaign. Routine direct Figure 12 uses the hosted `-O0` producer once.

```sh
"$HOST/bin/mlfpkg" --manifest tests/mlf-package.json --compiler "$HOST/bin/emlf" \
  --runtime "$PWD/runtime/mlf_runtime.c" --build-dir "$P2/suites" build --target figure12
"$P2/suites/bin/figure12" --list --format json --report "$P2/figure12-inventory.jsonl"
"$P2/suites/bin/figure12" --exact figure12/paper/A8 --format json --report "$P2/figure12-A8.jsonl"
"$P2/suites/bin/figure12" --exact figure12/paper/A12.1 --format json --report "$P2/figure12-alias.jsonl"
MLF_TEST_COVERAGE_REPORT="$P2/figure12-coverage.jsonl" "$P2/suites/bin/figure12"
python3 -B tools/testing/run.py figure12-direct --list
python3 -B tools/testing/run.py figure12-direct --exact figure12-direct/type/A2-principal \
  --report "$P2/figure12-direct-focused.json" -- --build-receipt "$HOST/receipt.json" --output "$P2/figure12-direct-focused"
python3 -B tools/testing/run.py figure12-direct --report "$P2/figure12-direct.json" -- \
  --build-receipt "$HOST/receipt.json" --output "$P2/figure12-direct"
python3 -B tools/shared/test_figure12_data.py
```

Run the baseline `figure12` binary and baseline `python3 -B tools/shared/test_figure12_direct.py --build-receipt "$HOST/receipt.json" --output "$P2/figure12-direct"` in its own checkout, with the same producer flags. In a disposable candidate checkout, change the expected A2 principal type in `tests/Tests/Figure12Suite.emlf`, rebuild `figure12`, and run `"$P2/suites/bin/figure12" --exact figure12/type/A2-principal --format json --report "$P2/figure12-wrong-type.jsonl"`. Confirm the A2 failure and nonzero status, then restore the intended expectation. Compare list IDs, actual result/alias records, two phase-specific protected failures, full 36 supplementary actions and both target oracles. Measure actual child launches from the hosted receipt's `commands` arrays and compare elapsed campaign time separately from fixture compilation and linking. Verify that native shared actions evaluate the identical compilation once per canonical label in a full process.

## Parity corpus

Frozen corpus IDs gain the `parity/` prefix and retain their original row ID in the raw batch. Listing reads the authenticated archive manifest. Execution prepares the existing authenticated exported corpus, including 179 API projections, two reviewed crate-cycle migrations, and regenerated HM, annotation and paper inputs. The 7,086 prescribed rows have 3,204 accepts and 80 rows with independent interpreter and LLVM runtime observations. The 11 existing same-input-and-oracle aliases remain tied to the same canonical source. Full receipts retain the previous `verification.json` parity counters and alias metadata. The audit can trace each typed result to its exported row and to its target, diagnostic, independent checker captures, or backend files under the build directory. The routine hosted CI artifact includes raw interpreter and LLVM stdout and stderr, including failed cases, so the output can be compared to the independent oracle without guessing from the exit status.

The routine campaign uses the GHC-built `compiler-tests`, `mlfpkg`, and `emlf`, checks the `-O0` build receipt, and compiles the native build runner for package work. The compiler's internal batch path calls the same source compilation, target printer and checker as the corresponding CLI actions. It replaces 7,075 source CLI processes and roughly 3,200 candidate checker CLI processes with one producer invocation. One separate target checker batch retains the independent oracle for ordinary rows and the independently prescribed crate-cycle references are still checked as separate observations. Runtime paths retain the distinct fresh interpreter, LLVM emission, Clang link and native execution processes. Runtime setup is skipped for a selection that contains no runtime row.

```sh
parity() {
  run_dir=$1
  shift
  "$HOST/bin/compiler-tests" parity --compiler "$HOST/bin/emlf" --manager "$HOST/bin/mlfpkg" \
    --compiler-receipt "$HOST/receipt.json" --build-dir "$P2/$run_dir" "$@"
}
parity parity-inventory --list --format json --report "$P2/parity-inventory.jsonl"
parity parity-focused --exact parity/figure12-A8 --format json --report "$P2/parity-A8.jsonl"
parity parity-reference --exact parity/module-reject-000025 --format json --report "$P2/parity-reference.jsonl"
parity parity-full --format json --report "$P2/parity-full.jsonl"
```

Baseline comparison uses its self-built `compiler-tests`, `emlf`, `mlfpkg` and build runner. From the baseline checkout, execute `MLF_BUILD_RUNNER="$BASE_BIN/mlf-build-runner" "$BASE_BIN/compiler-tests" parity --compiler "$BASE_BIN/emlf" --manager "$BASE_BIN/mlfpkg" --build-dir "$P2/parity-full"`. Check baseline/candidate exported manifests and alias rows, count compiler/checker process launches, and compare the 80 interpreter and 80 LLVM outputs/statuses against their prescribed values. Count source/target work separately from compiler setup and native runtime executions. Change one prescribed type and remove one observed worker row in isolated Phase 2 copies before repeating the full comparison. Interrupt the candidate during its compile batch and inspect `parity/compile.jsonl`, the absent completion summary and `verification.json`'s incomplete state. Confirm the native and GHC routes match pretty-printed target bytes, diagnostics and both backend traces. Confirm large batch resource behavior on the routine host and validate archive listing and runtime driver dependencies on the required platforms.

## Direct language and smoke

The standalone native PR smoke binary maps the four independent target observations to `pr-smoke/target/...` (identity, let, IO, and malformed-before-effects) and 12 existing backend labels to `pr-smoke/backend/...`. The selected backend fixtures still run both interpreters/drivers under the existing native matrix audit. The five hosted source-smoke assertions use framework cases and preserve the exact text, artifacts and progress read by the shell supervisor. The guest-interpreted compatibility route still runs the same five observations against the distinct guest producer. The shell imports individual hosted results and the guest runner’s completed PASS lines, while retaining its existing exit behavior. The direct shared frontend entry registers the existing parser/declaration/recursive frontend partition and two native semantics partitions, plus the old focused recursion and formatter selectors. The existing raw file grammar input route stays available. The direct candidate driver imports its pre-existing supervised cases, including the three frontend phases, and excludes its two C setup commands from coverage. It retains nested receipts for specialized cases. Recursive-managed (24), field projection graph (18), source field layouts (55), common calls (23), callback sharing (35), guest framework (5), and guest state laws (4) import covered rows from their existing independent expectations and authenticated receipts.

The native PR smoke matrix binary drops its copy of Figure 12. The standalone
native smoke campaign still invokes the shared Figure 12 registry once under
its distinct producer, while ordinary hosted CI runs the hosted registry once. It preserves cold/warm source-cache pairs, dedicated nonzero guest controls, native driver evidence, Haskell-host authentication, compiler ownership, and batch partitions. Reporting-only changes do not imply a saving inside the independent controls. For PR timing, compare the full checkout pipeline and the elapsed time to the last required job, then compare producer builds, reports and time to the first failing row separately.

```sh
MLF_SOURCE_SMOKE_RUNNER="$HOST/bin/source-smoke" MLF_SOURCE_SMOKE_RECEIPT="$HOST/receipt.json" \
  python3 -B tools/testing/run.py source-smoke --report "$P2/source-smoke.json"
"$HOST/bin/shared-frontend" --list --format json --report "$P2/shared-frontend-inventory.jsonl"
"$HOST/bin/shared-frontend" --exact shared-frontend/recursive-inference --format json
"$HOST/bin/source-smoke" "$PWD/tests/pr-smoke" "$P2" --exact source-smoke/malformed-before-effects --format json
python3 -B tools/testing/run.py direct-candidate --report "$P2/direct-candidate.json" -- \
  --bin-dir "$HOST/bin" --build-receipt "$HOST/receipt.json" --output "$P2/direct-candidate"
python3 -B tools/shared/build.py --bootstrap-only --optimization 2 --build-dir "$P2/ghc-O2"
for suite in recursive-managed parameter-field-graph source-field-layouts common-calls callback-sharing guest-framework guest-state-laws; do
  python3 -B tools/testing/run.py "$suite" --list
  python3 -B tools/testing/run.py "$suite" --report "$P2/$suite.json" -- \
    --build-receipt "$P2/ghc-O2/receipt.json" --output "$P2/$suite"
done
"$HOST/bin/compiler-tests" pr-smoke --compiler "$HOST/bin/emlf" --manager "$HOST/bin/mlfpkg" --build-dir "$P2/pr-smoke"
```

Run baseline commands using the same flags and their direct scripts. Compare the old logs, nested receipts and CI job selection with the candidate's reports. In isolated copies, change the expected hosted source-rejection diagnostic, provide a malformed target contrary to its independent assertion, and force a hosted backend or optimized driver to exit unsuccessfully. Re-run the matching commands above and inspect which case IDs failed or remained incomplete. The hosted frontend and native PR smoke retain existing grouped subchecks inside several registered actions and direct receipt adapters keep their suite-level fixture boundaries. Exact leaf selection is available for the converted Figure 12, parity, PR smoke and source-smoke binaries. The supervised shell source-smoke and grouped receipt adapters keep their full native invocations. Verify that the existing bounded frontend and optimizer routes retain their original producer identities, command logs, compatible output and exit semantics.

## Exact selection for receipt adapters

All eight receipt adapters expose their existing IDs before execution through `tools/testing/run.py SUITE --list`. The selected case still uses the authenticated producer and independent oracle. The direct candidate adapter executes one existing frontend phase, supervised process check, or delegated control. It retains the frozen full route and uses the same CRC, UTF-8 and candidate worker supervisors for those exact selections. The panic reaping check executes the panic fixture as a prerequisite and keeps both results in the receipt. The mixed guest framework compiles its Foundation crate as a prerequisite for the selected dependent crate. The guest state-law adapter runs only the selected positive or negative process. The host-side graph and optimizer checks evaluate the selected assertion. Source-field layout checks build the needed checked source or legacy artifacts and preserve cold/warm pairs when the selected assertion compares them. The managed-recursion adapter skips unrelated lanes. Its source cache case keeps the existing cold/warm and linked-target controls.

With `P2` and `HOST` from above, these commands exercise one case per adapter in Phase 2. Each focused result should name one selected test. Check the native receipts as well as the framework result to confirm only that case and its setup ran.

```sh
python3 -B tools/testing/run.py direct-candidate --list
python3 -B tools/testing/run.py direct-candidate --exact direct-candidate/panic-child-reaped \
  --report "$P2/direct-candidate-exact.json" -- --bin-dir "$HOST/bin" \
  --build-receipt "$HOST/receipt.json" --output "$P2/direct-candidate-exact"
language_case() {
  suite=$1
  id=$2
  python3 -B tools/testing/run.py "$suite" --list --exact "$id"
  python3 -B tools/testing/run.py "$suite" --exact "$id" --report "$P2/$suite-exact.json" -- \
    --build-receipt "$P2/ghc-O2/receipt.json" --output "$P2/$suite-exact"
}
language_case recursive-managed recursive-managed/raw-managed-recursion-first-signed
language_case parameter-field-graph parameter-field-graph/rigid-root-local-quantifier-is-eligible
language_case source-field-layouts source-field-layouts/checked-layout-key-retains-dead-quantifiers
language_case common-calls common-calls/raw-fresh-arrays-each-execution
language_case callback-sharing callback-sharing/kernel-anchors-reach-whole-cycle
language_case guest-framework guest-framework/distinct-custom-class
language_case guest-state-laws guest-state-laws/graph-build-negative
```
