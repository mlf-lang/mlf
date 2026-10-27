Fingerprint sharing A + C + D: isolated source candidate, not yet built/run
=======================================================================

Source tree (ONLY these two files edited by this task):
  /workspace/scratch/3f83e2ebe290/mlf-crates-fingerprint-source-20261026
  libraries/mlf-crates/Bootstrap/Crate.hs
  libraries/mlf-crates/Bootstrap/CrateArtifact.hs

Base namespace-candidate patch remains exactly
  8af698b399471bedcace8411d1db298dc5f7bf6913c30d065dea0b1dcfc26dcb
when excluding the two new files. No edits to S1, frozen inputs, Module.hs,
BuiltinPreludeData, locks, Lexer, tests in the production tree, or remote state.

Implementation
--------------
A. makeObjectWithPayload constructs one lazy pooled payload from the FINALIZED
   fragments, pairs it with the same CrateObject carrying fingerprint(payload),
   and makeObject retains its old API by projecting the first component.
   compilePreparedWith is a result-builder variant; compilePrepared retains
   its preceding API and projects only object/report. Both routes call exactly
   the same Artifact.validateInterface before returning the builder result.
   Only compileSources carries object/payload/report to writeObjectWithPayload.
   No source-finalization boundary is crossed with stale raw payload text.

C. decodeInterface still checks the raw prefix checksum first, then executes
   every parser and semantic validator in the preceding order. Its LAST test
   compares the complete input with pack(interfaceFields iface ++ [checksum]),
   using the checksum already verified above. It does not compare only fields,
   trust checksum equality to mean text equality, or skip canonical framing.

D. writeObject and the paired-payload writer bind one encodeInterface result
   and use exactly that text both for the .mlfco metadata fingerprint and the
   .mlfci contents. .mlfco still writes first. Legacy MLFCO-1 uses the original
   fragment serialization and never demands the irrelevant pooled payload.
   New encoder helpers require the exact corresponding immutable text; callers
   are the paired producer/writer, not decoders or externally supplied caches.

Equivalence argument
--------------------
A: p = encodePooledPayload finalizedFragments. The old object fingerprint is
   fingerprint p, and its old final encoder independently computes the same p
   from the same immutable fragments. Pairing/sharing p preserves every scalar,
   encoded datatype pool/reference, header/body distinction, object fingerprint
   and the four MLFCO-2 fields. The identity proof is syntactic immutable-input
   equality, NOT equality of two potentially colliding hashes.

C: Let raw input decode to prefix P and supplied checksum c, with c=H(pack P)
   already verified; let canonical reconstructed fields be Q. The old test is
   input == pack(Q ++ [H(pack Q)]); the new test is input == pack(Q ++ [c]).
   Either equality requires canonical framing and P=Q by framing injectivity,
   so c=H(pack Q). Thus the tests accept exactly the same bytes, without any
   collision-resistance assumption. Both reject with the same final error after
   identical preceding checks. Leading-zero lengths remain rejected.

D: iface is immutable and encodeInterface is pure. Both original writes use
   the same text; let sharing only avoids recomputation. Lazy let bindings keep
   filename validation before object/payload demand. The new paired writer's
   constructor case is INSIDE lazy contents, not outside the IO action; moving
   it outside would incorrectly change invalid-filename error priority.

No validation functions were removed or weakened. static-review.json hashes
the exact unchanged validateInterface, interfaceFields/rawInterfaceFields,
encodePooledPayload, and full decodeObjectFields/decodeObject definitions.

Authored controls: expected 2503, NOT YET EXECUTED
----------------------------------------------
FrozenFingerprint.hs contains exact preceding encodeInterface, decodeInterface,
makeObject, encodeObject and writeObject bodies. It deliberately shares unchanged
parsers, framing, pooled serialization and semantic helpers; this is independent
changed-logic differential coverage, not a new independent whole compiler.
The source/excerpts/hashes and unchanged dependency pins are in oracle-manifest.

FingerprintDifferential.hs tests:
* 3 identities (ASCII, Unicode/supplementary, combining/NUL/newline) x 8 fragment
  cases: empty, Int, Unicode payload, repeated layout, distinct header/body,
  header-only, body-only, and opaque independently checked fragment.
* Old/new object and interface byte equality, paired payload and interface reuse,
  unchanged validateInterface acceptance; header/body distinction is not repaired.
* Canonical metadata acceptance and exact old/new error results for checksum,
  framing/truncation/epoch, semantically invalid inventories, executable metadata,
  malformed protection, verified-but-noncanonical inner framing.
