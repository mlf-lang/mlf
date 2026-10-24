# Independent Haskell-first frontend review

Review date: 23 October 2026; implementation and focused evidence reviewed against local commits `53b8837` and `a24b8e0`, with the subsequent direct-dependency configuration repair and refrozen bridge rechecked separately below. This reviews the shared-source migration against `Haskell-First-Revision.md`, not the superseded `RebindableSyntax` design. It combines independent source inspection, bounded GHC 9.14.1 probes, and verification of the final committed focused evidence. It is not a whole native build, bootstrap, fixed-point, or O0/O2 qualification receipt.

## Executive assessment

The new standard class identities, ordinary GHC facade, canonical do-method references, recursive-let SCC treatment, and explicit rejection of unsupported syntax are the right design direction. The review found real semantic defects in operator fixity, source constructor scope, instance-method visibility, and default-method demand. The reviewed repairs are now present. All three focused parser/native-interpreter shards and the separate 94-file grammar shard pass against the settled source and the same authenticated O0 executable. All 94 shared modules compiled with GHC O0 and all 12 executables linked. No remaining behavioral mismatch is known in the reviewed repairs. This is a bounded source-review conclusion, not approval of the whole migration: combined whole-corpus name resolution, full native MLF typing/code generation, dual-host interface qualification, O2, bootstrap and fixed-point gates remain incomplete.

The owned-corpus literal annotation campaign has meaningful independent evidence: 41 actual GHC-inferred generalized definitions were concretized through ordinary source signatures. The agreed qualification boundary is the closed manifest: source/profile validation checks grammar and names, while actual same-source qualification also requires both builds and an exported-interface audit. It does not promise that every newly marked `.hs` module infers identical interfaces on both compilers.

## Findings and current disposition

### 1. Spelling-based fixity cannot apply to rebound operators

Initial `Parser.sharedBindExpr` through `sharedMultiplyExpr` resolved operator values lexically but still assigned facade fixity by spelling. Haskell gives a newly bound operator the default `infixl 9` when it has no fixity declaration. In particular:

```haskell
let { (++) x y = subInt x y } in 10 ++ 3 ++ 1
```

GHC returns 6. A parser that retains facade `infixr 5 ++` produces 8. A bounded GHC 9.14.1 expression probe confirmed 6. This is an accepted-program meaning difference, not a request for general custom fixity support.

The chosen bounded repair is appropriate: allow prefix uses of supported symbolic names, but permit infix uses only when namespace resolution identifies the canonical `MLF.Primitive` binding whose fixity the parser knows. A renamed/re-exported canonical entity retains its identity and may remain supported. A merely same-spelled local/custom/qualified operator must be rejected explicitly. Custom fixity declarations remain outside the subset.

**Follow-on issue found during repair:** tagged infix references must be normalized before lexical dependency/SCC analysis. Otherwise `let { (+) x y = x + y } in (+) 1 2` loses its self-edge, becomes a nonrecursive `SLet`, and its own RHS can accidentally resolve to facade `(+)`. The signed variant must not escape rejection either. The worker added `Dependency.lexicalValueName` and used it in dependency and free-name analysis; static inspection confirms the normalization. Both unsigned and signed self-recursive regressions are now present. The final source-bound parser/namespace shard passes both regressions; broader native qualification remains separate.

### 2. Source True, False and Unit must obey imports

Initially `sharedAtom`/pattern parsing converted `True` and `False` straight to canonical literals. `Module.resolveType`, `resolvePattern`, and `resolveBound` bypassed lookup for `Unit`. That admits names absent from scope under `NoImplicitPrelude`, or hidden/abstractly imported constructors. GHC requires the corresponding source names to be in scope.

The repair tags actual source constructor/type references and routes them through lookup, while preserving genuinely internal canonical literals. Static inspection confirms the separation now covers expression, pattern, type and datatype-field forms. The focused namespace shard covers absent/hidden constructor cases and passes. Broader qualification should retain abstract `Bool`/`Unit` imports, qualified constructor uses, explicit hiding, and positive ordinary constructor cases.

### 3. Module-local/import ambiguity must remain

An attempted repair briefly changed module scopes to prefer local declarations over imported entities. This was reverted after an independent GHC probe:

```haskell
import Prelude (Integer, (+), return)
return :: Integer
return = 3
answer = return + 1
```

GHC reports an ambiguous occurrence of `return`. Lexical let/lambda shadowing is different and remains valid. The existing union-of-identities module scope behavior is correct. Do not make module scope left-biased in a later cleanup.

