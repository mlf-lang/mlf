# Guards and tuple/list integration review

Status: exact-head and merged-worktree source reviews complete. No concrete integration omission found in the reviewed Parser, Layout, guards/Core/backend registration, or tuple/list root targets. No parser execution, compiler build, runtime test or full qualification was run for this review.

Inputs inspected through read-only GitHub file APIs:

- PR #11: `f29ad8b770eae70b505c40d9ba0d91b123f3db51`.
- PR #12: `af88e6f417780c9d5f39f53604eb99b409de81a6`.
- Relevant current source paths are `libraries/mlf-frontend/Bootstrap/Parser.emlf` and `libraries/mlf-frontend/Bootstrap/Layout.emlf`; old `bootstrap/Bootstrap/` paths from the older local checkout are not the current source locations.

## Required merged Parser behavior

1. `valueDeclaration`, inline `bindingHead` annotations, class methods and expression annotations retain tuple/list's `annotationSymbol = pChoice (pToken "::") (pToken ":")`.
2. `bindingHead` must combine `ty <- pOptional (pThen annotationSymbol annotation)` with guards' `pLook (pChoice (pToken "=") (pToken "|"))`. It must not consume `=` there. `equation` owns the choice between `pThen (pToken "=") expr` and `pSome (guardBranch "=")`.
3. Keep complete tuple/list implementation: right-associative cons at concatenation precedence; `legacyAnnotation`; tuple/list expressions, nested patterns, types and datatype field syntax; ordinary constructor lookup; the no-range/comprehension/section/trailing-comma checks.
4. Keep `legacyAnnotation`'s `|` and `=` end markers. These preserve `f x | true = x : Int | otherwise = 0` and `g flag | flag : Bool = 1 | otherwise = 0`. They do not change the ordinary type-arrow grammar: guard-if condition annotations before `->` continue to require parentheses.
5. Keep guards' `ifExpr`, `guardBranch` and `guarded`: exactly one final contextual `otherwise`, ordered/lazy conditional lowering, no equation fallthrough, and the existing duplicate-pattern-variable check.

## Required merged Layout behavior

- Keep guards' `nextToken`: when `if` is immediately followed by `{`, remove its just-pushed `IfMark`, so it cannot steal a surrounding ordinary `if`'s `then`/`else` or keep an implicit `do` block open.
- Also keep tuple/list's `]` and comma continuation tokens, `::` and comma previous-token continuation entries, explicit `[` frames, `]` closing handling, and `closeCollection`/`searchCollection` for commas that terminate implicit inner blocks up to the nearest tuple/list delimiter.
- The two changes address different state-machine transitions and must be combined, not resolved by choosing either whole file.

## Registration and coverage that must survive

- Guards belongs only to `core-language`: `Tests.CoreLanguage` imports and registers `Tests.Guards.guardTests`; `Tests.CorePartitions` includes `core/guards` in the global family list and only that partition.
- Guard runtime fixtures remain registered in `Tests.BackendCases`, `Tests.BackendSuite`, and the checked catalog/inventory paths. Do not create a duplicate Core registration in another partition.
- Tuple/list remains in the root `mlf-package.json` as executable `tuple-list` and command test targets `tuple-list` and `tuple-list-native`, with `tests/TupleListMain.emlf`, `tests/fixtures/tuple-list-runtime.emlf` / `.stdout`, and `tools/release/test-tuple-list.sh` preserved.
- `TupleListMain` has seven fixed-AST delimiter assertions: colon and explicit annotations before `|` and `=`, lowercase cons before `|`, empty-list cons before `=`, and constructor-shaped annotation before `|`.
- `Tests.Guards` separately contains two fixed-program-AST regressions for annotations before guard bars/equalities. Both layers are useful: the tuple/list tests exercise a surrounding parser without depending on guards grammar, while the guard tests exercise the actual declaration grammar. They must not be deleted as duplicates.
- These source checks do not qualify a combined compiler. Future focused qualification must execute these retained cases plus mixed tuple/list-in-guards and guard-if-in-collection/layout scenarios on the actual merged compiler and native runtime.

## Final merged-worktree review

Reviewed at `2026-10-23T14:12:50Z` in `mlf-integrated`; observed HEAD was `2e394ff375ec3ca86df58a1ad12f27d73122cd66` (the tuple/list integration commit). The parent may subsequently merge CI-only PR #16; this review is tied to the exact frontend bytes below.

- Parser SHA-256: `46f53ac936865958d33fd10631912938345a6f533353926c1448d85c637e320e`.
- Layout SHA-256: `b9a9c36c58ecc464b4d5c2a7b71d030c144b405ba3ccb97d19c7bbaca857da5c`.
- Relative to exact tuple/list head, Parser differs only by guards' equation RHS dispatch, non-consuming `= |` binding lookahead, and guarded `ifExpr`/`guardBranch`/`guarded` definitions. The tuple/list `annotationSymbol`, complete legacy annotation discrimination (including `|` and `=`), collection/type/pattern/field lowering remain intact.
- Relative to exact tuple/list head, Layout differs only by guards' `nextToken` braced-if marker handling. All collection continuation, bracket frame, comma closing and `closeCollection` logic remain intact.
- Seven files compare byte-for-byte equal to exact guards head: `Tests/Guards`, `Tests/CoreLanguage`, `Tests/CorePartitions`, `CoreLanguageMain`, `Tests/BackendCases`, `Tests/BackendSuite` (all under `tests/`), and `tests/mlf-package.json`. Guards appears only in the `core-language` partition and retains its backend family.
- Four tuple/list files compare byte-for-byte equal to exact tuple/list head: `tests/TupleListMain.emlf`, both `tests/fixtures/tuple-list-runtime` input/output files, and `tools/release/test-tuple-list.sh`.
- Parsed JSON target objects `executables/tuple-list`, `tests/tuple-list`, and `tests/tuple-list-native` equal the exact tuple/list-head definitions. All 14 static preservation comparisons passed.
- Conflict-marker scan of Parser, Layout, Guards and TupleListMain found no markers (`rg` exit 1 means no matches).

These are source-preservation and registration checks only. Mixed-feature parsing, typechecking, runtime behavior and lock generation were not executed or independently qualified by this reviewer. No code changes were made by this review; only this evidence note was updated.
