# eMLF → xMLF in Haskell

A standalone compiler for the core eMLF language in Boris Yakobowski's
*Graphical types and constraints — second-order polymorphism and inference*
(2008), using the supplied [thesis text](papers/these-finale-english.txt).
It performs graph-based MLF inference and emits explicit, independently
type-checked xMLF.

## Build and run

Requires GHC and Cabal. Dependencies are `base`, `containers`, `mtl`, and
`parsec`; no external solver is needed. Tested with GHC 9.14.1.

```sh
cabal build all --offline -j1
cabal test --offline -j1 --test-show-details=direct
cabal run emlf -- examples/self-application.emlf
cabal run emlf -- --type examples/choose-id.emlf
```

Omit `--offline` if the dependencies are not already installed. The executable
also accepts standard input and `--expr '...source...'`. `--type` prints only
the inferred type. A failed parse, inference, elaboration, or verification
exits unsuccessfully and identifies the failing phase.

The output is xMLF source, preceded by a comment containing its type. Compile
and check a file with the executable directly, keeping Cabal's build messages
out of the generated file:

```sh
EMLF_BIN="$(cabal list-bin exe:emlf)"
"$EMLF_BIN" examples/choose-id.emlf > choose-id.xmlf
"$EMLF_BIN" --check choose-id.xmlf
```

`--check` parses the xMLF and runs the target checker; it does not call the
source inference engine. All identifiers in this output carry explicit IDs,
for example `x_12` and `a27`. These distinguish source shadowing and graph
sharing; the numbers have no type-theoretic significance.

## Source language

```text
e ::= x | integer | true | false
    | \x -> e | \(x : annotation) -> e
    | e e | let x = e in e | (e : annotation)

annotation ::= type | exists a ... . type

type ::= a | bot | type -> type | Constructor type ...
       | forall a ... . type
       | forall (a >= type) ... . type
       | forall (a = type) ... . type
```

Use parentheses to group expressions and types. `\x y -> e`, `λx. e`,
`forall (a > type). type`, and `let x : annotation = e in e` are also accepted.
`forall a.` abbreviates `forall (a >= bot).`. Type constructor names start
with an uppercase letter. Annotations must be closed except for their explicit
existentials, whose values are inferred. Comments use `--` or nested `{- -}`.

The source includes lambda, application, nonrecursive let, expression and
parameter annotations, and integer/Boolean literals. Constructor types are
uninterpreted; there are no datatype declarations, pattern matching, recursive
bindings, arithmetic primitives, or runtime/code-generation backend in this
core compiler. xMLF type computations are compilation evidence; they erase at
runtime.

For example, this retains the MLF instance bound, rather than specializing the
identity function to a monotype:

```haskell
let choose = (\x y -> x) : forall a. a -> a -> a in
let id = \x -> x in
choose id
```

Its inferred type, up to names of bound variables, is
`forall (b >= forall a. a -> a). b -> b`.
The annotation gives `choose` the type used in the thesis: the unannotated
constant function `\x y -> x` has a more general type.

Annotated self-application is accepted:

```haskell
\(f : forall a. a -> a) -> f f
```

Its type is `forall (b >= forall a. a -> a). (forall a. a -> a) -> b`.
Unannotated `\f -> f f` is rejected. Existential annotations are supported, for
example [`examples/partial-annotation.emlf`](examples/partial-annotation.emlf).

## Implementation and thesis correspondence

| Stage | Implementation | Thesis |
| --- | --- | --- |
| Parse and resolve source binders | `MLF.Parser`, `MLF.Constraint` | §9.4 |
| Embed annotation types and desugar annotations to coercions | `MLF.Constraint` | §8.2.2, §12.3.2 |
| First-order unification, then `Rebind` and permission checks | `MLF.Graph.unify` | Figures 7.3.1–7.3.2 |
| Expand schemes with frontier equations and binding/flag reset | `MLF.Graph.expand` | §10.1 |
| Solve equalities, then instance edges in dependency order | `MLF.Constraint.solve` | Figure 12.1.1 |
| Normalize the presolution for translation | `MLF.Graph.normalize` | §15.2.6–15.2.8 |
| Translate types in leftmost-lowermost order | `MLF.Elaborate` | §15.2.7, Figure 15.3.2 |
| Generate computations and elaborate terms | `MLF.Elaborate` | §15.3.2–15.3.10, §15.4.1 |
| Independently check xMLF | `MLF.X.Check` | Figures 14.2.6 and 14.2.8 |