### 4. Provided instance methods must be visible

GHC rejects `import Prelude (Functor)` followed by an instance supplying `fmap`, because the method is not visible. GHC accepts a qualified `Prelude` import and `instance P.Functor Box where fmap ...`, so visibility must be by exact entity, not only unqualified spelling.

`renameInstance` initially fabricated the method entity from the resolved class without checking visibility. The worker has added a shared-source check that supplied method identities occur in the visible entity set before adding internal standard defaults. This is the appropriate distinction. Standard defaults themselves need not be imported by the source author. Custom classes with the same spelling must not receive standard defaults.

### 5. Standard defaults must preserve partial-application demand

The first native defaults were extensionally plausible but over-eta-expanded. The installed GHC 9.14.1 `GHC.Internal.Base.hi` gives these relevant forms:

```haskell
(<$) x = fmap (const x)
(<*>) = liftA2 id
(<*) = liftA2 const
liftA2 f x = (<*>) (fmap f x)
(*>) x y = (<*>) ((<$) id x) y
(>>) x y = (>>=) x (\_ -> y)
return = pure
```

The first four must not acquire extra lambdas. With supplied `fmap = error "fmap bottom"` or `liftA2 = error "liftA2 bottom"`, GHC throws when evaluating `seq ((<$) 1) 7`, `seq (<*>) 7`, and `seq (<*) 7` at appropriate `Box` types. The old native default AST returned 7 because its outer lambdas delayed the bottom. A bounded `runghc` probe confirmed all three throws.

The worker has changed these defaults to the exact eta levels above; static inspection confirms the change. `*>`, `>>`, and direct `return` already had the right forms. Final qualification must exercise default and explicit-method branches, partial as well as full application, and both O0 and O2. Panic tests must assert the exact runtime message (or separately establish successful compilation), because a generic `isLeft` also passes on parser/type errors. A sequencing override must itself be polymorphically valid: `(>>) a b = b` with a poisoned first action is valid; `(>>) a b = Box 91` is not a valid general `Box b` result. Both test issues were corrected during review: panic tests now use exact `failsWith` assertions, and the sequencing override uses a polymorphic panic to prove that the override was selected. Direct substitution of provided method bodies does not remove the need to test recursive method/dictionary uses.

### 6. Explicit shared Prelude imports must not expose the legacy interface

`Module.preludeSource` is the legacy two-method Monad interface, whereas `MLF.Primitive` has the new standard hierarchy. Initially shared `.hs` import validation allowed `import Prelude`, which therefore denoted a different class/method API from GHC's actual Prelude. In particular, `Monad(..)` cannot expose `bind` on one host and `>>=`, `>>`, `return` on the other.

The smallest truthful subset is to reject explicit `Prelude` imports and a shared source module identity of `Prelude` until the legacy builtin is properly segregated or a real standard Prelude interface exists. Otherwise a user-defined shared `Prelude` also takes the legacy builtin injection/import-bypass path. The legacy builtin may remain internal to `.emlf` handling. The worker now explicitly rejects both shared imports of `Prelude` and the shared module identity `Prelude`. Static inspection confirms both checks; executable regressions are present.

### 7. Literal type agreement is bounded by the qualified manifest

A bounded GHC facade probe established:

```haskell
plainInteger = 1       -- Num a => a
plainString = "hello"  -- IsString a => a
asDouble :: Double
asDouble = 1           -- accepted
```

Native shared parsing still lowers these spellings directly to concrete `SIntLit`, `SDoubleLit`, and `SStringLit`. Therefore general literal polymorphism/type-directed conversion is not implemented merely by removing `RebindableSyntax` from GHC.

The owned-source audit substantially addresses the measured corpus problem:

- The plan contains exactly 41 definitions in 19 files: 39 `IsString` and 2 `Num` generalizations.
- Every exact planned ordinary signature is present in current source.
- The post-change GHC dump covers 98 units, comprising 94 shared units and four adapters.
- It contains no `Num`, `Fractional`, or `IsString` constraints in shared signatures; the adapter's real `IsString String` instance remains, as it should.
- At the initial audit checkpoint, independently removing exactly the recorded signature insertions reconstructed the recorded original SHA-256 on 17 unchanged files. The remaining files were already being edited, so the annotation receipt is historical rather than a final-source identity.
- The final O0 producer contains inferred-interface records for all 94 shared modules. The reviewer independently verified every signature-record digest and found no `Num`, `Fractional`, or `IsString` constraints. These are GHC interface records, not a completed comparison with native inferred interfaces.

