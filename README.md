# eMLF → xMLF in Haskell

A standalone compiler for the core eMLF language in Boris Yakobowski's
*Graphical types and constraints — second-order polymorphism and inference*
(2008), using the supplied [thesis text](papers/these-finale-english.txt).
It performs graph-based MLF inference and emits explicit, independently
type-checked xMLF.
An interpreter runs checked `IO` programs with console input and output.

## Build and run

Requires GHC and Cabal. Dependencies are `base`, `containers`, `mtl`, and
`parsec`; no external solver is needed. Tested with GHC 9.14.1.

```sh
cabal build all --offline -j1
cabal test --offline -j1 --test-show-details=direct
cabal run emlf -- examples/self-application.emlf
cabal run emlf -- --type examples/choose-id.emlf
cabal run emlf -- --type examples/monad-maybe.emlf
cabal run emlf -- --type examples/monad-state-do.emlf
cabal run emlf -- --run examples/io-hello.emlf
cabal run emlf -- --run examples/snake.emlf
```

Omit `--offline` if the dependencies are not already installed. The executable
also accepts standard input and `--expr '...source...'`. `--type` prints only
the inferred source type, including class constraints. A failed parse,
inference, dictionary resolution, elaboration, or verification
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
program ::= ((data-declaration | class-declaration | instance-declaration) ";")* e

e ::= x | integer | string | true | false | ()
    | \x -> e | \(x : annotation) -> e
    | e e | let x = e in e | (e : annotation)
    | Constructor | case e of { pattern -> e; ... }
    | do { statement; ...; e }

statement ::= pattern <- e | e | let x [: annotation] = e

data-declaration ::= data TypeName parameter ... = Constructor field ... | ...
parameter ::= a | (a : kind)
kind ::= * | kind -> kind
pattern ::= Constructor x-or-wildcard ... | x | _

class-declaration ::= class [context =>] ClassName parameter ... where { method : type; ... }
instance-declaration ::= instance [forall parameter ... .] [context =>]
                         ClassName type-atom ... where { method = e; ... }
context ::= ClassName type-atom ... | (ClassName type-atom ..., ...)
type-atom ::= a | Constructor | (type)

annotation ::= type | exists a ... . type

type ::= a | bot | type -> type | type type
       | forall a ... . type
       | forall (a : kind) ... . type
       | forall (a >= type) ... . type
       | forall (a = type) ... . type
       | context => type
```

Use parentheses to group expressions and types. `\x y -> e`, `λx. e`,
`forall (a > type). type`, and `let x : annotation = e in e` are also accepted.
`forall a.` abbreviates `forall (a >= bot).`. Type constructor names start
with an uppercase letter. Annotations must be closed except for their explicit
existentials, whose values are inferred. Comments use `--` or nested `{- -}`.

The source includes lambda, application, nonrecursive let, expression and
parameter annotations, integer/Boolean/string literals, algebraic data types, and
type classes with multiple and higher-kinded parameters, and `do` blocks.
Abstract constructor types are still allowed in annotations for library
signatures. General recursive source bindings and a native code-generation
backend are not implemented. Instance methods can
be recursive through their dictionaries. The interpreter evaluates erased
xMLF with lazy bindings and executes explicit IO actions. xMLF type computations are
compilation evidence; erasure removes them.

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

## Algebraic data types

Put declarations before the expression and terminate each with a semicolon:

```haskell
data Maybe a = Nothing | Just a;

let fromMaybe = \default value ->
  case value of {
    Nothing -> default;
    Just x -> x
  }
