# Focused shared-host primitive qualification

This suite builds only the production GHC primitive facade, its three adapter modules,
small handwritten probes, and the native process transport. It does not build or
translate the compiler. The optional native filesystem oracle compiles the unchanged
C runtime directly and calls its existing filesystem helpers; no guest compiler is
needed. No package is installed.

Run on the qualified Linux x86_64 / GHC 9.14.1 environment:

```sh
PATH=/workspace/shared/mlf-toolchain/bin:$PATH \
python3 tests/shared-host/run.py \
  /workspace/shared/mlf-ghcup/.ghcup/ghc/9.14.1/bin/ghc \
  --gc-root /workspace/shared/mlf-toolchain/gc
```

`--gc-root` is optional and must identify an existing BDWGC installation with
`include/gc/gc.h` and `lib/libgc.a`. Without it the native filesystem oracle is
explicitly omitted. The remaining tests use only GHC's bundled packages and libc. GCC and Clang native
environment probes run when each compiler is on PATH; the saved final receipt
includes both.
Every command is bounded by a 60-second timeout. The source list, SHA-256 hashes,
exact commands, environments, return codes and expected observations are written to
`.runs/<UTC timestamp>/receipt.json`; objects and executable files remain ignored.

`evidence/latest/` preserves the final reviewed receipt and text logs without binaries.
Earlier defect observations are retained in `evidence/before-*`,
`evidence/cancel-before.log`, and `evidence/argument-review.log`.

## Coverage

- 87 direct production-facade contract checks at both `-O0` and `-O2`, with
  `-fpedantic-bottoms -fno-state-hack -dcore-lint`: cold IO/ST/async construction,
  comparison argument order, lazy ST initializer/snapshots, strict scalar IO cells,
  action-time errors, enormous sizes/indices/handles/delays, Unicode scalar/NUL
  operations, typed lazy one-shot completions, FIFO callbacks and closure status.
- 590 bit-exact comparisons at each optimization level against a C `strtod` oracle:
  signed zero, subnormal/overflow boundaries, large integers and exponent extremes.
- Actual `Prelude.Bool` identity for patterns/guards and ordinary Prelude
  Functor/Applicative/Monad identity, polymorphic `pure`, and standard IsString
  literals, without RebindableSyntax. The user explicitly superseded the earlier
  custom-Monad/IO-only-pure design; its original receipts are historical evidence.
- Compile-negative cross-array tests prove IntArray and ByteArray are distinct.
  Wrapped array coldness, payload validation, writes, reads and lengths are tested.
- Exact nested-panic and Unicode panic diagnostics at both optimization levels and
  both locales; native exit-code diagnostics and path-before-content demand.
- Literal +RTS/-RTS argv survives executable links using `-rtsopts=ignoreAll`.
- Regular file/directory/FIFO/device distinctions; raw-byte-invalid symlink targets
  and executable paths; strict malformed UTF-8 rejection; stdin remains open at EOF.
- UTF-8 argv and non-ASCII file paths under `LC_ALL=C` and `LC_ALL=C.UTF-8`, including
  malformed argv bytes and embedded-NUL file content.
- Deterministic safe-FFI cancellation: a linker wrapper delays the return after the
  C adapter allocates its result. Cancellation must propagate and free that result.
- Fault injection into the second transport-string allocation: OOM must free the
  already allocated wrapper.
- Optional direct native runtime observations for the three filesystem divergences
  and explicit setEnv name-before-content sequencing under both GCC and Clang.
  The latter is an intentional clarification of previously unspecified C order.

The cancellation wrapper and allocator fault injector are test instrumentation only;
production code contains no observation hooks or source rewriting.

## Boundaries

These results are Linux evidence, not macOS or Windows qualification. They do not
prove every decimal literal conversion, every allocation-failure cleanup path,
interruption of indefinitely blocked foreign calls, process child reaping on every
failure, concurrent access to the single-coordinator async API, full guest/native
parity, bootstrap fixed points or performance. The existing native process, completion
storage, and direct Async library gates remain necessary.