This is evidence for exported-corpus type stabilization, not a general acceptance proof. The agreed scope intentionally retains native MLF inference rather than adding a new Num/IsString inference subsystem. `--check-shared` is grammar/name-resolution validation only. Qualification of a maintained source set requires the closed-manifest dual build and exported-interface audit, and this limitation must remain explicit. An arbitrary newly marked module may therefore typecheck on only one host or expose a different inferred interface; it is not automatically qualified. `x :: Double; x = 1`, numeric patterns at non-Int types, overloaded string instances, and negative floating/signed-zero syntax are useful boundary probes. Any both-accepted program with different observable behavior remains a blocker.

## Positive design checks

- The facade re-exports actual GHC `Functor(..)`, `Applicative(..)`, and `Monad(..)` identities. Native builtin class declarations now include the same method sets and the `Functor => Applicative => Monad` superclass chain.
- Ordinary `do` lowers bind statements to canonical `>>=` and expression statements to canonical `>>`, rather than a lexical `bind`/`return` hook. A single final expression does not require a fabricated bind.
- `if` uses canonical Bool semantics, independently of a lexical `ifThenElse` value. Refutable shared do patterns and shared guards are explicitly excluded rather than routed through the legacy failure/otherwise machinery.
- `Surface.bindValues` uses dependency SCCs for recursive Haskell let scope. Only actually cyclic SCCs require closed signatures; acyclic declarations retain inference. This restriction belongs to the shared source subset, not the guest inferencer. Infix marker normalization is necessary to keep this sound.
- Omitted export lists return local entities. Explicit re-exports, qualified imports/aliases, selection and hiding are based on nominal entities and parent membership. The method namespace and source-constructor corrections above are essential to that design.
- Shared list/tuple/unit sugar is not silently rebound to unrelated custom algebraic constructors. Explicit `List`, `Nil`, `Cons`, `Pair`, and `Unit` remain ordinary library entities.
- Layout validation rejects unsupported inline/implicit-boundary cases rather than quietly applying the legacy layout heuristics. No claim of complete Haskell layout support is needed.
- Guest inference, checked-target translation and native compilation remain separate code paths; this review does not recommend replacing them with GHC inference or synthesizing superclass instances to preserve old mixed-source examples.

## Final evidence and remaining qualification

### Completed bounded evidence

The committed evidence is [tools/shared/evidence/frontend-O0](../../tools/shared/evidence/frontend-O0/README.md). The reviewer independently checked each shard receipt against the committed summary, the exact stdout bytes and empty stderr, the current executable hash, all 127 recorded current input hashes, and the 125 shared/host/runtime input hashes in the producer receipt. All checks matched. The 127 inputs comprise the 94 shared files, 31 host/runtime files, `shared-sources.json`, and the retained `bootstrap/tests/shared-frontend.emlf` fixture.

The common executable SHA-256 is `50728040aba323149be1f592847f73e9d7b7febdf90fdfe05465319d801fb211`.

- `final-o0-frontend`: PASS, 3.75 seconds. Parser and name-resolution regressions, including signed/unsigned local infix recursion and legacy-Prelude exclusion.
- `final-o0-native-first`: PASS, 47.56 seconds. Full standard hierarchy inference, both Applicative minimum-definition branches, overridden do sequencing, and exact `fmap bottom` demand.
- `final-o0-native-second`: PASS, 47.44 seconds. Exact `<*>`, `<*`, `liftA2`, and `return` panic-demand checks, plus partially applied default `>>` remaining in weak head normal form.
- `final-o0-grammar94`: PASS, 24.65 seconds. Grammar-only validation of all 94 canonical shared files.

These shards run actual native frontend/MLF-inference/interpreter algorithms hosted by the direct-source GHC O0 build. They are not native LLVM executions or an O2 campaign. Each shard has a completed bounded-resource receipt. Their source and executable remained unchanged before and after execution.

The O0 producer receipt records successful compilation of all 94 shared modules and successful links for all 12 executables; the reviewer also checked the current output hashes. Its overall `complete` value remains false because the combined 94-file grammar/name-resolution command did not finish within the aggregate 120-second build watchdog. The independent grammar-only pass must not be substituted for that unfinished name-resolution gate.

### Subsequent package-configuration repair

The actual H0 manager exposed a missing selected direct `mlf-frontend` dependency for the `emlf` executable. The root package manifest now selects that dependency, and `tools/shared/build.py` now validates direct import visibility rather than granting visibility through transitive dependencies. The bootstrap script's generated manifest received the corresponding direct dependency. These are later integration changes, not inputs covered by the original O0 producer configuration receipt.