As recommended by §15.3.10, elaboration happens **after** inference. Each
instance edge is re-expanded from the final presolution. The unifier's map
from copied nodes to their destinations supplies identity-based evidence.
The elaborator introduces target quantifiers in dependency order and consumes
source bounds at their mapped destinations. This groups graft/raise/merge/
weakening operations as discussed in §15.4.1, and explicitly witnesses
quantifier reordering; it does not implement a literal one-operation-at-a-time
trace of Figure 15.3.4.

The implementation uses the modular normalization of §15.2.8: all inert nodes
are weakened, rigid bounds are inlined, and existential nodes do not introduce
spurious type abstractions. The let constraint uses §15.2.6's extra enclosing
scope, so the type abstractions needed by the bound expression remain in scope.
Syntactic source alias bounds are normalized during graph embedding (§15.6.2).

The target checker uses only alpha-equivalence. It checks all eight type
computations, including the `Inst-Hyp` bound premise; it intentionally does not
use the unchecked type-computation function in Figure 14.2.7. It allows lexical
quantification within types and prevents variable capture by computation and
term binders. It provides no rule to instantiate under an arrow or constructor.

Every successful compilation checks both:

1. The xMLF term has the type extracted from the normalized presolution.
2. Erasing its types and computations gives exactly the resolved source term
   after annotation desugaring (§15.3.14).

The Haskell API is `MLF.Compiler.compile :: FilePath -> String -> Either
CompileError Compilation`, or `compileExpr` for a source AST. A `Compilation`
contains `inferredType`, `compiledTerm`, and the normalized `presolution`.
The checker and xMLF parser can be used independently of the compiler.

This is a reference implementation using persistent maps, explicit graph
validation, and simple least-common-ancestor queries. It does not implement the
linear-time data structures discussed in §7.5, and rigid-bound inlining can
duplicate types, as discussed in §15.4.

## Validation

`cabal test` exercises the eight computation rules and their failure cases,
capture-avoiding substitution, alpha-equivalence, rigid/skolem checks, graph
domination, expansion reset, let scopes, `choose id`, `g g`, arbitrary-rank
annotations, existentials, and the source examples. Generated xMLF is printed,
parsed again, and checked in the targeted and annotation tests.

An independent Algorithm W implementation in `test/Oracle.hs` checks the
unannotated-language typability correspondence of Theorem 12.3.1. The corpus
contains all 1,712 closed terms through AST size 6 plus 5,000 deterministic
larger terms, including both accepted and rejected programs. Another corpus
contains 126 typed annotation programs over polymorphic and nested types.
These tests do not substitute the inference engine for its own oracle, and
elaboration/verification failures are never treated as legitimate rejections.

The separate `figure12-tests` suite tests examples from the **MLF column** of Figure 12 in
[A Quick Look at Impredicativity](https://simon.peytonjones.org/assets/pdfs/impredicativity.pdf).
It covers all 34 rows and 43 expressions, using the paper's library signatures
and checking printed/reparsed xMLF for every accepted expression. **All 43
regression cases pass; 42/43 outcomes agree with the paper.** A8 (`choose id auto'`)
expects rejection for the explicit signature
`forall b. (forall a. a -> a) -> b -> b`, matching the authors' `camlf` reference
prototype. Its test requires an inference failure with the protected-variable
raising diagnostic. The paper's acceptance claim is stored separately and the
suite reports the discrepancy; a passing suite does not mean full table
agreement. See [the reference comparison](docs/figure12-a8-reference.txt).

```sh
cabal test figure12-tests --offline -j1 --test-show-details=direct
```

See [the test report](docs/figure12-results.txt) for the encoding, type checks,
and [a closed A8 reproduction](test/fixtures/figure12-a8.emlf). Passing this
table is a finite conformance check, not a proof of theoretical completeness.
