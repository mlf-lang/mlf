# Port test performance

The 0.2.0 work preserves every retained port assertion, all six independent
reference programs, both execution backends and both runtime layouts. The
[coverage audit](../tests/coverage-overlap.md) records the exact consolidations.

## Interpreter execution

Two changes remove repeated allocation in `Bootstrap.Runtime`: primitive arities
come from a constant exhaustive match, and syntactically direct primitive calls
construct their lazy argument list once. All 82 arities are checked against the
unchanged type signatures. Controls exercise partial application, unused lazy
branches, error order, and primitive results that are themselves functions.
Overapplication still follows ordinary evaluation.

The following serial observations use the same frozen checked input, native
compiler, runtime objects and Clang `-O2` configuration on macOS ARM64. Every
command exited successfully with identical stdout and IO trace.

| Input and initial heap | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| GraphDense, 512 MiB | 101.18–101.93 s | 76.55–76.90 s | about 25% |
| SolverReuse, 512 MiB | 437.74 s | 328.88 s | 24.9% |
| StateTypes, 512 MiB | 272.81 s | 206.06 s | 24.5% |
| GraphDense, 8 MiB | 136.47 s | 101.14 s | 25.9% |

GraphDense includes baseline bookends and an arity-only/direct-call ABBA
comparison. The other rows are single observations, not statistical bounds.
StateTypes peak process RSS decreased from 4.38 GB to 3.30 GB. SolverReuse still
used about 6.5 GB with the existing free-space divisor of one.

These timings measure interpreter execution of unchanged checked targets, not
the complete port command or a released compiler's benchmark performance.
The [machine-readable record](port-test-performance.json) contains command exit
status, wall time, CPU time, peak process RSS, input and binary hashes, source
hashes and the completed regression controls.

Bounded environment indexing was rejected: its isolated GraphDense run took
128.54 s. A version that allocated a lazy ordinary-application fallback also
lost to arity-only execution. Earlier concurrent pilots, and an initial
include-path experiment that accidentally rebuilt the baseline, are retained
as diagnostics and excluded from these performance claims.

## Hosts with limited memory

Increasing the collector's free-space divisor trades CPU time for memory. A
separate serial SolverReuse comparison retained the same optimized executable,
input, 512 MiB initial heap and exact output/trace checks:

| Free-space divisor | Wall time | Peak process RSS |
| --- | ---: | ---: |
| 1, default | 328.88 s | 6.48 GB |
| 2 | 455.84 s | 4.44 GB |
| 4 | 621.53 s | 3.42 GB |

The direct native test command keeps divisor 1 by default. The release
`native-ci.sh port` wrapper selects divisor 4 only on hosts with at most 8 GiB
of physical memory, to leave room for the parent test process and operating
system. This is a memory tradeoff, not an isolated CPU speedup. Larger hosts keep
divisor 1. An explicit `MLF_TEST_MATRIX_GC_DIVISOR=1`, `2` or `4` overrides the
selection. Both runtime layouts retain their prescribed initial heaps; the
native verification report records the actual initial heap and divisor for
each matrix. There is no maximum-heap cap or reduced fixture coverage.

## Building test entries

The former test library contained all 77 test modules. Even port qualification
first inferred unrelated unit and backend cases. The manifest now keeps eight
common support modules and gives each executable its actual remaining imports.
Port plus its reference executable compiles 21 test modules including the two
entries, instead of 79. Every original module remains reachable through the
unchanged test entrypoints.

With the coverage consolidations and runtime changes held constant, serial
fresh-cache builds of `references` and `port` took **1,311.03 s before** and
**710.99 s after**, a **45.8% wall-time reduction**. CPU time decreased from
1,255.49 s to 670.43 s. Peak process RSS was 3.34 GB before and 3.46 GB after;
this change reduces build work, not peak compiler memory.

The two source copies differ only in `tests/mlf-package.json`, use the same
compiler and manager, and each start with an empty build directory. All six
reference executables' selections ran from both builds and matched the
unchanged expected outputs. These measurements cover building the two test
entries, including their library dependencies; they exclude the subsequent
fixture matrix. They are one serial pair rather than a statistical estimate.
