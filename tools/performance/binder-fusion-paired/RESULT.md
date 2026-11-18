# Binder fusion: weak continuation signal, not a proven speedup

Exact main baseline fc300bc9; candidate/screen checkpoint 773797dab9e685da522a3e0fde02dce2e573a148. Actual paired GitHub run44219723394 completed all build, qualification, artifact, sampling and cleanup gates.

A1 19.835141313 s, C1 19.738686988 s; A2 19.855434012 s, C2 19.655606811 s. Pair C/A ratios 0.9951372000 and 0.9899358936. Geometric C/A 0.9925331397, a descriptive 0.7467% reduction. RSS ratios 0.9856624532/0.9868463454. Predeclared screen decision CONTINUE. Only two pairs and sub-1% difference: not statistical evidence of stable improvement, no merge qualification, no GHC parity claim.

All 1656 compiler artifacts per call equal across six qualification/sample calls. Fixed toolchain and build/source postchecks passed. ZIP SHA256 7bd060a9fb7c2287dafcfdd378dd02b2f23144cb5cd9402d81f20ee0141c9be0; artifact14390526581; all10159 inventory files hash-verified, no omissions (hidden locks included), CRC passed and terminal cleanup complete.

Finite run44219094415 at8879a04eb63f1578b192218c7c90c9396b8f1d74 passed33 expected graph controls,132 equal sidecars O0/O2, four bounded alias-cycle controls and cleanup. ZIP00f59fcbb1e00a3e6ab2fc914750f0f4482d5d886b9c1804dcd5b40b71bb3784, all321inventory files verified. First run44218625636 failed an obsolete branch admission guard before installation; retained rather than counted as a compiler failure. Guard was corrected and positive/negative controls added.

The candidate removes one private dense binder-check/descendant-load traversal, not any semantic validation and not a duplicate node lookup. Original public helpers remain; no memo or depth-cursor code is stacked. Main unchanged, native A/B fixed point paused. Next: preserve this weak screen and require stronger predeclared replication and representative workloads before promotion. Do not pool previous runners' timings.
