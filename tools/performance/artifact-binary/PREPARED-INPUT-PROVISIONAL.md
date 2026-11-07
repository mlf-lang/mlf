# Provisional prepared-input successor

This is an isolated Linux experiment. `source_migration_adapter.py` is unchanged and never selects it. `prepared_input_contract.live_contract` always rejects admission. There is no final manifest, producer evidence, P/Q seal, builtin regeneration or native qualification here.

The reviewed draft source pins identify the CrateGraph/CrateQuery candidate on recovery commit 5b96787c9247504e5494f2664bf30126cf240e8d, tree 31417fe654a9b6543480c2bd500c31d43819f6ab. Candidate runtime correctness remains unproven. Any changed fix requires reviewing those pins again. Test fixture manifests/deltas are generated into temporary directories, never represented as finalized metadata.

## Implemented structure

- Authenticate the unchanged CI predecessor implementation SHA, manifest SHA and complete canonical materialized value SHA before installing the new layer.
- Bind the exact two draft source identities and corresponding lock only. Current inventory and registry hashes cover all 196 files and 135 modules. Restore the complete predecessor value exactly, then invoke its unchanged validator.
- Apply exact raw-byte splices through the frozen bounded codec, with path binding, old/new full hashes and lengths, and required forward/inverse equality. No fuzzy patching, raised symbol limits or recoding of historical deltas.
- Compose projections and inverse projections through the CI parent for all existing ancestor APIs. The five provenance-record callbacks (CI, index, roots, open-release and builtin) now dispatch through their exact historical value-specific proxies; they are tested against the unchanged historical JSON records and reject changed records. CI proxy manifest SHA and metadata inventory are explicitly restored to CI identity. Host/runtime and maintenance APIs remain inherited with their unchanged guards.
- Preserve the builtin literal and closure. A fresh source_identity check of this recovery tree remains builtin-source-v1:208a79cd23693358d7624822110f2e44fd98cc9fd82270638c2ef08a0276564c. This is only a source identity check, not generator execution.
- Physically materialize the exact CI predecessor, authenticate its unchanged selector and test entrypoint, and execute that suite. It pins and executes query-index, package-roots, open-release, builtin and writer predecessor suites in their own reconstructed trees. Optimized test runs propagate -O to that child suite.

## Run source-only controls

From this directory: python3 -B -m unittest -v test_prepared_input_transition test_prepared_input_contract

Repeat with python3 -O -B. These tests invoke only Python and read-only Git blob access, not a compiler. Negative controls include wrong predecessor code before execution, changed source/parent/inventory/base/scope pins, malformed owner/delta and splice offsets even after rehash, missing/unrelated files, stale/half-updated locks, symlinks/FIFO/oversized input, original parent-traversal components before normalization, relocation, and rejection of live admission.

## Finalization prerequisites

1. Establish the real passing production fix and final functionality diff. Recompute and independently review raw source and lock identities, manifests, delta bytes and complete inventory/registry identities from that final tree.
2. Implement the maintained cross-platform admission path and its platform controls before any live selector switch. Current provisional code intentionally rejects non-Linux use.
3. Attach real source-authenticated producer/validation evidence with an honest qualification scope. The current layer has no new evidence record and makes no compilation claim.
4. Keep every old contract, manifest, delta, historical test and source-parent constraint unchanged. Retain physical replay tests.
5. Only then update the reviewed selector and build final append-only P/Q history seals. Run synthetic post-squash and real native/both-tool fixed-point campaigns separately.

## Independent review corrections

The historical CI class itself does not project a direct open-release provenance callback to the open-release value. The new layer fixes its own direct callback by selecting the already-authenticated historical open-release proxy; no historical implementation or evidence predicate was changed. Coverage claims are limited to the five explicitly tested record callbacks and the existing projection APIs, not arbitrary inherited private methods. The unchanged historical suite remains the physical baseline.

## Separate candidate integration

A subsequent live source-only layer is now in prepared_source_contract.py; see PREPARED-SOURCE-CANDIDATE.md. This original Linux experiment remains unselected. Its physical predecessor test now installs the saved original CI selector so the historical fixture remains exact after the separate live selector switch.
