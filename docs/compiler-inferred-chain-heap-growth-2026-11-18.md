# Live heap and growing costs in inferred dependency chains

At 1,024 functions, the preceding compiler’s complete builds took 453.80 ms for MLF and 693.70 ms for GHC 9.14.1. The OLS slopes were 0.13579 and 0.14900 ms/function. The fitted exponents were 1.0945 and 1.1240, with a paired 95% difference interval of [−0.2508, +0.2182]. Five of six comparisons pass. [Full paired comparison](compiler-inferred-chain-prelude-reads-2026-11-18.md)

## Four-size diagnostics

Eight MLF cost-centre profiles and sixteen live-heap profiles used the preceding compiler source and produced the reference interface, object and LLVM. Eight additional GHC builds on the same source bytes recorded per-pass timers and RTS memory. Their executables produced the 24 expected results. Compiler instrumentation and whole-worker elapsed measurements ran separately.

| Functions | MLF profile allocation (MB) | MLF ordered-map allocation (MB) | GHC RTS allocation (MB) | GHC Main renamer/typechecker (MB) | GHC Main simplifiers (MB) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 271.98 | 46.70 | 71.27 | 19.81 | 21.49 |
| 256 | 393.52 | 62.42 | 146.89 | 43.40 | 49.20 |
| 512 | 522.65 | 79.91 | 234.10 | 71.93 | 82.95 |
| 1024 | 779.53 | 117.24 | 440.41 | 140.89 | 168.70 |

For MLF, growth from 512 to 1,024 functions exceeded twice the 256-to-512 increment by 2.37 MB in ordered maps. Across the entire profiled compiler the corresponding difference was −1.38 MB. The compiler’s GC accounted for 3.5 ms of the 10.4 ms difference in sampled time. At the sampled maximum, lists, boxed integers and ordered maps occupied about 1.90, 1.06 and 1.03 MB respectively at 1,024 functions. Peaks can belong to different compilation phases at different sizes. GHC's compiler allocations ran from 71.27 to 440.41 MB. Its repeated Main simplifier passes are summed within each build before averaging.

## Isolated ordinary compiler measurements

Each variant used a warmup and six paired builds at 0, 256 and 1,024 functions, followed by twelve independent measured pairs per size and a warmup. Three separate RTS pairs at 0 and 1,024 measured allocation, live heap, copied bytes and individual peak RSS. The table shows the 1,024-function compiler subprocess in milliseconds and memory in decimal MB.

| Variant | Screen before / after (ms) | Confirmation before / after (ms) | Allocation before / after | Maximum live before / after | Copied by GC before / after | RSS before / after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Bulk local declaration map | 261.405 / 264.144 | 259.485 / 264.053 | 765.644 / 762.479 | 10.063 / 10.064 | 87.141 / 85.957 | 61.489 / 61.538 |
| Supply the new symbol value during lookup | 260.062 / 260.866 | 264.127 / 263.073 | 765.641 / 764.202 | 10.063 / 10.568 | 87.141 / 86.798 | 61.489 / 62.521 |
| Share types and coercions during term-name substitution | 261.022 / 260.608 | 261.790 / 263.105 | 765.640 / 765.794 | 10.063 / 10.977 | 87.167 / 87.150 | 61.456 / 63.701 |

The bulk local table saved 3.17 MB of allocation at 1,024 functions, while taking longer in both time comparisons. It also gave the private prepared Prelude a different map shape. The first warmup using the preceding generated witness reached the ordinary linker and emitted 125,447 bytes of LLVM instead of 9,342. Its full error and outputs are preserved. Regenerating the literal from the isolated candidate source, checking it against fresh preparation and its disk images, then rerunning the original controls restored exact LLVM on the preceding installed builtin. The table uses the compiler with its verified matching Prelude.

Supplying the new symbol value during an ordered lookup saved 1.44 MB of cumulative allocation, with mixed elapsed results and an increase of 0.50 MB in maximum live heap. The term-only mapping reused type syntax but increased maximum live heap by 0.91 MB and offered no repeatable elapsed improvement. The preceding implementation is retained for all three.

The controls covered 3,433 module interfaces or duplicate diagnostics and three reserved-name precedence cases, 1,340 ordinary and 9,380 resource-bounded symbol plans, 67 independent UTF-8 and first-occurrence checks, 2,733 name-only and 5,466 general term/type substitutions, and seven independently rechecked fragment inventories and fingerprints. Before the module probe ran, the strict command harness rejected a compiler warning about historical kind syntax in its frozen comparison module. The fixture build then used the same syntax with that deprecation diagnostic disabled. All 360 completed ordinary diagnostic compiles preserved exact interface, object and LLVM bytes, the independently decoded query graph with its actual producer identity, and 1,080 executable results.

The object still occupies 302,673 bytes for 1,024 functions. This investigation produced no retained source change, so the preceding GHC comparison remains current. The finite-range exponent comparison remains open. Raw profiles, separate compatibility failures, regenerated-witness checks and paired receipts are under `.mlf-build/inferred-chain-heap-growth-20261118`.
