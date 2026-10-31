# Sparse selection of predecessor contracts — discovery candidate

Historical first sparse-selector experiment: **not adopted as a standalone candidate**. Its exact candidate and 79-control source snapshot is archived under `.mlf-build/owned-source-context-20261101/previous-candidate/`. The later combined implementation was subsequently authorized for integration as a structural improvement; see [the follow-up report](../owned-reservation/README.md). The fixed discovery experiment did not establish an improvement in dependency-chain growth. Do not report the point estimates below as confirmed speedups or a change in overall asymptotic complexity. No extra samples were added to seek significance.

The baseline is `48275901cd7b760cc8dd000ed54898a23a494a87`. Two owned parsed-file operations now look up the ascending set of referenced names instead of filtering the full predecessor map: prepared-group bindings and the source-contract portion of the query key. Sorted order, missing-name omission, duplicate handling and complete key bytes are retained. The contract and encoding maps must have identical domains and current values; initialization and the same left-biased finalized deltas maintain this invariant. Missing encoding entries still fall back to structural encoding.

Public structural `prepareGroup`, `makePrepared`, and key encoders retain the former traversal and partial-value demand behavior. The sparse route is selected only by the drivers that own the synchronized finite contract/cache maps. The change does not reuse target inference, remove validation, or change compiler flags. `contractOverloads`, protection-map construction, and filtering source/support declarations remain; this is not elimination of every full scan.

The builtin literal was regenerated through the current nongenerated `builtin-prelude` generator. Its bytes differ only in the embedded source identity; the following ordinary build verified the candidate and exact regeneration. The first build correctly rejected the stale identity and remains archived. A subsequent benchmark preflight had a wrong baseline producer path; it failed before any sample and was corrected. Neither failure is a performance sample.

## Fixed experiment, 2026-11-01

Two chain families, sizes 8/32/128/512. Each cell has one predeclared ABBA or BAAB block: two ordinary fresh builds per MLF version, **32 total**. A separate pass in the same session collected two GHC builds per cell, **16 total**. GHC is a descriptive reference, not a paired noise correction. Both compile the identical shared source to a native executable; fixed builtin/primitive/runtime dependencies are reusable. The MLF endpoint is the standard `crate-bootstrap-v1` worker using an ordinary GHC 9.14.1 `-O2` producer and serial ordinary Clang `-O2`, not the installed `emlf SOURCE -o` endpoint.

The table shows seconds, median of two observations (their arithmetic midpoint).

| Chain / implementation | 8 | 32 | 128 | 512 |
|---|---:|---:|---:|---:|
| Annotated / baseline MLF | 0.870 | 1.003 | 1.670 | 4.108 |
| Annotated / sparse MLF | 0.846 | 0.980 | 1.466 | 4.034 |
| Annotated / GHC | 0.620 | 0.641 | 0.687 | 1.006 |
| Inferred / baseline MLF | 0.873 | 0.942 | 1.484 | 4.186 |
| Inferred / sparse MLF | 0.872 | 0.941 | 1.485 | 4.053 |
| Inferred / GHC | 0.629 | 0.688 | 0.659 | 1.057 |

At 512, descriptive geometric whole-run time reductions are **1.77% annotated / 3.13% inferred**. Frontend times are 2.753→2.692s and 2.852→2.766s, respectively. These observations are consistent with a small local benefit, but do not establish it independently of noise. The annotated-128 observations vary substantially (baseline 1.840/1.500s, candidate 1.360/1.572s); none was removed. The 128→512 whole-run increment per function increases 5.35% for annotated chains and decreases 4.93% for inferred chains. The mixed directions and sparse samples do **not** support claiming an improved growth curve. No confidence interval is assigned.

[Growth curves and individual observations](growth-20261101.png) · [SVG](growth-20261101.svg) · [Exact results and raw receipt identities](results-20261101.json)

## Correctness and retained evidence

- Independent full frozen `CrateQuery` and `SourceInference` from the baseline, with only module headers renamed and pinned in `oracle.json`.
- O0 and O2: **79 controls each**, including actual group preparation, complete keys, sorting/absence/bound names, public partial-value behavior, multiple synchronized deltas with replacement, and successful finalization.
- All 32 timed builds: the complete expected ordered group inventory, **zero reused groups**, raw `.mlfci`/`.mlfco` comparison with independent references, and three closed-form executable outputs. All 16 GHC executables also passed those output checks.
- Ordinary shared-source O2 build and canonical builtin verification passed. This typechecks current source with GHC; its `--check-shared` check parses/resolves shared source and is not a current-source MLF self-bootstrap.
- Retained validation and malformed-builtin boundary suites passed; the refreshed lock passed the actual `mlfpkg --locked plan` check without being rewritten. Its first attempt was stopped by the work-directory guard because the runner scanned the whole experiment directory; a separate bounded validation output corrected the scope, with the same resource limits. This was outside performance sampling.
- Metadata adapter tests: 18 Patricia and 34 A1 tests passed. Old pinned manifests/oracles remain unchanged; the new migration and reversible driver projection affect source admission only, not runtime expectations.

This was a discovery candidate, not full production qualification: no new 711-group compiler cohort, full retained P1–P3/graph sweep, native installation build, or formal confirmation was scheduled for this source snapshot. This initial candidate was superseded by the archived follow-up experiments; the later combined implementation's integration decision and qualification are recorded in its own report. The useful next question was whether the remaining repeated environment-view construction or per-group source-list scan accounted for more of the frontend cost. This experiment does not assign that cost.

All raw commands, plans, full output comparisons, failures and receipts are in `.mlf-build/sparse-contracts-20261101/`. The exact-child/resource runner was unchanged. Queries were private and empty for every build; only runner-owned disposable query files were inventoried and removed between complete blocks.

Reproduce the descriptive report (requires matplotlib; existing analysis environment can be reused):

```sh
python tools/performance/sparse-contracts/analyze_curve.py \
  --workdir .mlf-build/sparse-contracts-20261101
```

Run the independent controls with a qualified ordinary O2 producer and a fresh output directory:

```sh
python3 -B tools/performance/sparse-contracts/run_controls.py \
  --producer "$PRODUCER" --source "$PRODUCER_SOURCE" --output "$FRESH_OUTPUT"
```
