# Current A1 representation compatibility

`../check_integrated.py` uses `../run_current_controls.py`. The historical
`../run_controls.py`, all `../controls/` bytes, the historical builtin hashes,
and the frozen performance reproduction remain unchanged. This is a separate
finite correctness gate, not a new performance baseline or A1 acceptance.

## Explicit source migration

`source-compatibility.json` starts from the historical runner's 123 exact source
hashes and records **15 changed + 3 added** shared modules at reviewed PR #25 head
`1f4c2f817cc2de2b3b5f3ceb6b35120d7a0976c1`. There are exactly **126** modules.
Neither the private `CrateSession` owner nor `Graph.IndexStore` changed. The
maintained producer authenticator still checks all source/configuration inputs,
the actual GHC 9.14.1 O2 toolchain, inferred interfaces, builtin verification,
outputs and complete copied object inventory before/after execution. Source
hashes are reviewed inputs, never expectations generated from compiler output.

`source-migration-cf39.json` preserves the subsequent six-module transition to
`cf39c68e`. `source-migration-query-v6.json` then records the sole changed
input `Bootstrap.CrateQuery` at `8fe77dc8`. The other 125 shared inputs are
unchanged. The separately proposed printer routing change was withdrawn so
existing printer oracles remain independent.
Both prior manifests and all behavioral oracles remain pinned independently;
the current gate rejects stale inputs from either earlier source snapshot.

### Additive C4 integration compatibility

The original `source-compatibility.json`, six-module
`source-migration-cf39.json` and one-module `source-migration-query-v6.json`
remain byte-identical. The new, separately pinned `source-migration-c4.json`
chains **after query-v6**, from the exact 126-module snapshot at reviewed
PR #25 parent `d96f67726599fa4e21f236462886106434c8e417`. The migration binds
both earlier migration hashes; it cannot skip query-v6 or restore the old
`Bootstrap.CrateQuery` source. It changes exactly
`Bootstrap.Constraint`, `Bootstrap.Graph.Solver` and `MLF.BuiltinPreludeData`;
the other **123** module hashes are unchanged. The latter changes only its one
source-identity token: the current split literal, all 74 split term declarations
and every other byte remain the parent's representation. A fresh ordinary
producer must still prove full literal regeneration and independent checking;
this source inventory is not a generated behavioral oracle.

C4 changes the prepared **public** solver route, not A1's private index
algorithm. Its permitted representation relation allows the two reverse-index
outer trees and their bucket trees to rebalance. It does **not** permit changing
any graph node, alias tree, fresh counter or scope-index tree, nor any ordered
reverse-edge set. This is C4 representation compatibility, not a new A1
optimization, benchmark, historical speed claim or acceptance of A1.

`c4_session_adapter.py` creates a test-only copy of the frozen `SessionTests.hs`.
The only edits are one qualified import and replacement of the **single**
`C.solvePrepared` comparison in `runCase` by
`CurrentC4TransactionOracle.checkTransactionalOutcome`. It is not a `True` to
`False` change: the old `False` comparator still fixes bucket shape and is not
the C4 relation. The adapter requires the exact frozen input hash and an exact
inverse restoring every original byte, checks the written copy again, and
rechecks that inverse after execution. The private route, all other public
assertions, 28 traces, old expected stdout and all original controls stay intact.

`CurrentC4TransactionOracle.hs` is the independently authored complete C4
transaction comparator (original SHA-256
`bf5000014cc1aa4d97a98ee1380a9307796182dc1cfd433522308521b1a1cd8c`), with
**only** its module name changed. The adapter reverses that header and verifies
the original hash. It checks physical graph/alias/counter/scope equality,
complete independent structural and binding edge enumeration, cached sizes,
BST order, balance and nonempty buckets, both frozen and public full graph
validators, and frozen `finish` on **both** results. Left results must have the
same exact first error; a changed success/failure category is rejected.

