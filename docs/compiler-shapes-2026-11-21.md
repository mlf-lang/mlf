# MLF and GHC compilation across program shapes

On this Apple M1 Max, 120 of 125 standard comparisons completed all six pairs. MLF had the lower median compile time in 106 of those 120 comparisons. The matrix covers 25 shapes at 8, 32, 128, 1,024, and 8,192 units. The two additional nested-type checks at depths 4 and 16 also completed.

The tables include 30 standard comparisons rerun after the initial sweep. Each rerun replaces that shape’s five earlier cells. Every cell uses its own six-pair schedule. The code, runtime arguments and expected outputs for each fixture match the initial run.

Including the two additional depths, these measurements account for 1,465 successful builds, 5 failed attempts and 54 scheduled builds skipped after a failure. The recorder completed 732 pairs and verified 117,183 output lines in 4,635 untimed executable invocations.

## Compiler revisions

Each paired build uses the same program source for MLF and GHC. MLF uses the GHC-hosted `crate-fused-v1` compiler and Clang with `-O2`. GHC 9.14.1 uses `--make -O2`. Both builds include native linking. The compilers run serially and alternate which starts the next pair. The CSV identifies the recorder revision, compiler source revision, executable SHA-256 and producer receipt for every row.

The initial sweep used MLF `c8eaf641ec1d27a1fce126fdb6f722ec2d2f089c`. The two additional nested-type depths retain that original compiler. The following rows identify the compiler for the standard reruns.

| Remeasured shape | Six-pair comparisons completed | MLF compiler commit | Executable SHA-256 |
| --- | ---: | --- | --- |
| `class_instances` | 5/5 | `052906a8e0749b26a0d69b0cfd5d8f0c8973cf77` | `ba210fbddf22d9edaa9e2af1ec337155d42eb7df65bdbc8cde2f401bfc6ef226` |
| `decoder_pipeline` | 5/5 | `ac54c40db1019b1a9956e5b49dd4dbca61643071` | `efe67ae5a7c044891699606ea0cf3b18dc49c6d931ccf45ed9f0122f0cbf2201` |
| `dependency_chain` | 5/5 | `d893e3dd5fce35cad9ac838a9666557b780078d6` | `2afbcad29d73562395e0fef5cc64f6d669c745841e3c54ddc4805730d7e7e8b8` |
| `dependency_diamonds` | 5/5 | `d893e3dd5fce35cad9ac838a9666557b780078d6` | `2afbcad29d73562395e0fef5cc64f6d669c745841e3c54ddc4805730d7e7e8b8` |
| `inferred_chain` | 5/5 | `d893e3dd5fce35cad9ac838a9666557b780078d6` | `2afbcad29d73562395e0fef5cc64f6d669c745841e3c54ddc4805730d7e7e8b8` |
| `inferred_poly_chain` | 5/5 | `d893e3dd5fce35cad9ac838a9666557b780078d6` | `2afbcad29d73562395e0fef5cc64f6d669c745841e3c54ddc4805730d7e7e8b8` |

**class_instances**. A defining module shares its instance environment across declarations and methods. Lexical givens keep their order at each qualified body, including copied helpers.

**decoder_pipeline**. The earlier compiler rejected the deep query graph. After query publication succeeded, a standard rerun reached the 90-second MLF wall. The checked optimizer now reuses callback-use information and LLVM emission reuses the free-variable sets of nested functions; the generated LLVM matched byte for byte.

**dependency_chain**. The previous 8,192-unit MLF build stopped during query-graph validation. This rerun uses the explicit traversal of deep acyclic dependencies.

**dependency_diamonds**. The checked LLVM optimizer now preserves multiply used functions whose bodies branch to shared dependencies. Query publication and cache validation traverse deep acyclic paths with explicit frames, while continuing to reject cycles.

**inferred_chain**. The previous 8,192-unit MLF build stopped during query-graph validation. This rerun uses the explicit traversal of deep acyclic dependencies.

**inferred_poly_chain**. The previous 8,192-unit MLF build stopped during query-graph validation. This rerun uses the explicit traversal of deep acyclic dependencies.

## Elapsed compile time

Each cell shows MLF / GHC median wall time in seconds for the six full builds per compiler. The timed interval includes the build worker, compilation and native linking.

