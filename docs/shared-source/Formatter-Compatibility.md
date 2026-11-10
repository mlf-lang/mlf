# Haskell formatter compatibility

The maintained library corpus is tested with **Ormolu 0.9.0.0** (commit
`c0017d4b81449840fe96d250ce40b6ac7fe27e3e`, ghc-lib-parser
`9.14.1.20251220`) and the actual MLF frontend built with **GHC 9.14.1**.
The gate covers every `libraries/**/*.hs` file, including generated literal
modules, plus the focused fixtures in `tools/shared/fixtures/formatter/`.
It formats isolated copies, not the working library files.

## Run

Use the official Ormolu release and the repository's pinned GHC toolchain:

```sh
python3 tools/shared/test_formatter_compatibility.py \
  --ghc /path/to/ghc-9.14.1/bin/ghc \
  --ormolu /path/to/ormolu \
  --output /tmp/mlf-formatter-compatibility
```

The output directory must be new. The script records exact source/tool hashes,
formatter versions, commands, logs, and individual original/formatted hashes.
The dedicated `formatter-compatibility.yml` CI workflow downloads the official
Linux release archive and verifies SHA-256
`367eb4969986504cf171f71f91e24ea5d7d9d97c41701e8e6eef9b642fd0d201`.

Formatting keeps Ormolu's AST safety check and enables its idempotence check.
It does not use `--unsafe`, source pre-processing, or a replacement MLF parser.
A formatter failure is a failed gate, not a skipped module.

## What is checked

`FormatterCompatibility.hs` parses both sources with `Bootstrap.Parser` and
compares their complete source-module ASTs with `Bootstrap.SourceEquality`.
Only source file/coordinate metadata and the ordering of import declarations
and import-selection members are normalized. Import multiplicities, selections,
aliases, call-site labels, declaration wrappers, literals, signatures, recursive
groups, and binding order are preserved. Negative controls must detect changed
literals, missing declarations, changed imports, and invalid syntax.

The maintained frontend also tests forward-scoped and shadowing `let` groups,
inline and multiline `do`/`case`, nested `case` and `do` scrutinees ending at
`of`, closures at `in`, `else`, parentheses and collection commas, and the
split LANGUAGE prologue that Ormolu emits. The legacy sequential-let profile
is unchanged. Existing malformed-indentation and explicit/implicit boundary
rejections remain in force.

Ormolu 0.9.0.0 initially rejected one nested one-line case in
`Bootstrap.SourceInference` because its own input/output AST check disagreed.
Putting the existing nested alternatives on separate source lines makes its
safe formatting succeed; no formatter safety check is bypassed.

This is a bounded formatting/parser-structure compatibility gate. It does not
claim every Haskell extension or every legal layout form is supported, and it
does not replace inference, execution, LLVM, or native self-host qualification.
No native A/B or fixed-point run is part of this gate.