in fromMaybe 0 (Just 42)
```

This program has type `Int`. Constructors are ordinary curried values, so
`Just` has type `forall a. a -> Maybe a` and can be passed to functions,
partially applied, or let-bound. Datatype and constructor names start with an
uppercase letter; type parameters and term variables start with a lowercase
letter. Declared names are unique throughout the program. `Int`, `Bool`,
`String`, `Unit`, and `IO` are built-in types. `True`, `False`, and `Unit`
retain their primitive meanings. `Unit` and its constructor are supplied by
the language; omit a separate `data Unit = Unit` declaration.

Declarations may be recursive or mutually recursive:

```haskell
data List a = Nil | Cons a (List a);
data Tree a = Leaf a | Branch (Tree a) (Tree a);
```

Fields contain type parameters, primitive types, declared types, functions,
and explicitly polymorphic types. Parenthesize a field containing type
application, an arrow, or a quantifier, as in `Cons a (List a)`, `Fn (a -> b)`,
or `Poly (forall a. a -> a)`. Parameters default to kind `*`; write an explicit
kind for a higher-kinded parameter:

```haskell
data Wrap (f : * -> *) a = Wrap (f a);
```

Declarations require at least one constructor. GADTs, existential fields,
records, and deriving are not implemented.

Cases use explicit braces and semicolons. A constructor pattern must bind
exactly its fields; use `_` to ignore a field. Cases must cover every constructor
or end with a wildcard or variable alternative. Patterns from different data
types, duplicate constructors or variables, and alternatives after a default
are rejected. A variable alternative binds the whole scrutinee. Constructor
patterns have one level; use nested `case` expressions to inspect deeper values.

MLF can instantiate datatype parameters with polymorphic types:

```haskell
data Box a = Box a;
let boxed = Box (\x -> x) : Box (forall a. a -> a) in
case boxed of {
  Box f -> let id = f : forall a. a -> a in
           let number = id 42 in id true
}
```

Pattern fields are not implicitly generalized. An explicit annotation can
expose a field's polymorphic type for independent uses, as above.
See [`maybe.emlf`](examples/maybe.emlf),
[`recursive-data.emlf`](examples/recursive-data.emlf), and
[`polymorphic-data.emlf`](examples/polymorphic-data.emlf).

Algebraic data is an extension to the thesis's core xMLF calculus. Generated
output carries the declarations, explicit type arguments for constructor
primitives (`construct Just(Int)`), and the result type of each case. The
independent checker validates declarations, field substitution, pattern scope,
coverage, and all branch result types. Erasure retains constructor tags and
case structure while removing declarations and type arguments.

## Standard prelude

Every compiler entry point imports a small standard prelude from
[`MLF.Prelude`](src/MLF/Prelude.hs). It supplies this class and its `IO` instance:

```haskell
class Monad (m : * -> *) where {
  return : forall a. a -> m a;
  bind : forall a b. m a -> (a -> m b) -> m b
};

instance Monad IO where {
  return = ioReturn;
  bind = ioBind
};
```

Programs can use `Monad` constraints, declare instances for their own types,
and sequence IO with `do` without repeating those declarations. For example:

```haskell
let twice : forall (m : * -> *) a. Monad m => m a -> m a =
  \action -> do { action; value <- action; return value }
in twice (putStrLn "Hello!")
```

`return` and `bind` are overloaded class methods. A standalone `return 42`
does not determine a monad: write `return 42 : IO Int` or `ioReturn 42` when
IO is intended. Dictionary resolution does not guess a type from the available
instances. `ioReturn`, `ioBind`, and the IO-specific `pure` alias remain
available as primitive operations.

Ordinary lexical bindings and locally declared class methods shadow imported
method names. A source declaration
named `Monad` replaces the imported class and its associated `IO` instance,
allowing the custom hierarchy in `monad-maybe.emlf`. Duplicate instances for
the imported class are rejected by the normal overlap check.

To disable the implicit prelude, put `--no-prelude` before other CLI options:

```sh
cabal run emlf -- --no-prelude --type --expr 'return 42'
```

The library exposes `compileWithPrelude`, `compileExprWithPrelude`, and
`compileProgramWithPrelude`, each taking `ImplicitPrelude` or
`NoImplicitPrelude` as its first argument. The existing `compile`,
`compileExpr`, and `compileProgram` functions enable the prelude by default.
Disabling it keeps the built-in types and primitives, including the earlier
IO-specific `return`/`bind` fallback aliases. Parsing and low-level constraint
generation alone do not import the prelude.

Unused prelude declarations are omitted using lexical name and class-reference
analysis. Programs that do not use the prelude retain their previous graphs
and xMLF. Imported
dictionaries undergo the same validation and independent target checks as
user-defined instances; they are not trusted, unchecked runtime dictionaries.

## Type classes

Classes have one or more parameters, each optionally with an explicit kind,
and named method signatures. Instances implement every method. The following
adds a `Maybe` instance to the prelude's `Monad` class:

```haskell
data Maybe a = Nothing | Just a;

