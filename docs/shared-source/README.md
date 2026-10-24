# Shared implementation source cutover

This draft is one coordinated migration of implementation syntax, primitive
facade, compiler sources, native packaging, bootstrap and qualification.
It is not a staged feature rollout. The guest MLF language and inference engine
remain supported in full.

## Baseline and review

The implementation starts at the reviewed PR19 snapshot
`2f8584423fa3055ca96d1479734357f742c9b3df`, whose compiler code is
`8a3e69b165765931c3ff762379a78db9659b2cd8`. This retains guards, TupleList
and typed async. PR19 has subsequently advanced to `4d732f3`; its separate
staged test-framework work is not silently folded into this cutover. The
migration's review delta starts after `2f85844` and its draft targets PR19's
integration branch. Reconciliation with changes to that branch must be
explicit before landing.

Audited host adapters are copied from paused PR20 commit
`767a5b66172ccf3931e0954c38ca47eb8b4e7a28`; PR20 is not modified. The
adapter provenance file lists the original hashes and intentional changes.
No translator is part of the normal build contract.

## Current design authority

The user-approved [Haskell-first revision](Haskell-First-Revision.md) supersedes
the earlier RebindableSyntax/custom-Monad design. Both hosts now target ordinary
Haskell syntax, standard Functor/Applicative/Monad and normal literal desugaring.
The complete syntax conflict audit and remaining qualification gates are there.

## Contract

- Both hosts compile the same committed implementation `.hs` files.
- Shared files declare `-- mlf:syntax shared-haskell-v1` and import the fixed
  `MLF.Primitive` facade. Older `.emlf` syntax remains narrowly scoped compatibility; owned builtin
  hierarchy uses are migrated explicitly, not silently synthesized.
- GHC uses Haskell2010 and an explicit extension allowlist, actual Prelude.Bool,
  and `-fpedantic-bottoms -fno-state-hack` at both optimization levels.
- Primitive IDs remain append-only 0–94. Native and GHC runtimes preserve
  forcing order, cold actions, lazy typed payloads and checked FFI narrowing.
- Normal builds may choose source roots and host adapters, but may not rewrite
  implementation source. A one-time reviewed migration tool is not a build
  dependency.
- The released seed route uses a source-complete frozen legacy bridge. It
  cannot parse final shared source directly.

## Initial bounded checkpoint (superseded by recovery below)

The canonical inventory now contains 94 shared modules and 12 executable
entrypoints. All 94 passed the actual ordinary-class GHC no-code build, with
resolved input paths and inferred interfaces recorded. The interface audit
found 41 literal generalizations, corrected with explicit ordinary signatures;
the repeated audit has no unresolved Num/Fractional/IsString constraints.

Bounded runtime adapter qualification passes 84 command expectations, 87
contracts and 590 numeric-bit comparisons at each of O0 and O2. Independent
runtime review's seven concrete findings were reproduced and corrected.
Focused shared frontend/name-resolution and native interpreter hierarchy/default
checks pass. All three final-source hash-bound semantic shards and the separate
94-file grammar check passed under explicit limits; exact source and executable
hashes match the recorded O0 producer inputs. Release control and mock
orchestration tests pass; these are not a real seed/bootstrap result.

All 94 modules also completed actual GHC O0 code generation and all 12
executables linked. The shared 120-second budget then expired during the
combined whole-corpus grammar/name-resolution command; the overall build
receipt remains incomplete. Peak process-group RSS was 456 MiB.

The frozen legacy bridge has 171 source files and a patch independently checked
to reproduce every archived file from the pinned baseline. The existing native
producer exposed and helped fix two backport defects, then its type probe hit the
enforced 1 GiB limit. Released-seed bootstrap, unrestricted combined source
validation, O2 code generation, native compilation, the full guest/async/TupleList
campaign and native fixed point remain outstanding. No merge-readiness or whole-compiler qualification
claim is made by the bounded probes.

## Historical qualified host checkpoint (before metadata repair)

Source checkpoint `98d6df3` completed the actual GHC O0 exact-source producer:
all 94 modules, 12 executable links, and the complete 94-file grammar/name
resolution gate passed. The final gate took 346.83 seconds; total producer run
was 384.63 seconds with 453.5 MiB peak process-group RSS. The receipt is complete
and authenticates that checkpoint’s source, configuration, toolchain and output hashes.
The earlier 120-second limit was insufficient, not evidence of nonconvergence.

The authenticated direct O0 runtime suite passed all 12 commands in 100.11
seconds: async tasks/processes/wait graph, panic cleanup and child reaping,
three frontend/MLF-semantic shards and suite-receipt checks. The separate
TupleList runner passed 90 checks in 2.00 seconds. Current producer identities
were re-authenticated after both runs. Evidence is under
`tools/shared/evidence/{ghc,direct,tuplelist}-O0-complete-recovery/`.

