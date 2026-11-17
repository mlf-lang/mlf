# Finite Solver depth-cursor qualification

Exact push branch `perf/depth-cursor-solver-qualification-20261117`; baseline main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. One Ubuntu24.04 job,12min,read-only contents. No main/PR changes, ordinary compiler benchmark or native execution.

33 inputs:17 Haskell homes and16 C/header files. Main SHA256 `813dae8ca0eb99b1c11f38b5f24c892befc5ca01ecd3ae10c47619fa25cfffc4`. Other30 inherited inputs remain byte-identical to the successful Graph CI v3 bundle. Baseline Solver is exact main source; candidate Solver changes only module declaration and Graph import. The inherited Candidate.Graph is the module-renamed frozen version SHA256 `f8f98a2324092bffa3ea3421c8b5c1b02394e532cf5884fc2a7f719a4277e7e7`, not the original unrenamed overlay identity. Graph algorithms are unchanged.

Four groups cover graft, signed IDs, alias, errors-and-reuse. Each mode must produce exactly32 files: per group A/C/hand-written expected graph-error bytes, four complete snapshots and PASS LF. All A=C=expected; all snapshot A/C before/after bytes equal. Exact COMPLETE stdout and empty stderr. COMPLETE alone is not success. Actual compile logs and object/interface sets must show exactly17 homes per fresh O0/O2 build. Source/toolchain/runtime/binary identities are checked before/after; warnings and all failure logs retained.

Snapshots are deliberately fully forced before operations. Arbitrary graph-payload laziness, hidden-stub independent fixtures and captured prepared-fallback transactions remain unqualified. Old29 Graph cases are not rerun. This is finite semantics only, not production/native qualification, timing or performance benefit.

## Unchanged inherited resources
Official GHC9.14.1 archive306812040B, SHA256 `60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841`; installation300s,1GiB per-file,initial disk12GiB. Focused180s,aggregate compile120s,target20s (10s each),AS4GiB,8MiB per-file,host available4GiB/disk4GiB. Jobs1,artifacts <=96MiB excluding toolchain prefix/archive. No retry. Normal proxy/certificate inheritance without logging values; only allowlisted GitHub identity recorded.

Graph run44109098015 exact download succeeded but extraction failed SIGXFSZ under512MiB; original failure retained. Historical largest installed file629328882B and peak disk8008471877B justified the corrected installation-only1GiB/12GiB policy inherited here. No old failure is reclassified. Process-group cleanup is retained, not a global/ECHILD claim.

Preparation was static only. One metadata assertion initially confused original unrenamed Graph overlay SHA with inherited module-renamed Candidate.Graph SHA; preparation stopped before harness completion. Corrected by checking every inherited source against its original source-pin record, with zero Graph-byte changes. No compiler, target, workflow or publication was executed during preparation.

## V2 preparation record
The initial v1 metadata assertion stopped after partial source copying. Before the separate-directory instruction arrived, a follow-up preparation completed v1 and documented the assertion failure. That completed v1 state remains preserved without further modification. V2 is a new copy with explicit independently checked overlay and module-renamed Graph identities; the sole module-declaration transformation was verified byte-for-byte. No source, contract, execution budget, harness or workflow changed from completed v1. This is preparation evidence, not execution success.
