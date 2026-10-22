# Regular expressions

`Bootstrap.Regex` is a reusable MLF module. Import it from the `mlf-bootstrap`
package, or add `-i bootstrap` when compiling a source file directly. It runs
unchanged in the interpreter and native backend and needs no foreign library.

The public API is:

```text
compile      : String -> Either String Regex
find         : Regex -> String -> Int -> Maybe (Pair Int Int)
countMatches : Regex -> String -> Int
replaceAll   : Regex -> String -> String -> String
```

`compile` validates the complete pattern. `find regex subject offset` returns
the first match at or after `offset` as half-open `(start, end)` offsets. Invalid
offsets return `Nothing`. `countMatches regex subject` counts nonoverlapping
matches. `replaceAll regex replacement subject` replaces those matches with
the literal replacement string: `$1` and backslashes have no special meaning.

Patterns support literal Unicode characters, `.`, bracket classes and ranges,
negated classes, grouping, alternation, greedy `*`, `+`, `?`, and bounded
`{n}`, `{n,}`, `{n,m}` repetition. Escapes include `\n`, `\r`, `\t`, escaped
punctuation, and ASCII `\d`, `\w`, `\s` with their uppercase complements.
`.` excludes newline. `^` and `$` match only the absolute beginning and end of
the subject; `$` does not additionally match before a terminal newline.
Grouping is structural and does not capture. Backreferences, lazy quantifiers,
lookaround, flags, and other alphabetic escapes are rejected. Repetition
bounds above 1000 and patterns exceeding a conservative compilation budget of
10000 construction steps are rejected, including nested empty repetitions.

Matches are leftmost first. Alternatives preserve their written order, and
repetition prefers consuming another character whenever a complete match can
still result. After an empty match the next search starts one Unicode scalar
later; an empty match at the end is counted once. Replacement preserves the
character skipped by this search advance. This also means `a*` matches both
`aaa` and the empty position immediately after it.

Strings and offsets use Unicode scalar values, not UTF-8 bytes. ASCII input
therefore has the same character and byte offsets. Embedded NUL is an ordinary
character. The ordered Thompson NFA deduplicates consuming states at each
input position. Reentering a repetition without consuming input follows its
continuation at the current path priority, so nullable repetitions terminate.
The matcher does not use recursive backtracking.
