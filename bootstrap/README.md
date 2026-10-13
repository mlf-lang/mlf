# MLF compiler written in MLF

`Main.emlf` is the compiler entry point. `Bootstrap/` implements source parsing,
layout, modules, classes, graph inference, evidence, elaboration, the independent
xMLF checker, the interpreter, and LLVM generation in ordinary MLF. It uses the
same language available to other programs, including algebraic data types,
polymorphism, classes, recursive functions, modules, and IO.

The Haskell implementation is the seed compiler. Native MLF stages use the
generic C runtime and GMP. They do not call the seed, embed its executable, or
use a compiler-specific runtime primitive. File IO, Unicode text operations,
command-line arguments, and floating-point bit conversion are ordinary runtime
operations, specified in [RUNTIME.txt](RUNTIME.txt).

The bootstrap binaries use the runtime's optional compact BDWGC allocation profile so
that long pure compiler phases can reclaim temporary allocations. The build
downloads the pinned BDWGC 8.2.12 source, verifies its SHA-256, builds it locally,
and runs its upstream tests under `dist-newstyle/bootstrap-deps/`. It does not
install system packages. Normal generated programs and benchmark binaries keep
the existing runtime allocation profile. The collector interface is documented
by [BDWGC](https://www.hboehm.info/gc/gcinterface.html).

The bootstrap profile keeps automatic collection during allocation and requests
an additional collection at IO boundaries after 1,048,576 value/environment
allocations. Native self-compilation defaults to a 512 MiB initial collector
heap and free-space divisor 1; `GC_INITIAL_HEAP_SIZE` and
`GC_FREE_SPACE_DIVISOR` override those settings. The verification report records
the chosen settings. These controls do not change language evaluation semantics.
On macOS, compiler binaries link with a 64 MiB main stack so the MLF interpreter
can run the deep lazy programs in the backend suite.

Run the complete bootstrap gate from the repository root:

```sh
python3 scripts/bootstrap-compiler.py
```

The gate builds the seed, compiles `Main.emlf` to stage 1, asks stage 1 to compile
the same sources to stage 2, and asks stage 2 to compile them to stage 3. It
requires byte-identical stage 2 and stage 3 LLVM, then runs the exported language
and runtime corpus through stage 2. Every accepted target is checked by the
independent Haskell xMLF checker and compared with the reference type by alpha
equivalence. Runtime cases run through both the MLF interpreter and its generated
native code. Rejected cases must fail in the expected compiler phase, including
Figure 12 A8. A source hash check rejects results if files change during the run.

Artifacts, logs, timing, hashes, and the gate result are written under
`dist-newstyle/bootstrap/`. `verification.json` reports `complete: true` only
after every gate succeeds. `--seed PATH` accepts an already built seed;
`--manifest PATH` accepts a freshly exported test corpus.
After an interrupted run, `--reuse-stage1` can reuse the seed-produced LLVM only
when its hash, all MLF source hashes, and the seed hash still match the report.
It relinks stage 1 with the current runtime profile and always recompiles stages
2 and 3 and reruns parity.

The ordinary compiler tests and smaller differential port tests run with:

```sh
cabal test -j1 --test-show-details=direct
```

`bootstrap-port-tests` runs explicit fixtures on both backends and compares
graph, inference, and primitive metadata results with independent Haskell
references. The large corpus exporter also checks Algorithm W typability,
annotation cases, Figure 12, examples, modules, readability fixtures, local-state
scope safety and runtime behavior, and all
Benchmarks Game workloads. Passing a subset of these tests is not a completed
bootstrap: the fixed point and parity gate are both required.

To repeat selected port regressions, pass their fixture names explicitly:

```sh
cabal test bootstrap-port-tests -j1 --test-show-details=direct --test-options='--only Target GraphStack'
```

The selector rejects empty, duplicate, or unknown names and still audits both
backends for every selected fixture. Without `--only`, the suite runs all fixtures.

Run the complete shared backend matrix through both native MLF implementations:

```sh
python3 scripts/bootstrap-backends.py
```

The helper builds the Cabal seed and test harness, recompiles `RuntimeDriver.emlf`
and `LLVMDriver.emlf`, then runs `cabal test backend-tests -j1
--test-show-details=direct` with both drivers configured. `--compiler PATH` uses
another compiler, such as a completed `emlf-stage2`, to build the drivers; the
default is the Haskell seed. Drivers are always rebuilt, with no artifact reuse.

Both driver runtimes explicitly use `-DMLF_USE_BDWGC`, `-DMLF_COMPACT_BDWGC`, and
`-DMLF_GC_THRESHOLD=1048576`, a 512 MiB initial heap, free-space divisor 1, and a
64 MiB main stack on macOS. Only the interpreter driver links the stdio tracing
runtime and `test/native_trace.c`. Generated test programs use the ordinary
runtime with `-O2`. The helper sets the candidate budget to 1800 seconds and puts
the Cabal seed on `PATH` for the ancillary module CLI tests.

Artifacts and diagnostics go to `dist-newstyle/bootstrap-backends/`; `matrix.log`
contains the Cabal output. `verification.json` records source, compiler and driver
hashes and reports `complete: true` only after Cabal succeeds, the full nonempty
two-backend coverage audit passes, and the source hashes still match. `--output
DIR` changes the artifact directory. `--dry-run` prints the command plan without
building drivers, executing tests, or recording a successful result.

For direct harness use, the source-only `LLVMDriver.emlf` and `RuntimeDriver.emlf`
expose the ported backend and interpreter.
`MLF_BOOTSTRAP_LLVM` and `MLF_BOOTSTRAP_INTERPRETER` select those native drivers in
the test harness; configured drivers must execute every row, with no fallback to
the Haskell implementation. The interpreter driver must be linked with the
test tracing runtime, as used by `Backends.hs`, to check ordered effects and
remaining input as well as stdout.

The matrix defaults to a 60-second execution budget. When either native MLF
driver is configured, set `MLF_BOOTSTRAP_TIMEOUT_SECONDS=1800` for the full
candidate matrix: an interpreter written in MLF needs a larger budget on these
workloads. This explicit positive-integer setting applies only to candidate
interpreter execution and candidate LLVM emission. It requires a configured
driver, is printed in the test log, and leaves the ordinary backend and
toolchain budgets unchanged. The harness performs no automatic retries or
fallbacks; an actual timeout fails its matrix row and coverage audit. The test
executables use GHC's threaded runtime so process waits remain interruptible.

The compiler stages and native test drivers use `--emit-llvm-gc` and a runtime
compiled with both `MLF_USE_BDWGC` and `MLF_COMPACT_BDWGC`. BDWGC owns tracing,
so values and environments omit the ordinary collector's 16-byte header.
Their public payload offsets are 16 bytes smaller; saturated constructors of
arity three or greater store their fields inline from byte 24. An ABI symbol in each
LLVM entry rejects an incompatible runtime during linking. Ordinary
`--emit-llvm` output retains the standard layout and ordinary pooled runtime.
The fixed-point gate checks both layouts against both seed and native emission,
including negative link tests, and exercises ordinary, standard BDWGC, compact
BDWGC, and both collector debug profiles with independent C allocation probes.

The complete backend matrix can also exercise compact generated programs:
set `MLF_LLVM_TEST_ABI=compact-gc`, `MLF_LLVM_TEST_CFLAGS` to BDWGC's include
flags, and `MLF_LLVM_TEST_LIBS` to its linker flags, then run
`cabal test backend-tests -j1 --test-show-details=direct`. Every row still runs
both the interpreter and LLVM backend; only the generated native layout changes.

To measure the native stage 1 compiler against the nine Benchmarks Game
workloads after completing the bootstrap gate, select its executable explicitly:

```sh
cabal bench compiler-bench -j1 --benchmark-options='--emlf dist-newstyle/bootstrap/emlf-stage1 --runs 5 --max-compile-ratio 5 --max-runtime-ratio 2'
```

Run this after other compiler and test jobs finish. Each measured MLF build
uses the native compiler for checked source-to-LLVM compilation, overlaps that
phase with fresh C runtime compilation, and then compiles and links the LLVM.
No runtime object or emitted LLVM is reused between samples. Generated workload
executables use the ordinary runtime; the compiler process itself uses compact
BDWGC. The [benchmark methodology](../benchmarks/README.md) describes timing,
correctness oracles, resource accounting, and per-workload limits. The
[results](../benchmarks/RESULTS.md) distinguish native stage 1 measurements from
earlier Haskell seed measurements.

The [2026-10-13 validation record](../benchmarks/results/2026-10-13-stage1-validation.json)
archives a passing stage 2/3 fixed point, all 7,023 parity cases, 26 port fixtures
on both backends, and three complete matrices of 468 rows on both backends.
Those matrices cover standard generated programs, compact generated programs
under an 8 MiB initial heap, and both native MLF drivers built by stage 1.
The same stage 1 executable passes all nine Benchmarks Game workloads with
five samples and the 5x compilation / 2x runtime limits; its identity and
benchmark report hash are included in the validation record.
