# Owned seen single probe candidate

Decision: STOP this variant before an ordinary compiler build or workload screen. This is a cost-structure prioritization decision, not a measured slowdown. No native/fixed-point A/B was run, and this archive does not change main or a pull request.

## Mechanism and invariant

Against main fc300bc9fdc389b585cbef0630fc8915d53e89c5, two internal Solver entry points start a new canonical seen map at empty. A single Patricia search returns either a hit or a deferred insertion continuation. Only after the unchanged graph-node lookup succeeds is the Node supplied; discovery order and the map rebuild demand point remain unchanged. The original generic helper and generic IntMap are retained. This is restricted call discipline, not language-enforced export privacy. Raw malformed maps must not be routed through the new helper.

## Actual finite result

One fresh GHC 9.14.1 O2 execution compiled 16 home modules: original Graph and Solver plus the renamed candidate Solver and fixture. All 14 cases, 56 sidecars and five complete physical graph/map renderings passed A/C raw equality, fixed first-line expectations and independent finite parsing. Tests include contiguous, signed/gapped and wide original identities, duplicate discovery, Gen boundaries, missing-node error priority, unused payloads, delayed key demand and both changed Solver entry points. Dense/Dense/Sparse labels refer to original input validation during prepare, not a promise of sparse projected local unification. The fallback-success fixture has no fresh nodes or hidden stubs. Raw malformed-map coverage exercises only the unchanged original helper.

The five child steps exited zero and cleanup completed. All original input checks remained valid. Eighteen compiler warnings were preserved: the prior seventeen plus GHC-63394 for fixture head on its fixed four-key input. Fixture stderr was empty. This is finite O2 qualification only: no O0 equivalence, general bottom/sharing proof, complete expanded-instantiation coverage, ordinary producer, native qualification or performance result.

## Cost decision

Both real business callers reach the new owned worker, which reaches seekMissingTree; the optimization is not dead code. The intended second insertTree search is absent from that new path, but rebuilding remains. Miss return paths retain a 32-byte continuation plus 16-byte Just per traversed ancestor; hit Bin paths retain additional nomatch calls. These are gross conditional mechanism allocations, not a net 48-byte increase: the original also allocates an insertion thunk and wrapper, and its full recursive allocation ledger was not measured.

The candidate Solver ELF .text is 303,834 bytes versus 282,026, up 21,808 (7.73%). This section includes padding and GHC info tables; shared named function sizes and the old generic worker window are unchanged. No speed conclusion follows from section growth. Given real continuation/checking costs against only one saved descent, this variant does not warrant another producer or repeated small timing windows. It is not proved slower.

The original checking-path profile provides a ceiling, not savings: lookup plus insertion plus node rebuilding under component discovery is 1,800 of 35,691 self ticks. Those lookups serve several distinct maps, and rebuilding remains mandatory. Earlier standalone dominance caching and slow-kind handoff were separately screened out; neither profile shares nor their test designs are performance evidence.

## Files and reproduction boundary

candidate.patch applies only to the pinned Solver source. Prototype/OwnedSeenSolver.hs is that candidate with only its module declaration renamed; Main.hs imports the untouched original and this candidate in one program. fixture-contract.json and expected.stdout freeze the finite expected outputs. PINS.json records source and observed artifact identities; AUDIT.json and COST.json summarize the independently checked results. The finite compile used Haskell2010, O2, -fpedantic-bottoms, -fno-state-hack, complete-pattern errors, explicit global packages and fresh output/stub directories. This is an experiment archive, not a portable build harness or a merge recommendation.
