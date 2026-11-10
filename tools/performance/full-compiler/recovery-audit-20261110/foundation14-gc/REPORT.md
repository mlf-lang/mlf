# Foundation14 baseline managed-heap diagnostic

Completed one separately admitted SETUP and one Q/D qualification on the original f9 baseline. The target was all 14 foundation modules (173,594 source bytes), with a fresh builtin and 475 fresh groups per leg, zero reuse. This is a smaller completed control, not inference11 or full90.

## Result

The single diagnostic allocated 60,546,927,152 managed-heap bytes (about 60.55 GB), copied 4,299,126,432 bytes during GC, and reported maximum sampled residency 36,197,520 bytes across 59 major-GC samples. Raw RTS memory-in-use was 105 MiB.

GC took 5.413 CPU seconds / 5.544 elapsed seconds; mutator time was 26.817 / 27.375 seconds, and RTS total was 32.230 / 32.921 seconds. GC is about 16.8% of those reported total times; productivity was 83.2%. This shows high transient managed allocation in this foundation workload, but does not identify an unnecessary feature or attribute costs to a particular check, witness or serialization pass. Most recorded time was mutator time. If non-GC work stayed unchanged, eliminating only the measured GC time would give about 1.20× for this recorded run. That is an arithmetic upper bound for GC alone, not an achievable optimization claim or a full90/GHC extrapolation.

## Qualification and safeguards

- Ordinary Q: 32.938978249s; one-use diagnostic D: 34.016558770s. These are diagnostic qualification durations, not a throughput comparison or speedup claim.
- Both legs passed 475-fresh/zero-reuse, all 14 interface owners and builtin identity/path, query locks and complete ordered query-JSON checks. All three raw .mlfci/.mlfco/.queries files matched exactly.
- Fresh builtin qualification, both original-command C object reconstructions with raw equality, original emlf Main and exact 94 non-Main objects, literal RTS-argument transport and source/runtime input pins passed. Only compiled-in ordinary -s statistics was added, retaining -rtsopts=ignoreAll.
- SETUP completed 94.322s under 120s; QD completed 98.849s under 420s, each target below 180s. Original 5 GiB RSS / 6 GiB AS / 5 GiB free disk / 3 GiB host-available / 4 GiB output guards stayed in force. No limit violation or observed surviving descendant; all locks reacquired.

## Scope and reporting caveats

Ordinary GHC RTS statistics cover its managed heap, not C malloc, BDWGC or other native allocations. Residency is sampled liveness, not peak RSS or total allocation. Q is a new equivalence oracle for adding statistics, not historical B2/C01 raw equality or independent proof of baseline correctness; the separately qualified original producer supplies the semantic controls.

The frozen decoder incorrectly normalizes raw MiB to MB. This report and summary use the raw 105 MiB token; byte/time fields are unaffected. The raw literal %GC line says 0.0% despite nonzero GC times and 83.2% productivity, so the 16.8% share is explicitly derived from reported GC/Total times. The cause of the anomalous literal line is unknown.

Inference11 Q/D, full90 completion, feature-removal A/B, fixed-point/native generation, F3 integration and repeated throughput measurements were not run here. The failed 300s inference11 prerequisite cohort and first foundation preflight failure remain preserved; no partial dependency was reused. No heavy work followed QD.

## Evidence

summary.json contains the checked outcomes and exact timings. source-receipt-manifest.json records exact source/controller/plan/receipt hashes. diagnostic-rts.sanitized.txt preserves every statistics line verbatim, replacing only the private cohort-root prefix in the command banner with <COHORT_ROOT>. The exact original remains retained locally, SHA256 ddab3f617d14cc9e74cc5cca27de45f5f84c4f184efd9b72f2c503ab256e4912. The separate tiny transport-control report is sanitized the same way and individually hashed. This packet is archived with the coordinator recovery checkpoint.
