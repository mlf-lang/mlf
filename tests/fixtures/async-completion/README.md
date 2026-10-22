# Actual typed completion gate

Run from the repository root with a new stage-2 compiler:

```sh
EMLF=.mlf-build/async-bootstrap/stage2 \
  MLF_GC_PREFIX=/path/to/collector \
  tests/fixtures/async-completion/check.sh
```

This suite uses the actual opaque primitive catalogue and runtime. It is separate
from `../async-gate`, whose historical fixtures deliberately use a type-only
model. The runner rejects the unsupported seed-stage interpreter bridge.

The runtime fixtures check fresh execution of a polymorphic allocation action,
separate Int/String storage, a single impredicative identity-function payload,
lazy poison, repeated observation, duplicate resolution, pending/ready callback
cancellation, capacity reservation, closed/stale cells, scope-local dispatch,
same-scope reentrancy, cancellation of long timers, monotonic timer wake-up and
repeated scope cleanup. The native C suites additionally force collection and
inspect timer/continuation root removal and deterministic fake-clock ordering.

Source fixtures must elaborate and pass independent target checking. Both the
source and checked-target interpreter paths must agree with native output.
Source negatives must fail in their intended phase. Direct target attacks are
rejected by checking, execution, and LLVM emission, with no effects/output.

Evidence is retained under `.mlf-build/async-completion-gate` by default. Override
`MLF_ASYNC_COMPLETION_BUILD_DIR` for a separate CI artifact directory. The runner
sets a small initial GC heap and frequent collection unless overridden.
