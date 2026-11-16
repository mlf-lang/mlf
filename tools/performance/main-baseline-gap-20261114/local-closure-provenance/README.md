# Local closure-provenance diagnostic

GHC-host research against baseline `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. This archive records one finite O2 gate and one separately admitted Root + Foundation `--type` diagnostic. It is not an optimization, performance comparison, production qualification or MLF native-backend qualification. The baseline checkout and PR were not modified by these isolated runs.

## What is here

- `diagnostic.patch`: the actual Solver diagnostic changes **and** the CLI entry-point change at `host/ghc/app/emlf/Main.hs`. The latter writes the capture after `runEntry` returns.
- `Prototype/LocalProblemDigest.hs`: exact diagnostic helper, including the physical-input fingerprint and metadata selector.
- `FocusedMain.hs`: exact synthetic finite fixture.
- `analyze_provenance.py`: bounded, read-only Python parser for the numeric capture. It validates schema, selection, conservation and optional ordered first-seven-field comparison; no compiler or target is launched.
- `finite-results.json`: the 14-record contract, retained artifact hashes and finite actual result.
- `real-results.json`: the independently checked real-run totals and per-site aggregates.
- `BOUNDARIES.md` and `PINS.json`: interpretation limits and exact identities.

The patch is relative to the named baseline repository. The helper must also be included in the GHC source roots as `Prototype.LocalProblemDigest`. `FocusedMain.hs` is a separate fixture entry point, not the CLI Main. Do not apply this on top of a previous digest overlay. This archive does not contain a turnkey build controller, toolchain, executable or private real input tree.

The measured CLI invocation, with path roles substituted, was:

```text
<DIAGNOSTIC_ELF> --no-prelude -i <FIXED_FOUNDATION_SOURCE_DIR> --type <FIXED_COMMON_ROOT>
```

Those placeholders denote the same preserved 16 source files and paths used by the preceding input-fingerprint diagnostic. They are not newly generated workloads or an invitation to combine results from different paths.

## Meaning of the diagnostic

The ordinary and prepared-fallback routes retain their original projection, local `G.unify`, guard and restoration order. Diagnostic sibling traversals add six strict first-discovery counters. A successful local action is evaluated to `Either` WHNF, then its complete **input** graph and equations are fingerprinted. Metadata is retained only for successful inputs containing 129 through 2,048 encoded nodes. All other accepted rows carry 16 literal `NA` fields.

The six origin buckets record whichever pending traversal edge **first discovers** a node: equation seed, fresh external seed, structural child, binder parent, structural parent, or binding child. The node partition is connected + added scopes + fresh nodes + hidden stubs. Direct equation/fresh/external set sizes are separate, overlapping observations. None measures necessary work or proves that a route can be removed.

The completed run has 16,738 successful rows, no Left rows and 3,404 metadata rows. Selected inputs contain 1,312,087 node occurrences summed across events: 1,218,852 connected, 31,043 added scopes, 25,433 fresh and 36,759 hidden stubs. Connected is about 92.9% of these selected node occurrences, not 92.9% of CPU or a savings estimate. These are not unique program nodes, allocations, CPU work or removable cost. Detailed values and exact source/producer/raw identities are in the JSON files.

The first seven fields match the earlier v4 capture row-for-row as original decimal strings. That qualifies route/order/input fingerprint consistency, not collision-free input equality. No old timing interval is imported into this run.

## Rechecking numeric data

For a separately available capture:

```text
python analyze_provenance.py capture.tsv --sha256 <CAPTURE_SHA256>
python analyze_provenance.py capture.tsv --sha256 <CAPTURE_SHA256> --reference-v4 earlier.tsv --reference-sha256 <EARLIER_SHA256>
```

The raw real TSV and real graphs are deliberately not published here. The script reports aggregate large integers as decimal strings and parses all input integers exactly. It does not turn hashes into equality proofs or turn interval sums into a performance result.

## Preserved stops

Source v1 was rejected before execution because its appended explicit module declaration lacked a separator and because the actual metadata selection gate was absent. Source v2 corrected both and added finite range/poison controls. The v1 static rejection is retained, not reclassified as a target failure or later pass.

The 14 finite records include only two complete original/new Solver-result comparisons. The metadata boundary records use synthetic identity actions and do not establish valid generated-program reachability. See `BOUNDARIES.md` before interpreting any result. No validation was deleted, no baseline compiler behavior was adopted, and no follow-up experiment is automatically authorized.
