# Offline validation dependency ledger

Research-only parser of already-published finite observer evidence at commit
`d9c14d396353dffe2b5cebbcfb78aeb91817a9df`, path
`tools/performance/main-baseline-gap-20261114/validation-read-observer/results.json`.
Download that unchanged file as `observer-results.json`, then run:

```
python3 -m unittest -v test_ledger.py
python3 ledger.py observer-results.json > ledger-results.json
```

No Haskell/compiler/profile/benchmark ran for this ledger. Original validation,
production sources, main, all existing evidence and native fixed-point pause are
unchanged. Tests exercise metadata protocol, not Graph semantics.

## Findings

All 71 saved sidecars are independently length/SHA checked. Twelve traces have
well-nested observation frames; one typed-Probe trace has no recoverable events;
one sparse trace is explicitly unobserved. There are 17 edge frames, all missing
ordered parent/original-child keys, and 15 global Euler tokens. These counts are
finite fixture observations, not real workload volume or savings.

Entry/exit order, successful and failed frames, direct selector/alias/node events
and nested frames are retained. Successful children under a later failed parent
are NOT promoted to a successful parent. Every report says reusable=false.
The helper `eligible` is an abstract conservative token-set specification only;
it cannot manufacture provenance, certify a graph, or authorize bypassing the
validator. Its complete-write and prepass flags are assumptions, not checks.

## Smallest justified observer delta (design, not implemented)

1. Give edge observations ordered parent/original-child identity only AFTER the
original operations have demanded those identities. Do not render or force the
parent before a Gen-child or missing-child failure merely to log it.
2. Record denseContains operands and its already-demanded Boolean at the original
if boundary. A global Euler token remains authoritative until full relation
provenance is proven. Coordinate equality is not ancestry equality; endpoint
identity does not cover edits to intermediate ancestors.
3. Keep alias presence AND terminal absence; need version/incarnation identity
and every recursive merge/canonicalization/binder/flag write. Copying a skeleton
Node is not proof of copying an original Node. Partial GCon children must not be
traversed for logging.
4. Preserve full root/binder/Euler prepasses, incoming-edge checks, occurs checks,
ordered failures and original validator execution. No cache return path, no
cross-call state, no poisoned payload equality/hash/show.
5. Reuse original cached-kind-edge, earlier-error/late-poison, absent-alias,
ancestor-move and coordinate-drift counterexamples; extend finite O0/O2 parity
only for this new metadata delta after source review. No repeat broad profiling.

## Explicit blockers

Existing observations lack keyed edges and complete write/version transport.
No complete real shadow/reuse implementation or net-work benefit is established.
All safe invalidation in this ledger is conservative. A future relation generation
must be refreshed behind original gates; replay cost and retained payload cost
must be accounted for before calling the design an optimization.

The parser accepts only the closed event-label vocabulary in the pinned fixture;
it is not a parser for future observer revisions. It checks nesting and the global
Euler success marker's frame/identity, not every Graph transition. Initial review
found assert-based integrity, duplicate-name and open-vocabulary defects. These
were corrected with explicit errors, unique names, closed labels and marker guards;
16 tests pass with ordinary Python and `python3 -O`.
The alias/binder/ancestor tests exercise supplied symbolic invalidation tokens,
not extraction or propagation of actual Graph writes. The poison test proves only
Python metadata early-return ordering, not Haskell evaluation equivalence.
The input is additionally bound to the connector-verified immutable Git blob
`15c14ef13a72da74fbd52f38e9738715ea7f2a88` (29,089 bytes). The parser rejects
any differently encoded input before the per-sidecar SHA-256 checks; malformed
archive tests therefore fail at the outer pin as well. The inner validations are
defense in depth, not independently reached by those mutation tests after pinning.