Recovery also hardens seed bundle integrity, preserves actual seed identity
through the timed caller, and adds manager host identity checks to native
routes. Both compiler and manager must identify as native for the supported
local shared-aware route. Input integrity and identity strings are not
cryptographic publisher authentication. Focused caller/control regressions and
independent review passed; those are not native compiler qualification.

The unchanged source also completed the exact GHC O2 producer: 94 modules,
12 links and whole-corpus resolution, in 135.20 seconds with 528.4 MiB peak
process-tree RSS. O2 direct runtime checks passed all 12 commands in 17.02
seconds, and TupleList passed all 90 checks. The separate PR source-smoke
passed all five cases with both O0 and O2. Both producer receipts were
re-authenticated after testing. Evidence is under
`tools/shared/evidence/{ghc,direct,tuplelist,source-smoke}-O2-complete-recovery/`
and `tools/shared/evidence/source-smoke-O0-complete-recovery/`.

A separately reviewed direct GHC O2 Figure12 entry also passes the maintained
43 labels / 41 distinct expressions and all 36 supplementary checks
(29 signature assumptions, four principal-type assertions, three annotation
repairs), including current-target roundtrip type and erasure equality. Its
fail-closed fixture decoder and oracle-helper guards pass 13 Python controls.
This reuses authenticated compiler objects without interpreting a compiler
inside a compiler; it is not full native-unit coverage. Evidence is in
`tools/shared/evidence/figure12-direct-O2-complete-recovery/`.

Real released-seed/native bootstrap, native fixed point and the full
unit/Core/guest campaign remain pending. Direct host tests and source-smoke
are not substitutes for those gates. The earlier archive object upload was
explicitly authorized and succeeded; branch publication is still pending
separate documentation/evidence authorization. This is not merge ready.

## Builtin metadata validation repair

The exact manifest-derived foundation `--compile-crate` probe exposed a real
boundary error: compiled metadata names were validated by the public source
parser, which correctly refuses user-owned `MLF.Primitive` modules. This also
rejected the compiler’s own builtin interface. Metadata now uses the existing
module-name grammar with full-input and exact-spelling checks; the public source
ownership ban is unchanged. Frontend regressions cover canonical metadata names,
malformed/noncanonical names, both source syntax profiles’ reserved-name ban,
and builtin interface/object encoding roundtrips.

The frozen legacy bridge receives the same repair. Its inventory remains 171
raw files, with four raw files changed (metadata validation, allocator hints, lexer semantic
versions, and builtin identity); the compatibility patch
reproduces all archived raw files from the pinned baseline. This does not prove
native bootstrap. Earlier host receipts above are historical for pre-repair
sources; affected producers and relevant suites must be requalified. No native
LLVM or fixed-point stage is claimed by the metadata-only probe.

The new builtin artifact roundtrip regression then exposed unsafe synthetic
`$` binder hints in printed checked targets. Source hygiene must not be removed:
standard defaults are inserted after input cleaning and their names prevent
capture. The inference allocator now encodes only target display hints that do
not satisfy the existing target identifier grammar. Original source environment
keys and fresh numeric target identities are unchanged; valid hints (including
Unicode and top-level ABI symbols) remain byte-identical. The strict target
parser and checked-object validation are unchanged. Frontend semantics advance
to revision 3 and builtin interface/identity to revision 4; cache keys also bind
the producer binary. Requalification includes collision/capture, type/erasure
roundtrip, and existing default-method demand checks.

### Requalified repair checkpoint

Source checkpoint `351e95d` has complete exact-source producers at both GHC O0
(373.76 seconds) and O2 (128.27 seconds). Both pass the direct runtime suite,
90 TupleList checks, five source-smoke cases, and the faithful Figure12 campaign
(43 labels / 41 expressions plus 36 supplementary checks). The new metadata,
hygienic-name capture, strict artifact roundtrip and default-method demand
regressions pass. Final source, tool, binary and object hashes were rechecked.
Evidence is retained in `tools/shared/evidence/builtin-repair-recovery/`;
pre-repair receipts remain historical rather than being relabeled.

The maintained `--compile-crate` route also completed actual MLF inference,
elaboration and checked-artifact production for foundation (12 modules),
language-core (four), and frontend (nine), using exact manifest-derived specs
and hashed dependency interfaces/objects. These performed 900 fresh inference
groups, not cached successes. They took 24.50, 4.84 and 43.12 seconds and produced
11.08, 5.75 and 47.18 MB respectively. Inputs were unchanged and the O2 producer
was reauthenticated afterward. No LLVM or native output was requested.

This covers 25 of 72 library modules. The other eight library crates and
executable closures, the full guest/Core/unit campaign, released-seed native
bridge, and compiler-plus-manager native fixed point remain pending. Further
crate/native work is held at the disk safety floor; existing checked artifacts
are retained. Documentation/evidence publication authorization is also pending.
