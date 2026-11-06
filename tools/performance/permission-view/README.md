# Dense permission-view reuse

This is a new, narrow adaptation of the historical C1 idea, not a recovery of
its original patch or reuse of its historical measurements. Baseline is
`01ef8e70741c9f9ac4f27e489d059c96a4b33df5` on PR #25.

## Ownership and semantics

One dense rebind transaction constructs an old permission view before examining
the raised binding view. Node tags and flags stay fixed during these checks.
Inertness follows only flexible binding children; flexible paths stop at a
rigid or generalization node. Rigid nodes' own binding parents therefore do not
affect either component. When **all flexible parents are equal**, both views
have the same ordered binding-child lists, paths and permission values, so the
second view can share the first view's index and memo tables.

The equality scan follows the original second constructor's entry order and
stops at the first changed flexible edge. The original constructor then handles
the entire raised view. The old constructor has already demanded every
flexible old parent and checked every nonempty parent index. Equal raised
parents require no new bounds demand; differing raised parents reach the old
constructor, which retains its original checks. Rigid binder payloads and node
tags are not inspected by this admission scan. Permission queries retain their
original order. No cache crosses a rebind transaction or a graph mutation.

The sparse route, persistent graph representation and rollback behavior are
unchanged. This saves an index, three memo arrays and repeated demanded queries
in admitted cases; the new ordered scan also has a cost. It does not change the
overall asymptotic upper bound or establish a universal speedup.

## Closed ordinary screen — 2026-11-01

The protocol fixed eight compiler runs in two balanced blocks, ABBA then BAAB,
before ordinary sampling. The primary estimand is the mean of block-average
paired log B/A wall ratios. Its unrounded point gain must be strictly positive,
under the user's current structural-optimization rule. No independent
confirmation or confidence interval was added. Two guard cells were also
fixed before sampling, conditional on a positive compiler screen; a meaningful
regression requires both a slowdown over 5% and an absolute delay over 0.1s.

| Input | Runs A / B | Geometric A / B seconds | Point time reduction |
| --- | ---: | ---: | ---: |
| Frozen 711-group compiler | 4 / 4 | 43.722 / 43.669 | 0.12% |
| flat_functions-512 | 2 / 2 | 3.869 / 3.823 | 1.19% |
| higher_order_chain-128 | 2 / 2 | 0.934 / 0.933 | 0.06% |

All runs were fresh with zero reused target groups. Every checked artifact was
directly compared as raw bytes with its independently retained reference. The
two shape cells additionally passed all three closed-form native output
checks, using serial ordinary Clang O2 and the fixed runtime/dependencies.

The compiler gain is very small. ABBA improved 0.244%; BAAB slowed 0.00076%.
Descriptive compiler medians were 43.693s / 43.708s, slightly favoring the
baseline; medians are not the chosen primary estimand. These fixed local
observations meet the engineering point-gain rule, but do not demonstrate a
stable, statistically significant or portable gain. No samples were added to
improve the estimate. Neither historical C1's 0.588% nor any other candidate's
gain is pooled with this window.

Both ordinary producers were built once from their final complete source with
GHC 9.14.1 O2, `-fpedantic-bottoms` and `-fno-state-hack`, using the existing
bootstrap crate endpoint. The target is the existing frozen compiler-source
workload, not a self-bootstrap of this edited compiler or a new GHC comparison.
The compiler timing ends at checked crate artifacts. Preparation, diagnostics,
correctness tests and native output checks are outside ordinary timing.

## Mechanism and correctness

A private diagnostic compiler recompiled the affected closure with counters
and CSE/full-laziness disabled. It observed 71,552 dense rebindings: 15,627
shared views and 55,925 fallback constructions. It made 127,477 permission-view
constructions, satisfying `shared + 2*fallback`; 15,627 second constructions
were avoided relative to two per observed rebind. Its complete 711 fresh /
0 reused output also passed the independent raw-byte comparison. These are
diagnostic source-path counts, not ordinary CPU shares or allocated bytes.

O0 and O2 controls use the complete frozen baseline Graph module, adapted only
by a reversible module rename. They compare 720 permission-view inputs at
negative, zero and wide positive offsets, all demanded permission values,
admission decisions, shared-cache versus fallback isolation, ten authored
partial-value/exception-order cases, and 720 exact public graph/first-error
results. The graph serializer observes full Patricia structure, nodes, aliases
and counters. The generated permission family has eight nodes with varied
flags, tags and acyclic parents; it is finite coverage, not a semantic proof.

The original semantic oracles remain unchanged. An additive source-admission
layer records Graph and the freshly regenerated canonical builtin only; the
other 126 shared module identities are unchanged. Fresh generation verified
that the entire builtin literal differs only in its preparation-source token.
The locked source snapshot was refreshed and the actual locked plan is part
of integration qualification.

Integration passed all 14 scheduled checks: retained P1–P3, graph/transaction,
Map balance, validation boundary, builtin, all nine parsed-file cases through
both candidate entries against the independent baseline, native library,
native containers, fingerprint, direct entry, frozen optimizer, all 18 native
IO cases, the actual locked plan, and the static source snapshot. The source
adapter suite passed 20 tests both normally and with Python O; the A1 metadata
suite passed 34 tests, and the CI workflow policy checks passed. The candidate
is accepted under the strict-positive point-gain rule, with the evidence limits
above. No further ordinary compiler samples were added after the fixed window.

Before push, PR #25 advanced to `1fbb8b63`, which only partitions the native
Patricia test and adds CI contract checks. Rebase preserved every production
source, build/configuration input and ordinary object identity, verified by the
unchanged producer authenticator. The updated gate then passed all eight native
partitions and its selected-payload rejection, preserving the exact original
full fixture, error fixture, inventory and 4,107 model-output lines. Its seven
contract tests passed normally and with Python O, and the integrated CI policy
checks passed. The original 14-gate evidence is retained separately from this
additional test-runner qualification; no ordinary performance sample was added.

Reproduce focused controls against an authenticated ordinary O2 producer:

```sh
python3 -B tools/performance/permission-view/run_controls.py \
  --producer .mlf-build/shared-ghc --producer-source "$PWD" \
  --optimization 2 --output .mlf-build/permission-view-20261101/ci-controls
```

Use a fresh output directory; select `--optimization 0` separately for O0.
The O2 CI step retains source copies, receipts, stdout and stderr. The frozen
oracle requires the complete Git history.

Raw plans, all timing legs, controls, producer authentication and diagnostic
sources remain in `.mlf-build/permission-view-20261101/`. Preparation failures
are preserved: the first ordinary build rejected a stale Prelude source token;
the first diagnostic relink lacked a GHC internal worker referenced by dependent
interfaces; the next diagnostic build completed but its target launch rejected
a work/log directory collision. The successful diagnostic run reused that
compiled binary with a fresh target directory. None is an ordinary timing
sample. [Summary data](results-20261101.json) records evidence identities and
the integration outcome.
