# Public-API fixture build feasibility: static review

**Not compiled or run. No toolchain was installed, no compiler/build command was invoked, and no execution restriction was cleared.** All 24 Haskell cases remain untested. This note is a feasibility boundary, not build admission or a successful build receipt.

Repository: `mlf-lang/mlf`. Source commit: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. Fixture reviewed: `OpenFragmentGuardPublicApi.hs`, 19,750 bytes, SHA256 `d33cc56c63e97da961b25877e58b8d5b803ce4398e457a4d9840c2e33a99fc93`. References to implementation files below are repository-relative at that commit. The earlier nine-file comparison with main does not establish identity of this newly inspected, larger closure at another revision.

## Conclusion

The fixture is a small **test input**, but not a small standalone Haskell dependency set. It can plausibly be built without building the complete compiler executable or every module of `mlf-shared`, by separately admitting a source-level build of its actual module closure. That has not been attempted and has no measured resource bound. It is still compilation of substantial real compiler-library source, not a base-only semantics experiment or an exception to the existing restrictions.

The current investigation reports no installed `ghc`, `runghc`, `ghci`, `cabal`, or `stack`; this review did not repeat installation discovery. The unresolved earlier execution receipt is a separate blocker. Installing a toolchain, obtaining objects, or selecting a new output directory would not itself authorize running the fixture.

## Direct imports and real transitive scope

Fixture lines 14–24 directly import eleven project modules:

- Types and maps: `Bootstrap.Types`, `Bootstrap.Map`.
- Real checker/receipt/type APIs: `Bootstrap.X.Check`, `Bootstrap.X.Checked`, `Bootstrap.X.Syntax`, `Bootstrap.X.Type`.
- Fragment and actual encoding APIs: `Bootstrap.OpenFragment`, `Bootstrap.ArtifactStructure`, `Bootstrap.Bitstream`.
- GHC representations and byte-array primitives: `MLF.Host.Base`, `MLF.Primitive`.

Its exception handling, logging, hexadecimal rendering, and exit handling also use ordinary host libraries. There is no opaque receipt or Fragment constructor bypass.

Independent traversal of imports from these eleven roots found **47 project modules, totaling 1,318,860 UTF-8 source bytes**, excluding this Main, package sources, and C/header dependencies:

| Source directory | Modules |
| --- | ---: |
| `libraries/mlf-foundation` | 13 |
| `libraries/mlf-frontend` | 10 |
| `libraries/mlf-xmlf` | 6 |
| `libraries/mlf-crates` | 6 |
| `libraries/mlf-language-core` | 4 |
| `libraries/mlf-inference` | 4 |
| `host/ghc` | 4 |

The independent result matches the separately collected closure: all 47 module paths, source lengths, and Git blob hashes were checked against the fixed source tree. `IMPORT-INVENTORY.json` records the collected source/import inventory. Resolution used actual Cabal source roots, not suffix matching against archived fixtures. Prelude is an external module, not `Bootstrap.Prelude`.

This is a static import-header closure, not a GHC-generated dependency proof, optimized link graph, or runtime call graph. Both CPP branches in `MLF.Host.IO` are conservatively included. Source size is not a compilation-time, memory, or runtime estimate.

The widening is concrete: `Bootstrap.OpenFragment` lines 24–29 import Pretty, Separate, EvidenceBoundary, Bitstream, ArtifactStructure, and ArtifactStorage. `Bootstrap.Separate` lines 6–30 import Lexer, Module, Classes, Parser, Desugar, Surface, SourceEquality, and the xMLF parser/checker/pretty-printer. Classes brings ClassDemand, Dependency, ST, and Kinding; Module brings the surface-language Prelude and resolver. EvidenceBoundary brings Evidence. Removing the fixture's snapshot observations would **not** remove these imports from unchanged OpenFragment.

The inspected closure does not contain `Bootstrap.Compiler`, `Bootstrap.CompilerCore`, Graph/Solver, LLVM modules, native drivers, or `Bootstrap.InferenceUnit`. Consequently a whole-compiler executable build is not a logical dependency of this Main. Conversely, the nine previously restored pinned files alone are insufficient to compile it. Splitting OpenFragment, stubbing dependencies, or replacing host primitives would be a different source experiment, not this unchanged public-API regression.

