# Independent focused codemod review

Reviewed `Migrate.hs` for matrix demand order, lexical capture and do continuation scope, and exercised the produced source using the small checked-in regression suite. No production implementation corpus was built.

## Findings resolved during review

1. Generated literal decisions initially used unqualified `eqString`/`eqInt`, allowing outer local bindings to capture fixed matching semantics. Both now use `MLF.Primitive`-qualified identities. Synthetic equality-shadow fixtures changed from the observed wrong result 3 to the required 2.
2. The initial comment scanner treated the closing backslash of a string gap as an escape for the following closing quote. It lost a real following comment and extracted later string data as a comment. The scanner now follows the lexer's whitespace-gap rule. The regression checks nested block comments, line comments, escaped quotes, the gap boundary, and runtime literal contents.

## Matrix and scope review

The matrix transcription preserves the original `Bootstrap.Surface` selection of the first row's leftmost nonvariable column, constructor specialization and literal fallback. It does not first force the full nested constructor spine. Poisoned-tail, poisoned-head, fallback-alias and required-demand checks pass for the exercised shapes.

The ordinary-let capture check correctly computes free names using the legacy sequential scope, resolves them through prior lexical renames, and renames a new binder only if the emitted name would capture a free RHS reference. Nested repeated shadows, function-name capture, sequential forward references and do-local shadows all pass. Inner lambda and case binders are not falsely treated as free references. Closed single and mutually recursive groups pass, and unsigned/open recursive groups reject.

Constructor do binds correctly place the complete remaining continuation inside the constructor case. The fixture uses a custom `Monad` class without `Prelude.Monad` superclasses; the continuation retains all constructor-bound variables, and a discarded lazy payload remains unevaluated.

## Bounded outcome

All 30 assertions pass: five transformed synthetic modules, runtime and lexical checks, and four intended migration rejections. The helper's negative-zero and negative-one bit patterns, sign-toggle roundtrip at zero, and `negateInt` rename are included.

`focused-fixture-receipt.json` records the exact tool/source/test identities and `focused-fixture-run.log` retains warnings and results. Reproduction is documented in `../tests/README.md`; outputs are regenerated in a temporary directory. This is focused tool validation, not evidence that either full production host or its runtime is qualified.
