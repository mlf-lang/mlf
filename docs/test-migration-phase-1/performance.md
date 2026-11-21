# Benchmarks and performance gates

Baseline `720dd649627fbf8b19c7447493a4fdf6fd05eb39`. Implemented, unverified.

| Baseline coverage | Framework coverage | Entry point |
| --- | --- | --- |
| Generator and transport pilot, with one paired GHC and MLF execution per coordinate | `compiler-shapes/correctness/<family>-<size>` from the same matrix and oracle inputs, with a distinct `baseline-0` when selected | `compiler-shapes-correctness` |
| Default paired shape sweep, 125 coordinates and 1,500 measured compilations. PR profile has 13 coordinates at size 8 and 156 measured compilations | Correctness and `compiler-shapes/comparison/<family>-<size>` from the same executed coordinate. Plan and evidence identify endpoint, compiler receipts, actual samples and checked inputs | `compiler-shapes` with `sweep`, `run` or `all`. Developer `bench shapes`, the targeted PR check and the manual workflow use this adapter |
| Separate installed before/after/GHC comparison, including fresh, warm and shared-leaf-edit paths | `compiler-shapes-installed/{correctness,comparison}/<family>-<size>[-edited]` with the original lane and state matrix | `compiler-shapes-installed` |
| Ten Benchmarks Game workloads, each with its independently checked small inputs on C, baseline MLF and candidate MLF | `benchmark-game/correctness/<workload>` records each manifest workload. Correctness-only selection retains the same independent executables and expected outputs | Developer `bench apps --check-only` or `application-benchmarks --exact` |
| Fresh-runtime application timing and separate native packaging gate | `benchmark-game/performance/<workload>` retains both threshold dimensions, fresh samples, default-input checks and tool identities. Release still requires all ten workloads, seven samples and the 3× compile and 2× runtime limits | `application-benchmarks` for local selection and `benchmark-game` for the qualified macOS arm64 release route |
| Installed default-driver application benchmark | `benchmark-installed/{correctness,performance}/<workload>` retains the tool and installation receipts, five measured pairs, and the excluded correctness warmup | `application-benchmarks-installed` |
| Shape contract, sweep, cancellation, data-shape, rank-shape, and growth regressions | Existing Python unittest identities under the six shape control suites. Source-defined and inherited test inventories are discovered by unittest in Phase 2 | `tools/dev.py check-tools` for its existing platform-specific subset, with `compiler-shapes-fit-growth` also available directly |
| Benchmark verifier, provenance and transition controls | 27 gate controls, manifest and pin checks, one case per patch reconstruction, current transition and reconciliation unittest identities, and the frozen predecessor unittest identities (6 for DeclId and 33 for main per Python mode). The provenance shell still owns setup and cleanup | `benchmark-gate-controls`, `benchmark-provenance`, `benchmark-transition-controls`, `benchmark-reconciliation`, and `benchmark-predecessor-{declid,main}` |

Harness still owns the independent benchmark-oracle and native process controls
defined in `Tests.BenchmarkSuite`. Splitting correctness and timing evidence
lets the application runner report a successful correctness case alongside a
failed performance limit. The measured paths use their existing optimization,
pairing order, fresh build scopes, timing boundaries and independent baselines.
Existing `results.json`, `gate.json`, cohort plans, receipts, CSV and Markdown
remain the consumers' evidence. The framework report is a sibling artifact.

## Expected saving and Phase 2 measurement

One immutable correctness stdin file now serves the three languages for each
workload/input pair. All three executables still run separately. The ten
workloads prescribe 46 small-input values, giving 46 preparations in the
candidate and 138 in the baseline. The three FASTA-consuming workloads
contribute 14 of those values and should require 14 small FASTA generator
launches in place of 42. The pinned fixture oracle also runs once per
workload/input where applicable. Focused numeric runs avoid building an unused
FASTA generator. The installed endpoint still finds the checked stdin in its
existing `checks/mlf/<size>/stdin` location.

Correctness and comparison IDs in a measured shape invocation share the same
compilation results and independent output checks. No paired samples, shape
builds, application timed builds, per-sample runtime warmups, or clean cache
boundaries were removed. The measured shape adapter reports evidence after each
coordinate and does not call the pilot again. The sweep indexes scheduled cases
by ID rather than searching the generated list for every leg. The expected
shape savings are limited to outer orchestration.

With the same host, compiler producer, cache state, and selection, compare the
baseline and candidate setup wall time separately from the raw timed samples.
Count FASTA generator starts, fixture reads, compilation starts and process
counts. Compare compiler-shape preparation, recorder/adapter startup,
and per-leg timings separately. Report the added evidence-writing cost along
with saved setup work. No elapsed-time saving has been measured.

## Phase 2 commands

Run these from the candidate checkout. Assign `PHASE2_CANDIDATE` and
`PHASE2_BASELINE` to the absolute paths of the independently built native
compilers and `PHASE2_CLANG` to the absolute path of Clang. Use distinct,
fresh build/output directories for baseline and candidate. Select exactly the
same families, sizes, repeat count, flags, workload tools, inputs and host for
matching baseline comparisons.

