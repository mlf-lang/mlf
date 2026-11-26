# Exact byte-array equality

`MLF.Primitive` provides:

```haskell
byteArrayEqual :: ByteArray -> ByteArray -> IO Bool
```

The result is `True` exactly when the arrays have the same length and every
corresponding byte is equal. Empty arrays compare equal. Embedded zero bytes
are ordinary data. Comparing an array with itself returns `True`.

The comparison executes inside `IO` because byte arrays are mutable. Creating
or evaluating the action does not demand either array or read its contents.
Executing it demands the left operand, then the right operand, before
comparing their lengths and bytes. Reusing an action compares the current
contents each time, including mutations made after the action was created.

The host adapter borrows the two pinned array owners through nested
`withByteStorage` scopes and a safe foreign call. It does not create byte
snapshots. The native runtime performs the same length check and bulk byte
comparison; the interpreter invokes the host operation at its ordinary IO
boundary. The operation uses constant auxiliary space and takes time
proportional to the compared prefix, with immediate rejection of different
lengths. Callers that allow concurrent writes must synchronize them when a
stable comparison is required.

## Primitive compatibility

The primitive is appended at opcode **137**, with arity **2**. Existing opcode
assignments, including `stringUtf8Length` at 136, remain unchanged. Primitive
metadata, source name lookup, artifact encoding/decoding, interpreter action
classification and native direct/dynamic application all use this identity.

Generated native programs require `mlf_require_byte_array_equal_abi`. The guard
ensures that a program using the operation cannot silently link against a
runtime that lacks it. Build the compiler, its builtin primitive interface and
the native runtime together when adopting the new primitive.

## Verification

After producing an authenticated shared-source build, run:

```sh
python3 tools/shared/test_byte_array_equal.py \
  --build-receipt .mlf-build/pr55-candidate/receipt.json \
  --output .mlf-build/byte-array-equal-controls
```

The output directory must be new and outside the producer build directory.
The control is also registered in `tools/shared/test_direct.py`.

The verifier compares the GHC host, the interpreter, and generated native
programs at Clang `-O0` and `-O2` against Python's independent byte equality.
Its finite vectors cover empty arrays, unequal lengths, exact matches,
differences at the first/middle/last byte, embedded zero and high bytes, and
arrays up to 1,048,583 bytes. Each vector also executes a shared action before
and after mutation, restores the data, constructs an action before its first
mutation, and checks aliasing.

Separate controls check lazy IO construction, an unused action, left-to-right
failure order, primitive metadata and artifact roundtripping. A copied host
adapter injects a collection while both pinned owners are borrowed. Native
C controls use both saturated `mlf_prim2(137, ...)` and dynamically applied
`mlf_primitive(137)`, including collection during operand evaluation,
disabled interior-pointer recognition, and invalid operand diagnostics.

`receipt.json` records commands, exact inputs, generated artifacts and their
hashes, backend vector counts, and completion status. These are correctness
and ownership controls; they do not assert an end-to-end compiler speedup.
