# W1 process readiness — fixed nine-leg confirmation

**Accepted by the predeclared criteria on the frozen baseline below. The ≤3× goal is not met.**

Production base: `a700a2893c3ff857faa775af87c0ecd060e11e30`. Two files, +34/-1: optional Linux owned-child readiness fd shortens the original 10 ms pause. `waitpid` remains the sole status/reaping authority; timeout checks, group cleanup and unavailable/error fallback are preserved.

| Leg | Side | Compiler wall (s) | Reaped-child user (s) | System (s) |
|---:|---|---:|---:|---:|
| 1 | ghc | 8.120156844 | 7.962880 | 0.171908 |
| 2 | base | 82.258378977 | 72.978365 | 6.357666 |
| 3 | W1 | 79.367313963 | 73.401441 | 6.202089 |
| 4 | W1 | 80.028038526 | 73.919327 | 6.314010 |
| 5 | ghc | 8.431455696 | 8.307063 | 0.147768 |
| 6 | base | 82.554496615 | 73.441999 | 5.948670 |
| 7 | base | 85.481505985 | 75.268166 | 7.583887 |
| 8 | W1 | 81.903208187 | 75.570533 | 6.527690 |
| 9 | ghc | 8.233948303 | 8.108671 | 0.151036 |

Medians: GHC **8.233948303 s**, base **82.554496615 s**, W1 **80.028038526 s**. Wall improvement **3.060351880%**, with W1 faster in all three rounds. Reaped-child CPU median increased from **79.390669 s** to **80.233337 s** (**+1.061419447%**), within the predeclared ≤2% tolerance; this is **not CPU acceleration**. W1/GHC is **9.719278720×**, not ≤3×.

All nine prescribed legs completed without replacement or interruption; six MLF legs each inferred 544 groups and reused 0, with exact checked bytes and ordered group projection. All nine resource guards terminated successfully with empty owned descendants. Three samples per side and the narrowly passed wall threshold do not establish broad statistical or cross-host generality.

Qualification includes the independently frozen transport, mocked fault/call-order, actual descendant-cleanup, eligible-GHC fd lifetime, unsupported-kernel fallback and symbol controls; official O2 producer and 7 independently checked / 0 reused dependency objects plus corrupted-object rejection. F1/P123/A1 gates completed under their original guards. Two earlier exact qualification outer sessions were interrupted; their guards remain explicitly incomplete. Successfully finished exact-2 component exit codes/logs/input hashes and receipts were reauthenticated, and the missing final plans plus end authentication completed under a new terminal exact-tail guard. This is composite recovery, not a claim of one uninterrupted exact campaign.

Method limits: plain GHC O2 .hi/.o versus checked xMLF and query caches; cold target is not cold OS caches. Reaped-child CPU is separate from wall; guard RSS includes setup and postchecks. Linux readiness is the only fast path; no new Mac performance claim or native 74-module bootstrap claim. Raw private evidence is retained separately, not public Git metadata.
