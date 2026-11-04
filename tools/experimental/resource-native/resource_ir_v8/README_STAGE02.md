# Stage02: host-only all-body resource analysis

This package extension implements the frozen plan
`STAGE02_ALL_PATH_CHECKER_PLAN.md`, SHA256
`b6ed450b6ae9c0e67828903572583a7dd2220721b21e05d1ffa7a311c7620cd4`.
It adds only new modules. Stage01 `declarations.py` and `__init__.py`, the old
`resource_ir` package, compiler, emitter, model, native runtime, and dispatch are
unchanged. No project imports, compilation, tests, probes, or graph execution were
performed while preparing these source files. Independent implementation/helper
review and an exact finite execution plan remain mandatory before any such work.

## Public API

Explicitly import `resource_ir_v8.checker` for `check_resources(data)` and
`loads_resources(text)`. The package initializer remains declaration-only.
`ResourceError` exposes immutable `path`, `layer`, `code`, and `message`.
`ResourceCheck` is frozen/slotted with equality disabled. Its six public fields
are `canonical_json`, `sha256`, `declaration_sha256`, `derived_json`,
`derived_sha256`, and `counts`; private `_report` is built/charged once, and
`report()` returns that same immutable tuple. There is no data/run/generate or
execution adapter. Public dataclass construction and hashes are not authority.

Success means exactly `checked-resources-only`. Every source-proof/lowering,
runtime-table, Access/physical representation, code emission, model/native/ABI,
allocator/terminal, GC replacement, and performance gate remains pending.

## Implementation and preservation ledger

- `program_schema.py`: exact plain JSON snapshot, strict duplicate/nonfinite
  rejection, incremental UTF-8 byte accounting before oversized input traversal,
  bounded-depth iterators, mandatory scopes, exact operation/context preflight.
  Schema counts are checked before materializing analysis inventories.
- `declaration_adapter.py`: calls the unchanged declaration checker afresh and
  adapts canonical tuple object identities to flat integer IDs. No recursive tuple
  hash/equality/index or forged-index admission. Stage01 errors keep original
  path/code under the `declarations` layer. Complete vectors and environment order
  survive adaptation, including dead parameters.
- `ownership.py`: local source port of old checker helpers at lines 48–101 and
  288–342. Globally fresh group/node/capability/storage symbols, exact owner
  anchors, SSA liveness, tickets, strict versus non-strict Order, and explicit
  discharge are retained. No import of the runtime-bearing old package.
- `body_checker.py`: local operation-by-operation port of old lines 388–744,
  omitting public call/loop/choose. Full canonical types replace nominal-only
  comparisons everywhere. Once capture/application moves, retain/Force/carrier
  restrictions, readiness, and argument-node identity are still checked.
  Every callback and factory arm is checked regardless of reachability.
- `provenance.py`: canonical code/site/instruction/intro/use order, occurrence
  distinct provenance DAG, exact FactRefs and rule rows. Scoped allocation graph
  is same-S and acyclic. Imported home aliases have group authority only.
- `budgets.py`: monotonic creation/work budgets, atomic compound insert/copy
  helpers, incremental canonical JSON with append chunks at most 4096 bytes.
- `checker.py`: orchestrates raw ingress, fresh declarations, structural
  preflight, scoped schemas, coverage, graph checks, sorted callbacks, entry,
  final derived output and cached report. No executable consumer is exposed.

Generalize starts a separate child name scope and copies only justified Order
facts. Seal preserves capability/storage/node/group/readiness and exports Scheme
classification. Instantiate separately moves either an owner without dependent
loans or an exact anchored loan, preserving its anchor; it never calls the
owned-only consume helper for a loan. Scheme owners remain legal group authority,
but cannot enter Mono value slots. Retain/borrow preserve provenance and known
projection; Force/field/choice create conservative symbolic provenance without
inventing E0 or a local use descriptor. A deferred application always has its own
actual APPLICATION site, even for an argument-identity callee.

## Host bounds and charged categories

Raw and derived canonical JSON each have an independent 33,554,432-byte bound.
Container depth is 32; instruction count is 10,000; combined code/site count is
2,048; code/factory total captures are at most 64; factory field and external
capture categories are separately at most 32. These are host guards, not native
metadata-size or performance claims.

One per-check creation budget has 65,536 units. New rows/facts, explicit symbols,
state/order headers, every stored variable member, copied/sorted temporary member,
lookup/SSA membership, and dynamic graph/order worklist or visited membership are
charged before insertion. Compound row+inventory, operand, obligation, provenance,
choice, Order copy, and State copy helpers precharge their complete batches.
Standalone immutable record construction and its later insertion are separately
charged operations; earlier successful charges are not refunded on rejection.
Raw snapshot/parsing and the initial accepted Stage01 adapter use their separate
bounds; constant vocabulary and bounded final-encoder buffers are not semantic
analysis inventories. No other variable semantic-container copies are free.
Order searches additionally charge each examined adjacency edge against
8,388,608 shared work units. Copying edges charges creation, not search work.

Useful private boundary controls (not public program-acceptance APIs):

- `Budget.charge(n)` / `examine(n)` atomically advance the corresponding counter.
  `record_append(list, **fields)` atomically costs one row plus one member.
- `Order(budget).add(upper, lower, strict=False)`, `copy()`, and
  `below(lower, upper, strict=False)`. Add costs 3 plus a new adjacency bucket;
  copy costs 1 header + edge members + adjacency keys + bucket members.
- `State(budget, order=None, home=None, result_type=None, require_ready=False,
  finish_allowed=False)` and `copy()`. Copy costs 1 state header + values + used
  names + the full Order-copy cost, all checked before any copy.
- `Analysis(budget, declarations).choice(alternatives)` atomically costs
  3 + number of references. It is a construction helper; its callers supply
  already-derived provenance references. Synthetic budget fixtures are not valid
  whole-program provenance proofs.
- `CanonicalEncoder(limit=DERIVED_BYTES).emit(bytes)`, `string(value)`,
  `value(value)`, `finish() -> (text, sha256)`. Each emitted append is at most
  4096 bytes and checked before buffering. Helpers may build deliberately partial
  streams to exercise the byte boundary; only public checking builds reports.

Creation failure is `bounds/ANALYSIS_ROWS` at `analysis.creation_units`; order
work failure is `bounds/ORDER_WORK` at `analysis.order_edge_examinations`; derived
byte failure is `bounds/DERIVED_BYTES` at `analysis.derived_bytes`. Structural
bound coordinates and declaration wrappers follow the frozen plan exactly.
Generic/context/unknown opcode failures use `schema/OPCODE` at the instruction
path; full value type mismatch is `type/TYPE`; forbidden Scheme VALUE is
`type/SCHEME_VALUE`. Ordinary old ownership guard codes are preserved.

## Verification status

Source preparation and text-only reasoning are complete; imports, syntax
compilation, unit/helper runs, fixture probes, compiler/model/native execution,
publication, and runtime/source/GC/performance acceptance are all unexecuted.
Static fixture predictions must be frozen independently before probes and must
never be backfilled from observed test output. Separate ongoing CI repairs are
not overwritten by this source-only stage and must be adopted before integration.
