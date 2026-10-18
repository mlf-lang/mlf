| Phase | Wall seconds | User seconds | System seconds | Peak RSS bytes | Exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| package-manager | 403.17 | 324.42 | 51.52 | 10180476928 | 0 |
| mlf | 325.83 | 253.79 | 48.54 | 10180476928 | 0 |
| runtime-c | 0.70 | 0.33 | 0.11 | 102858752 | 0 |
| llvm-and-link | 26.14 | 25.11 | 0.71 | 2183774208 | 0 |
| mlf | 37.58 | 36.40 | 0.66 | 2612936704 | 0 |
| runtime-c | 0.33 | 0.30 | 0.02 | 102219776 | 0 |
| llvm-and-link | 6.80 | 6.58 | 0.20 | 631537664 | 0 |

The package-manager row contains the child calls; do not add it to their totals. Full argv, raw time output, host identity, tool hashes and native build reports are retained in the artifact.

Peak process RSS: 10180476928 bytes; budget: 0 bytes (0 disables the diagnostic budget); passed: true.
