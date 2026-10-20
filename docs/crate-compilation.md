# Crate compilation

The native compiler separates four graphs:

| Graph | Purpose | Cycle rule |
| --- | --- | --- |
| Crate dependencies | Metadata and implementation ownership | Acyclic |
| Module namespaces | Imports, selection, hiding and reexports | Fixed-point resolution permits cycles |
| Value declarations | Generalization and recursive inference groups | Actual SCCs retain the existing signed-recursion rule |
| Semantic queries | Persistent checked inference results | Dependencies carry closed schemes and required nominal layouts |

A library is a crate. An executable or native test is a crate containing its
entry and private modules; it depends on the package library and direct
dependency libraries. Source CLI compilation treats its reachable module
inventory as one uncached crate. Modules remain visibility and instance-scope
boundaries, rather than independent inference units.

## Inference and identity

Namespace resolution establishes all declarations before resolving bodies.
Type exports and term exports settle to a fixed point, followed by strict
selection, ambiguity and visibility checks. Definition identities include the
crate, module, namespace, declaration role and spelling. Graph allocation IDs
never identify persistent declarations.

Classes are checked and lowered with each declaration's defining-module
instance scope. The lowered selectors and dictionaries become ordinary value
vertices. An indexed deterministic SCC traversal orders inference queries.
Each query receives exactly the observed predecessor schemes and the transitive
nominal context needed by expressions, annotations, constructors and imported
types. Candidate dictionary schemes are conservative dependencies because
instance selection can depend on types still being inferred.

Every fresh query uses the existing graph generation, solver, evidence,
elaboration, inferred-type agreement, source-erasure agreement and independent
xMLF checking pipeline. Its output has closed normalized schemes and an
independently checked implementation abstracted over its imports. Solver graphs
are transient. A cached fragment is decoded and checked again, including its
owned symbols, parameter schemes and datatype context.

A module import SCC does not require signatures. An actual recursive value
SCC retains the compiler's existing requirement for closed signatures; this
supports its existing explicitly polymorphic recursion. Acyclic declarations
retain separate generalization. Unrestricted inferred polymorphic recursion is
not added by this migration. See the [migration evidence](crate-migration.md).

## Artifacts

`emlf --compile-crate SPEC -o PREFIX` writes:

| File | Contents |
| --- | --- |
| `PREFIX.mlfci` | Versioned canonical metadata: ownership, dependency locations, module exports/reach, nominal declarations, class and instance headers, lowered layouts and closed schemes |
| `PREFIX.mlfco` | Independently checked SCC fragments and their import parameters |
| `PREFIX.queries` | Inferred/reused groups, stable member inventories and query fingerprints |

Compilation reads dependency metadata recursively. It does not read upstream
source or implementation objects. The linker subsequently loads implementation
objects, rejects crate cycles and ownership conflicts, freshens binders, compares
actual consumed schemes and nominal layouts, resolves the entry dictionaries,
and checks the closed program. Reexports retain the original defining identity.
Recorded dependency semantic fingerprints must still match: removing an export
or changing a type, class, instance or namespace contract requires fresh consumer
metadata. Implementation and private value changes leave that contract stable.
A fresh consumer can reuse its unchanged inference queries while recording the
updated dependency contract.

The interface points to dependency metadata at stable absolute artifact paths;
its own object is the sibling `.mlfco` with the same basename. Moving an artifact
pair preserves that sibling relationship; moving dependencies requires rebuilding
the metadata locations. Checksums detect damaged or mismatched artifacts and
are not signatures. There is no source fallback.

The built-in Prelude has one canonical generated crate identity and artifact
location shared by sibling dependencies. It cannot be redefined by user source.

New objects use `MLFCO-2`: one sorted pool of canonical datatype declarations
and, for each fragment, ordered references for its interface and actual term
contexts. Keeping those two contexts separate lets linking detect a forged
layout. `MLFF-2` stores the remaining fragment metadata and canonical body with
a body checksum. Decoding restores the ordinary checked fragment and checks its
closed term independently. The reader rejects invalid references, duplicate or
unused pool entries, noncanonical encodings and checksum failures. Existing
`MLFCO-1` objects remain readable with their original checksum rules; no old
module compiler is retained.

The decoder retains the opaque `CheckedTerm` returned by the independent checker.
Linking can reuse that result for the exact term; raw fragments still cross the
checker. Cached queries retain the same proof only when their complete canonical
datatype context agrees, and recheck after a context replacement. Ownership,
parameter schemes, layouts and checksums are still validated, and the assembled
whole program receives its final independent check. Binding extraction validates
its initial environment once, then extends it with inferred or explicitly checked
types. Shared datatype checksum prefixes compose the original scalar rolling
hashes exactly; object bytes and checksum formats remain unchanged.

