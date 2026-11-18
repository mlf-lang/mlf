# Canonical resolution memo stopped after paired regression

Decision: STOP. Do not merge or rerun this exact candidate.

Run44216240882 at86746e6cb9cbd2778de2b979ee6decd1841631e0 completed the fixed main
Foundation15 A1 C1 C2 A2 screen. A1/A2:19.9850/20.0767seconds;
C1/C2:21.8368/21.8887seconds. C/A geometric wall ratio1.09145455, about9.15% slower.
Individual paired ratios1.09265627 and1.09025416; peak RSS ratios1.00604662 and
1.00818666. This is a two-pair descriptive screen, not a broad benchmark or GHC
comparison. Qualification and seed calls were not counted as samples.

Every call produced identical complete CI/CO/query bytes and all1653 query-result
files (1656compiler artifacts per call). All install/build/screen receipts finished
and outer cleanup was terminal without survivors. Candidate's finite O0/O2 gate
had passed24controls and96sidecar equality before screen launch.

Archive14388628377 ZIP SHA256:
77368832edbf4f1225b4b87090599b8f00e39b81523190a821896817f2c5983c
ZIP CRC passes.10152present inventory files match lengths/SHA256. Exactly7empty
query-cache/.lock files listed by the10159-entry inventory were omitted by the
historical upload action's hidden-file default. They were not reconstructed;
archive_complete=false. All compiler outputs and measurement/cleanup receipts
are present. This omission does not turn the regression into a speedup.

No production main change or native A/B work. Extra memo allocation/lookups are a
plausible cause, not separately measured attribution. Return to other justified
bottlenecks; do not generalize finite memo correctness into cross-call reuse.