instance Monad Maybe where {
  return = Just;
  bind = \value f -> case value of {
    Nothing -> Nothing;
    Just x -> f x
  }
};

let roundTrip : forall (m : * -> *) a. Monad m => m a -> m a =
  \value -> bind value (\x -> return x)
in roundTrip (Just 42)
```

The result is `Maybe Int`. [`monad-maybe.emlf`](examples/monad-maybe.emlf)
contains the full `Functor` → `Applicative` → `Monad` superclass hierarchy,
including a generic function that uses `pure` from an inherited constraint.
Method type variables other than the class parameters are implicitly
universally quantified at kind `*`; explicit `forall` is also accepted.

Use `C a b => ...` or `(C a b, D b) => ...` after a signature's quantifiers.
In constraints and instance heads, parenthesize each argument that contains
type application, as in `Convert (Box a) (Box b)`.
Constraints on ordinary let-bound functions are inferred from their method
uses; each use of the function gets its own dictionary arguments. Explicit
qualified signatures check their bodies polymorphically and make the given
dictionaries available to method calls. Dictionary resolution uses the
inferred types; it does not choose an instance to guess an unknown type.
An unconstrained bare method therefore needs a type or qualified signature.

Instances can have contexts and can use partially applied type constructors,
such as `instance Functor (Either e) where { ... }`. For example:

```haskell
instance Inspect a => Inspect (List a) where { ... };
```

See the complete recursive example in
[`contextual-instance.emlf`](examples/contextual-instance.emlf). Context
predicates must be structurally smaller than the instance head and use only
its variables, counting all arguments together. Single-parameter instance
heads start with a named type constructor; multiparameter heads also allow
variable arguments, including repeated variables such as `Convert a a`. Overlapping
instances, cyclic superclass hierarchies, missing or extra methods, ill-kinded
applications, and unresolved dictionaries are rejected. Declaration order
does not affect instance selection. Class methods share a global namespace;
ordinary local bindings may shadow them.

The implementation translates classes to nominal dictionary datatypes with
polymorphic method fields, and translates constraints to explicit dictionary
arguments. Superclasses are dictionary fields. Instance builders and selectors
use typed recursive xMLF bindings, whose declarations and bodies are checked
by the independent target checker. The erasure check compares against this
dictionary translation. These extensions are additional to the thesis's core
calculus; the compiler checks types, not the algebraic laws of a class.

For example, a class can relate an input type to an output type:

```haskell
class Convert a b where {
  convert : a -> b
};

instance Convert Int Bool where {
  convert = \value -> true
};