The remaining commands are:

```sh
emlf --show-crate PREFIX.mlfci
emlf --link-crate PREFIX.mlfci > program.xmlf
emlf --run-crate PREFIX.mlfci -- argument
emlf --crate-to-llvm PREFIX.mlfci > program.ll
emlf --crate-to-llvm-gc PREFIX.mlfci > program-compact.ll
```

## Driver protocol and caches

The package manager generates `SPEC`; normal users should use `mlfpkg build`.
It is a sequence of eight length-framed strings, each `length:value` with lengths
measured in the language's String units:

1. `MLF-CRATE-1`.
2. Stable crate identity.
3. Entry module, or the empty string for a library.
4. `true` to disable implicit Prelude, otherwise `false`.
5. A framed list of framed `(module name, absolute source path)` pairs.
6. A framed list of direct dependency `.mlfci` paths.
7. Absolute persistent inference cache directory.
8. Absolute prefix for the shared built-in Prelude artifact pair.

Query keys include compiler identity, canonical resolved syntax with lexical
alpha normalization, exact polymorphic predecessor schemes, and needed nominal
layouts/kinds. They retain literal bits, annotation flags and evidence roles.
They exclude predecessor body hashes. SHA-256 addresses cache files; the full
canonical key is also compared on reload. A damaged cache entry is a miss.
Writers use locks and atomic replacement.

`MLF-QUERY-CACHE-2` omits repeated datatype contexts only when both the fragment
header and its actual term context match the layouts already recorded in the
complete query key. Reloading restores those layouts from the current query,
then performs the same ownership, scheme, context and independent term checks.
This also permits canonical datatype-binder renaming. Older cache entries remain
readable; an incompatible or malformed entry causes fresh inference.

The package manager's outer artifact cache remains conservative about source
and implementation inputs because assembly and final code must reflect changed
bodies. An outer miss can still reuse all unaffected inference groups. Reports
label the source of reuse, so an outer hit cannot masquerade as an exercised
inference-cache test.
The manager loads and validates the complete metadata graph on each new crate
build. It independently decodes the new root object. Upstream object checks can
be reused only through a valid SHA-stamped artifact and recursive dependency
receipt covering both exact metadata and object paths. Conflicting proofs are
rejected, and every reused pair is rehashed. Unproven objects retain independent
decoding. A stamped validation sidecar records checked and reused object counts;
outer hits report zero new checks and identify their artifact-cache provenance.
Build reports embed compact query summaries and retain paths to full per-group
reports. The package manager stamps the saved summary alongside the crate
artifact; outer cache hits read that summary rather than the detailed inventory.

The current driver schedules crates and inference SCCs serially. Independent
ready crates, and SCCs whose predecessor schemes are closed, provide possible
process-level parallelism without changing generalization. Cache locks already
serialize writers to the same inference namespace. No parallel speedup is
included in the migration's performance claims.

LLVM currently optimizes the linked erased program. Nominal constructor tags,
global optimization and closure layouts remain code-generation inputs.
Inference-fragment reuse does not by itself imply native object reuse. The
[migration ledger](crate-migration.md) records the implemented code-generation
cache boundary and accepted measurements. The [validation record](crate-validation.json)
binds the six native groups, fresh self-hosting, exact tool/source identities
and isolated performance evidence.

Crate code-generation input keys follow the checked entry's transitive value
dependencies. All fragment, scheme, visibility and nominal-layout checks finish
before this lookup. The key retains the declaration spine and complete constructor
and runtime ABI; only bodies unreachable from the entry are masked. Every branch
and captured free reference contributes conservatively, including recursive groups.
Identities are normalized before dependency analysis and again after masking.
The key is versioned separately from the ordinary erased-input query.

This is reuse of one complete linked program. The projection is never sent to the
optimizer or emitter: cold LLVM and optimization rules remain unchanged. A cache
hit may retain older LLVM for irrelevant declarations; it preserves the entry's
behavior and the complete ABI. Final package tests compare clean and incremental
executables and verify that live dependencies still invalidate generation.

The optimizer builds capped free-use counts beside normalized rewrite subtrees,
without first indexing an unused copy of the input. Inlining
uses these counts and retains subtrees with no reference to the substituted
variable. Child order, rewrite rules and fresh-name allocation order are
unchanged. Permanent tests compare each index with independent scoped scans and
compare complete normalized trees with the preceding rewrite algorithm.
