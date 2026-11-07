# Recovery status

This is a reconstructed design, not implemented successor code or a validation receipt. The previous transient workspace was lost. No successor code, negative tests, or final P/Q seal had been created. New toolchain evidence is stored separately in pr22-toolchain-recovery-20261107.

## Append-only successor

Keep every frozen contract, manifest, raw-byte delta, historical oracle and source parent unchanged. Add a prepared-input successor above the current CI-integration contract, authenticating that entire parent value before interpreting the new manifest. The current baseline contract value SHA256 was previously observed as 8dc771f8f71e402cf758793b6f6460be74b3cbe227ee0e586a3d587d65c15e5b; this is historical context and must be reverified.

The proposed production patch affects Bootstrap/CrateGraph.hs and Bootstrap/CrateQuery.hs: use structural prepared SourceKey values instead of flattening an entire SCC into one binary symbol, preserve exact ordered candidate lists with an authenticated local scope table, and add prepared-source-tree-1 to the query cache basis. Do not raise defaultLimits or alter legacy text encoders. The actual fix remains conditional on reproduction and controls.

The baseline builtin identity closure excludes both production modules. No builtin identity refresh is justified solely by this patch. Recompute the closure from the final source. If a later change affects it, use the maintained actual generator and fresh verifier, never a manual identity substitution represented as generation.

Final manifest must name exact owner paths, old/new raw SHA256 and byte lengths, reversible byte-splice files, complete current inventory and registry hashes, and corresponding mlf.lock changes only. Old parent projection must reproduce the complete canonical parent value exactly. Preserve physical historical-suite replay, not merely an in-memory approximation.

Composition needs explicit parent projection and inverse for CI, index, roots, open, builtin, writer and frozen layers. Parent proxy must retain parent metadata and provenance callbacks; do not validate historical provenance against successor metadata accidentally. Verify initializer ordering because inherited constructors invoke virtual validation before live inventory.

## Negative controls to implement

Reject missing or half-updated lock entries, unrelated source or lock changes, wrong cache basis, wrong owner or base, modified or forged pins, invalid or non-invertible deltas, missing inventory members, symlink/FIFO/oversized inputs and relocation errors. Independently replay the unchanged historical suite on a physically reconstructed parent inventory. New fixture checks must run through the existing mandatory source-graph gate without editing frozen oracles.

## Final history seal

After real functional changes are final, append functional F to old Q. Create new P with sole parent F, SOURCE_PARENTS=(F,), SOURCE_ANCHOR zero. Child Q may only substitute P's exact hash into that source anchor. Parent and tree constraints remain exact. Revalidate any moving MAIN_BASE rather than silently updating it.

Construct synthetic squash S from final Q tree with sole parent MAIN_BASE. Use a fresh clone with S/main history and explicit permitted source refs to run release/history/composed checks. Also validate the exact-tree synthetic two-parent merge. After real squash verify actual parent/tree and rerun from fresh history. Do not publish releases or tags. Downstream PR28/31 need current metadata reread and deliberate authored-delta reconciliation after retargeting.

## Remaining work

Implement and test the successor, establish the actual successful source patch, regenerate exact deltas and pins, run real producer and native qualification, and only then create final seal. This document proves none of those gates passed.

## New work after recovery

prepared_input_transition.py now implements draft pure transition primitives: exact three-file inventory projection, explicit old/new raw identity checks, exactly two lock-source owner changes, duplicate-key JSON rejection, and bounded regular-file reading that rejects links in any path component and does not block on FIFOs. test_prepared_input_transition.py ran eight tests successfully (transition-tests.log). These are new synthetic unit tests, not source-contract acceptance or historical replay.

The module deliberately is NOT wired into source_migration_adapter.py. Full successor materialization, ancestor callback composition, actual byte-splice generation/inversion and physical old-suite replay are still unimplemented. Final production identities must come from the tested final diff. No P/Q seal exists.

## Later provisional implementation

The Linux-only `tools/performance/artifact-binary/prepared_input_contract.py` now implements full fixed-parent materialization, reversible raw-byte deltas, ancestor projection/provenance composition and physical unchanged CI-suite replay. See PREPARED-INPUT-PROVISIONAL.md for precise scope and finalization prerequisites. Earlier “unimplemented” statements above describe the initial recovery stage, not this later code. The live selector and all historical files are still unchanged. Tests generate temporary metadata only; no final producer evidence or seal is present.

## Subsequent candidate source selection

A separate portable candidate source contract is now selected locally, documented in tools/performance/artifact-binary/PREPARED-SOURCE-CANDIDATE.md. The earlier Linux experiment remains unselected. Exact source/manifest/code pins and three byte deltas are present for the current candidate, with only two lock source-owner updates. This supersedes the earlier status that no candidate selector exists, but does not finalize producer evidence, native acceptance or history seals.

## Candidate reader portability blocker

The whole-path reader race was corrected with retained directory descriptors and no-follow relative opens. Platforms lacking those capabilities, notably ordinary Python Windows, now intentionally reject candidate live admission. Thus the earlier description of a portable candidate layer is superseded: Linux source controls do not establish Windows/macOS integration or final merge readiness.