convert 42 : Bool
```

Instance selection checks the whole argument list. `Convert Int Bool` and
`Convert Int Int` are distinct instances. There are no functional dependencies
or defaulting: `convert 42` alone leaves its output type undetermined and is
rejected. Supply a result annotation or a qualified signature. Every class
parameter must appear in each method's type; ambiguous methods are rejected.
[`multiparameter.emlf`](examples/multiparameter.emlf) also demonstrates a
recursive instance with a multiparameter constraint.

Default methods, functional dependencies, associated types, bounded method
quantifiers, and constraints nested inside method signatures are not implemented.

## Do notation

Use explicit braces and semicolons, as with `case`:

```haskell
do {
  value <- action;
  let saved = value;
  anotherAction;
  return saved
}
```

`value <- action` translates to `bind action (\value -> ...)`. A statement
without `<-` also uses `bind` and discards its result. `_ <- action` discards
the result explicitly. Local `let` statements are nonrecursive, support
annotations, and generalize like ordinary lets. A block must end with an
expression; that expression is used directly, without inserting `return`.
Nested blocks and an optional trailing semicolon are accepted. Indentation
alone does not delimit a block.

`bind` is the function in lexical scope, normally the prelude's `Monad` method.
With `--no-prelude`, its built-in fallback is IO-specific. This lets
`do` work with the existing class machinery or an ordinary local `bind`
function. The translation generates fresh temporary names so discarded results
and pattern matching cannot capture user variables. Flat constructor patterns
are supported when exhaustive, for example `Pair x y <- action` for a
single-constructor `Pair` datatype. Refutable patterns require an explicit
`case`; there is no implicit `MonadFail` operation.

[`monad-state-do.emlf`](examples/monad-state-do.emlf) defines
`class Monad m => MonadState s (m : * -> *)` and a `State s` instance. Its
generic `replace` function uses `get`, `put`, and `do` under a single
`MonadState s m` constraint; `bind` and `return` are obtained from the `Monad`
superclass. The complete program compiles to `Pair Int Int`.

## IO and execution

`IO` is an opaque type of kind `* -> *`. An `IO a` value describes an action
that produces an `a`; creating or returning an action does not execute it.
The following complete program has type `IO Unit`:

```haskell
do {
  putStr "What is your name? ";
  name <- getLine;
  putStrLn (concatString "Hello, " name)
}
```

Run it with `cabal run emlf -- --run examples/io-hello.emlf`. Ordinary
compilation, `--type`, and `--check` perform no program IO. `--run` checks the
generated target before executing its final action; the action's result is
discarded. The entry point must have type `IO a` (possibly universally
quantified). Runtime IO errors, including EOF, are reported on standard error
and cause a nonzero exit. Console output is flushed before the next action.

| Operation | Type |
| --- | --- |
| `ioReturn` | `forall a. a -> IO a` |
| `ioBind` | `forall a b. IO a -> (a -> IO b) -> IO b` |
| `getLine` | `IO String` |
| `putStr` | `String -> IO Unit` |
| `putStrLn` | `String -> IO Unit` |
| `printInt` | `Int -> IO Unit` |
| `concatString` | `String -> String -> String` |
| `showInt` | `Int -> String` |
| `addInt`, `subInt` | `Int -> Int -> Int` |
| `eqInt`, `ltInt` | `Int -> Int -> Bool` |
| `eqString` | `String -> String -> Bool` |
| `ifThenElse` | `forall a. Bool -> a -> a -> a` |

Integer arithmetic uses arbitrary-precision signed integers. `ltInt` is strict
less-than, and string equality is case-sensitive. `ifThenElse condition yes no`
evaluates only the selected branch; it also works with functions, datatypes,
and IO actions. Selecting an IO action does not execute it until it is sequenced.

The standard prelude connects `return` and `bind` to these operations through
its `Monad IO` instance. `pure` is an IO-specific alias for `ioReturn` in this
minimal prelude. Local bindings and source class methods take precedence.

[`monad-io.emlf`](examples/monad-io.emlf) uses the imported class and instance
in a generic `twice` function with `do`. Running it prints the greeting twice.
Programs that define their own `Monad` class can provide their own IO instance
using `ioReturn` and `ioBind`.

Strings use double quotes, Unicode characters, and Haskell-style escapes such
as `\n`, `\t`, `\"`, and `\\`. `()` is an alias for the `Unit` constructor
in expressions and patterns, and for the `Unit` type in annotations.

Use a file or `--expr` when the program reads interactive input:

```sh
EMLF_BIN="$(cabal list-bin exe:emlf)"
"$EMLF_BIN" --run --expr 'do { printInt 42; putStrLn "done" }'
"$EMLF_BIN" examples/io-hello.emlf > hello.xmlf
"$EMLF_BIN" --run-xmlf hello.xmlf
```

`--run-xmlf` parses and independently checks emitted xMLF before running it.
Without a file, `--run` and `--run-xmlf` consume standard input as source, so
that input stream is unavailable for subsequent `getLine` actions.

The library entry point is `MLF.Runtime.runTerm`, with an `IOBackend` providing
`readLine` and `writeText`. Tests use a deterministic backend to observe action
order and failure behavior. The runtime keeps data fields, arguments, lets,
and recursive dictionaries lazy, while `ioBind` executes actions in order.
Reusing an action executes it again. There is no pure operation that extracts
a value from `IO`; file IO, concurrency, and language-level exception handling
are not implemented.

## Snake example

[`examples/snake.emlf`](examples/snake.emlf) is a complete turn-based terminal
Snake game written in the source language:

```sh
cabal run emlf -- --run examples/snake.emlf
```