```sh
python3 -B tools/testing/run.py compiler-shapes --list
python3 -B tools/testing/run.py application-benchmarks --list -- --check-only
python3 -B tools/testing/run.py benchmark-game --list
python3 -B tools/testing/run.py benchmark-provenance --list
python3 -B tools/testing/run.py benchmark-predecessor-declid --list
python3 -B tools/testing/run.py benchmark-predecessor-main --list --python-optimization
python3 -B tools/dev.py check-tools
python3 -B tools/testing/run.py compiler-shapes-fit-growth
python3 -B tools/testing/run.py compiler-shapes-contract \
  --exact compiler-shapes/contract/LanguageFeatureShapeTests.test_wide_case_batch_detects_missing_or_swapped_interior_arms
python3 -B tools/testing/run.py compiler-shapes-contract \
  --exact compiler-shapes/contract/AnalyzerTests.test_rejects_missing_sample
python3 -B tools/testing/run.py compiler-shapes-cancellation \
  --exact compiler-shapes/cancellation/RecorderCancellation.test_public_launcher_cancels_its_recorder

python3 -B tools/testing/run.py compiler-shapes --exact compiler-shapes/comparison/wide_case-8 \
  -- sweep --workdir .mlf-build/phase2-shape-pairs --family wide_case --size 8 --repeats 6
python3 -B tools/testing/run.py compiler-shapes-correctness --exact compiler-shapes/correctness/wide_case-8 \
  -- --setup .mlf-build/phase2-shape-pairs/setup/setup.json --output .mlf-build/phase2-shape-pilot
python3 -B tools/testing/run.py compiler-shapes -- sweep \
  --workdir .mlf-build/phase2-all-shapes --prune-build-products
python3 -B tools/testing/run.py compiler-shapes-installed -- \
  --before "$PHASE2_BEFORE_INSTALL" --after "$PHASE2_AFTER_INSTALL" \
  --output .mlf-build/phase2-installed-shapes --size 16 --repeats 3 --diamond-edit

python3 -B tools/testing/run.py benchmark-migration-contract
python3 -B tools/testing/run.py benchmark-gate-controls
python3 -B tools/testing/run.py benchmark-gate-controls --exact benchmark-gate-controls/missing-timed-sample
python3 -B tools/testing/run.py benchmark-gate-controls --exact benchmark-gate-controls/native-ratio-exceeds-limit
python3 -B tools/testing/run.py benchmark-provenance
python3 -B tools/testing/run.py application-benchmarks --exact benchmark-game/correctness/regex-redux \
  -- --candidate "$PHASE2_CANDIDATE" --baseline "$PHASE2_BASELINE" --clang "$PHASE2_CLANG" \
  --output .mlf-build/phase2-regex-check
python3 -B tools/dev.py bench apps --check-only \
  --candidate "$PHASE2_CANDIDATE" --baseline "$PHASE2_BASELINE" --clang "$PHASE2_CLANG" \
  --output .mlf-build/phase2-app-checks
python3 -B tools/testing/run.py application-benchmarks --exact benchmark-game/performance/binary-trees \
  -- --candidate "$PHASE2_CANDIDATE" --baseline "$PHASE2_BASELINE" --clang "$PHASE2_CLANG" \
  --output .mlf-build/phase2-app-limit-fault --samples 3 --compile-limit 0.000000001
python3 -B tools/testing/run.py application-benchmarks-installed -- \
  --compiler "$PHASE2_INSTALLED_COMPILER" --install-receipt "$PHASE2_INSTALL_RECEIPT" \
  --install-timing "$PHASE2_INSTALL_TIMING" --oracle "$PHASE2_ORACLE" \
  --baseline-dir "$PHASE2_CHECKED_BASELINE" --check-dir .mlf-build/phase2-app-checks \
  --clang "$PHASE2_CLANG" --output .mlf-build/phase2-installed-apps
```

The deliberately low limit command should write a failed performance verdict
and exit nonzero. The verifier mutation cases should pass because the independent
gate rejects the bad receipt in each case. For the installed workload commands,
provide the authenticated installed builds and the independent checked baseline,
oracle program and installation receipts described in the
[application benchmark guide](../../tools/bench/README.md#default-executable-build-comparison).

On the native release host, provision and verify the candidate using the
`benchmark-game` job in `native-qualification.yml`, then use the same measured
step and verify the legacy receipt in the uploaded artifacts.

```sh
tools/release/time-stage.sh benchmark-game python3 -B tools/testing/run.py benchmark-game \
  --report .mlf-build/test-framework/benchmark-game.json
```

Baseline comparisons use `python3 -B tools/dev.py check-tools`,
`python3 -B tools/dev.py bench shapes`, the existing `bench.py all` and
`run.py --pilot` for matched shape routes, `python3 -B tools/dev.py bench apps`
with the same arguments and `tools/release/run-benchmarks.sh` in the pinned
checkout. Compare all framework results with the original per-coordinate,
per-workload and per-sample evidence. On the candidate, interrupt a focused
cohort after its first start event and check the inherited signal, partial
evidence and child cleanup. Verify the PR and manual artifact uploads carry
both the old results and the framework receipt on failures as well as success.

Assumptions to verify include native MLF acceptance of the event-writing
callbacks, immutable stdin handling on the qualified platforms, supervised
cancellation through the new outer dispatcher, actual frozen unittest
discoveries matching their declared source methods, and measurable setup
savings. The original fatal setup or subprocess errors may leave a started
case with no result. The dispatcher must classify those runs as incomplete and
retain the exact exit and legacy diagnostic. Direct invocation of low-level
preparers and analyzers remains available for evidence tooling.
