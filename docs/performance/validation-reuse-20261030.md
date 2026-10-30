# Reuse successful generation validation, 2026-10-30

The private crate compiler used to validate the same initial graph twice: once
inside `Constraint.generateProgram`, then again at `CrateSession.prepareGraph`.
It now enters `solveGenerated` immediately after successful generation and
retains the remaining admission checks and the complete solving/final-check
continuation. Arbitrary constraints still enter the original validation path.
The [boundary controls](../../tools/performance/validation-reuse/README.md)
describe the semantic argument and the independent previous-source reference.

This refactoring makes no performance claim. The preceding frozen discovery
window used ordinary GHC 9.14.1 `-O2` binaries with ABBA then BAAB order. Its
pooled block-log wall point improvement was **0.2478%**, with block effects
**−0.3820%** and **+0.8737%**. It failed the predeclared requirement of at least
0.5% with both blocks positive. That decision and all eight samples are retained;
there is no added confirmation window or retrospective acceptance-rule change.
The auxiliary child-CPU point improvement was 0.8712%, which does not replace
the wall criterion. Integration is for removal of redundant work after a
separate decision to accept that scope. Statistical noninferiority was not
established by this small window.

The integrated implementation differs from the screened implementation only in
comment wording and layout. Its ordinary producer is built and authenticated
from the actual integration checkout. The generated Prelude and other shared
source modules are unchanged. The controls reconstruct the entire previous
CrateSession owner to its existing frozen hash; historical oracle bodies and
expected results are not edited.

The fixed workload is 15 mlf-crates modules, **711 fresh / 0 reused** inference
groups, with fixed dependencies reused. Raw `.mlfci` and `.mlfco` bytes and the
ordered group inventory are compared with the independently qualified
pre-candidate reference. That reference is not represented as a newly rebuilt
original P3; the original P3 semantic oracles have their separate role. The
single integration execution is qualification, not another performance sample.

The actual ordinary integration producer passed the complete retained P1/P2/P3,
A1, F1, Map and query-encoding controls, the full C4 gate (including its nine
before/after file comparisons and builtin admission), and the new generated
boundary controls. The final target execution passed **711 fresh / 0 reused**,
exact ordered group identity/member comparison, and raw `.mlfci`/`.mlfco`
comparison. No historical oracle body or expected result was changed.
The [evidence summary](validation-reuse-20261030.json) records source and binary
identities, gate receipt hashes, all eight original screen samples, the failed
screen decision and the separate integration qualification.

CI now runs the new boundary gate on its ordinary O2 leg and retains its logs,
receipts and test sources on failure. YAML parsing and the new step's selection,
guards and artifact retention checks passed locally. The complete existing CI
policy script could not pass on this host: macOS Bash 3 rejects its existing
empty `suite_args` array under `nounset`. The unchanged parent workflow and this
workflow produce byte-identical failure stderr; this is not counted as a passed
full policy check.

A separate, already completed diagnostic census on the preceding production
baseline recorded 70,621 private local projections, 58 ordinary public
projections, 505 prepared fallback projections and eight generation flushes.
There were 176,557 elaboration edges, all handled by alpha-equality or direct
proof, with zero witness fallbacks. These are diagnostic observations, not CPU
shares or speedup evidence. The count probes and their optimizer changes are
absent from the integrated producer.

This work does not claim a new whole-compiler/GHC ratio or a remeasurement of
the ten native benchmark-game workloads.
