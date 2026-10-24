# Independent one-time migration input audit

## Result

The audited PR20 parser accepts every source in the closed 84-file reference inventory at baseline commit `2f85844`. It finds exactly **89 string-pattern leaves in 17 modules**, all within case alternatives. It finds **13 negative Double expression literals**, no Double patterns, and one logical syntax-hook collision: `Bootstrap.Std.negate`.

No repository implementation source was changed. Inputs were extracted from the immutable commit into `/tmp`. Only the small audit tool was compiled, plus a bounded `-fno-code` contextual-name probe; no compiler/runtime qualification corpus was executed.

## Exact string-pattern counts

| Module | Leaves | Original source |
|---|---:|---|
| Async.Process.Internal | 1 | `libraries/mlf-async/Async/Process/Internal.emlf` |
| Bootstrap.Crate | 3 | `libraries/mlf-crates/Bootstrap/Crate.emlf` |
| Bootstrap.CrateArtifact | 3 | `libraries/mlf-crates/Bootstrap/CrateArtifact.emlf` |
| Bootstrap.CrateCodegen | 1 | `libraries/mlf-crates/Bootstrap/CrateCodegen.emlf` |
| Bootstrap.CrateQuery | 3 | `libraries/mlf-crates/Bootstrap/CrateQuery.emlf` |
| Bootstrap.InferenceUnit | 1 | `libraries/mlf-crates/Bootstrap/InferenceUnit.emlf` |
| Bootstrap.Module | 2 | `libraries/mlf-frontend/Bootstrap/Module.emlf` |
| Bootstrap.Separate | 13 | `libraries/mlf-crates/Bootstrap/Separate.emlf` |
| MLF.Entry.Emlf | 37 | `bootstrap/Main.emlf` |
| MLF.Entry.Mlfpkg | 1 | `package/Main.emlf` |
| Package.Build | 3 | `libraries/mlf-package-core/Package/Build.emlf` |
| Package.Command | 7 | `libraries/mlf-package-core/Package/Command.emlf` |
| Package.Distribution | 2 | `libraries/mlf-package-core/Package/Distribution.emlf` |
| Package.Scheduler | 7 | `libraries/mlf-package-core/Package/Scheduler.emlf` |
| Tests.Catalog | 2 | `tests/Tests/Catalog.emlf` |
| Tests.CompilerTests | 2 | `tests/Tests/CompilerTests.emlf` |
| Tests.Selection | 1 | `tests/Tests/Selection.emlf` |

`summary.json` lists every leaf by module, source, AST path and original literal token spelling. The counts reproduce the earlier manual lower bound exactly. No direct equation-parameter, lambda-parameter or do-bind string-pattern leaves occur in this baseline.

## Scope and signature findings

- 1,743 ordinary local groups: 728 expression lets and 1,015 do-lets.
- All local groups, including the two recursive ones, contain one logical binding. No ordinary group introduces multiple sequential declarations.
- No ordinary group's own binder occurs free in its right-hand side. For the frozen baseline, preserving nested boundaries suffices to retain legacy nonrecursive scope; blanket alpha-renaming is not necessary.
- The free-variable calculation respects equation/lambda/case/do pattern binders, nested recursive scope and sequential ordinary-let/do-let scope. It does not count qualified names as unqualified references.
- `Bootstrap.Elaborate.prepareTypes` contains `context : TypeContext`, recursively referenced in its RHS (line 37).
- `Bootstrap.Runtime.recursiveEnv` contains `result : REnv`, recursively referenced in its RHS (line 81).
- Top-level within-module value dependency analysis finds 550 cyclic SCCs, containing 755 bindings. Every such binding has an explicit signature; all these signature ASTs have zero free type variables. `top-cycles.json` lists the SCCs.
- This describes the frozen baseline only. Parallel frontend edits must be audited again before the codemod is applied/finalized.

## Binder names

There are zero Haskell2010 hard-reserved binder collisions. The hook `negate` has a signature and equation in `Bootstrap.Std` (lines 43–44), but no AST value use anywhere in this inventory. Rename it to `negateInt` as required by the design.

The scan also encounters `pattern` (60), `role` (12), `qualified` (8), `as` (8), `hiding` (2) and `family` (1), counting signatures and equations separately where present. A GHC 9.14.1 `-XHaskell2010 -fno-code` probe with exactly the proposed shared extension set accepts all six as ordinary bindings. They are contextual or extension-sensitive words, not collisions under that extension set. Do not mechanically rename all of them merely because a broad keyword list includes them.

