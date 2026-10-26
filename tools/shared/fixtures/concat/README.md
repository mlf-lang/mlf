# String-list concatenation controls

`ConcatReference.hs` freezes the balanced `Bootstrap.Std.concatStrings` and
`concatStringPairs` bodies from commit
`2957dd08321c38dbf94a75cb275a5f48e897f58e`. It uses the binary `concatString`
primitive and never calls the new list primitive. The driver verifies its
complete source hash before building.

`Main.hs` checks three engines: `Std.concatStrings`, direct
`MLF.Primitive.concatStringList`, and the frozen balanced reference. Each sees
16 literal cases, every fragment list through length four over six fragments
(1,555 cases), five large cases, and 13 exact demand oracles. Expected text uses
independent Prelude concatenation or literals; every scalar and scalar length
is checked. Large results remain live across `performGC`. Explicit `ErrorCall`
markers check head-before-tail failure order, required later heads and list
spines, singleton demand, unused/untaken results, and a failing join before a
failing suffix in an enclosing binary concatenation. A nested primitive inside
a list head checks error payloads beyond a direct panic. Eight literal metadata
oracles check code 107, previous code 106, name, arity, strictness, signature,
lookup, and the append-only opcode inventory.

The enclosing-concatenation cases call a separate `appendJoined` function to
exercise worker argument demand. The GHC wrapper is explicitly `NOINLINE`.

Three additional GHC controls enter `Runtime.runtimeStringChunks` directly.
They distinguish an already constructed `RString` wrapper from its bottom
payload, require that payload's exact error before a later `Left`, and check
valid-payload failure and canonical output order. The driver includes the
interpreter's shared-module source closure in the fresh GHC build.

`Native.emlf` runs the same three engines through the candidate interpreter and
Clang O0/O2 native executables. Each engine has 15 execution modes: literal and
scalar checks, generated-fragment checks, and the 13 demand controls. Thus the
driver requires 45 interpreter executions and 90 native executions. Interpreter
generated-list cases use 128 fragments; native cases use two lists of 32,768
fragments and verify every scalar while retaining the first result across the
second allocation. The test-only `gc_probe.c` observes BDWGC's collection count;
all six native stress executions must observe at least two collections. It
writes a dedicated receipt file so ordinary stdout and stderr remain exact.
Actual LLVM helper use is required, not merely a declaration.
Scalar verification uses 1,024-scalar chunks so the O0 test itself does not
require tail-call elimination; all 131,072 scalars in each result are checked.
Native stress starts with a 1 MiB GC heap.

The companion `tests/native/runtime_string_concat.c` adds 24 direct runtime
executions (12 modes at O0/O2), distinct from the portable fixture. They cover
the helper, opcode 107 and first-class primitive entry, singleton sharing,
head/tail evaluation order, malformed lists, overflowing byte lengths before
copying, and forced collections while lazy fragment heads/tails are evaluated.
The success control also runs with interior-pointer recognition disabled.

Run only after measured tasks have released the CPU, using fresh output paths:

```sh
python3 tools/shared/test_string_concat.py --mode ghc \
  --ghc /path/to/ghc-9.14.1 --clang /path/to/clang \
  --output /path/to/new-concat-ghc

python3 tools/shared/test_string_concat.py --mode native \
  --compiler /path/to/candidate-emlf --clang /path/to/clang \
  --gc-prefix /path/to/bdwgc --output /path/to/new-concat-native
```

`--mode all` combines both runs and requires all tool arguments. Every source is
snapshotted before compilation; commands are bounded, outputs are retained,
and source/tool/artifact hashes are rechecked after completion. Native compiler
identity is recorded, but its build provenance and the complete system-library
closure are not authenticated. This is finite semantic and observed-GC
evidence, not a performance result or full compiler qualification.