The separate `CurrentC4OracleControls.hs` supplies a handwritten graph prepared
by the frozen solver, a genuinely different valid reverse-map/bucket shape,
exact-error success, and **13** authored rejections: graph counter/alias/node
tree, scope tree, structural/binding edges, outer/bucket cached counts, invalid
self-comparisons and changed error/result categories. These have their own
fixed stdout; they do not replace any original session group or expectation.
The runner pins all new helper sources and verifies exact newly compiled module
closures and unchanged copied production objects. The builtin driver runs
first, session driver compiles the additional transaction oracle, then the
separate comparator controls reuse those exact objects.

The cheap Python suite tests migration metadata/deltas, stale producer inputs,
all helper pins, skipped/reversed/double-applied migration stages, stale
query-v6 plus old-C4 combinations, inverse/repeated/ambiguous adaptations,
private/other-byte mutations, and weakening/removal of comparator checks. These tests do **not**
execute Haskell or claim the 13 native rejections passed. The actual maintained
gate must compile and run every control against a **new, authenticated current
GHC 9.14.1 O2 producer**; old cloud receipts or historical C4 objects cannot be
relocated/relabelled as that producer. Keep failures, use fresh output paths,
and preserve the existing resource guard.

The native-library integration intentionally changed the canonical builtin from
one declaration fragment to an SCC-split object. Its old `.mlfci`/`.mlfco` hashes
cannot be an integrated-current expectation. The historical hashes remain
mandatory for fixed-ref reproduction; the current runner explicitly rejects that
old pair rather than relabelling it.

## New builtin admission contract

No current candidate output is written into an expected hash or literal. The
fixed structural oracle is the committed `MLF.BuiltinPreludeData.builtin`, whose
source digest is part of the explicit source migration. Its existing maintained
verification receipt must prove exact fresh regeneration and full independent
checking before this runner authenticates the producer.

`CurrentBuiltinControls.hs` additionally admits the **actual supplied disk pair**:

1. Decode both files and demand exact canonical re-encoding of both complete
   byte strings.
2. Validate the interface, dependency/export boundaries and datatype layouts;
   link the decoded object through ordinary artifact admission.
3. Reconstruct the interface, complete linked declaration term, declaration
   context, exported binding map and fresh serial **from the disk object**.
   Compare the actual interface with the fixed literal before reusing its source
   metadata (names, environment, contracts, witnesses and protection sets).
4. Compare the entire reconstructed `RawPrelude` structural literal with the
   committed oracle. Run `Check.checkClosed` on its raw term and
   `checkCompilerPrelude` on the reconstruction, which independently validates
   all exported binding types and source metadata. A derived composition type is
   not substituted for this full check.
5. Require seven authored rejections: malformed interface, malformed object,
   checksum-corrupt payload, corrupt interface checksum, mismatched interface pairing, a separately
   well-typed but different declaration term, and a missing export inventory.

Only after these gates can the supplied builtin participate in the unchanged
nine old/public versus private file controls. Its observed hashes are recorded
for before/after immutability **only**, not treated as a behavioral expectation
or historical-byte identity. There is no normalization of artifact bytes,
identities, paths or errors. This establishes finite admission of this exact
canonical representation, not a proof for arbitrary representations or complete
historical-versus-current compiler equivalence.

## Preserved original controls

The original handwritten expectations and frozen algorithms are read unchanged:
**6 session groups / 28 traces, 22 admission controls, 9 parsed-file cases and
4 sealed-interface negatives**. The current runner retains exact module
resolution and immutable object checks, full finite graph/index assertions,
independent public/private outcomes and byte-identical artifacts, checked types,
raw target rechecking, pretty/parse/erasure comparisons and malformed/privacy
rejection. Expected stdout is not re-recorded from the candidate.

The canonical builtin control and the two C4 compatibility controls are pinned
in `manifest.json`, together with the exact reversible adapter. All additional
controls supplement the original finite inventory. `../test_current.py` provides
cheap static/mutation checks for source/oracle separation and fail-closed
admission wiring; it does **not** replace compiling/running the control drivers.

```sh
python3 -B tools/performance/a1-private-index/test_current.py
python3 -B tools/performance/a1-private-index/check_integrated.py \
  --producer /absolute/path/to/current-o2-producer \
  --output /absolute/path/to/fresh-a1-current-controls
```

Keep failed output trees and use a fresh path for each attempt. No bootstrap,
benchmark, expectation regeneration, source replacement or optimization
qualification is part of this gate.
