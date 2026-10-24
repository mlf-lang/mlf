# Haskell-first shared-source revision

23 October 2026. Approved design adjustment; implementation and qualification are in progress.

## Authority and scope

This revision supersedes the earlier recommendation to use `RebindableSyntax`,
monomorphic literal hooks, and a custom implementation `Monad`. It also
supersedes presenting preservation of two public source-language modes as a
migration objective. The user requested ordinary Haskell syntax and asked that
other syntax conflicts be resolved in the Haskell direction as well.

The maintained implementation remains one set of committed `.hs` files consumed
directly by both compilers. This is one coordinated syntax, builtin, source,
package and bootstrap change in draft PR22, not another feature rollout.
The compiler still implements full guest MLF inference: bounded/rigid and
impredicative quantification, inference graphs, evidence, checked xMLF and native
execution are not replaced by GHC inference. Shared source is a supported subset
of Haskell syntax; it is not a claim that every Haskell feature is implemented.

Older `.emlf` inputs and fixtures may retain narrowly documented compatibility
handling. That handling is not a promise that every old builtin API can be mixed
unchanged with the new hierarchy. Owned implementation and affected test code
are migrated explicitly. No automatic synthesis of new superclass instances is
added merely to preserve old `Monad` spellings. User-defined guest classes remain
ordinary classes and the inference engine is not narrowed to Haskell's type
system.

## Normal Haskell desugaring

Canonical modules omit `RebindableSyntax`. GHC uses `Haskell2010` with the explicit
allowlist `NoImplicitPrelude`, `NoMonomorphismRestriction`, `RankNTypes`,
`KindSignatures`, `FlexibleContexts`, `FlexibleInstances`, `MultiParamTypeClasses`
and `OverloadedStrings`. The marker remains a source/cache identity, not a code
transform. `NoImplicitPrelude` only controls imports; it does not redirect wired
syntax operations.

* `if` uses the real `Prelude.Bool`. The host adapter already uses this type.
  There is no custom `ifThenElse` syntax hook. Guarded equations/alternatives
  are currently excluded from the shared subset rather than inheriting the
  legacy textual `otherwise` shortcut. Guest MLF guard support is preserved.
* `do` uses real `Prelude.Monad`. The eight owned custom instances are migrated
  to real `Functor`, `Applicative` and `Monad` instances. Their existing return
  and bind computations define the new methods, preserving demand order. `bind`
  may remain an ordinary compatibility function. It does not control `do`.
* `pure` is the standard `Applicative` method, not an IO-only primitive alias.
  `ioReturn` and `stReturn` remain their explicit primitive operations.
* Numeric literals and negation use the standard GHC numeric desugaring.
  Native `Int` is represented by GHC `Integer`, and native `Double` by GHC
  `Double`; source annotations fix the actual intended types. Any ambiguous
  numeric or string binding found by the real corpus build receives a local,
  reviewed annotation. No global defaulting or overlapping-instance trick is
  used to conceal an inference difference.
* Overloaded strings use a genuine `Data.String.IsString` instance for the
  opaque host `String`. UTF-8/scalar validation and the native string model stay
  in that representation adapter. There is no source-local `fromString` hook.
* The standard builtin hierarchy must have faithful nominal identities,
  superclass entailments, method namespaces and supported defaults. Merely
  labeling the former two-method class `Monad` would not satisfy the contract.
  In particular, selective `Monad(..)` imports must not acquire different
  method sets on the two hosts. Known standard default methods may be supplied
  by native class elaboration; arbitrary implicit legacy-instance synthesis is
  a separate, unapproved compatibility feature.

Installed GHC 9.14.1 probes already establish that ordinary do with the standard
hierarchy and an `IsString` adapter typechecks without `RebindableSyntax`.
Deliberately incompatible lexical `fromInteger`, `fromRational` and `ifThenElse`
bindings do not redirect the syntax. The old custom `Monad` plus a lexical
`(>>=)` fails ordinary do with a missing `Prelude.Monad` instance, as expected.
These are bounded feasibility probes, not whole-compiler qualification.

## Complete syntax conflict audit

### Modules, imports and exports

Use ordinary Haskell module identities, qualified imports, aliases, hiding and
explicit export lists. Preserve separate value/type/constructor/class/method
namespaces, nominal identities and method membership. An omitted export list
exports locally declared entities, not every imported name. Imported entities
must be re-exported explicitly where required. Operators use parenthesized
operator names in import/export lists and qualified symbolic syntax where
supported. `MLF.Primitive` remains the only reserved native builtin module and
handwritten host facade, not a per-source generated import overlay.

### Let, recursion, signatures and layout

