# Native shared-source transition: design baseline

This directory defines the next released-seed-native transition project. It does
not contain an implemented bridge, a new frozen archive, or a successful build
receipt. The existing `shared-haskell-v1-bridge` archive remains immutable.

The preferred architecture is **O -> H -> C**:

- **O** is the released-seed-derived frozen native compiler and matching manager.
  It uses frontend `/3`, builtin `/4`, primitives 0–94, MLFCI-1, and the old
  compact/process/async-completion runtime.
- **H** is a new maintained legacy-source cross-compiler and matching manager.
  O builds H with the exact old runtime. H itself must use only the old host
  primitive set. H implements the target language and runtime semantics needed
  to compile the unchanged current shared source.
- **C** is the current compiler and matching manager, built by H and linked with
  the exact current runtime. C implements frontend `/8`, builtin `/11`,
  primitives 0–131, MLFCI-5 and the current binary artifact formats.

The target in this design is exactly #22 c349: builtin `/11` and
`mlf-primitive-132-v7`. A later 134-primitive/builtin `/13` target, including
`freezeSTArray` opcode 132 and `stToIO` opcode 133 and their extra runtime ABI
guards, is outside this boundary. There is no automatic newest-version
selection and no claim that qualifying this target qualifies a successor.

H carrying target primitive descriptions and emitting calls to them does not
mean H can call those primitives in its own implementation. Host Prelude,
numeric behavior and constructor layout must be kept separate from target
Prelude, numeric behavior and constructor layout in the source organization.

## Why a complete transition is needed

The existing frozen lexer rejects canonical list and as-pattern punctuation;
its parser also rejects canonical unit and tuple constructors. The current
shared registry contains 135 modules. The compiler/manager import closure has
95 modules and 5,396,347 source bytes, but a package plan scans the broader
manifest inventory, including test targets and the independent oracle. The
95-module closure is not permission to remove those other sources.

The compiler/manager closure directly mentions 33 primitive operations added
after opcode 94. They include byte file IO and hashing, exceptions, bit
operations and arbitrary-precision Integer operations. Pure spelling changes
cannot supply those operations on the old host.

Retained opcodes 0–94 also need review: names and opcode numbers can remain the
same while Int width, String, Unit, list, tuple or exception representation and
forcing change. `primitive-matrix.json` lists every opcode 0–131 and explicitly
leaves signature/semantic compatibility unverified.

Old output requires `mlf_require_async_completion_v2_abi`. Current output
requires `mlf_require_haskell_boundary_v4_abi` and
`mlf_require_byte_file_v2_abi`. An empty alias for an old guard would conceal a
representation mismatch and is not part of this design.

## Concrete component boundaries

The following owners are an initial dependency-bounded review list, not a
complete implementation inventory:

1. `Bootstrap.Types`, `Primitive`, `Data`, `X.Type`, `X.Check`: target primitive
   descriptions, kinds, scalar/type rules and exhaustive cases.
2. `Bootstrap.Lexer`, `Parser`, `Surface`, `Module`, `Prelude`: real canonical
   constructor/type identity, imports and hiding, literal/pattern semantics,
   recursive scopes, classes and evidence. Adding punctuation alone is not a
   transition. Inference or evidence owners must be included when semantics
   require them, rather than bypassed.
3. `Bootstrap.LLVM` and `LLVM/{Build,Codegen,Native,StrictFields,StrictWrappers}`:
   target ABI, signed Int64 versus Integer behavior, literal emission, canonical
   constructor tags and primitive lowering. Old-host arithmetic facts must not
   silently become target optimization facts.
4. `Bootstrap.Crate`, `CrateArtifact`, `CrateCodegen`, `Separate`, and
   `Package/{Manifest,Build,Command}`: paired format validation, source closure,
   primitive/builtin/layout identities and explicit runtime selection.