## Build boundaries that must not be skipped

1. **The existing Cabal component is broad.** `mlf-shared.cabal` lines 10–18 describe one library exposing compiler, LLVM, package, and test modules. An ordinary fresh build of that component is not a promise to compile only the modules this fixture calls. The fixture is not a declared executable/test component. `cabal.project` also selects optimization 2 and one job; these settings are not a measured small-build bound.

2. **Two direct imports are package-hidden.** `MLF.Primitive` and `MLF.Host.Base` are `other-modules`, not exposed modules (`mlf-shared.cabal:13`). “Public API” here means exported source-module APIs and preserved opaque constructors, not that an unrelated client can import every helper from an installed package. A naive external client build using only the installed package can fail on hidden modules. A separately specified source-closure component could avoid that package-visibility problem without changing the fixture, but must keep project types/instances and host adapters from one coherent build, not mix duplicate package/home-module identities.

3. **The toolchain is constrained.** Cabal line 14 requires `base >= 4.22 && < 4.23`, `array >= 0.5.8 && < 0.6`, `bytestring >= 0.12.2 && < 0.13`, `text >= 2.1.3 && < 2.2`, `containers >= 0.8 && < 0.9`, and `directory >= 1.3.10 && < 1.4`. This is the full package's declared set, not a proof that every dependency is needed by this subset. The source closure visibly uses base, array, bytestring, text, and containers, including `Data.Text.Internal`, `Data.Array.Base`, and `GHC.Num.Integer`. An arbitrary older system GHC is not an established compatible setup. Cabal line 16 also specifies `-fpedantic-bottoms -fno-state-hack`, which matters to a demand-sensitive study.

4. **It is not Haskell-only at link time.** `MLF.Primitive:41–47` imports Host.Base, Host.IO, and Host.Async. Host.Base line 239 declares `mlf_ghc_format`; Host.IO lines 32–36, 285–286, and 325 declare host/shutdown, runtime argv, byte-file, and byte-array-digest FFI. Cabal lines 17–18 provide `host/ghc/cbits/host.c`, `runtime/mlf_process_supervisor.c`, and runtime includes. The C files include further platform/runtime headers. A faithful future link must resolve the required foreign symbols and record its actual C inputs; assuming unused source functions remove every foreign dependency is not a link proof. Linking supervisor support does **not** mean the fixture runs process/lock tests. It nevertheless prevents treating a plain unconfigured interpreter invocation as a complete build plan.

## Fixture-specific static checks

No definite syntax or API-signature mismatch was found in the inspected fixture. This is not a typecheck. In particular:

- The fixture correctly distinguishes Prelude `Either` for `try` from the project's `T.Either` for checker results.
- `MLF.Host.Base:53` makes `B.Int` an Int64; its IO/Bool and ordinary list/tuple identities match the host operations used here. `B.String` is distinct and is explicitly unpacked where required. Overloaded literals supply project strings.
- `Wire.encode` is `Limits -> Int -> [Value] -> IO (Either String ByteArray)` (`Bootstrap.Bitstream:527`). `Primitive.readByteArray` and `lengthByteArray` have the IO signatures used at fixture lines 105–114 (`MLF.Primitive:189–196`). The encoder is real IO, not a predefined byte surrogate.
- Open's context/accessors, check, normalize, audit, and encodeBody are exported. Checked exports its check/accessors/inventory without its constructor. The public raw `XEnv` has two fields; fixture lines 258–260 supply exactly two.
- The final rendered PASS line is fully forced inside `runCase`'s exception handler, after the case observations. No additional fixture change is proposed by this review.

## What a later result could establish

A separately admitted, bounded build of this genuine closure could run the unchanged 24 cases across baseline/delete-only/spine-only and collect actual compiler/link identities, outputs, exit status, and cleanup evidence. It would still not prove earlier append-spine forcing, heap equivalence, broad production correctness, or a speedup. The fixture README's deferred observations remain deferred.

A base-only Haskell program could instead test selected language semantics without importing the project. Even if genuinely executed, it would not test this fixture, the custom representations, the real checker/receipt APIs, the FFI encoder, or the candidate against production source. It must not be counted as any of these 24 public-API cases passing. No such substitute or runnable wrapper was created here.
