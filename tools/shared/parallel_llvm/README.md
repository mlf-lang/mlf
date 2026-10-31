# Optional parallel LLVM compilation

A tiny native launcher sends C, link, version and unsupported invocations straight
to ordinary Clang. Selected IR invocations use native orchestration with no Python
startup. That driver parses a fresh complete LLVM module with LLVM's API, partitions its
functions, runs up to four complete ordinary Clang `-O2` compilations, and uses
ordinary Clang's relocatable linker to combine the new objects into the requested
object. The caller then performs its ordinary executable link. It caches no
LLVM or native user-program output and requires no language-library native ABI.

Build against one installed LLVM distribution:

```
python3 tools/shared/parallel_llvm/build.py \
  --llvm-config /path/to/llvm-config --clang /path/to/clang \
  --output .mlf-build/parallel-llvm-install --jobs 4
```

The printed `clang-parallel` path can serve as the LLVM compilation driver.
Only `-O2 -c [ -Wno-override-module ] INPUT.ll -o OUTPUT` is partitioned; other
argument combinations execute the configured ordinary Clang unchanged. Unsupported
LLVM features fail closed. The public `emlf --emit-llvm` output is unchanged.
The driver produces `OUTPUT.parallel.json`, including fresh source/output hashes,
actual commands, elapsed stages and completion status. Installation provenance
is recorded in `receipt.json`; authenticate that receipt before selecting the
driver with `build.py --verify INSTALL_DIRECTORY`. Verification stays outside
timed compilation. `driver.py` remains a reference implementation for cleanup
controls; the installed launcher and orchestrator are native binaries. Timing must include driver startup, source parsing, splitting, all Clang
jobs, relocatable combination, and the outer final link. Configured parallel work uses more CPU concurrency than a single C compiler
process; report its actual job count explicitly. The default is four; larger
counts require separate compile/runtime validation. Tool first-launch overhead
is distinct from fresh program compilation; retain cold-start samples and use
the same declared tool warm-up policy across benchmark lanes.

The splitter uses LLVM parsing, SCCs, bounded merging of single-user components,
`CloneModule`, and LLVM verification. Functions used only within their partition
retain local linkage. Direct-only `alwaysinline` helpers may be copied locally;
address-taken functions and mutable globals are never duplicated. Globals follow
their users where possible. Cut symbols receive a content-derived namespace and
hidden linkage. User datatype tags and all program identities remain those of
the original full module. Inline assembly, aliases, ifuncs, comdats and thread-local
global definitions are rejected by this initial contract.

This is an optional parallel orchestration route, not one ordinary Clang
invocation. Partition boundaries can change ordinary interprocedural optimization
and runtime performance. Verify exact program output and compare full-input
runtime in the same cohort against the established compiler before enabling it.
No optimization level or Clang pass pipeline is reduced.