5. An explicit stage driver that binds the old host runtime for O -> H and the
   current target runtime for H -> C. The old frozen inner script uses one
   runtime throughout its stages and cannot directly express this crossing.

A transition entrypoint must reject an unimplemented operation, not return a
successful placeholder for interpreter, bootstrap or qualification commands.
Actual emitted-code execution remains mandatory.

## Artifact generations

Two metadata boundaries must remain distinct:

- O's compilation of H uses O's existing MLFCI-1 artifacts and O's validator.
- H's compilation of C uses H's paired writer and reader under a new private
  intermediate identity. The MLFCI-1 *shape* may be reused only if it can
  losslessly represent every required type, source identity, evidence and
  constructor layout. That has not been proved. Changing a namespace alone
  cannot make a lossy format sufficient.
- Once C runs, C produces and consumes its own current MLFCI-5 and binary
  artifacts. H-built internal crates are not labelled current-native artifact
  qualification.

O, H and C have disjoint cache roots. Their builtin, primitive, target and format
identities must prevent deliberate cross-generation cache/artifact reuse. No
fallback decoder may weaken existing validation.

## Smallest executable prototype

The first native prototype should establish the hard host/target boundary
before a complete compiler build:

1. O actually compiles a small H cross-emitter using old-host operations.
2. That native H emits programs exercising target byte IO/digest, Integer beyond
   64 bits, signed Int boundaries, Char, and exception propagation/recovery.
   Compile/link the emitted output with the exact current runtime and run it.
3. A wrong-runtime and stale-guard variant must fail. C-only tests or a Python
   model cannot stand in for this check.
4. A two-module, two-crate fixture then carries canonical list/unit/tuple types,
   patterns, classes and literals across exports/imports with H manager's full
   dependency validation, followed by actual link and execution.
5. Test corrupted, truncated, oversized, stale and mixed-generation artifacts.
   Then check the complete original manifest inventory, including
   `Tests.IndependentCheck`, without removing targets or changing assertions.

These tests decide whether H can directly build unchanged C. A more complex
extra stage with a translated source snapshot is not adopted here. No source
translator, decoder shortcut, private source profile or reverse-generated
compiler is implemented or added to the normal build path.

## Input identity and append-only changes

`input-identities.json` pins the clean c349 source/tree, all 196 source and 108
metadata identities, the 135-module registry, the compiler/manager closure and
all 171 old frozen archive inputs. These are read-only design inputs, not a new
source admission successor or a compilation receipt.

Current `[]`, `(:)`, unit and tuple syntax is intentional standard Haskell and
current MLF syntax. Replacing it with legacy nominal constructors would not be
an equivalent source-format repair. The independent oracle is unchanged.

New transition source should be maintained in a separately named directory and
frozen with its own complete source inventory, reviewable patch and reproduction
proof only when it exists and is validated. Preserve old archives, contracts,
physical replay and receipts byte-for-byte. The old `freeze_bridge.py` requires
an actual maintained legacy checkout and rejects the final `.hs` checkout.

If a later change touches the admitted current source or generated builtin/lock
identity, it requires a separate exact append-only successor with old/new
hashes, reversible deltas and strict refusal tests. New transition files do not
silently expand the existing 196/108 admission.

## Resources and verification limits

`plan.json` records source-only bounds and unmeasured future native estimates.
A 3600-second observation window is a stop budget, not a completion-time claim.
Every native stage needs fresh cumulative output accounting and retained-receipt
space. Existing outputs count toward the workspace budget; none are implicitly
deleted or overwritten.

The initial static checks validate identity and design consistency only:

    python3 bootstrap/native-shared-transition-v1/test_contract.py
    python3 -O bootstrap/native-shared-transition-v1/test_contract.py

They do not compile H or C, prove the intermediate format sufficient, validate
native semantics, or establish fixed point. The full native route still needs
actual paired builds, lock/plan validation, both-tool fixed point, package
cold/warm behavior, async parity, cross-platform qualification and full CI.
