# CRC-four isolated on baseline Host: HOLD / deferred

This experiment imports only PR #51's fixed `checksum` large-buffer dispatch and four private CRC helpers onto main `fc300bc9`. It does not modify the user's PR or main, public exports, Host/Primitive, query ownership, wire format or native compiler. The full PR has different Host storage; these findings do not establish its performance.

## Verified narrow semantics
The four fresh A/C × O0/O2 builds and direct checksum fixtures passed: 22 vectors each, threshold/remainder boundaries, ignored header bytes, tagged bounds/demand checks, and rerunning one shared action after mutations. Each lane rebuilt 15 home modules against its own new interfaces. This is a focused test, not whole-codec/producer/native qualification. Main-only no-CSE/no-full-laziness options do not change production flags. SOURCE-PINS identifies the four fixture executables, not full compilers.

## Corrected ordinary body accounting
The actual O2 encodeTables consumer reaches the compared checksum paths. Independent code review found a real omission in the initial report: old A's 120 B per-byte body also traverses three runtime partial-application allocations of 32, 40 and 64 B. Thus its complete successful normal four-byte local cycle is **1024 B**, not 480 B. C's corresponding complete local cycle is **856 B**, a local difference of 168 B. These are conditional emitted allocation ledgers, not runtime measurements. Header, tail, initialization and finalization are outside these body figures. The initial `504 > 480` negative argument is withdrawn; 504 was only a candidate subset. Baseline Host writes evaluate table values, so the earlier lazy-table first-touch description is also withdrawn. Original erroneous evidence remains preserved separately.

The table expands from 256 to 1024 cells. Its known build-construction regions add 61440 B, but this is not a complete setup difference. Remaining setup/header/tail/finalization costs do not yet have a reliable bound, so full amortization is not established. Bitstream `.text` grows from 287063 to 298599 B (+11536 B); baseline Host/Base/IO/Primitive object bytes match between lanes. These facts neither establish whole-runtime improvement nor prove regression.

## Decision
**HOLD / defer**, not a negative performance verdict. Do not continue whole95, timing windows, threshold tuning or a second CRC variant in this pass. Prioritize the separately investigated higher-potential existing Host structural path. No full compiler build, benchmark sample or native run was performed for this CRC candidate.

This archive includes the patch, direct fixtures, independent fixed-vector oracle, source/fixture identities, corrected accounting and sanitized result. Exact objects, actual linker/source maps and original supervision records are retained privately; no binary, machine-specific path or private recovery identifier is published. QueryGraph is outside this focused closure, so its machine code is not claimed verified.
