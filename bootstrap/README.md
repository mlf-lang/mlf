# MLF compiler written in MLF

`Main.emlf` is the compiler entry point. `Bootstrap/` implements parsing,
layout, modules, classes, graph inference, evidence, elaboration, independent
xMLF checking, the interpreter, and LLVM generation in ordinary MLF. The
Haskell compiler and historical Haskell/Python bootstrap harnesses have been
removed. Bootstrap with an installed native MLF release; no GHC, Cabal, or
Python is needed.

From the repository root, follow the two native generations in the
[root build instructions](../README.md#build-and-run). Clang/LLVM, GMP,
`pkg-config`, and a local BDWGC installation are the native dependencies.
`scripts/bootstrap-package.sh` builds the initial MLF package manager;
subsequent builds and tests use `./mlfpkg`. The manager never downloads a
compiler or native library. Set `MLF_GC_PREFIX` to your BDWGC installation,
or provide its `bdw-gc.pc` metadata. Compiler-profile builds use compact
BDWGC allocation; ordinary generated programs retain their runtime profile.
See [RUNTIME.txt](RUNTIME.txt) for the host primitives and allocator contract.

Keep the input compiler and manager outside the candidate output directory:

```sh
export MLF_COMPILER=/absolute/path/to/native-stage1/bin/emlf
export MLF_PACKAGE_MANAGER=/absolute/path/to/native-stage1/bin/mlfpkg
export MLF_GC_PREFIX=/absolute/path/to/bdwgc-install
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 build
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 test
```

The six root groups are `unit`, `packages`, `self-host`, `parity`,
`backends`, and `port`. The self-host gate makes a fresh next-stage build
and compares LLVM for a fixed point. Parity checks 7,086 prescribed outcomes
using frozen oracle data and an independent MLF target checker. Backend and
port fixtures run on the interpreter and LLVM, with standard and compact GC
layouts. All source snapshots, commands, hashes, coverage audits, and completion
flags are recorded under `.mlf-build/compiler-tests/`. Individual fixture
timeouts are preserved; large interpreted graph fixtures need substantial RAM
and the full suite uses the longer package timeout shown above.

Port fixtures and their expected output remain in `bootstrap/tests/`. The six
independent graph/inference reference programs live in `tests/Tests/`; the
shared C ABI and transport fixtures live in `tests/native/`. Frozen
Haskell-seed expectations and generated Unicode tables retain their original
provenance and require no Haskell executable. Do not regenerate golden types
from the compiler under test. See [native coverage](../tests/README.md).

Crate compilation persists independently checked declaration SCCs and generated
`.mlfci`/`.mlfco` artifacts. Both compiler and package-manager targets use the
same crate pipeline. Module cycles are accepted within a crate; dependency
crates form a DAG. See [crate compilation](../docs/crate-compilation.md),
[the migration ledger](../docs/crate-migration.md),
[package builds](../docs/package-manager.md), and
[native C/MLF benchmarks](../tools/bench/README.md). Pinned cross-language
benchmark baselines and historical measurements remain unchanged.

[Native release tools](../docs/releases.md) package only a candidate with all
six complete, matching test reports and a fresh self-host build.