This larger example takes longer to compile than the small examples. To play
again without recompiling, save the xMLF once and run that file:

```sh
EMLF_BIN="$(cabal list-bin exe:emlf)"
"$EMLF_BIN" examples/snake.emlf > snake.xmlf
"$EMLF_BIN" --run-xmlf snake.xmlf
```

Type `w`, `a`, `s`, or `d`, then press Enter to move up, left, down, or right.
Enter alone continues in the current direction; `q` quits. Reverse turns are
ignored, and invalid commands leave the game unchanged. The game prints a new
12-by-8 board after each move: `@` is the head, `o` the body, and `*` the food.
Each meal grows the snake and adds one point. Hitting a wall or the body ends
the game; filling the board wins. Moving into the old tail's square is legal
when the tail leaves on that turn. Food placement is deterministic, choosing
the first free square from the top left. Input uses `getLine`, so the game waits
for a command on every turn.

The example uses ADTs for positions, directions, commands, a nonempty snake,
game state, and outcomes. The standard prelude's `Monad IO` instance supplies
`bind` and `return` to the `do` blocks for drawing, input, and the game loop.
A small typed
fixed-point function, built with the recursive `Rec` datatype, supplies
recursion despite the source language's nonrecursive `let`. Movement and food
placement are pure functions; only the interface uses IO.

### Native Haskell baseline

[`examples/SnakeBaseline.hs`](examples/SnakeBaseline.hs) implements the same
game with Haskell ADTs, standard lists and `Maybe`, ordinary recursion, and
the standard `IO` monad with `do`. It uses `Integer` to match eMLF's unbounded
`Int`, and preserves the rules, deterministic food search, prompts, board
format, and flushing after each write. Only the `base` package is needed.

Compile an optimized native executable directly with GHC:

```sh
mkdir -p dist-newstyle/snake-baseline
ghc -O2 -Wall -Werror -main-is SnakeBaseline examples/SnakeBaseline.hs \
  -outputdir dist-newstyle/snake-baseline \
  -o dist-newstyle/snake-baseline/snake-haskell
./dist-newstyle/snake-baseline/snake-haskell
```

For compilation timing, add `-fforce-recomp` to avoid an up-to-date build being
skipped. GHC produces and links a native executable; `emlf` produces verified
xMLF, which `--run-xmlf` parses, checks, and interprets on each invocation.
These are different compilation outputs, so report their timings separately.

`cabal test` compares all seven scripted game transcripts byte for byte
between Haskell and eMLF, and checks the same eleven pure-rule outcomes against
handwritten expectations, including the departing tail and full-board win.

### Compiler performance

Graph validation uses indexed scratch tables for densely numbered graphs,
numbers the binding tree once, and checks kinds, scope, and structural cycles
in one traversal. Rebind uses a memoized dependency traversal and depth-based
lowest common ancestors. Sparse external identities retain the map-based
implementation. Graphs remain immutable outside each analysis, and unchanged
nodes are shared. During elaboration, alpha-equivalent instance
types use independently checked `Inst-Refl` evidence directly; other edges
retain expansion, frontier solving, and identity-based evidence construction.
An empty frontier needs no separate unification. The compiler still checks
graph invariants, unification permissions, target typing, and source erasure.

The project builds with `-O2`; the CLI uses a 32 MiB allocation area to reduce
garbage collection during inference. These defaults are in `cabal.project`
and `mlf.cabal`. The allocation area can be overridden with RTS options.

To check Snake against a freshly compiled Haskell baseline:

```sh
cabal build exe:emlf -j1
python3 scripts/benchmark-snake.py \
  --emlf "$(cabal list-bin exe:emlf)" \
  --runs 5 --output dist-newstyle/compiler-target/ghc-comparison.json
```

Every sample runs GHC with `-O2 -fforce-recomp`, including native linking.
The eMLF measurement includes verified xMLF emission. The script alternates
order, checks the emitted type and a Haskell/eMLF game transcript, records
input and compiler hashes, and fails if **any paired run exceeds 5×**.
The recorded medians are **2.83 s for eMLF and 0.75 s for GHC (3.79×)**;
the worst of five pairs is 4.83×. See
[`docs/snake-compilation-performance.txt`](docs/snake-compilation-performance.txt)
for raw samples, build settings, and validation details. Timings depend on
the machine and its load.

