# Typed completion gate fixtures

Run `EMLF=/absolute/path/to/emlf ./check.sh` from this directory or the repository
root. No fixture here requires new primitives. See
[`docs/async-typed-completion-gate.md`](../../../docs/async-typed-completion-gate.md)
for provenance, interpretation and the separate native storage proof.

- `Gate/CompletionInterface.emlf`: abstract, invariant **type-only** interface;
  its allocator intentionally panics and must never execute.
- `positive/`: accepted interface programs, emitted and independently checked.
- `negative/`: rejected attacks and invalid ST/IO transfers. One imported alias
  annotation has a recorded elaboration-diagnostic gap; arbitrary parse errors
  do not count as expected rejection.
- `counterexample/`: the deliberately incorrect quantifier contract is expected
  to typecheck, demonstrating why it must not be implemented. Never run it.
- `runtime/`: executable ST one-shot storage and CPS homogeneous-queue probes,
  with exact expected output. Neither is the full IO completion implementation.

The representation-only model is named `GateCell` so it does not redefine the
`Completion` primitive introduced by the live completion implementation. This
is a fixture alpha-renaming; quantifier scopes, acceptance/rejection oracles,
and the prohibition on executing the bad-contract counterexample are unchanged.