| Program shape | 8 | 32 | 128 | 1,024 | 8,192 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `flat_functions` | 0.266 / 0.562 | 0.274 / 0.523 | 0.313 / 0.565 | 0.669 / 0.786 | 4.996 / 5.251 |
| `inferred_functions` | 0.271 / 0.509 | 0.274 / 0.524 | 0.306 / 0.562 | 0.669 / 0.780 | 5.081 / 4.098 |
| `inferred_poly_functions` | 0.293 / 0.568 | 0.338 / 0.581 | 0.556 / 0.848 | 4.191 / 5.684 | Recorder EPERM |
| `dependency_chain` | 0.288 / 0.576 | 0.284 / 0.583 | 0.296 / 0.595 | 0.450 / 0.848 | 1.687 / 3.908 |
| `inferred_chain` | 0.290 / 0.581 | 0.282 / 0.572 | 0.294 / 0.566 | 0.425 / 0.744 | 1.644 / 2.999 |
| `inferred_poly_chain` | 0.293 / 0.568 | 0.287 / 0.595 | 0.304 / 0.615 | 0.445 / 1.045 | 1.837 / 5.463 |
| `recursive_ring` | 0.274 / 0.548 | 0.289 / 0.567 | 0.352 / 0.630 | 0.901 / 1.534 | 7.852 / 14.333 |
| `mono_calls` | 0.277 / 0.567 | 0.276 / 0.574 | 0.272 / 0.560 | 0.281 / 0.723 | 0.331 / 2.062 |
| `poly_calls` | 0.269 / 0.541 | 0.272 / 0.561 | 0.275 / 0.573 | 0.292 / 0.734 | 0.343 / 2.105 |
| `tree_chain` | 0.266 / 0.547 | 0.282 / 0.573 | 0.271 / 0.641 | 0.268 / 1.555 | 0.313 / 10.568 |
| `balanced_tree` | 0.266 / 0.578 | 0.276 / 0.568 | 0.274 / 0.661 | 0.291 / 1.594 | 0.405 / 10.807 |
| `literal_table` | 0.269 / 0.555 | 0.279 / 0.555 | 0.281 / 0.590 | 0.287 / 1.071 | 0.405 / 5.804 |
| `higher_order_chain` | 0.272 / 0.553 | 0.269 / 0.536 | 0.277 / 0.549 | 0.292 / 0.651 | 0.352 / 0.744 |
| `local_functions` | 0.266 / 0.536 | 0.274 / 0.542 | 0.289 / 0.585 | 0.385 / 0.819 | 1.437 / 6.957 |
| `wide_case` | 0.371 / 0.588 | 0.390 / 0.602 | 0.943 / 1.225 | 1.534 / 1.693 | 16.121 / 11.786 |
| `class_instances` | 0.466 / 0.643 | 0.596 / 0.679 | 1.209 / 1.037 | 7.206 / 4.551 | 62.802 / 39.571 |
| `dependency_diamonds` | 0.290 / 0.571 | 0.346 / 0.576 | 0.547 / 0.632 | 2.366 / 1.372 | 19.367 / 41.840 |
| `state_updates` | 0.413 / 0.612 | 0.561 / 0.707 | 1.213 / 1.389 | 11.949 / 23.242 | Recorder EPERM |
| `captured_closures` | 0.330 / 0.626 | 0.352 / 0.622 | 0.584 / 0.858 | 2.985 / 3.458 | 26.174 / 26.764 |
| `wide_product` | 0.322 / 0.645 | 0.394 / 0.687 | 0.712 / 0.699 | 3.533 / 1.615 | 39.878 / 26.353 |
| `rank2_arguments` | 0.320 / 0.624 | 0.350 / 0.588 | 0.499 / 0.683 | 1.938 / 1.739 | 15.419 / 11.719 |
| `irregular_literal_table` | 0.283 / 0.567 | 0.287 / 0.593 | 0.292 / 0.614 | 0.304 / 1.149 | 0.428 / 6.153 |
| `nested_poly_types` | 0.275 / 0.575 | 0.278 / 0.556 | 0.330 / 0.555 | MLF leg stopped | GHC leg stopped |
| `rank2_callbacks` | 0.325 / 0.562 | 0.459 / 0.604 | 1.089 / 0.840 | 7.130 / 5.803 | GHC leg stopped |
| `decoder_pipeline` | 0.340 / 0.624 | 0.364 / 0.640 | 0.477 / 0.708 | 2.880 / 1.901 | 11.575 / 15.623 |

