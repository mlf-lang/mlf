# Full-CLI bounded late profile, 2026-11-10

This is a completed **diagnostic prefix**, not a completed compiler build or an
ordinary performance sample. Production source remains
`f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`; the target is the same frozen 90-module
compiler closure as the adjacent [B0 checkpoint](../baseline-20261110/README.md).
Native self-host A/B and fixed-point campaigns were not run.

## What actually ran

1. GHC 9.14.1 rebuilt all 90 shared modules, four host modules and the private Main
   with `-O2 -prof -fprof-late`. Both C transports were privately rebuilt with
   their original flags. Build completed in 320.047 s, peak tree RSS 2.115 GB, inside
   the original 600 s budget. Exact 95 home-module provenance and 1013 input / 193
   output pins were checked.
2. All six controls passed in 13.585 s, peak 110 MB: normal tiny-crate checked-byte
   equality; internal timeout with a real nonzero JSON profile; actual compiler
   POSIX-lock ownership and post-cancellation reacquisition; actual active child
   identity/ancestry and cleanup; rejection of ordinary exit 124; rejection of a
   missing/invalid report after hard kill. No controls were skipped or retried.
3. One fresh full target ran through the original CLI and fixed dependencies.
   It stopped by the private 90 s timeout, exit 124, with matching incomplete-action
   outcome and a valid fresh report. The outer 120 s guard completed normally at
   98.475 s; the compiler command took 90.497 s. Peak tree RSS 1.784 GB. Descendants
   were gone and both serialization locks were independently reacquired.

The exact source files used are archived under `source/`, with their SHA256s in
`source-sha256.json`. `summary.json` records small safe evidence and original
receipt/report hashes. Raw profiles, full environment-dependent receipts, binary
and objects remain local and **are not published here**. Hashes do not imply that
those files can be downloaded or recovered from Git.

## Findings that can guide the next change

The report contains 89395 ticks at 1000 microseconds, reported time 89.39 s and
91.303 GB cumulative allocation. Self ticks and allocation totals reconcile
exactly with the report. GC accounts for 20.37% of samples; profiling overhead
accounts for 6.77%, so this is materially different from an ordinary run.

Leading compiler self costs include IntMap's specialized lookup 5.09%, Graph's
`readDense` 2.56%, IntMap `node` 1.81%, Parsec's worker `pBind` 1.72%, Map `balance`
1.63% and Bitstream's checksum worker 1.61%. `readDense` alone is attributed
6.298 GB allocation; it is a one-line `readSTArray` wrapper in Graph.hs.

Inherited context points to `Constraint.solvePrepared` 34.34% of samples and
45.38% allocation, then `Graph.Solver.instantiateClosedPrepared` 25.93%/32.42%,
`unifyPreparedFallback` 16.24%/22.84%, `Graph.unify` 12.11%/21.58%, and
`denseValidation` 9.51%/17.03%. Dense access is reached repeatedly through graph
validation/rebinding; prominent map lookups are under prepared-fallback component
canonicalization. Parsing separately accounts for 12.28%/12.39% under
`parseModuleWithProfileInPackage`. These inherited rows overlap: do not add them.

These are candidate directions, not demonstrated speedups. The bounded profiled
prefix has no complete checked oracle. Late cost centres preserve prior Core
optimization but change ABI, allocations and runtime behavior. Inlining can
charge helpers to callers; safe FFI, external children and waits are not a complete
Haskell CPU partition. Do not convert these shares to ordinary wall savings.

## Recovery and guarded entry

Read the adjacent B0 recovery instructions first. Restore the frozen source,
official toolchain and ordinary producer/setup before using this archive. The
scripts intentionally contain this run's exact absolute inputs and receipt hashes;
a fresh reconstruction with new receipt timestamps/hashes requires a newly
reviewed input identity. Do not weaken authentication to reuse the old label.

For the recorded environment, restore these four files into the sibling directory
`compiler-cost-centre-draft-20261110`, alongside `compiler-baseline-20261110` and
`compiler-toolchain-20261110`. This is their original layout; do not invoke the
archived copy in place. Only separately admitted future windows may run:

```
bash run-phase.sh build NEW_BUILD_GUARD_ROOT
bash run-phase.sh controls NEW_CONTROLS_GUARD_ROOT --build BUILD_GUARD_ROOT/work
bash run-phase.sh target NEW_TARGET_GUARD_ROOT --build BUILD_GUARD_ROOT/work --controls CONTROLS_GUARD_ROOT/work
```

The phases are not an automatic chain. The real target uses a one-use claim and
must not be repeated merely because its output was inconvenient or later lost.
Each next phase requires both the prior controller receipt and outer guard to be
complete. Build 600 s, controls 60 s total / 15 s per child, target 90 s internal / 120 s outer;
6 GiB per-process address-space, 5 GiB tree RSS, 3 GiB available-memory floor, 5 GiB disk
floor and 4 GiB output ceiling. The shared external flock and producer internal lock
remain mandatory. Masked foreign calls/cleanup can postpone async timeout; if the
outer guard wins or no valid report is written, retain failure and stop.
