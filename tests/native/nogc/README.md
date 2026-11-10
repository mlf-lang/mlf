# Restricted arena runtime: standalone C fixtures

This opt-in source increment adds the restricted entry-arena runtime and its
direct C fixtures. It does not connect the runtime to the compiler or change
the default compiler, package manager, build runner, or existing runtime path.
The new runtime refuses evaluation unless an embedding explicitly supplies
positive profile ceilings and enables `MLF_NG0_PROFILE_QUALIFIED` at compile time.
The macro name is an activation switch, not evidence of qualification.

The closed guest link has one entry function. Evaluation returns only a status,
a signed scalar, and accounting, never a language pointer. Language allocations
use one bounded arena released at return. An atomic gate rejects nested or
concurrent entry. Internal guest helpers are hidden symbols, not a host callback
or extension API. This is a restricted runtime foundation, not a claim that the
compiler host or the complete MLF language is GC-free.

## Run the focused checks

On 64-bit Linux, with a C11 GCC or Clang toolchain, libc C11 threads, GNU-compatible
linker wrapping, and `timeout`:

```sh
sh tests/native/nogc/check-runtime.sh
OPT_LEVEL=0 sh tests/native/nogc/check-runtime.sh
SANITIZE=undefined sh tests/native/nogc/check-runtime.sh
# Optional, when AddressSanitizer is supported by the toolchain and host:
SANITIZE=address,undefined sh tests/native/nogc/check-runtime.sh
```

`CC` selects a compiler executable. Each invocation uses a fresh temporary
directory, printed at startup and retained for inspection. Each compile and
execution has a 30-second deadline; timeout, setup failure, and nonzero results
are failures. Strict warnings remain errors. No package installation or network
access is needed.

The fixtures use a 65,536-byte arena and depth limit 128. These are deliberately
small test settings, not production ceilings or a machine-stack qualification.
The tests cover:

- Compile-only C function signatures and scalar result layout.
- Default-disabled and invalid-configuration refusal without guest execution.
- Integer boundaries, lazy branches/fields/partial application, single forcing,
  controlled faults, blackholes, and recovery after failures.
- Independently wrapped host allocations/frees, allocation failure, arena limits,
  cleanup order, and gate ownership during cleanup.
- Compact thunk captures, memoization, overflow, and exact allocation boundaries.
- Concurrent BUSY refusal and successful subsequent entry, using a finite spin
  budget; inconclusive thread setup or exhausted budget is not a pass.

Each alternate guest is linked separately. Allocation wrappers, fixture globals,
and thread coordination must not enter a production guest link. The handwritten
guests do not establish generated LLVM ABI correctness, compiler source admission,
native bootstrap or fixed-point success, complete backend/async conformance,
bounded process cleanup, portable stack safety, or performance. Those require
separate integration and qualification. These checks are supplemental and do not
replace the repository's required CI and native test groups.

The allocation-observer link uses `-fno-builtin-malloc -fno-builtin-free` so
compiler folding of `malloc` plus zeroing into `calloc` cannot bypass its named
linker wrappers. Other optimized fixtures retain normal compiler builtins.
