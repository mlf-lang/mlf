# r27 ordinary BENCH: one fixed batch

A is formal r25; B is formal r27 lazy counted projection. One authorized run, exit 0. No retries, extra batches, profiling, native-generation or fixed-point run.

## Qualification and cleanup

All 12 ABBAABBAABBA samples completed. Each has 475 fresh queries, 0 reuse, all 14 owners, exact ordered query equality, and all three raw artifacts byte-equal to r14. All 26 child guards exit 0 and clean. Post-completion readback recomputed all 36 artifact hashes and byte comparisons, reparsed 12 owner outputs and 12 frozen-parser raw RTS reports, and checked both measured binary pins. Query-lock reacquisition is the admitted worker's actual evidence; the report acquired no locks.

Worker 268.610574 s; outer 270.197542 s, within 600 s, per target 180 s unchanged. Outer cleanup, lock reacquired and lease cleared are true; active lease absent and active directory empty.

## Observed result, not a speedup claim

- Allocated bytes, identical in all six samples per side: A 60,040,794,280; B 60,040,489,688. Difference −304,592 B, **−0.000507308%**.
- Guard-wall medians: A 19.994898 s; B 20.041907 s, **+0.235104%**. Six adjacent pairs: B 2 faster, 4 slower; changes range −3.924238% to +5.386629%.
- This batch does not demonstrate a wall-time improvement. The observed whole-process allocation reduction is tiny. The emitted-code removal of one late length site is not evidence of a material runtime benefit. No exclusive allocation or time attribution follows.

## Independent RTS quantities

| Quantity | A median | B median |
|---|---:|---:|
| Bytes copied during GC | 4,273,134,232 | 4,269,755,776 |
| Maximum residency (sampled bytes) | 36,234,192 | 36,245,320 |
| Maximum slop (bytes) | 1,616,944 | 1,617,904 |
| GC CPU seconds | 3.4745 | 3.4590 |
| GC elapsed seconds | 3.4800 | 3.4625 |
| MUT CPU seconds | 16.2495 | 16.3665 |
| MUT elapsed seconds | 16.3875 | 16.4995 |
| Total RTS CPU seconds | 19.7200 | 19.8260 |
| Total RTS elapsed seconds | 19.8655 | 19.9620 |

Every sample: Gen 0 collections 14,279; Gen 1 collections/residency samples 58; reported RTS memory in use 105 MiB. Residency increases by 11,128 B in B, not a proof of a particular retained closure or peak RSS. GC times are rounded process totals. Raw %GC is 0.0% despite nonzero GC time and is not used as measured share. GC / Total CPU fractions computed from rounded totals have medians 17.653497% and 17.489539% respectively; these do not replace independent wall/GC/residency measurements.

## All observed samples

| Index | Side | Guard wall s | GC CPU s | GC elapsed s | Copied bytes | Residency bytes |
|---:|:---:|---:|---:|---:|---:|---:|
| 1 | A | 20.174825145 | 3.613 | 3.618 | 4273132416 | 36234192 |
| 2 | B | 21.062662907 | 3.662 | 3.666 | 4269756528 | 36245320 |
| 3 | B | 19.508253283 | 3.413 | 3.413 | 4269909840 | 36245320 |
| 4 | A | 20.305072738 | 3.602 | 3.608 | 4273134552 | 36234192 |
| 5 | A | 19.820589767 | 3.471 | 3.471 | 4273135368 | 36234192 |
| 6 | B | 19.833666089 | 3.418 | 3.418 | 4269720280 | 36245320 |
| 7 | B | 20.842044538 | 3.722 | 3.741 | 4269755024 | 36245320 |
| 8 | A | 19.776744620 | 3.461 | 3.461 | 4273134216 | 36234192 |
| 9 | A | 19.927137866 | 3.462 | 3.467 | 4273134248 | 36234192 |
| 10 | B | 20.100642031 | 3.461 | 3.462 | 4269909672 | 36245320 |
| 11 | B | 19.983171053 | 3.457 | 3.463 | 4269754896 | 36245320 |
| 12 | A | 20.062657464 | 3.478 | 3.489 | 4273134168 | 36234192 |

Sanitized per-sample metrics and raw RTS hashes are in samples.json. Raw internal execution receipts are not included. Formal validation coverage remains: 39 direct cases with 41 logical public-unify calls per side, separate Unify23 with 23 cases per side, and five CLI controls per side. These finite controls do not prove universal partial-value, async or retained-space equivalence.
