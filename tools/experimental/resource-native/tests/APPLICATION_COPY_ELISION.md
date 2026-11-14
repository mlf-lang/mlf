# Optional application input-copy elision

Call `resource_ir_v8.application_copy_elision.elide_application_input_copies`
explicitly on raw IR. This does not activate a planner/CLI default or modify
`forward_owned`. Both original and rewritten programs are freshly checked.
Old source witnesses, metadata, packets and native qualification do not transfer.

The first slice accepts only this contiguous, top-level concrete window:

```
retain f1 f
retain x1 x
application r f1 x1
drop f1
drop x1
```

It produces `application r f x` with the same authority and output. Structural
checked types must be Repeat Int -> Int (unknown result identity) and Int,
not merely a type named T0. Exact capabilities, operand roles and drop order
must match. All four handles are owned MONO, not tickets or loan anchors;
the authority cannot name a removed copy. Generic/nested bodies, Scheme/Once,
borrowed applications, reordered drops and any intervening operation are excluded.
Existing loans from an original owner remain anchored and untouched.

Application publication stores Node/Access slots, not these temporary Handles,
and does not force the argument or call the function. The original owners stay
live throughout. Two temporary owner acquisitions/releases are removed; the
application graph itself is not removed or eagerly evaluated. Equivalence is
limited to normal graph/evaluation behavior with sufficient resources: trace,
fuel, guard-work and allocation-failure positions can differ. This is not a
source qualification, general no-GC proof or measured CPU/RSS speedup.

Host controls:

```sh
python3 -B -S tools/experimental/resource-native/tests/test_application_copy_elision.py -v
```

Finite native controls, using a fresh output outside the checkout:

```sh
timeout --signal=INT --kill-after=10s 600s \
  python3 -B -S tools/experimental/resource-native/tests/test_application_copy_elision_native.py \
  --output /tmp/ir8-application-copy-new-run --cc gcc
```

The native plan is literal/pending arguments to a finite captured identity
wrapper, both group placements, before/after. Literal cases use one and three
entries (8 executions); pending cases use one (4 executions). Every run must
return independent Int 42, balance all ownership/group/node/RC counters, and
leave zero live allocations in all seven categories. Each entry must remove
exactly two retain/drop and owner acquisition/release operations, with unchanged
node/group/application/callback counts. Native results require an actual run;
neither the API witness nor the host emitter asserts one occurred.
