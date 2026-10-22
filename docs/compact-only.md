# Compact-GC native layout

The native compiler and runtime now use one layout: compact BDWGC. The repository
has no target requiring the previous no-BDWGC allocator. Compiler/package-manager
binaries and release bootstraps already used compact-GC; remaining dependencies
were default LLVM emission, ordinary package targets, benchmark linking, SDK
helpers and duplicate native qualification matrices. These callers now select
and link the same ABI.

The standard implementation's 16-byte object header, pooled allocation,
IO-boundary mark/sweep collector, LLVM header-offset selector and separate ABI
guard have been removed. Small integers/booleans/nullary data remain immediate;
heap values, environments and constructors use the existing compact offsets.
BDWGC collects during pure evaluation. GMP, BDWGC and libm are required for all
native builds. `GC_DEBUG`, allocation auditing, small heaps, disabled interior
pointers, incremental collection and semantic regression coverage remain.

`--emit-llvm`, `--xmlf-to-llvm[-io]` and `--crate-to-llvm` emit compact-GC.
Their existing `-gc` CLI spellings remain aliases. Package profiles default to
`compact-gc`; `compiler` remains a compatibility alias. An explicit `standard`
manifest profile is rejected. Code generation cache keys identify the new fixed
ABI and format, preventing reuse of the former selectable-layout cache entries.
Old standard LLVM/object files require regeneration; their ABI guard fails to
link against the new runtime. This audit establishes repository dependencies,
not the absence of external users of that old ABI.

Both execution backends still execute the 575-row differential matrix. All 25 port
fixtures still execute through LLVM with independent target/serialization checks,
six reference programs and generated inference-source equality. Removing the
second native layout removes a repeated representation pass; interpreter
semantics and the independent oracles remain. CI/release assembly takes six
qualification groups and a single port report. Windows SDK linking includes
BDWGC and copies its dependency DLLs with conflict checks.

The benchmark runner uses compact-GC for both candidate and baseline compilers;
the baseline must support the historical `-gc` spelling. C flags, workload sources,
check sizes, pins, performance limits and historical measurements are preserved.
New measurements belong to the compact-GC comparison series. Prior two-layout
qualification and timing reports describe their original snapshots unchanged.

All six native root groups passed the actual serial locked test command on the
immutable core snapshot. Its exact compiler/runtime/package/test inputs match
the final 3209-file snapshot; only the optional standalone LLVM benchmark
helper, its configurator and documentation changed afterwards. These three
paths received a fresh native helper build and full nine-workload validation;
the machine record links the input-hash bridge without relabelling core reports.
The fresh next-stage compiler reproduced both
LLVM and native bytes. The [machine record](compact-only.json) binds source and
actual tool hashes, group reports, benchmark results and compatibility controls.

| Group | Previous two-layout run | Compact-GC only |
| --- | ---: | ---: |
| unit | 14m 31.6s | 14m 21.6s |
| packages | 3m 42.9s | 3m 42.6s |
| self-host | 8m 47.6s | 8m 46.3s |
| parity | 8m 33.2s | 8m 33.1s |
| backends | 19m 17.3s | 12m 20.5s |
| port | 23m 35.3s | 21m 6.2s |
| Complete test command | 78m 29.9s | 68m 52.3s |

Initial compiler/manager building took 5m 33.2s separately.
These are single observations on the same M1 Max / 32 GiB host using genuine
content-addressed cache reuse. Compiler, manager and runtime sources changed;
this is not a controlled cold-cache estimate of layout removal alone. The first
unit group includes required root tool builds before the unit supervisor starts:
about 3m 42.4s currently and 3m 44.3s previously. These approximate
spans use the first supervisor process observation in the two-second samples. Group
timers include target builds, preparation and execution. The previous report
remains unchanged.

The [individual execution record](compact-only-execution-times.json) contains
1175 checked backend paths, 1157 measured children, and 18 LLVM rejections before
execution with null timers. There are 575 interpreter executions in backends,
557 native child executions there, and 25 native port launches. Port has no
outer interpreter pass. Unit retains 686 methods, 6712 logical HM cases / 6703
executions, 43 Figure 12 labels / 41 executions and 36 controls. Harness retains
58 methods. Resolver/integration retain 18/29 checks; parity retains all 7086
rows, 7075 source compilations and 160 interpreter/native executions.

All nine pinned benchmark workloads passed with three samples at the unchanged
3x C compilation and 2x C runtime limits, with independent correctness checks
at every prescribed check size. Both MLF compiler variants used compact-GC;
C inputs and flags were preserved. This is a new compact-GC comparison series.
The final n-body compilation ratio was 2.99945x C: it passed, but is very close
to the 3x limit and provides little margin against measurement variation.
The exact report and collector fingerprints are linked by the machine record.
The final benchmark runner and optional LLVM helper were built through the
actual native package manager/build tools on the final immutable snapshot.
Their actual paths, SHA256 and genuine content-addressed cache reuse are
recorded; no compiler identity or build receipt is substituted. All workload
LLVM/runtime objects and executables are fresh. The generic lite backend keeps
O1 register allocation, leaves helpers out of line, runs early CSE before
instruction combining, and disables instruction scheduling. No workload name
or source is inspected to select optimizations. Clang's C baseline flags remain
unchanged. The first compact nine-workload run failed the n-body compile limit
(3.47x); diagnostic O0 variants regressed runtime and were rejected. Original
failed runs and all diagnostic configurations remain under
.mlf-build/compact-only. The final successful run supersedes them for performance
acceptance, without modifying their records. The changed Clang and llc fallback modes also
compile/link/run the compact IO smoke program and reject invalid SSA dominance
through LLVM verification; the single-process helper retains its own input and
optimized-module verification.

Final controls execute source, target and crate CLI aliases, build and run an
explicit compact-GC package, reject an explicit standard package, and verify the
old standard ABI fails to link. The actual release gate expressions pass the
completed single-profile reports and reject 10 damaged/extra-profile
records. These derived controls are not new platform qualifications. Normal,
GC_DEBUG and allocation-audit regressions remain in the native harness.

All 2729 protected historical/oracle paths and all 72 benchmark pins
match the pre-change inventory. No GHC, Cabal or Python command ran. Initial
preflight failures (a removed layout argument in CheckedEmission and an audit
probe without an audit hook) are retained as failed records. The first full run
stopped at a manual LLVM test helper that omitted collector flags; after fixing
it, focused console/table/tree probes and the core suite passed before the
complete final gate. The R2 backend run also exposed standard-only structural
assertions; these now require compact constructor helpers and a single direct
wide-field pointer load. A complete remaining-suffix component check precedes
the final full run. A component launch missing its work-directory environment is
also retained as a setup failure. These are not qualification evidence. Final correctness/performance acceptance uses only the
completed records above. At the time of this local validation, changes were uncommitted and unpublished.
This record predates the 0.3.0 version bump. Its historical source/tool identities
remain unchanged; the cross-platform release workflow separately qualifies the
exact release commit and includes those platform reports in the archives.
Windows and Linux native execution was not repeated in this local environment.
