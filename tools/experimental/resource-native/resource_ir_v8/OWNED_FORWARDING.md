# Adjacent owned-handle forwarding

This opt-in post-resource-check pass removes one narrow source of unnecessary
reference-count work. It is not ownership inference for MLF, general last-use
placement, a source-language optimization, or a replacement for the GC runtime.
No default compiler, planner, runtime or existing test entry changes.

## Rule and safety boundary

For adjacent instructions `retain y x; drop x`, keep the original owner `x`,
remove both instructions, and rewrite later operands of `y`'s exact capability
to `x`. Match only a concrete owned Mono value with no outstanding construction
ticket. Scheme handles, loans, generic callback bodies and nested introduction
bodies are deliberately excluded. An intervening instruction prevents a match.

The raw input is checked before pattern matching. Invalid input, including a
Once copy or a drop with a live exact-owner loan, cannot be repaired into
acceptance by hiding the offending instructions. All callbacks, even unused
ones, remain subject to the original all-body checks.

The retained owner has the same node, nominal/full callable type, readiness,
group, view, projection and provenance. No operation can inspect the temporary
extra owner between adjacent instructions. The paired drop cannot close its
group because the new owner is still live. After the pair, only the surviving
handle identity differs. Future borrow anchors are rebuilt against that exact
surviving owner. Existing sibling owners and their loans remain distinct.

Rewriting uses capability identities and operand paths from this call's freshly
computed checker output. It does not replace text: code names, layouts, fields,
capture keys, and child import binders are untouched. Parent import operands
can change while a child binding with the same spelling keeps its own identity.
Instantiation's move from a Scheme name to a Mono name is not treated as a fresh
owner, and the pass never forwards a Scheme capability.

The rewritten raw IR is independently checked again. This is a safety gate,
not a substitute for the local semantic argument above. All instruction paths,
capabilities, storage identities, anchors and metadata must be regenerated.
An old source map, captured source witness, packet or native binary is not valid
for the transformed program merely because the second resource check succeeds.

This is one bounded sweep, not a fixed point. For example,
`retain y x; retain z y; drop y; drop x; return z` exposes another adjacent pair
after the first rewrite. A caller can request another independently checked
sweep; the API does not loop automatically.

As with ordinary allocation elimination, normal results are preserved under
sufficient resources. Allocation-failure injection positions, diagnostic work,
owner identities and event/accounting totals can change. There is no claim of
fault-trace equivalence, universal peak-memory reduction or elapsed-time speedup.

## API

From `tools/experimental/resource-native`:

```python
from resource_ir_v8.forwarding import forward_owned
from resource_ir_v8.runtime_emit import emit_runtime

result = forward_owned(raw_ir_dictionary)
new_raw = result.data()
emission = emit_runtime(new_raw)  # Fresh resource/metadata/packet checks.
```

The immutable result contains canonical raw JSON, original/result hashes, the
new resource-derived hash, and a JSON witness of original instruction pairs.
`data()` returns a fresh copy. No prechecked object or caller-supplied analysis
is accepted as authority. The witness explicitly has `source_admitted=false`
and `native_executed=false`. Native testing is a separate operation.

Input/derived byte ceilings and monotone analysis creation/work limits are
inherited from the resource checker. Owner-chain resolution uses iterative path
compression and an explicit work budget. Exhaustion returns no partial result
and leaves the caller's input unchanged. This does not introduce an aggregate
process-memory or wall-clock guarantee.

## Validation and reproduction

Host controls:

```sh
python3 -B -S tools/experimental/resource-native/tests/test_ir8_forwarding.py -v
```

The initial cloud validation passed 16 new test methods, including the existing
140 raw-input fixture decisions, injected copies across concrete allocation
sites, exact new-loan anchors, pending callbacks, name collisions, generic-body
exclusions, immutable snapshots and two fresh checks. Combined with the existing
resource/declaration/metadata suites, 497 tests ran: 494 passed and three
explicitly optional historical-baseline comparisons were skipped.

Independent review additionally exercised 207 lawful injected pairs, including
Mono instantiation outputs, callback parameters/captures, same-spelled parent
and child imports, authority operands, filled holes and sibling loans. A
1000-pair chain became four instructions without recursive chain traversal.

Native controls use the existing bounded smoke builder and unchanged C runtime.
Each invocation requires a fresh output path outside the checkout:

```sh
base=tools/experimental/resource-native
python3 -B -S "$base/tests/test_ir8_forwarding_native.py" \
  --output /tmp/forwarding-o0 --optimization O0
python3 -B -S "$base/tests/test_ir8_forwarding_native.py" \
  --output /tmp/forwarding-o2 --optimization O2
ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
python3 -B -S "$base/tests/test_ir8_forwarding_native.py" \
  --output /tmp/forwarding-sanitized --optimization O0 --sanitize
```

Six cases cover a scalar, identity-function parameter, pending thunk, closure,
SUM field factory and filled hole. Before/after versions each run one and three
entries, giving 72 executions across O0, O2 and ASan+UBSan. All returned Int42
with seven zero-live memory categories. Full reports for each corresponding
program were byte-identical across those three build configurations. Force,
memo, callback and group/node lifecycle metrics were unchanged by forwarding.
Each executed pair removed exactly one retain, drop, owner increment/decrement
and handle allocation. On this x86_64 build, that saved 128 requested bytes per
entry; only two cases also lowered peak requested bytes. These are runtime
ledger bytes, not RSS or a timing benchmark. LSan was disabled under ptrace, so
the sanitizer result is not a LeakSanitizer pass.

The independent CI workflow runs these focused checks separately from the
existing fixed-inventory host runner. Hosted exact-head CI and the full MLF
repository build remain separate from the local results above.