* Semantically valid but noncanonical sorted module/binding/protection fields,
  with independently recomputed raw checksums; exact final canonical error.
* Unchanged malformed object rejection; wrong paired payload still fails existing
  object checksum validation (no unchecked decoder was introduced).
* Lazy unused fragments/interface; preserved compilePrepared API type witness.
* Actual old/new .mlfco/.mlfci bytes, including legacy encoding; first-write failure
  must not create metadata, second-write failure leaves the first complete object;
  NUL filename is rejected before demanding bottom object/payload.

Future command (PARENT ONLY after authenticated producer build + resource permit):
  python3 W/validation/fingerprint-sharing/run_fingerprint_differential.py \
    --build-receipt <S2 producer build receipt> \
    --source-root /workspace/scratch/3f83e2ebe290/mlf-crates-fingerprint-source-20261026 \
    --output <new isolated output directory>
Replace W with /workspace/scratch/3f83e2ebe290/mlf-crates-profile-work-20261026.
Runner authenticates producer objects, copies rather than links them, compiles
only the frozen oracle and harness, pins inputs, and verifies original producer
unchanged. New transport C objects are built separately. It does not build the
compiler or run native MLF bootstrap. GHC flags include O2/fpedantic-bottoms/
fno-state-hack. It expects exactly 2503 checks and empty stderr.

Static status and remaining qualifications
-----------------------------------------
git diff --check passes; Python runner py_compile passes. No Haskell parser,
typechecker, compiler build, harness or performance run has been executed here.
The parent's official generator must regenerate/verify any required producer
identities/locks, then shared-language acceptance controls and full14 target-cold
artifact/median/RSS benchmarks must pass. Final checked .mlfci/.mlfco must remain
byte-identical; no target inference/cache is reused. Added payload/interface
retention may increase residency; measure it rather than assuming sharing wins.
No component or overall speed gain is claimed, and gains are not additive.

2026-10-27 validation revision for separately-authored streaming checksum change
----------------------------------------------------------------------------
The official P2 producer also contains an intentional Separate.hs zero-start
streaming checksum implementation authored by audit_measurement. This agent
edited only this validation folder during the revision, not S2 or the producer.

Do NOT simply replace an unchanged dependency pin. oracle-manifest.json v2 moves
Separate from unchanged pins to an explicit changed_dependency_oracles entry:
- Original full source is preserved as original-Separate.hs and pinned to the
  original868a4074204a9522f98eaed5ed1a2bafb56f2219b49a523e9ddf99ed949e0388.
- Candidate is pinned to20638086fbdbcffa888cf12dd05d1f901d7963c2870cff36aa0594087b224c0d.
- Runner additionally proves all source bytes outside fingerprintFrom through
  the beginning of fingerprintPower match the frozen original exactly.
- Every OTHER original shared dependency pin is retained without relaxation.

FrozenFingerprint now independently contains original indexed fingerprintFrom
and fingerprintStateFrom, fingerprint, power/part/append/after. Frozen artifact
encoder/checksum operations use these old loops. Additional frozen pooled, unit
and contextual serializers ensure nested oracle payload checksums also use old
loops; there are no Separate.fingerprint calls in the frozen oracle. Unchanged
framing/parsing/semantic checks remain shared as explicitly scoped before.

1,594 additional checks, added to the preceding909 =2,503:
* 16 texts including empty, ASCII, NUL/newline, combining Unicode, supplementary
  characters, all scalar/UTF8-width boundaries, and lengths31/32/33,255/256/257,
  4095/4096/4097.
* Six initial states including zero, nonzero, negative, modulus and arbitrary-
  precision40-digit magnitudes. Seven start positions include negative, zero,
  positive, exact end and beyond end. Production full digest, seeded digest and
  state compared directly with frozen original loops, plus part/append/after.
* Ten exception-priority combinations: bottom text/index/each seed, negative
  offset with bottom seed, terminal bottom state and invalid Unicode scalar.
  Both independent outcomes must fail with identical exception text.
* Six explicit lazy/strict controls: terminal pair WHNF leaves seeds untouched,
  each terminal field can be demanded independently, nonempty loop retains the
  original strict state updates.

No Haskell build or test was run during this revision; only Python py_compile
and static pin/outside-region comparisons executed. static-review.json retains
the earlier A/C/D-only report; separate-pin-transition.json and current hashes
document this additional validation scope. Parent serial qualification pending.
