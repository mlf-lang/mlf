# Host ByteArray: three INLINE annotations

**Semantic checks passed; the ordinary-code gate rejected this candidate. No full compiler or performance experiment followed.**

This archive isolates `INLINE` on `MLF.Host.IO.v_readByteArray`, `v_writeByteArray`, and `v_lengthByteArray`. It retains every baseline function body, the ForeignPtr representation, the Host interface, the public Primitive facade, and the Bitstream consumer. The source base is `fc300bc9fdc389b585cbef0630fc8915d53e89c5`.

The idea is adapted from PR51's exposure annotations at `63fbd13d253a3f1a54170311dcbe076f1d0718f4`; it is **not** a port of that PR's IOUArray storage, IntArray, arithmetic-rule, or other changes. It does not modify or qualify the PR.

## Results

- **Semantics:** all 39 named checks passed in each of four fresh baseline/candidate O0/O2 executables. Every lane compiled the actual 14-module closure, including rebuilt Host.IO → Primitive → Bitstream interfaces and objects. No previous home interfaces or objects were reused. An independent audit verified the four exact stdout results, empty target stderr, source mappings, controls and complete 180-file output set.
- **Code mechanism:** the annotations reached actual Bitstream consumers, but the matched successful two-ASCII loop increased its conditional local allocation account from **528 to 544 bytes**. Including both position-thunk result boxes gives **560 to 576 bytes**, not an additional total. Inlining replaced a 16-byte code box with a 24-byte checked-value thunk rather than removing all value storage. The selected actual read path retained its 56-byte local primitive account.
- **Code size:** Host.IO `.text` changed by −96 bytes, Primitive by 0, and Bitstream by +10,416. Combined `.text` grew **10,320 bytes**, from 338,299 to 348,619. These are section sizes including GHC tables, not instruction counts.

The decision was **STOP** before a 95-module producer. The conditional machine-code accounts are neither measured heap totals nor evidence of a runtime regression or speedup. No timing ratio, performance sample, or new optimization variant is implied.

## Files and coverage

`candidate.patch` is the exact three-line production change. `tests/Main.hs` is the executed fixture, not a model of the adapter. `results/semantic.json` retains the four executable identities and exact expected stdout. `results/codegen.json` records fresh ordinary object/interface identities, the matched allocation ledger, section sizes and exclusions. `SOURCE-PINS.json` identifies source and evidence bytes.

The fixture uses literal expected values and byte/CRC vectors, exact synchronous error labels, action-construction versus execution distinctions, array/index/value error order, ignored-result checks, boundaries, aliases, repeated actions, and one forced-GC owner-retention observation. Expectations are not merely baseline=candidate comparisons. It also checks real Bitstream aligned ASCII/Unicode output and sentinels, partial failure, unaligned bytes, and the standard CRC32 `123456789` vector.

The bounded run used official GHC 9.14.1 in the ordinary way with `-fpedantic-bottoms -fno-state-hack`, isolated package selection and `-rtsopts=ignoreAll`. The four O0/O2 builds used the same unmodified package/toolchain inputs. There were two unchanged GHC adapter C compilations, four GHC builds, four fixture calls and four loader-metadata checks. GHC also generates its usual link support. No native MLF or 95-module compiler was built or run in this experiment.

## Limits

These are finite semantic observations and ordinary-code evidence, not complete Host/codec qualification, arbitrary malformed-buffer tests, a general GC-lifetime proof, a native result, or a merge recommendation. The code ledger excludes common string-indexing work, arbitrary operand thunks, runtime keepAlive/GC internals and unrelated paths; it does not certify every non-ASCII branch or read consumer. Repository CI was not run by this export, and no CI status or source/checker-version mismatch is attributed to the annotations. Compilation/fixture timings are not interpreted as a benchmark.

This directory contains sanitized extracts, not original execution receipts. Exact source/test bytes and hashes are preserved; private execution paths and system-specific process metadata are omitted.
