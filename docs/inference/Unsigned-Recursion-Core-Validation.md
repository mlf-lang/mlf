# Ordinary unsigned recursion: core milestone validation

This records the ordinary-recursion core milestone, not completion of generalized
recursive class-context inference and not a full native qualification campaign.

## Reproducible base and isolation

- Repository: `mlf-lang/mlf`.
- PR #22 head verified initially and pinned: `c0c5dddd11ed5775e2a3d5564cfeeef8383610a5`.
- Isolated local branch: `codex/unsigned-recursion-pr22-20261024`.
- Report-first design commit: `be13785`.
- Explicit recursive-mode plumbing commit: `1c8b706`.
- No changes to the unrelated integration checkout; no push, PR or merge.

## Toolchain

GHC 9.14.1 was installed only under this checkout's ignored `.toolchain/` after
explicit permission. The official Debian 12 x86-64 bindist was 306,812,040 bytes:

```
60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841
```

The checksum matched the official `SHA256SUMS` before extraction/execution.
No GHCup, cabal-install, LLVM, GC or system configuration change was made.
Installation provenance is retained in `.toolchain/installation-receipt.json`.

## Verified checks

1. `tools/shared/build.py` succeeds with GHC 9.14.1 at both `--optimization 0`
   and `--optimization 2`. Both builds compile all 103 raw shared modules,
   audit actual inferred host interfaces, check module provenance, and run the
   compiler's shared grammar/name-resolution check. Complete source-bound
   receipts are under `.mlf-build/unsigned-core-final-O{0,2}/receipt.json`.
2. The direct `shared-frontend --recursive-inference` suite passes at O0 and O2:
   17 accepted source programs, 9 inference rejections, 3 original recursive-knot
   order/count checks, 3 dependent-bound/higher-kind projection checks, and
   malformed recursive RHS rejection by both target checkers. Accepted programs
   use authored expected types and both current/frozen checkers before and after
   target serialization, plus erasure comparison.
3. Full `shared-frontend --frontend` parser/namespace checks pass at O0 and O2.
   The existing unsigned local-infix test now reaches its intended module
   resolution rejection rather than the removed early signature gate. Its source
   and label are retained, and the exact stage/diagnostic are asserted.
4. Authenticated `tools/release/source-smoke.sh` passes at O0 and O2: two
   accepted sources, two inference rejections and one malformed target in each
   authenticated run.
5. The new Core graph export aggregate executes successfully through the O2
   host interpreter, without LLVM/native compilation. It checks internal clone
   identity, shared outer frontiers, wholly outer roots, nested bounded/kinded
   nodes, dense/sparse normalization, an independent graph validator, and three
   scaffold permutations. Its earlier O0 interpreted run timed out after 300s;
   that timeout is not counted as a pass.
6. The existing recursive crate-query boundary case passes through the O2 host
   interpreter (186.98s), including signed contracts, unsigned divergent-function
   generalization, mode preservation and query plumbing. Its unsigned expected
   type is independently prescribed as `forall a b. a -> b`, not the narrower
   signed identity type.
7. `python3 -m unittest discover -s tools/shared -p test_provenance.py -q`:
   40 tests pass. `git diff --check` passes.

The frozen `Tests.IndependentCheck`, `Tests.IndependentType`, and mandatory
`CompilerCore.finishCompilation` source/type/erasure checks are unchanged from
the pinned base. No test was deleted to force a pass. The reviewed Core inventory
adds one graph case (739 to 740); two obsolete early-signature rejections become
positive recursive-inference cases while other IDs/oracles/metrics remain.

## Current limits

- Recursive uses of unsigned members share one unsolved type per SCC. They are
  not unrestricted polymorphic recursion. Signed polymorphic recursion remains.
- No claim is made about solving arbitrary cyclic data or proving termination.
- Concrete/captured-given class wants can resolve in unsigned recursive bodies.
  Fresh generalized recursive dictionary interfaces are not implemented in this
  core commit. They remain the next phase, with lexical-let evidence abstraction
  and full predicate argument identity requiring a separate design.
- Focused success and independent target checking are not a proof of principal
  inference for every source expression or of the proposed qualified extension.
- The full native/LLVM/GC campaign was not run, as instructed.

## Retained receipt digests

- O0 build: `6019df9dd631cc28d9cab2a9d646ec92a54dd5488c1f41309061ab60ccd69aba`.
- O2 build: `a707a8d2a9a1b6998c5ef984df16611ca05332381de986b0aff02717bfa6bdeb`.
- O0 smoke result: `86f68f41e5bac9e069fcb275a16b150796b717a938d2aaf9be7e95548508b95c`.
- O2 smoke result: `a327ec0650ad556a3bb8201d419726b5f3aa4f10fcec64b20a27a379369dbbaf`.

These receipts bind the exact tested working-tree source hashes. Their Git HEAD
field is the preceding plumbing commit because the core patch was tested before
its commit; they are not a claim that the unmodified parent commit contained the
new implementation. Build/profile logs and focused execution logs are retained
in `.toolchain/logs/` and the corresponding build directories.