## Peak resident memory

Each cell shows MLF / GHC in MiB. The recorder sampled the resident set size (RSS) of the build process group every 100 ms, summed the resident sizes across its processes, then took the largest sample for each build. The table gives the median of those six peaks. Short-lived peaks between samples can be higher. Shared pages may count toward multiple processes.

| Program shape | 8 | 32 | 128 | 1,024 | 8,192 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `flat_functions` | 96.3 / 342.9 | 86.9 / 345.1 | 95.3 / 341.2 | 117.9 / 382.7 | 372.7 / 627.9 |
| `inferred_functions` | 92.4 / 343.5 | 87.1 / 342.9 | 95.1 / 337.2 | 117.9 / 384.3 | 324.1 / 680.2 |
| `inferred_poly_functions` | 87.4 / 332.0 | 103.5 / 375.6 | 100.2 / 457.7 | 205.3 / 676.2 | Recorder EPERM |
| `dependency_chain` | 86.5 / 340.3 | 86.5 / 329.9 | 86.3 / 332.7 | 109.0 / 371.8 | 246.1 / 619.4 |
| `inferred_chain` | 86.8 / 382.3 | 86.6 / 337.3 | 86.4 / 322.4 | 110.6 / 463.4 | 283.1 / 569.6 |
| `inferred_poly_chain` | 87.7 / 335.4 | 87.6 / 432.4 | 88.5 / 370.2 | 114.5 / 387.9 | 302.3 / 607.6 |
| `recursive_ring` | 87.1 / 336.9 | 86.9 / 331.1 | 104.7 / 365.2 | 164.5 / 379.4 | 624.0 / 762.9 |
| `mono_calls` | 86.9 / 339.6 | 87.1 / 337.5 | 88.4 / 321.8 | 88.8 / 423.0 | 94.6 / 491.4 |
| `poly_calls` | 88.4 / 341.4 | 87.3 / 339.1 | 87.3 / 325.0 | 87.9 / 433.4 | 92.1 / 504.1 |
| `tree_chain` | 92.8 / 335.9 | 88.0 / 382.5 | 89.2 / 351.6 | 90.2 / 466.2 | 90.5 / 951.5 |
| `balanced_tree` | 96.9 / 334.7 | 87.2 / 313.5 | 87.8 / 347.5 | 96.4 / 441.4 | 124.4 / 1,031.3 |
| `literal_table` | 95.5 / 336.9 | 87.9 / 328.2 | 87.2 / 433.2 | 87.8 / 384.0 | 104.8 / 578.7 |
| `higher_order_chain` | 88.7 / 339.2 | 95.3 / 336.7 | 87.3 / 331.9 | 88.1 / 343.3 | 92.7 / 426.6 |
| `local_functions` | 96.8 / 340.5 | 87.0 / 343.5 | 86.5 / 366.8 | 95.6 / 366.4 | 372.2 / 629.7 |
| `wide_case` | 93.8 / 320.6 | 93.9 / 369.4 | 103.1 / 378.8 | 189.5 / 460.1 | 1,442.4 / 874.8 |
| `class_instances` | 105.8 / 421.4 | 114.7 / 347.7 | 139.0 / 452.8 | 497.3 / 522.7 | 3,201.9 / 2,202.2 |
| `dependency_diamonds` | 86.5 / 342.6 | 98.4 / 319.1 | 100.3 / 360.5 | 178.7 / 454.5 | 926.4 / 1,418.5 |
| `state_updates` | 94.7 / 428.7 | 107.7 / 373.4 | 146.8 / 400.7 | 490.1 / 881.4 | Recorder EPERM |
| `captured_closures` | 87.5 / 383.4 | 99.8 / 359.9 | 113.9 / 452.0 | 318.1 / 532.9 | 2,878.0 / 1,646.9 |
| `wide_product` | 87.4 / 429.4 | 104.2 / 403.7 | 137.7 / 348.9 | 297.0 / 403.9 | 1,538.0 / 1,444.6 |
| `rank2_arguments` | 87.5 / 422.0 | 93.0 / 353.9 | 105.2 / 347.5 | 251.3 / 414.8 | 1,771.8 / 969.8 |
| `irregular_literal_table` | 86.8 / 322.2 | 86.9 / 347.7 | 87.8 / 379.6 | 88.8 / 400.0 | 106.8 / 548.1 |
| `nested_poly_types` | 87.1 / 338.1 | 86.7 / 339.3 | 90.9 / 338.1 | MLF leg stopped | GHC leg stopped |
| `rank2_callbacks` | 92.6 / 326.9 | 106.4 / 399.0 | 129.5 / 355.2 | 332.5 / 612.1 | GHC leg stopped |
| `decoder_pipeline` | 108.9 / 410.8 | 98.9 / 392.7 | 119.2 / 351.1 | 212.6 / 431.0 | 972.5 / 721.3 |

