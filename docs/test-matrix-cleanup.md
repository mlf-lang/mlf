# Native port and test matrix cleanup

All six native test groups passed on the immutable source snapshot. The actual
serial, locked root test command exited 0. Changes are uncommitted and unpublished.
The [machine record](test-matrix-cleanup.json) binds the 3207-file source inventory,
actual compiler/manager identities, completed group reports and selection review.
The compiler is byte-identical to the preceding accepted R6 compiler;
the manager was rebuilt from the changed orchestration sources.

| Group | Previous R6 | Current | Observed change |
| --- | ---: | ---: | ---: |
| unit | 14m 40.8s | 14m 31.6s | -1.0% |
| packages | 3m 44.2s | 3m 42.9s | -0.6% |
| self-host | 8m 58.7s | 8m 47.6s | -2.0% |
| parity | 8m 38.5s | 8m 33.2s | -1.0% |
| backends | 20m 16.6s | 19m 17.3s | -4.9% |
| port | 60m 49.9s | 23m 35.3s | -61.2% |
| Complete serial test command | 117m 10.1s | 78m 29.9s | -33.0% |

Initial tool building took 5m 32.2s separately.
Group timers include their target builds, preparation and execution. This is one
observation per revision on the same M1 Max / 32 GiB host, using genuine verified
shared artifacts. It is not an empty-cache controlled benchmark, and unrelated
group fluctuations should not be attributed to the matrix reductions alone.

Port retained all 25 fixtures and both native layouts: 50 LLVM executions and
zero outer interpreter executions. Only LLVMDriver was built for port. All 25
checked target hashes exactly match R6 and both layouts; the unchanged target
bytes and expected outputs isolate the removal of outer interpretation from
fixture input changes. Independent target/type checks, serialized round trips,
six reference programs and regenerated inference-source equality remain. Native
port child executions took 24.8 seconds;
the remaining 1390.5 seconds include preparation,
references, LLVM emission/linking and supervision, not pure compilation.
Preparation recorded 0 hits and 25 misses.

Removing outer interpretation deliberately gives up compiler-scale interpreter
stress coverage. Focused interpreter semantics remain in RuntimeCases/StateRuntime
compiled through LLVM, the 575-row differential backend matrix in both layouts,
80 CLI parity interpreter executions and package integration. Native GC layouts
and their complete port executions remain independent.

The [coverage decisions](../tests/coverage-overlap.md#subsequent-matrix-cleanup)
record the smaller graph/projection matrices and exact-input deduplication.
Small structures retain modes, renamings, error paths and independent oracles;
selected large cases retain depth, balance, identity and jump-level regressions.
The reduced cross-products are intentional coverage selections, not a claim that
every previous concrete input still executes. Known stack, GC churn, spill,
capture, ST-budget and counter regressions remain unchanged.

The 686 unit methods, 58 harness methods, 6712 logical HM cases / 6703 executions,
43 Figure 12 labels / 41 executions and 36 controls passed. Resolver/integration
retain 18/29 checks. Parity retains 7086 rows / 7075 primary compilations and 160
runtime executions. Self-host used a genuinely fresh next stage and reproduced
LLVM and native bytes. Backend and parity interpreter coverage were retained.

The [individual execution timings](test-matrix-cleanup-execution-times.json)
contain 2350 checked backend paths and 2314 measured child executions. The 36
LLVM target-rejection paths have diagnostics and null execution timers; removed
port interpreter paths have no fabricated zero timers or execution records.
Unit assertions are measured within their group, not individually instrumented.
The port matrix audit rejects missing, duplicate, wrong-count and two-backend
summaries. The release profile helper passed 10 positive/negative controls
using labeled projections of the actual completed report, including incorrect
backend count/names. Those derived records are explicitly not new qualifications.

All 2716 protected historical/oracle paths and all 72 benchmark
pins match the preceding snapshot. No GHC, Cabal or Python invocation occurred.
The initial R1 attempt stopped before executing tests because a new recursive
test helper needed an explicit closed signature. Its failed record is retained;
R2 passed unit/packages/self-host/parity and the standard backend matrix, then
stopped at compact row 86 when the unchanged native supervisor child exited 71
before opening output files. The exact case replay and 2000 diagnostic launches
passed. The OS cause remains unconfirmed. No launch check was weakened and no
failed matrix was qualified. R3 repeats the complete gate from the same code
(with documentation corrections) and supplies the completed results above.
The preceding [R6 evidence](shared-test-artifacts.md) remains unchanged. No new
Windows/Linux execution, release publication or benchmark performance rerun is claimed.