Shared `let` uses ordinary Haskell recursive scope, including within a group.
The one-time lexical audit found no own-RHS capture hazards in the original
ordinary local groups; it still checks every binding rather than assuming that
result. Actual cyclic SCCs keep closed signatures needed by native MLF, while
noncyclic bindings retain normal inference. This is a shared-source restriction,
not a restriction on the guest inferencer.

Use `::`, `forall a.`, kind annotations `(m :: * -> *)`, ordinary arrows and
class contexts. Do not reinterpret a Haskell-local signature as a legacy
sequential binder. Explicit braces/semicolons in maintained code are ordinary
Haskell, not a new layout dialect. Accepted indentation must produce Haskell
layout; unsupported layout forms are rejected rather than interpreted with the
legacy separator algorithm. Same-indentation continuations and explicit/implicit
brace boundaries have dedicated differential tests.

### Operators, if and guards

Supported infix operators have the same precedence and associativity as their
Haskell declarations. The bounded implementation resolves every operator by
ordinary lexical lookup, then permits fixed-table infix use only for the exact
canonical facade or builtin-method identity. Rebound/imported noncanonical
operators are usable in prefix form; their infix use is explicitly rejected
because a local binding without a declaration has Haskell's default `infixl 9`,
not the shadowed facade's fixity. Supporting arbitrary scoped fixities requires
scope-aware infix-chain reassociation and is not claimed by this cutover.
Tests cover local and qualified shadowing and standard method identities.
Native parsing must not silently bypass lexical lookup by replacing a shadowed
operator with a primitive ID. The facade may expose deliberately monomorphic operations:
for example its `(/)` can be integer quotient under `NoImplicitPrelude`; that is
an ordinary library definition, not altered Haskell syntax. Unsupported custom
fixity declarations or symbolic forms are diagnosed explicitly until implemented.
`if` and pattern fallback use ordinary Haskell forms and their demand behavior
remains a dual-host gate. Shared guarded equations/alternatives are explicitly
rejected for now: the legacy parser's textual `otherwise` sentinel and required
fallback do not implement Haskell's ordinary lexical Bool guards. Explicit
`if`/`case` in maintained source avoids giving an accepted guard a different
meaning. This is an incomplete supported subset, not complete Haskell syntax.

### Data, tuples, lists and unit

`List`, `Nil`, `Cons`, `Pair`, `Triple`, `Quad` and the explicit `Unit` constructor
are ordinary algebraic library types and remain readable shared source. Their
existence does not require Haskell list or tuple sugar to be rebound. Do not map
`[]`, `(:)`, `(,)` or `()` to unrelated custom constructors while calling that
Haskell-compatible syntax. The initial shared subset can explicitly exclude
unused sugar; admitting it later requires its actual Haskell identities and
semantics. The baseline inventory had no list brackets or `Char` use, so there
is no measured need for a speculative collection rewrite.

### Patterns and literals

Constructor patterns and pattern order remain ordinary source forms.
The existing reviewed string-pattern conversion is retained as explicit case
and equality code, because it makes the native decision-matrix demand order
visible and testable. No ViewPatterns, compiler plugin or source preprocessor is
needed. In particular, whole-matrix lowering must not force a later poisoned
field before an earlier string mismatch selects a fallback. Literal spelling
and embedded guest programs remain byte-identical during the mechanical pass.
Refutable do binds are made explicit case expressions where the shared subset
does not provide a matching `MonadFail` contract; it must not silently invoke a
different failure mechanism. Negative Double behavior includes signed zero.

### Classes and advanced types

Use normal class/instance syntax, including symbolic method names and explicit
superclass relations. GHC's standard hierarchy is an actual identity requirement,
not a structural approximation. Rank-n signatures are retained where both
implementations support them. `ImpredicativeTypes`, `ScopedTypeVariables`,
`ViewPatterns`, `GADTs`, type families and Template Haskell are outside the
currently tested allowlist, not intrinsically illegitimate language features or
a universal ban. A concrete need can justify adding an extension after native
parser, typing, elaboration and runtime evidence establishes the same supported
meaning in the maintained source. In particular, scoped variables or GHC
impredicative instantiation can be legitimate tools; enabling the latter does not
establish equivalence with full MLF inference. Do not enable an unknown feature
silently or use acceptance by one host as proof of semantic agreement.

The architectural restriction is different: normal builds must not use CPP to
select different implementation algorithms, a mandatory source translator,
header rewriting, generated overlays or other host-dependent source
substitution. Both hosts consume the same maintained implementation files.
Explicitly isolated bootstrap compatibility inputs remain part of the reviewed
bootstrap route. Unsupported source forms receive explicit diagnostics rather
than a misleading claim that all Haskell features have already been qualified.

## Qualification boundary: syntax versus inference