## Additional nested type depths

These additional sizes use the same six-pair schedule. Depth counts the nested `Box` layers in `nested_poly_types`.

| Depth | Elapsed seconds, MLF / GHC | Peak RSS in MiB, MLF / GHC |
| ---: | ---: | ---: |
| 4 | 0.276 / 0.542 | 92.1 / 340.9 |
| 16 | 0.288 / 0.556 | 86.8 / 339.1 |

## Incomplete paired measurements

A failure stops the remaining builds in that cell. The CSV retains the successful and skipped counts for both compilers.

| Shape | Size | Completed pairs | Stopped leg | Skipped MLF / GHC | Recorded reason |
| --- | ---: | ---: | --- | ---: | --- |
| `inferred_poly_functions` | 8,192 | 0/6 | GHC | 6 / 5 | PermissionError(1, 'Operation not permitted') |
| `state_updates` | 8,192 | 0/6 | GHC | 6 / 5 | PermissionError(1, 'Operation not permitted') |
| `nested_poly_types` | 1,024 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 binary expanded-work limit exceeded |
| `nested_poly_types` | 8,192 | 0/6 | GHC | 6 / 5 | process-tree RSS limit |
| `rank2_callbacks` | 8,192 | 0/6 | GHC | 6 / 5 | wall limit |

## Initial sweep and follow-ups

These results document the 21 November 2026 sweep on MLF `c8eaf641ec1d27a1fce126fdb6f722ec2d2f089c`. Its standard matrix completed 110 of 125 comparisons. The historical diagnostics and separate follow-ups below retain the original measurements for superseded rows.

The initial report reused 98 cells across 20 shapes from benchmark revision `939968bd7c6d0064433520261879a72455825a8f`. Revision `64e4140e509c20f4bb61aad7b070c8be1ad6cdfc` reproduced their source bytes, inputs and expected output, and supplied 29 fresh cells. Those cover four additional shapes, the revised `wide_case` workload, and two `rank2_arguments` sizes. The revised `wide_case` checks every constructor arm in one extra executable invocation. Its original three-input measurements remain in the earlier run.

The original sweep held back 2 `rank2_arguments` cells at sizes 1,024 and 8,192. Each completed 12 builds and verified their program outputs. The sweep detected a tracked edit to `CONTRIBUTING.md` and declined to combine those cells with its earlier measurements. The audit confirmed that only the contributor guide changed and that the measured inputs retained their recorded hashes. The initial tables used fresh runs from a clean tracked checkout for those two sizes and retain the three smaller cells from the original sweep.

### Initial incomplete paired measurements

The recorder stopped a cell at its first failure. A paired median requires all six pairs. The skipped counts show how many scheduled builds remained for each compiler.

| Shape | Size | Completed pairs | Stopped leg | Skipped MLF / GHC | Recorded reason |
| --- | ---: | ---: | --- | ---: | --- |
| `inferred_poly_functions` | 8,192 | 0/6 | GHC | 6 / 5 | PermissionError(1, 'Operation not permitted') |
| `dependency_chain` | 8,192 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 cyclic/deep query graph |
| `inferred_chain` | 8,192 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 cyclic/deep query graph |
| `inferred_poly_chain` | 8,192 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 cyclic/deep query graph |
| `class_instances` | 1,024 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 binary symbol byte limit exceeded |
| `class_instances` | 8,192 | 0/6 | MLF | 5 / 5 | wall limit |
| `dependency_diamonds` | 32 | 0/6 | MLF | 5 / 5 | PermissionError(1, 'Operation not permitted') |
| `dependency_diamonds` | 128 | 0/6 | MLF | 5 / 5 | PermissionError(1, 'Operation not permitted') |
| `dependency_diamonds` | 1,024 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 cyclic/deep query graph |
| `dependency_diamonds` | 8,192 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 cyclic/deep query graph |
| `state_updates` | 8,192 | 0/6 | GHC | 6 / 5 | PermissionError(1, 'Operation not permitted') |
| `nested_poly_types` | 1,024 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 binary expanded-work limit exceeded |
| `nested_poly_types` | 8,192 | 0/6 | GHC | 6 / 5 | process-tree RSS limit |
| `rank2_callbacks` | 8,192 | 0/6 | GHC | 6 / 5 | wall limit |
| `decoder_pipeline` | 8,192 | 0/6 | MLF | 5 / 5 | source-to-llvm exit 1 cyclic/deep query graph |

