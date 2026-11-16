# Local-problem diagnostic archive

GHC-only research against main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. This is diagnostic evidence, not an optimization patch or production/native qualification. Main and the user's PR were not changed.

## Contents
- `diagnostic.patch`: the two Solver observation sites and diagnostic CLI entry-point wrapper, using repository-relative paths.
- `Prototype/LocalProblemDigest.hs`: exact source-v4 helper.
- `FocusedMain.hs` and `expected-encoding-cases.tsv`: exact finite fixture and 26 synthetic token-stream expectations.
- `finite-results.json`: separately identified finite source-v3/source-v4 results.
- `diagnostic-results.json`: separate v3 repeat-screen and v4 action-WHNF observations, including the fixed size bins.
- `PINS.json`: source, producer and raw-evidence hashes, with no private locations.
- `BOUNDARIES.md`: demand, fingerprint, timing and sampling limits.

To reconstruct the diagnostic sources, apply the patch to the pinned baseline and add the supplied `Prototype/LocalProblemDigest.hs` on the GHC home-module search path. The standalone `FocusedMain.hs` is a separate finite-test entry point, not the ordinary compiler Main. This archive does not contain the original real input texts, binaries, toolchain or an execution controller; it is not a turnkey run harness.

The sanitized real-target argv template is:
```text
<DIAGNOSTIC_COMPILER> --no-prelude -i <INPUT_ROOT>/foundation --type <INPUT_ROOT>/root/CommonFoundationRoot.hs
```
These are explanatory placeholders, not the original absolute argv. The two real runs used the same fixed sixteen input texts. Both require exit 0, `Bool\n` and empty stderr.

## Findings
The v3 complete successful set contained 16,738 events. Fingerprint repeat candidates were small: the largest had 101 nodes, while all 3,419 events above 128 nodes had distinct keys. Excess candidate weight was 5.8546% of encoded words, not solver time or possible savings. Generic full-graph hash caching was stopped.

The v4 run adds input-size versus reported action-to-Either-WHNF intervals. Its final independent results are in `diagnostic-results.json`; no cost-savings estimate, optimization choice or cross-run speedup is inferred. Re-entry and lazy shared demand can overlap intervals. Do not divide their sum by target wall time as an exclusive phase share.

The next evidence question, if separately authorized, concerns a specific large-graph algorithm mechanism. This archive neither revives the cache direction nor authorizes more samples, observers or builds. See `BOUNDARIES.md`.
