# Candidate source identity integration

The live selector now authenticates `prepared_source_contract.py` and `prepared-source-candidate.json` with explicit SHA256 pins. This admits exactly the current source inventory and its reversible historical projection. It is NOT a native qualification, release approval, final history seal, or assertion that the entire dependency campaign passed. The manifest deliberately retains `provisional: true` and its source-only scope. The legacy selector variable name `FINAL_MANIFEST_SHA256` denotes an exact manifest-byte pin, not a P/Q seal or runtime qualification.

The parent contract, parent manifest, complete parent materialized value, reviewed two source identities, raw lock identities, complete inventory and registry hashes are fixed separately. The edge contains three raw-byte splice files: CrateGraph.hs, CrateQuery.hs and mlf.lock. The root lock changes only the two corresponding source-owner hashes. The generated builtin literal and its lock entry are unchanged.

The recorded base is recovery commit 5b96787c9247504e5494f2664bf30126cf240e8d, tree 31417fe654a9b6543480c2bd500c31d43819f6ab. It identifies the reviewed candidate bytes, not a completed qualification run. If the real full campaign leads to further source fixes, regenerate and review this edge and all its explicit source/manifest/code pins from the actual new bytes before relying on this selector.

## Historical compatibility

`ci-integration-test-loader.py` preserves the former selector byte for byte, with a fixed SHA in the new contract and tests. The new suite reconstructs the entire physical CI predecessor, installs that loader, then runs the unchanged CI test suite and its five historical levels. No historical contract, delta or original test is edited. Generic query-graph and writer-bridge tests still run unchanged against the newly selected current source contract. The release provenance runner invokes the new current suite, which owns the complete old-suite replay.

The five provenance record validators use their authenticated historical value-specific proxies. The CI proxy restores its own manifest SHA and metadata inventory. The minimal manifest-validation interface used by unchanged generic graph controls is retained; restoring a predecessor still requires its complete fixed canonical hash, not a partial field check.

## Portability and tests

The live code does not import the Linux-only `prepared_input_transition.py` experiment. The new reader requires reliable relative-directory opens, no-follow flags and no-follow directory-entry queries. It opens every component relative to retained directory descriptors, compares identities, reads a bounded regular file, and rechecks the original directory entries through those retained parents. Rename followed by a same-target symlink is rejected. No whole-path fallback is allowed. The selector uses the same self-contained implementation.

Only Linux has actually been executed here. Missing secure APIs cause explicit failure before admission. In particular, ordinary Python on Windows does not provide this required dir_fd/no-follow combination, so this candidate's live source selector is currently BLOCKED on Windows. This is a real unresolved merge/qualification blocker for any Windows workflow that reaches the selector, not a passed portability gate. A separately reviewed Windows handle/reparse implementation, or an explicitly accepted maintained boundary, is still needed. macOS has not been executed either.

Tests reproduce parent swaps before directory-open and before file-open, for both contract and selector readers, plus missing API, reparse metadata and FIFO refusals. They run under normal and optimized Python. These are Linux observations, not Windows or macOS acceptance. Native/both-tool fixed point remains required separately.

Run from this directory:
- python3 -B -m unittest -v test_prepared_source_contract
- python3 -O -B -m unittest -v test_prepared_source_contract
- python3 -B test_query_graph_migration.py (and -O)
- python3 -B test_p2_writer_bridge.py (and -O)

These source tests execute no GHC/native compiler and create no fabricated generation receipt. No new compilation evidence is attached to the manifest. Existing historical evidence remains its original, narrower historical claim.

## Executed source-only validation

After the descriptor-reader correction, Linux candidate controls passed 21 tests under normal Python and -O, including the same physical unchanged CI-suite replay and reproducible directory-swap refusals. Unchanged generic graph controls passed 10 tests in each mode; unchanged P2 writer bridge passed seven in each mode. The retained experimental suite passed 25 controls in each mode after adapting only its fixture to use the saved CI selector.

Before that reader correction, the complete maintained `tools/release/check-benchmark-provenance.sh` completed successfully: benchmark transition controls, current graph/source controls, full historical replay, crate-prelude controls in both modes, all pinned benchmark hashes and 19 exact patch reconstructions. After the correction, the current candidate suite, unchanged graph controls and unchanged writer controls were all rerun successfully in both modes; the full shell wrapper was not repeated. These are actual source/provenance tests. No new compilation or runtime conclusion follows from them.

## Reader race correction

The earlier implementation checked parents and then opened a whole path. A same-target symlink swap could evade that path check despite retaining pinned bytes. The descriptor-anchored implementation supersedes it. All old parent contracts and evidence remain untouched; secure handling of new code is fail closed rather than silently using the former portable fallback.

## Canonical temporary workspace at the maintained entrypoint

A symlinked inherited TMPDIR was reproduced on Linux before the wrapper fix. In both normal Python and -O, the unchanged generic bounded-reader test rejected the symlinked parent, and the candidate relocated-root test compared a physical path against its logical spelling and failed. These failures were not bypassed or weakened.

The maintained shell entrypoint now pre-creates a mode-0700 Python temporary directory inside its own existing private work directory, obtains its physical path with `pwd -P`, and exports TMPDIR before any Python controls. All nested historical replay processes inherit that physical path. The existing EXIT trap removes only the invocation's own work directory, never the caller's inherited TMPDIR.

`tools/release/test_provenance_temp_root.py` runs the real complete wrapper with a symlinked inherited TMPDIR and a caller-owned sentinel. It checks the wrapper's success, sentinel/link preservation and cleanup of its private work directory. No commands, gates or historical tests are mocked. This is a Linux reproduction of the macOS path shape; real macOS execution remains unperformed, and Windows secure-reader support remains unresolved.

The complete symlink-TMPDIR regression was executed successfully with both normal Python (117.6 seconds) and -O (120.8 seconds). Each invocation ran the real full wrapper, including its normal/-O source and historical controls and all 19 patch reconstructions. Both preserved the caller-owned sentinel/link and left no invocation work directory behind. This supersedes the earlier note that the full wrapper had not been repeated after the reader correction.