The reviewer rechecked the source hashes after this repair: all 94 shared and 31 host/runtime producer inputs, and all 127 inputs in each of the four focused shard receipts, still match current bytes. The original producer receipt itself is unchanged, but its recorded root `mlf-package.json` and build-driver hashes no longer match the current files. The focused implementation results therefore remain applicable to the unchanged source and executable; they do not qualify the revised package configuration or driver. The implementation reports 40 passing static tests. The actual metadata-lock retry was still in progress at this review checkpoint, and final package/bootstrap qualification remains pending even if that metadata-only operation succeeds.

### Resolved final-source issues

The initial full grammar attempt failed on adjacent `sharedPunctuation` and `sharedValueOperators` signatures before either definition. The signature has been moved immediately beside its definition. Closed signatures for the precedence-parser SCC, marker-aware lexical dependencies, qualified-name/operator dot adjacency, and ordinary treatment of the legacy-only words `rec`, `exists`, `true`, `false`, `bot` are included in the settled source covered by the final hash-bound shards. The previous “rerun pending” caveat for those source edits is closed.

### Bridge evidence and limit

The source-complete frozen bridge is in [bootstrap/shared-haskell-v1-bridge](../../bootstrap/shared-haskell-v1-bridge/README.md). After the generated-manifest repair, the reviewer independently reverified the current archive SHA-256 `46042269373e9965eb742555d16a5a763f45edb6baf4b75f634734bfaa1f74ae`, patch SHA-256 `60f7ba3434e638982a11497c31b711725ab6cbd2e3f8338edcf34a7a0d170ca9`, and all 171 declared raw input-file hashes inside the archive. The extra archive member is the checksum index `bridge-inputs.sha256`, whose entries also exactly match the manifest. The recorded source checkpoint is now `41c74fbbee9ae06151c24476d7f9280222d678ff`; the base remains `2f8584423fa3055ca96d1479734357f742c9b3df`. Comparing the old and current archive manifests shows that only `scripts/bootstrap-async.sh` changed among the 171 raw inputs; the current archived script includes the direct `mlf-frontend` dependency.

The implementation reported an isolated patch-reproduction check for the earlier frozen checkpoint. This report independently checks the current refrozen bytes, not a fresh patch application or execution of the revised bootstrap script. The native bridge parser audit passed on the unchanged compiler source; after earlier syntax and closed-signature defects were corrected, the separate native `--type` attempt reached the 1 GiB address-space ceiling. That is incomplete native typechecking, not a passing bridge build or demonstrated native bootstrap.

### Still required

1. Finish the combined 94-source name-resolution gate and full native typechecking of the final maintained source.
2. Finish native bootstrap/manager compatibility, guest type and checked-target suites, native code generation, async/package/runtime campaigns, and the native fixed point.
3. Run the O2 demand campaign with the same exact panic oracles and source-bound receipts. Preserve both partial and full application tests, explicit-method overrides and recursive method/dictionary cases.
4. Complete dual-host exported-interface comparison for the closed manifest. Retain the explicit distinction between grammar/name validation, GHC inferred-interface auditing and actual native inference.
5. Keep broader namespace/operator regressions: re-exported canonical operators, qualified and hidden constructor names in all source positions, custom same-spelled classes, missing superclass instances, and method import/export membership. Do not describe the existing focused sample as exhaustive Haskell conformance.

## Evidence locations

Committed final evidence: `tools/shared/evidence/frontend-O0/{README.md,summary.json}` and the four adjacent shard directories, each containing the exact command, receipt, stdout and stderr. The producer receipt is `.mlf-build/shared-ghc-O0/receipt.json`; the focused summary records its digest and explicitly incomplete overall status.

Literal migration evidence: `tools/shared-migration/literal-signatures.json` and `tools/shared-migration/evidence/literal-annotation-adjustment.json`. Final GHC inferred-signature records are also present in the producer receipt.

Temporary independent GHC probes remain in `/tmp/mlf-independent-frontend-review/`: `OperatorFixity.hs`, `TopShadow.hs`, `HiddenMethod.hs`, `QualifiedMethod.hs`, `DefaultDemand.hs`, `typecheck.log`, and `ghc-base-interface.txt`. The earlier corpus type dump was inspected at `/tmp/mlf-standard-inferred-types/types-after.log`. These temporary paths are historical review evidence, not required normal-build dependencies; the committed hash-bound final shards supersede the earlier weak-provenance execution logs.
