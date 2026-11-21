# UTF-8 byte length

`stringUtf8Length :: String -> Int` returns the encoded UTF-8 byte count.
`stringLength` continues to count Unicode scalars. For example, `"λ😀"` has
scalar length 2 and byte length 6. Embedded NUL counts as one byte; storage
terminators are excluded. Slices and concatenation use their own resulting
text lengths.

The unary primitive is strict in its text argument. An unused call remains
lazy. Invalid Unicode construction retains its existing failure. The opcode
is appended as 136, preserving codes 0–135. The primitive ABI is
`mlf-primitive-137-v12`; the builtin interface is
`mlf-primitive/shared-haskell-v1/16`. Old caches must follow the normal identity
invalidation path; the bitstream wire layout and schemas are unchanged.

The GHC host reads the length from its private validated UTF-8 text. Native
strings validate and cache their Unicode index lazily, so a standalone first
call may scan the text. Later calls reuse that validation. Native lengths
outside the nonnegative Int64 range fail with `string too large` before reading
bytes. No String layout or collector ownership rule changes.

The binary codec retains its scalar-length precheck and its error order, then
checks the cached byte length against the byte budget. On the native backend,
that precheck already establishes the validation/index cache. The separate
`utf8SizeAt` helper retains its original scanning behavior.

`tools/shared/test_utf8_length.py` exercises independent Unicode byte counts,
limits, slices, concatenation, metadata/opcode roundtrips, generated native
helper calls, interpreted calls and direct runtime dispatch. Native O0/O2 probes
cover validation, type/overflow failures, demand and collection with ordinary
and disabled interior-pointer recognition. The control is part of
`tools/shared/test_direct.py`.
