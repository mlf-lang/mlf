# Length-prefixed string fields

`packStringFields :: [] String -> String` concatenates each field's decimal
Unicode scalar count, `:`, and unchanged contents. The empty list produces `""`;
an empty field produces `"0:"`. For example, `["", "a:β", "🌍"]` produces
`"0:3:a:β1:🌍"`. Counts are neither UTF-8 byte lengths nor grapheme counts.

The operation demands the list and each field in order, forcing a head before
its tail. An unused result remains lazy. Counts and total byte sizes are checked
for overflow before output allocation. The primitive is appended at code 135;
all previous codes retain their meanings. The builtin interface is `/15`, with
primitive ABI `mlf-primitive-136-v11`.

`Bootstrap.Separate.pack` uses this operation without changing its framing
format. The GHC host combines header creation with the text-fragment traversal.
It shares the complete decimal-length-plus-colon header for scalar lengths
0 through 1023 in a fixed lazy table. Larger fields format the same header
directly; the table never retains payloads or grows with the number of fields.
Each field contributes two text fragments, with unchanged demand and overflow
checks. This host-only optimization does not change the primitive ABI or the
builtin source identity.
The native runtime validates and memoizes fields, then allocates one output
buffer and copies each header and payload. Both implementations eliminate the
intermediate source list of three fragments per field. This changes transient
allocation, not encoded file size. Prepared builtins and artifacts still need
their new ABI identity; older prepared builtins are not accepted as current.

Run the independent host, interpreter, native O0/O2 and direct runtime controls:

```sh
python3 tools/shared/test_string_fields.py \
  --build-receipt /absolute/path/to/producer/receipt.json \
  --clang /absolute/path/to/clang \
  --output /absolute/path/to/fresh-controls
```

The test uses a Python scalar-length oracle, a legacy concatenation reference,
Unicode and decimal-boundary cases, source demand failures, malformed runtime
lists, synthetic overflow lengths, and forced GC with interior pointers both
enabled and disabled. These are finite semantic checks, not a native compiler
self-bootstrap qualification or a performance claim.
