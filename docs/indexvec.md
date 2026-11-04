# Typed dependency graphs

An index is a zero-based slot in one typed domain. `Bootstrap.IndexVec`
exports `Index d`, `Builder s d a` and immutable `IndexVec d a`. The `d`
parameter distinguishes declaration, module, package and edge slots. Use
`fromInt` at a boundary and `toInt` when a numeric offset is needed. `get`,
`set` and `at` check `0 <= i < length`, including signed negative and very
large inputs. `indices` and `toList` enumerate insertion order. A
`FixedBuilder` allocates exactly its declared length and omits the growable
header; its typed reads and writes have the same bounds checks and its freeze
has the same snapshot semantics.

A builder contains a shared header with its logical length, capacity and
boxed `STArray`. `push` returns the inserted index. On growth it doubles
capacity, copies the live cells and installs the new storage in that same
header, so aliases see subsequent appends. The last growth saturates at
2⁶⁰ − 1 cells, the existing ST array allocation bound. Invalid lengths,
out-of-range access and append at the bound raise distinct errors. Memory
exhaustion can occur earlier.

The new `freezeSTArray :: STArray s a -> ST s (Int -> a)` primitive takes a
snapshot at action execution. The GHC host copies the boxed array. The native
runtime copies pointers into a GC-scanned closure environment. Both look up a
cell in O(1) and preserve element laziness. The region parameter in `runST`
keeps mutable handles local. Freezing a builder takes O(capacity), and
native/GHC append is amortized O(1). The interpreter captures the current
persistent `IntMap` of cells and its lazy default. Its lookup has the cost of
a trie search. `fromList` uses exact allocation when the input is enumerable.

`IOWorld` is the distinguished state token for arrays used by IO actions.
`stToIO :: ST IOWorld a -> IO a` constructs a lazy IO action; executing it
runs the state action, and its result remains lazy. Repeating the IO action
executes the state action again. World arrays may be shared between IO calls
and callbacks, and snapshots retain their old contents. The rank-2 `runST`
interface still prevents world arrays and local region arrays from crossing
one another. The interpreter stores world cells in traced boxed arrays so
unreachable handles can be collected; local `runST` regions retain their
independent persistent store.

The binary graph reader checks the header and checksum before allocating an
exact-size world builder. Each node's child reads, depth and expanded-work
checks, and final write share one `ST IOWorld` action. Its checked entry is
written directly to the canonical slot. The frozen vector serves graph lookup
and canonical-order checks. Legacy `Value` trees are
materialized on demand, while the low-level `decodeTables` compatibility entry
retains its original caller-supplied layout validation path.

## Production paths

| Path | Representation and ordering |
| --- | --- |
| Declaration SCCs | Module resolution assigns each visible value or method entity a typed declaration ID. Each resolved global expression contains that ID. The SCC builder walks the expression to read its edges. One path-based DFS tracks discovery and closure in an indexed mark table. An edge to an open vertex merges candidate roots. Closing a surviving root emits its whole component in the historical finish order. Roots, outgoing edges and members keep their lexical ordering. Duplicate declarations still fail before SCC construction. Only references to active declarations contribute local SCC edges. |
| Module imports and instance reach | `Bootstrap.Module` uses module IDs for the shared-module cycle check and transitive visibility. All modules in an SCC share one reach set. In dependency-first order each component unions its member IDs with the previously computed sets of its successors. External-only names are leaf vertices. It returns the named owner/reach sets consumed by resolution and crate interfaces. Aliases, source positions, import selectors and instance ownership stay on the source and interface records. |
| Datatypes used by crate queries | `Bootstrap.CrateQuery` indexes validated declarations in lexical order. Each SCC query unions the precomputed reach sets for its observed type names, constructor owners and binding schemes, then reads just those declarations by ID. |
| Persistent query graph | During admission, physical wire IDs share decoded and hash-checked read pairs across owners. Closure validation resolves dependency versions and walks typed ordinals with three DFS colours. An exactly equal, previously admitted canonical generation retains its content address. Publication still verifies the retained payloads. |
| Package DAG and scheduling | `Package.Manifest` builds separate typed tables for packages and modules after validating names and canonical paths. Module discovery retains dependency-first order, including cycles inside a crate. `Package.Scheduler.libraryJobs` takes the closure of selected direct dependencies by ID and emits jobs in the original package order. Worker JSON is name-based and reconstructs the index on read. |

The resolver stores the canonical name for each value or method in its declaration
slot. A top-level reference is a `Bootstrap.Resolved.Global (Index Declaration)`.
An overloaded string pattern stores the method IDs for equality and conversion.
Each binding owns its indexed RHS, and both SCC construction and instance helper
capture read that expression directly. Re-exports and qualified imports retain
the defining entity's ID. A local
binder masks a top-level spelling before an edge can be recorded. Distinct
entities can even share an emitted spelling. An inactive external entity never
adds a local edge, and duplicate emitted names among active declarations still
fail. The source-to-ID association belongs to one resolution of one crate.

Class selectors, dictionary bindings and synthetic entries can appear after
resolution. They receive new slots without moving the source IDs. Class
lowering connects resolved method slots to selectors and adds the generated
evidence dependencies. DFS ordering uses separate lexical ranks. Consumers
that start with generated or independently lowered syntax can still build a
graph from names. The file query driver selects the members of each source SCC
from the indexed declaration table, preserving source order within the group.
Named class lowering, xMLF generation and the artifact writer project the
spellings they consume from the table. Only stable names and digests enter
artifacts and cache keys.

Initial manifest discovery works in IO and identifies local packages by
canonical path, releases by digest, and conflicts by their names. This phase
precedes ID assignment so its cycle and path diagnostics still use the original
trail. Namespace export fixed points operate on visible entities and selectors.
The persistent query format records keys, digests and ordered dependencies.
Its temporary ordinals belong to one admitted graph. The inference constraint
graph keeps its own solver identities.

Primitive codes 132 and 133 append array snapshots and `stToIO` to the wire
inventory. Earlier code assignments retain their meaning. The builtin interface
is `/13`, the builtin crate identity ends in `:13`, and the primitive ABI is
`mlf-primitive-134-v9`. The runtime retains
the old link markers and adds a marker for the IO-world bridge. Standalone name
allocation visits the original entities before the appended primitives and
`IOWorld`, preserving existing generated names. Locks, interfaces, cache keys,
worker JSON and diagnostics continue to use source or crate identities.

## Reproduction

From the repository root, run the GHC, interpreter, LLVM, collector, package
and type-rejection fixtures with the following command.

```sh
python3 -B tests/indexvec/run.py --compiler INSTALL/bin/emlf --output FRESH_DIR
```

Pass `--reference-manager BEFORE/bin/mlfpkg` to check the actual plan and failure
diagnostics byte for byte against the previous implementation. The graph
fixture compiles a library and a client in separate declaration domains.
With a wire-compatible previous compiler, pass
`--reference-compiler BEFORE/bin/emlf` to check every producer/client pairing
and run each linked program with both readers. The ordered SCC
fixture independently derives SCC membership by mutual reachability and checks
ordered output and reach for every three-node graph, deep chains and rings.
It also checks query depth, corrupt dependencies and canonical generation reuse.

The installed compiler measurements and their raw receipts are in the
[comparison report](../benchmarks/results/2026-11-04-indexvec/README.md).