`shared-haskell-v1` does not claim identical principal type inference for every
arbitrary marked module. MLF still uses its own inferencer. Under the exact
canonical GHC flags `NoMonomorphismRestriction` and `OverloadedStrings`, an
unannotated exported `x = 1` or `s = "hello"` may infer a `Num`/`IsString`-qualified
scheme, while native MLF specializes its primitive literal to `Int`/`String`.
Other GHC flag/defaulting contexts can infer differently. The actual owned
closed manifest is qualified using both hosts and the audited explicit public
interfaces; syntax acceptance alone is not that proof.

`--check-shared` validates grammar and name resolution only. Normal qualification
also requires actual native/GHC builds, inferred exported-type audit, concrete
literal signatures and semantic tests. An extra GHC-accepted form such as an
integer literal used directly at `Double` is not automatically part of the
native-supported intersection. No new native numeric/string overloading
subsystem is claimed here, and no rejected external program is reported as
qualified simply because its marker or GHC typecheck passes.

## Bootstrap, packaging and runtime

The released 0.3.0 seed rejects `::`, so it cannot compile the final files.
The committed, source-complete legacy bridge is an isolated bootstrap input.
It must include the revised frontend/builtin support, be buildable from the
released seed using its own legacy implementation syntax, and then compile the
same final shared files used by GHC. Its archive, reviewable patch, source hashes
and tool receipts are committed. No mutable old branch or reverse-translator is
a normal build dependency. Internal bootstrap compatibility is not a public
promise to preserve every old syntax/API combination indefinitely.

Native manifests, Cabal and the direct GHC builder describe one closed module
inventory. Source and cache receipts include syntax, frontend semantics, builtin
interface identity and actual resolved source paths. A source-syntax profile is
not a runtime ABI profile. Package locks must be regenerated with qualified new
tools and checked with `--locked` after the final source edits.

GHC builds retain `-fpedantic-bottoms -fno-state-hack` at O0 and O2. Executable
links additionally use `-rtsopts=ignoreAll`, preserving literal user argv such as
`+RTS --info -RTS` rather than allowing GHC RTS parsing to consume it. Primitive
IDs 0–94 remain stable. Array nominal identities, cold actions, UTF-8 boundaries,
lazy typed payloads, cancellation ownership and forcing/error order remain
runtime contracts. Native `setEnv` argument validation is explicitly sequenced
name-before-content to remove pre-existing C argument-order dependence; that
change is disclosed and tested, not described as an old portable guarantee.

## Acceptance and evidence status

The earlier RebindableSyntax probe receipts remain historical evidence only.
They do not qualify the revised interface. The initial raw 91-module GHC
no-code campaign reached all 95 units including four adapters and found one
imported-type re-export defect, now fixed; it predates the ordinary-class source
revision. The later ordinary-hierarchy pass typechecked all 94 current shared
modules. Bounded runtime adapters now pass 84 command expectations, 87 contracts
and 590 numeric-bit comparisons at both O0 and O2, after seven independently
reviewed defects were corrected.
A separate inferred-signature audit then found 41 generalized literal bindings
(39 `IsString`, two `Num`) which plain no-code success had not ruled out.
Forty-one ordinary signatures were added in 19 files, retaining unrelated
polymorphism and all non-signature source bytes. The repeated 94-module audit
passed with zero remaining `Num`/`Fractional`/`IsString` constraints in exported
shared signatures. This corrects the earlier provisional statement that no
literal annotations were needed. A bounded actual O0 build then compiled all 94
shared modules and linked all 12 executables; its shared 120-second budget
expired during combined grammar/name resolution, so the overall receipt remains
incomplete. Source and output hashes were rechecked after the cap.

The frozen 171-file legacy bridge is now reproducible from the pinned baseline
plus its reviewable patch. An existing native producer caught legacy annotation
and recursive-signature defects, corrected before freezing; its subsequent
type probe reached the enforced 1 GiB cap, not a passing type result.
No whole native compiler build, optimized
raw-source compiler qualification, final full guest/async/TupleList campaign or
native fixed point is claimed here.

Required final gates are unchanged in scope: exact raw source on both hosts;
O0/O2 compiler/runtime laws; full guest type inference and checked-target tests;
async and typed completions; TupleList; package/bootstrap bridge; source-bound
receipts; and native fixed-point qualification. Independent review must assess
the revised interface, not the superseded custom facade. Unrun, failed and
platform-limited gates remain explicit.

## Recovery qualification update

At source checkpoint `98d6df3`, the complete GHC O0 producer and its 94-module
name-resolution gate passed, followed by all 12 authenticated direct runtime
commands and 90 TupleList checks. This supersedes the earlier O0 timeout status
above, not the pending O2/native/full-guest qualification requirements. See
[the current recovery checkpoint](README.md#current-recovery-checkpoint) for
exact scope, timings and source-bound receipts. The seed/manager identity and
timed-caller fixes are documented in [Bootstrap and CI](Bootstrap-and-CI.md).