## Negative Double literals

- `Bootstrap.Parser.negateValue`: 1 (`-1.0`). Preserve `mulDouble (negateDouble 1.0) n`; do not algebraically refactor it.
- `Package.Benchmark.initialBodies`: 11, including the constants in the planetary state records and `-1.0` in momentum adjustment.
- `Package.Verification.measurement`: 1 (`-1.0`).

All 13 exact spellings and AST paths are in `summary.json`. No negative zero literal occurs in these 13, but the helper needs a separate negative-zero bit-pattern test.

## Matrix demand contract

The normative algorithm is `Bootstrap.Surface.matrix`, not an arbitrary Haskell pattern-to-guard transformation:

1. Examine the first surviving row. If every pattern is variable/wildcard, bind that row without further demand.
2. Otherwise select that row's leftmost nonvariable column.
3. A constructor decision tests only that constructor and inserts its fields into the matrix at that column; it does not eagerly traverse all nested fields.
4. A literal decision compares the selected field, then recursively matches the surviving rows. Variable rows participate in each compatible specialization while retaining row priority and original scrutinee bindings.
5. Preserve ordered alternatives and reject the same unreachable/nonexhaustive matrices as the source lowering.

The design's whole-matrix rewrite is faithful if it literally follows these decisions and emits only flat constructor cases plus explicit `eqString` tests. Matching the complete nested constructor spine before checking the string tag is observably wrong.

### Recommended demand fixtures

Use legacy and migrated versions and compare values or the same deliberate failure:

1. Exact poison-tail case: rows `Cons "a" (Cons x xs) -> 1`, `Cons "b" rest -> 2`, `_ -> 3`; input `Cons "b" (panic "tail")` must return 2 without touching the tail.
2. The same three rows as a function-equation matrix must also return 2.
3. Lambda nesting: apply a lambda whose body is the case from fixture 1. It must return 2. A lone direct lambda parameter containing a string literal has no default row and is rejected by native `Surface.matrix`; preserve that as a negative fixture rather than assuming it is accepted.
4. First-row demand beats globally earliest string: rows `Cons _ Nil -> 1`, `Cons "b" rest -> 2`, `_ -> 3`; input `Cons (panic "head") Nil` must return 1. An eager tag test would be wrong even though it looks like left-to-right string matching.
5. Correct failure demand: fixture 1 with `Cons "a" (panic "tail")` must fail on the tail. Avoid turning all mismatches into unconditional fallback or suppressing required demand.
6. Preserve fallback aliases: first row `Cons "a" Nil`, second row a variable binding `whole`; with `Cons "b" (panic "tail")`, a second-row body that matches only `whole`'s outer constructor and reads its head must succeed. Bind `whole` to the original list, not a specialized field.
7. Nested outer data: wrap fixture 1's list inside `Pair`, and add an unused poisoned other field. Only the selected decision path may be forced.

### Recommended lexical-scope fixtures

These are synthetic regression inputs even though the frozen inventory currently needs zero capture renames:

- Outer capture: `let x = 41 in let x = x + 1 in x` has legacy result 42. Rename only the inner binder and its body references; the RHS must keep the outer reference.
- Function capture: outer `f n = n + 10`, inner ordinary `f x = f x + 1`, then `f 1`, has legacy result 12. Turning it recursive loops.
- Repeated shadows: `let x = 1 in let x = x + 1 in let x = x + 1 in x` yields 3.
- Sequential forward-name capture: outer `y = 7`, then ordinary group `{ x = y; y = 8 }`, result `x`, yields 7. Emitting one recursive Haskell group incorrectly yields 8.
- Do-local shadow: `do { let x = 40; let x = x + 2; return x }` yields the appropriate custom-monad action containing 42.
- False-positive exclusions: `let x = (\x -> x) 7 in x`, a RHS case with its own `x` pattern binder, and `let x = Q.x in x` need no own-RHS capture rename.
- Closed recursive signatures: preserve the two production recursive examples and add mutual recursion with explicit closed signatures. A recursive SCC with a missing or open signature remains a profile rejection.

## Reproduction

The isolated directory contains `extract.py`, `Audit.hs`, `inventory.tsv`, `inventory.json`, `baseline-ast.tsv`, `summary.json`, `top-cycles.json`, and `ContextualNames.hs`. The source parser is imported unchanged from the reference design checkout. The top-level SCC computation is based on the audit's emitted binding dependencies; it is a within-module lexical graph, not a type inference or whole-program runtime qualification.