The original EPERM record contains a permission error from the recorder and no terminal resource reading or compiler diagnostic that establishes its cause.

### Follow-ups on the initial compiler

A single-compiler follow-up repeats the other compiler after a paired cell stopped. An original-monitor retry repeats all six pairs under the original supervisor. A fixed-monitor rerun uses the same source, ordinary compiler, per-command limits and schedule with the updated Darwin process monitor. A guard reported by that monitor belongs to that rerun. The cause of the original EPERM remains undetermined. Each row uses only its own measurements. A dash marks an unavailable median.

| Shape | Size | Measurement | Elapsed seconds, MLF / GHC | Peak RSS in MiB, MLF / GHC | Outcome |
| --- | ---: | --- | ---: | ---: | --- |
| `decoder_pipeline` | 8,192 | Single compiler | — / 13.493 | — / 770.6 | Completed |
| `nested_poly_types` | 1,024 | Single compiler | — / 6.156 | — / 555.1 | Completed |
| `nested_poly_types` | 8,192 | Single compiler | — / — | — / — | MLF · binary expanded-work limit exceeded |
| `rank2_callbacks` | 8,192 | Single compiler | 57.676 / — | 3,236.4 / — | Completed |
| `inferred_poly_functions` | 8,192 | Original-monitor retry | — / — | — / — | GHC · PermissionError(1, 'Operation not permitted') |
| `dependency_diamonds` | 32 | Original-monitor retry | — / — | — / — | MLF · PermissionError(1, 'Operation not permitted') |
| `dependency_diamonds` | 128 | Original-monitor retry | — / — | — / — | MLF · PermissionError(1, 'Operation not permitted') |
| `state_updates` | 8,192 | Original-monitor retry | — / — | — / — | GHC · PermissionError(1, 'Operation not permitted') |
| `inferred_poly_functions` | 8,192 | Single compiler | — / — | — / — | MLF · binary symbol byte limit exceeded |
| `dependency_chain` | 8,192 | Single compiler | — / 3.825 | — / 611.7 | Completed |
| `inferred_chain` | 8,192 | Single compiler | — / 2.727 | — / 572.9 | Completed |
| `inferred_poly_chain` | 8,192 | Single compiler | — / 5.369 | — / 618.6 | Completed |
| `class_instances` | 1,024 | Single compiler | — / 4.450 | — / 522.3 | Completed |
| `class_instances` | 8,192 | Single compiler | — / 38.780 | — / 2,938.6 | Completed |
| `dependency_diamonds` | 32 | Single compiler | — / 0.565 | — / 323.1 | Completed |
| `dependency_diamonds` | 128 | Single compiler | — / 0.607 | — / 405.1 | Completed |
| `dependency_diamonds` | 1,024 | Single compiler | — / 1.303 | — / 462.5 | Completed |
| `dependency_diamonds` | 8,192 | Single compiler | — / 39.649 | — / 1,420.5 | Completed |
| `state_updates` | 8,192 | Single compiler | — / — | — / — | MLF · wall limit |
| `inferred_poly_functions` | 8,192 | Fixed-monitor rerun | — / — | — / — | GHC · wall limit |
| `dependency_diamonds` | 32 | Fixed-monitor rerun | — / — | — / — | MLF · process-tree RSS limit |
| `dependency_diamonds` | 128 | Fixed-monitor rerun | — / — | — / — | MLF · process-tree RSS limit |
| `state_updates` | 8,192 | Fixed-monitor rerun | — / — | — / — | GHC · wall limit |

The [full-precision CSV](compiler-shapes-2026-11-21.csv) contains the measurements used in the current tables. Run `python3 tools/dev.py bench shapes` to collect the standard matrix. [Benchmark instructions](../tools/performance/compiler-shapes/README.md).
