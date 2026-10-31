# Parsed-source query encoding reuse

The parsed-source drivers retain encodings of predecessor contracts alongside the contract map. Each entry shares its encoded binding between group bindings, typed evidence candidates, and the complete source-contract encoding. A successful finalized group extends both maps with the same left-biased delta; candidate and binding types come from the same contract environment through `prepareGroup`. This ownership invariant permits reuse by name. Entries and their encoded fields remain lazy, so unused initial contracts and delta values are not forced.

Both parsed-source driver implementations carry the owned encoding pool. The public structural encoders retain their existing behavior, and the cache helpers fall back to structural encoding when an entry is absent. The encoding keeps the existing query key format and exact bytes, including ordered candidates, roles, classes, and protection flags. This change reuses encoding work, not inference results. It does not hardcode a candidate count such as 44. Repeated query-key file writes, digesting, and reads remain unchanged.

The independent controls compare complete keys and contract encodings against the retained frozen encoder at O0 and O2. They exercise type and name variants, ordered and repeated candidates, roles and protection, lazy unused values, missing-entry fallbacks, a real prepared group and a successful finalized contract delta. Historical validation controls invert the exact pinned, reversible contract-driver source edits, then the existing datatype-driver edits, solely to establish the retained source proof. They still run the unprojected candidate; the historical oracle and its expectations remain unchanged.

From the repository root, with an authenticated ordinary producer and its source snapshot:

```sh
python3 -B tools/performance/contract-context/run_controls.py \
  --producer "$PRODUCER" --source "$PRODUCER_SOURCE" --output "$FRESH_OUTPUT"
python3 -B tools/performance/patricia/test_adapters.py
python3 -O -B tools/performance/patricia/test_adapters.py
python3 -B tools/performance/a1-private-index/test_current.py
python3 tools/testing/check_manifest_snapshot.py
```

`FRESH_OUTPUT` must not exist. The last command is a static snapshot check; it does not replace the native locked package plan.

The datatype-only formal comparison reported -0.09% with a 95% confidence interval of [-0.66%, +0.48%]. Incremental exploratory measurements of the combined change reported 13.1% for the inferred-shape workload and 2.20% for the compiler workload. These exploratory figures are not final confirmation results.

## Results — 2026-11-01

The full candidate passed the frozen compiler acceptance rule: **1.58% time reduction**, nominal 95% block interval **[1.32%, 1.83%]**. Both ABBA and BAAB execution directions improved. There were 24 complete fresh compilations in six balanced blocks, with 711 fresh / 0 reused groups each; every checked artifact was directly compared as raw bytes with the independent reference. Descriptive medians were 47.278s before and 46.509s after. The primary estimand is the block-paired geometric ratio, not the ratio of those medians.

The secondary inferred-chain-512 check used eight new compilations in two balanced blocks, reduced from 24 **before any secondary sample**, following user feedback about excessive repetition. Its descriptive paired improvement was **14.16%**; medians were 4.579s and 3.908s. Each run had 515 fresh / 0 reused groups and passed raw-byte and three closed-form executable-output checks. No confidence interval or formal significance claim is assigned to this secondary check.

Both comparisons use committed `c1b802bd` as baseline, ordinary GHC 9.14.1 `-O2` default native installations, and a fixed local macOS environment. Shape programs use serial ordinary Clang `-O2`. The 711-group workload uses frozen historical target modules; it is not a fresh self-bootstrap of the edited compiler. The shared-source build typechecks current modules with GHC, while `--check-shared` parses/resolves them. Results are conditional on these binaries and inputs; they do not establish speed of an MLF-built compiler, cross-machine portability, or a new GHC comparison.

The full retained P1–P3, graph, balance, validation, builtin, file-cache, native-container, fingerprint, and direct-entry suites passed, as did the native locked package plan. Five Linux live-proc release controls are unavailable on macOS and are not claimed passed. The complete oracle is retained; source projections only establish historical source ownership.

See [machine-readable results](results-20261101.json) and [compiler time series and interval](confirmation-20261101.png). Raw plans, commands, logs, checked outputs, receipts, the unsuccessful datatype-only confirmation, and preparation failures remain under `.mlf-build/contract-encoding-20261101/` and `.mlf-build/datatype-context-only-20261031/`. The measurements use the unchanged `tools/performance/process-spawn/compare.py` and `analyze.py` runners. Discovery samples are excluded from the compiler confirmation.
