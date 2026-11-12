# Optional Int conditional branch owner reuse

This is an opt-in fragment-planner optimization. It is not source admission,
a runtime change, a garbage collector, or a general IR optimization.

The existing Python fragment API accepts an optional keyword:

```python
plan = planner_v8.plan_fragment(projected_annotated,
                               reuse_int_branches=True)
```

The keyword must be an actual Boolean and defaults to `False`. The existing
source CLI does not expose or enable it. `data_groups=True` is independent.
Omitting the new option or explicitly passing `False` preserves the complete
original plan, including its diagnostic maps and work counters.

After the unchanged fragment replay and normalization, an intrinsic-Int
`ifThenElse` arm that is exactly an ordinary Int variable can retain its
original owner instead of allocating a forwarding thunk. It does not force,
substitute, clone, inline, instantiate, or expand that variable's value.
Other arms keep their original lowering. The selector still consumes two
distinct owner handles, even when they refer to the same node. The unselected
branch stays unevaluated. Recursive bindings currently admit arrows only;
future scalar/value recursion would require a new eligibility review.

The plan records exact source, binder, scope, owner, retain instruction and
selector-arm correspondence in `binding.source_map.branch_owner_reuse`.
`binding.optimizations` records the policy and static reuse count. These are
diagnostics, not authority: callers must independently resource-check the
complete returned program. This does not add a source-envelope adapter or
qualify a source compiler or native bootstrap.

Run the synthetic host regression suite explicitly:

```sh
python3 -B -S tools/experimental/resource-native/tests/test_branch_owner_reuse.py -v
```

The suite covers both placement modes, same-owner and alias branches, pending
values, ordinary parameters, mixed eligible/ineligible arms, an unselected
recursive branch, default-plan equality, unchanged fragment refusal, actual
Boolean options, resource-checker negatives, and provenance mutations. It
checks real generated C text but does not compile or execute that text.
The isolated branch-owner-reuse workflow runs these tests and the existing
planner host suites. Synthetic fragments are not genuine source-producer
qualification, and this workflow is not full-repository CI.

Fewer thunk callbacks can change work, fuel, guard work, allocation-failure
positions, traces and memo counts. No equal-fuel progress, universal allocation
or peak-memory improvement, elapsed-time speedup, RSS reduction, general leak
freedom, or full no-GC claim follows. A failed evaluation retains the existing
explicit terminal-surrender contract; the optimization does not make it
resumable or automatically roll it back.

## Maintained native regression

The separate native job now compiles and executes generated C at O2:

```sh
timeout --signal=INT --kill-after=10s 600s \
  python3 -B -S tools/experimental/resource-native/tests/test_branch_owner_reuse_native.py \
  --output /tmp/ir8-owner-reuse-new-run --cc gcc
```

Choose a fresh output directory outside the checkout. Six fixtures cover
same-owner true/false selection, mixed variable/expression arms, pending
values, an unselected recursive branch, and a nested conditional. Each runs
with both `data_groups=False/True`, before and after reuse, for one entry:
24 native executions. Both IRs pass the resource and metadata checkers, and
the optimized source-map rows are independently audited. Every execution
must return the independent Int result 42 with no fault, balanced group,
node, owner, loan and RC counts, zero live bytes/blocks in all seven memory
categories, and empty terminal retirement.

This is a maintained subset following the previously completed 48-execution
native research campaign, not a claim of first native validation. It does
not repeat that whole historical matrix: multiple entries and sanitizers
are not covered by this O2 job. Raw plans, generated C, command logs and
terminal reports are retained, including failures. It does not establish
source qualification, general no-GC correctness, or performance benefits.
