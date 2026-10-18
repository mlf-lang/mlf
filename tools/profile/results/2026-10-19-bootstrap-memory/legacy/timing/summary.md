| Phase | Wall seconds | User seconds | System seconds | Peak RSS bytes | Exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| package-manager | 447.12 | 434.36 | 6.13 | 5152686080 | 0 |
| mlf | 349.27 | 342.48 | 3.65 | 5152686080 | 0 |
| llvm-and-link | 24.88 | 24.09 | 0.68 | 2151809024 | 0 |
| runtime-c | 0.60 | 0.31 | 0.09 | 103333888 | 0 |
| mlf | 59.81 | 59.28 | 0.40 | 1468416000 | 0 |
| runtime-c | 0.30 | 0.28 | 0.01 | 102858752 | 0 |
| llvm-and-link | 6.25 | 6.13 | 0.15 | 628932608 | 0 |

The package-manager row contains the child calls; do not add it to their totals. Full argv, raw time output, host identity, tool hashes and native build reports are retained in the artifact.

Peak process RSS: 5152686080 bytes; budget: 5500000000 bytes (0 disables the diagnostic budget); passed: true.
