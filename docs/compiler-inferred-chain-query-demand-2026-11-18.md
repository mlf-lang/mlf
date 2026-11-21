# Query lookups, allocation and object size on the inferred chain

At 1,024 unsigned monomorphic functions all four experiments reduced cumulative allocation. None gave repeatable compiler speedups and each increased sampled maximum live heap. The preceding compiler remains the measured implementation. [Full 128-pair MLF and GHC comparison](compiler-inferred-chain-prelude-reads-2026-11-18.md)

## Query processing

Across two current-source profiles at each of 0, 256, 512 and 1,024 functions, preparing query inputs added 15.15 ms and 62.75 MB from smallest to largest. Within that work, hashing rebuilt values added 4.00 ms and 15.61 MB. The input-key parser allocated 0.59 MB while validating cold queries. These are overlapping instrumented costs.

| Isolated compiler change | First paired medians (ms), before → after | Second paired medians (ms), before → after | Allocated (MB), before → after | Peak live heap (MB), before → after |
| --- | ---: | ---: | ---: | ---: |
| Reuse the small input’s framing bound | 259.449 → 262.641 | 263.494 → 261.310 | 765.641 → 764.712 | 10.063 → 11.184 |
| Reuse the checked parameter nodes | 261.392 → 269.473 | 264.491 → 260.018 | 765.643 → 764.337 | 10.063 → 11.051 |
| Parse only keys found in the previous generation | 261.496 → 263.366 | 263.641 → 262.078 | 765.644 → 765.052 | 10.063 → 10.525 |
| Join fields of a query report in chunks | 262.076 → 265.383 | 260.503 → 261.295 | 765.643 → 759.794 | 10.063 → 10.398 |

Each change ran against the same producer at 0, 256 and 1,024 functions, with six measured pairs in the first comparison and twelve fresh pairs in the second. Three separate instrumented pairs at 0 and 1,024 measured heap use. The 480 ordinary builds emitted identical interface, object and LLVM bytes and passed 1,440 native execution checks. The decoded graph in every build retained its actual compiler identity and the same declarations and ordered dependencies.

The receipt tests covered 208 independently framed SHA digests and 217 previous/current validation and digest outcomes. The parameter-node variant passed the current and frozen declaration suites covering scope, evidence, slot drift, imported and local declarations, and warm cache reuse. Both suites produced 33 identical cache files when run inside the same executable. Separate test executables had different provenance hashes in the historical file-cache format. The previous-query lookup passed 2,592 comparisons with an independent validator and 720 expected-read comparisons. Query reports matched an independent encoder for Unicode, control characters, empty arrays, integer boundaries and a 2,049-group case.

## File size with short child references

The offline writer used a one-bit flag followed by a four-bit distance for one of the previous 16 nodes, or by the existing full-width reference for longer distances. It retained the 80-byte header and used a distinct experimental flag. These are actual complete-file sizes, including framing, final-byte padding and a recalculated CRC32.

| Functions | Interface, original → experiment (bytes) | Object, original → experiment (bytes) | Query generation, original → experiment (bytes) |
| ---: | ---: | ---: | ---: |
| 0 | 734 → 730 | 1,338 → 1,321 | 1,328 → 1,326 |
| 32 | 3,995 → 3,972 | 10,071 → 9,849 | 7,710 → 7,702 |
| 64 | 7,221 → 7,206 | 18,960 → 18,435 | 13,918 → 13,938 |
| 128 | 13,945 → 13,920 | 37,288 → 36,055 | 26,926 → 26,944 |
| 256 | 27,426 → 27,375 | 74,257 → 71,397 | 53,242 → 53,219 |
| 512 | 54,603 → 54,478 | 149,071 → 142,520 | 106,631 → 106,438 |
| 1024 | 110,447 → 110,122 | 302,673 → 287,854 | 215,983 → 215,269 |

At 1,024 functions the object saved 14,819 bytes (4.90%), the interface saved 325 bytes (0.29%) and the query generation saved 714 bytes (0.33%). All 21 streams converted back to the exact original bytes and passed the existing independent structural reader. The current reader rejected the experimental flag. Compiler support and a versioning decision would be needed for deployment. This experiment measures storage only.

MLF’s previous finite-range fitted exponent was 1.095, compared with 1.124 for GHC. Its paired 95% difference interval was [−0.251, +0.218]. The four rejected changes supply no new formal GHC cohort and no evidence for an asymptotic complexity difference. [Previous heap and map experiments](compiler-inferred-chain-heap-growth-2026-11-18.md)
