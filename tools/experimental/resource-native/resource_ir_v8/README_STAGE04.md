# Experimental IR8: static checks and native metadata packets

This additive experiment is separate from the maintained resource IR v7 frontend
and runtime. No default command, compiler exporter, v7 dispatcher, evaluator or
allocator imports this package. The existing source path still rejects a shared
generalized term used at different closed types. This work does not enable a new
runtime mode, replace GC, or establish a speedup.

## Available layers

- `resource_ir_v8.declarations`: bounded declaration/type checking only. The
  detailed declaration API is documented in [README.md](README.md).
- `resource_ir_v8.checker`: fresh raw IR8 all-path resource checking. See
  [README_STAGE02.md](README_STAGE02.md).
- `resource_ir_v8.metadata`: fresh raw IR8 static type, representation, origin,
  Access/Transport and storage-obligation closure. See
  [README_STAGE03.md](README_STAGE03.md).
- `resource_ir_v8.packet`: deterministic C metadata source generation from fresh
  raw IR8. `emit_packet(data)` and `loads_packet(text)` return immutable source and
  manifests. They never run a compiler, evaluate a graph or admit source code.
- `packet_v8/ir8_packet.h` and `.c`: bounded structural validation of the compiled
  immutable metadata packet. This is not a callable-body or runtime ABI.

Each Python admission layer rechecks its lower raw input. Cached results and
producer-supplied metadata are not alternative admission paths. The C validator
checks packet structure and expected bindings; it does not recheck raw IR. The exact normative design is
[CORE_CONTRACT.md](CORE_CONTRACT.md), SHA256
`0c54e24fe48deda73547e0dd3a7e9eb285ba0b36d5d938ee8c35a312d509ee83`.
Its historical adoption gates and unimplemented future obligations remain part
of the preserved contract; the current implemented layer boundaries are above.
The earlier stage READMEs describe their source-preparation scope, not a claim
that later qualification never occurred.

## Reproduce the host-only tests

From the repository root, on POSIX with unoptimized Python 3.12:

```sh
python3 -B -S tools/experimental/resource-native/tests/run_ir8_host.py \
  --output /tmp/ir8-host-fresh
```

The output path must not exist. Use a new path for every attempt. The runner runs
exactly four standalone test scripts, expects 103 declaration, 170 resource,
117 metadata and 85 packet tests (475 total), rejects skips/failures/errors, and
retains each command, bounded streams and evidence. It sets each suite's required
fresh evidence environment. These are **script entrypoints**, not a promise that
unittest discovery can import the evidence-producing modules directly.

The packet script also generates the twelve finite C fixture source sets and
stops before compilation. Neither the runner nor the host-only CI job launches
native code, a language compiler, evaluator, model or checked graph. The runner
has finite process, time, memory, stream and retained-evidence limits; its receipt
states which commands completed and preserves failures. A successful host run is
not native ABI or runtime validation. The runner is a bounded test orchestrator,
not an adversarial-code or filesystem sandbox.

The `IR8 host checks` workflow runs this explicit entrypoint and retains its
artifacts. Existing CI and default runtime behavior are separate. No new external
Python package or native toolchain is needed for the host suite.

## Native packet qualification boundary

An independently reviewed finite native stage compiled the unchanged production
emitter/validator output and checked twelve packet baselines: 80 structural
mutation rejections, 24 repeat/copy acceptances, two coherent structural-OK
mutations rejected by a fresh raw-input correspondence oracle, and 15 private
arithmetic controls. Those results are historical, exact-source evidence, not
new executions by this host runner. The final template and driver had two
separately reviewed test-only corrections; the original 85-test run did not
qualify those later files wholesale. Fresh publication host results must be
reported separately from the retained native results.

Observed packet sizes were 3,672–11,564 bytes, alignment 4, padding 0–3 bytes,
workspace 49,992 bytes, and report size 88 bytes. These finite measurements do not
prove maximal public capacity. Private arithmetic buffers are not valid maximum
programs. Packet bounds are 4 MiB for actual packet storage, 128 KiB for validator
workspace and 67,108,864 work units. Additional runtime objects are not included:
`runtime_total_static_bytes` remains null and body binding remains unbound.

The packet's copied digest fields and structural validator alone cannot prove
semantic authenticity. The independent oracle must freshly check the exact raw
IR and compare every decoded packet field, actual object census and selected
variant supplement. Coherent tampering controls explicitly demonstrate this
trust boundary. Readable immutable input and valid nonoverlapping caller buffers
are API preconditions; no arbitrary-pointer safety promise is made.

Preserved native qualifications include the MPFR 4.2.1-header/4.2.2-library warning,
one lost first-TU dependency file in a failed historical compilation, the initial
compiler-plan time-limit variance (actual time below both limits), and historical
fixtures 01/02 whose lto-wrapper file was not pre-pinned. Later evidence did not
rewrite those earlier attempts or prove the warnings harmless. Native/compiler
reruns require their own exact tool/source/command/evidence plan; this host runner
does not perform or silently substitute one.

## Still unsupported or unqualified

- Real runtime body binding, complete typed-static runtime storage and dynamic
  origin/Access/transport/pending/memo/capture/curried-instance guards.
- Runtime/model equivalence, enlarged allocator ledger and terminal lifecycle,
  and unchanged-default runtime requalification for that future ABI.
- Current-target shared-polymorphic source proof/lowering, ordinary checking and
  erasure correspondence, including outer-first conditional proof substitution.
- Callable-valued SUM storage. Legal callable DATA and scalar SUM with an external
  callable factory do not expand that restriction.
- General MLF coverage, complete GC replacement, performance or Perceus superiority.

The earlier allocator/default terminal policy is unchanged by this additive
package. Future integration must not infer runtime acceptance from these static
checks, matching hashes or fixture names.
