# Typed dependency graphs

An index is a zero-based slot in one graph construction. `Bootstrap.IndexVec`
exports `Index d`, `Builder s d a` and immutable `IndexVec d a`. The `d`
parameter distinguishes declaration, module, package and edge slots. Use
`fromInt` at a boundary and `toInt` when a numeric offset is needed. `get`,
`set` and `at` check `0 <= i < length`, including signed negative and very
large inputs. `indices` and `toList` enumerate insertion order.

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

## Production paths

| Path | Representation and ordering |
| --- | --- |
| Declaration SCCs | `Bootstrap.Dependency.components` interns canonical names and builds dense node and edge vectors. Both Kosaraju passes traverse IDs and indexed visited flags. Roots, outgoing edges and members keep their lexical ordering. Duplicate declarations still fail before SCC construction. Only local value references become declaration edges. |
| Module imports and instance reach | `Bootstrap.Module` uses module IDs for the shared-module cycle check and transitive visibility. External-only names are leaf vertices. It returns the named owner/reach sets consumed by resolution and crate interfaces. Aliases, source positions, import selectors and instance ownership stay on the source and interface records. |
| Package DAG and scheduling | `Package.Manifest` builds separate typed tables for packages and modules after validating names and canonical paths. Module discovery retains dependency-first order, including cycles inside a crate. `Package.Scheduler.libraryJobs` takes the closure of selected direct dependencies by ID and emits jobs in the original package order. Worker JSON is name-based and reconstructs the index on read. |

Initial manifest discovery works in IO and identifies local packages by
canonical path, releases by digest, and conflicts by their names. This phase
precedes ID assignment so its cycle and path diagnostics still use the original
trail. Namespace export fixed points operate on visible entities and selectors.
Persistent query graphs use content addresses for cache validation and
publication. The inference constraint graph has its own solver identities.
These graphs have different identity or visibility contracts from the
dependency tables covered here.

Primitive code 132 is appended to the wire inventory. Earlier code assignments
retain their meaning. The builtin interface advances to `/12` and the primitive
ABI to `mlf-primitive-133-v8`. The runtime keeps its old link markers and adds
the freeze marker for new generated code. Standalone name allocation visits entities from the original 132-entry inventory before assigning names for appended primitives. This preserves existing generated names even when a new primitive sorts ahead of a user module. Locks, interfaces, cache keys, worker
JSON and diagnostics continue to use source or crate identities.

## Reproduction

From the repository root, run the GHC, interpreter, LLVM, collector, package
and type-rejection fixtures with the following command.

```sh
python3 -B tests/indexvec/run.py --compiler INSTALL/bin/emlf --output FRESH_DIR
```

Pass `--reference-manager BEFORE/bin/mlfpkg` to check the actual plan and failure
diagnostics byte for byte against the previous implementation. The graph
fixture independently derives SCC membership by mutual reachability and checks
ordered output for every three-node graph.
