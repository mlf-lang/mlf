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

The only new Haskell control is pinned in `manifest.json`. Its malformed controls
are additional to the original finite inventory. `../test_current.py` provides
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