To compare compiler revisions, save the earlier executable before rebuilding,
then run the serial benchmark (Python 3, standard library only):

```sh
python3 scripts/benchmark-compiler.py \
  --before /path/to/emlf-before \
  --after "$(cabal list-bin exe:emlf)" \
  --runs 3 --output dist-newstyle/compiler-performance/comparison.json \
  examples/*.emlf
```

Use the same GHC version, optimization settings, source files, and prelude
configuration for both builds. The script
alternates execution order, records every sample and input/binary hashes,
requires byte-identical xMLF, and independently parses and checks the output.
Timing includes process startup and the full source-to-verified-xMLF pipeline,
but excludes building the compiler. See
[`docs/compiler-performance.txt`](docs/compiler-performance.txt) for recorded
measurements. The tests also compare graph validation with an uncached
reference on 12,000 graphs and cover deep scopes and shared higher kinds.
Unification is compared with the previous map-based algorithm on 5,616
cases, with additional sparse/negative identity, scope, and occurs checks.

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

As recommended by §15.3.10, elaboration happens **after** inference. Reflexive
instance edges use `Inst-Refl`; other edges are re-expanded from the final
presolution. The unifier's map from copied nodes to their destinations supplies
identity-based evidence.
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
CompileError Compilation`, `compileProgram` for a `Program` AST containing
declarations, or `compileExpr` for an expression without declarations. Use
`MLF.Parser.parseProgram` to parse a complete source file. A `Compilation`
contains `inferredType` (the explicit target type), `sourceType` (the source
display with class constraints), `compiledTerm`, and the normalized `presolution`.
The checker and xMLF parser can be used independently of the compiler.

This is a reference implementation using persistent maps, explicit graph
validation, and simple least-common-ancestor queries. It does not implement the
linear-time data structures discussed in §7.5, and rigid-bound inlining can
duplicate types, as discussed in §15.4.
Permission calculations are cached per immutable graph, and binding-tree
reconstruction uses a dependency queue while retaining every validation check.

## Validation

`cabal test` exercises the eight computation rules and their failure cases,
capture-avoiding substitution, alpha-equivalence, rigid/skolem checks, graph
domination, expansion reset, let scopes, `choose id`, `g g`, arbitrary-rank
annotations, existentials, and the source examples. Generated xMLF is printed,
parsed again, and checked in the targeted and annotation tests.

The datatype regressions cover constructors, recursive declarations, matching,
polymorphic type arguments, invalid declarations and patterns, and independently
constructed invalid target terms. Every successful source regression also
prints, reparses, and checks its generated xMLF.

The class regressions cover higher kinds, polymorphic methods, generic
qualified functions, superclass dictionaries, recursive contextual instances,
instance overlap and termination, lexical shadowing, and invalid independently
constructed target bindings and type computations. Successful cases also
round-trip through the standalone xMLF parser and checker.

Multiparameter regressions check joint instance matching, repeated parameters,
simultaneous substitution, parameter kinds and arity, ambiguity, and superclass
projections that reorder or drop parameters. Do-notation tests check statement
order, lexical scope, fresh temporary names, local polymorphism, constructor
patterns, invalid blocks, and integration with `MonadState`.

IO tests run printed-and-reparsed target programs with a deterministic backend.
They cover console traces, repeated actions, lazy unused actions, recursive
dictionary methods, polymorphic `Monad IO` functions, EOF and backend errors,
and representative monad-law traces. Invalid target programs are rejected
before effects, and forged IO constructors, types, or primitive signatures are
rejected independently of inference.

Prelude tests cover automatic IO dictionaries, generic functions at IO and
user-defined monads, superclass and instance contexts, lexical and class
shadowing, explicit opt-out through every compiler API, ambiguity, instance
overlap, and the unchanged output of programs that do not use the prelude.

Snake tests execute the actual example through both generated and
printed/reparsed xMLF. Scripted sessions check the rendered boards, WASD input,
quit, invalid commands, growth, reverse turns, and wall/body collisions.
Additional checks call the example's pure rules to cover all four walls,
the departing tail, food occupancy, and the full-board win.

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
