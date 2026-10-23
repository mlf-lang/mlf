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

## Contract

- Both hosts compile the same committed implementation `.hs` files.
- Shared files declare `-- mlf:syntax shared-haskell-v1` and import the fixed
  `MLF.Primitive` facade. Legacy `.emlf` guests retain legacy semantics.
- GHC uses Haskell2010 and an explicit extension allowlist, actual Prelude.Bool,
  and `-fpedantic-bottoms -fno-state-hack` at both optimization levels.
- Primitive IDs remain append-only 0–94. Native and GHC runtimes preserve
  forcing order, cold actions, lazy typed payloads and checked FFI narrowing.
- Normal builds may choose source roots and host adapters, but may not rewrite
  implementation source. A one-time reviewed migration tool is not a build
  dependency.
- The released seed route uses a source-complete frozen legacy bridge. It
  cannot parse final shared source directly.

## Current status

Implementation is in progress. The new primitive facade and its three host
modules pass GHC 9.14.1 `-fno-code` with the required language/demand flags.
This is only a four-module typecheck, not runtime, compiler, bootstrap or full
semantic qualification. No completion, performance or merge-readiness claim is
made. The final receipt set will bind exact source/tool hashes and separately
report passed, failed, pending and unrun gates.
