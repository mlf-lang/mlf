# Concrete Int lazy-selection core review

**Accepted for bounded source integration, not source acceptance.** New `resource-ir-int-lazy-if/1` / v5 core. Exact six-file worker implementation manifest SHA256: `d57b93c253eb7fa2a61a4ccf0d31d380e8d2ba0d909f74fc01ee253a3000fd41`.

Reviewed checker/model/native/emitter diffs against the frozen scalar core. select_i64 requires ready owned Bool, independent owned Int branch capabilities and checker Down(authority) support. It consumes both branch names, transfers the selected exact owner and drops the unselected owner without a branch Force, allocation or owner acquisition. The result has a conservative unknown abstract group below the authority, unknown symbolic identity and no readiness proof. Authority cannot be either consumed branch. Both cursors are validated before a selection event/drop; ticketless aliases of raw holes reject in both model and native. Existing return promotion handles selected local storage.

Verified all final 75 command records / 150 stream hashes and lengths; final 83/83 gate passes, with before/after source hashes equal current bytes. Coverage: 10 normal explicit-IR cases, four terminal cases, 16 checker rejects, O2 and selected ASan+UBSan, malformed native helper controls, same-node independent owners, selected local storage promotion, nine-entry context-only sessions/clean close and poison immutability. The preserved first attempt failed three harness assertions that incorrectly demanded a new recursive force_enter after callback-return selection; the corrected assertion also accepts exact raw/invoke owner transfer. Core bytes were not fixed or changed by that harness correction.

Fresh independent tests passed **16 commands** across O0 and ASan+UBSan:

- False selection from two independent owners of one node preserves result 37.
- Nested selections transfer custody and return 44.
- Unselected filled self-indirection is never forced and returns 42.
- Selecting that same indirection produces BUSY, null result and retained fault memory.
- Normal complete events and terminal observed prefixes match the independent model with validated native-only Force markers.
- Attempt to turn the abstract selected group into a same-group capture proof rejects CAPTURE_RELATION.

Raw commands, scripts, generated IR/C and test binaries remain in this audit. LSan is disabled; poisoned heaps remain intentionally retained. No independent allocator-interposition witness was added for this helper; allocation/acquisition checks use native runtime snapshots and source inspection, not a whole-process memory claim.

Fresh kernel/native receipts permit source integration using exactly the manifest-bound bytes. Genuine PIfThenElse[Int] provenance, proof normalization, whole-source branch checking, delayed branch wrappers and source-native cases remain separate gates. The design discussion in CONTRACT_REVIEW.md does not qualify the pending normalization implementation. No general polymorphic if, sums, Text/IO/ST, broad old-suite replay, M1–M6 restoration, full GC replacement or performance qualification.
