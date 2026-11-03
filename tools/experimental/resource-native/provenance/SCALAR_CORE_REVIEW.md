# Independent NEW scalar-core qualification

**Accepted for bounded source-bridge integration only, 2026-11-02.** New reconstruction, not historical M1–M6 restoration. This does not accept the source bridge itself, full GC replacement, timing or whole-language semantics.

## Inspected identity / contract

`IMPLEMENTATION_MANIFEST.json` binds six exact core files: checker, Python model, package initializer, C emitter, native runtime C/header. Reviewed actual PR28 host Int64 definition, primitive enum mapping and native arithmetic demand; the contract admits only addInt/subInt/mulInt/eqInt/ltInt (IDs 8/9/14/10/11). Quot/rem/if are deferred. Bool is an intrinsic scalar, not a nominal spelling. Typed payload allocation, READY checks, hole/thunk canonical Force, owner/loan cleanup, capture/memo behavior and finish-result publication were inspected.

Two prequalification issues were raised and corrected before final acceptance: native Repeat descriptors now reject reserved '#' names; public codegen requires a matching checked digest, rather than optional caller binding. These are new-stage fixes, not changes to frozen recovered-runtime artifacts. Source bridge exporter/transport/planner diff received preliminary review only; its actual compiler provenance and captured loader remain a separate gate.

## Fresh independent execution

`run_independent.py` passed 21 commands against unchanged core hashes, retained in `independent-commands.json` and `independent-summary.json`:

- Eight newly selected explicit-IR cases: MIN+MIN wraps to zero; MAX-(-1) wraps to MIN; -7×6=-42; MAX×MAX wraps to one; signed -1<0; unequal zero/MIN; filled #i64 MIN and #bool false holes forced to canonical results.
- Model/native exact result and event parity (existing native-only ir_force_result event filtered), native zero tracked live bytes.
- Fresh O2 and ASan+UBSan C session checks: scalar MIN → Bool false → Unit repeated three times, context-only boundaries and clean close; separate INVARIANT leak and BUSY fault sessions, result reset/suppression, forbidden reentry and poisoned close preserve snapshots.
- LSan explicitly disabled. Poison sessions retain their heaps intentionally. Independent tests do not sweep or pretend to recover those heaps.

## Author evidence independently inspected

All final evidence stream hashes/lengths verified: 174 commands, 348 stdout/stderr files across:

- `gate-final`: 147/147 checks, 158 commands; 21 positive IR cases, two demand-order BUSY cases, 19 checker negatives, malformed native descriptors/types/finalization, O0/O2 and selected ASan+UBSan runs. Before/after source hashes equal current inspected files.
- `allocation-attempt02`: eight executions, 134 boundary checks. Separate pointer-size observer compares all eight requested-memory fields; three scalar/memo/closure programs each repeat 37 entries and return to context-only baseline/close zero. Five literal allocation failure sites demonstrate OOM poison, suppression of result, no reentry allocation and preserved retained memory. These are not every possible allocation failure site.
- `legacy-subset`: three unchanged recovered cycle/memo/fn_cycle manual fixtures rebuilt against NEW native/model; exact events/common metrics and zero tracked live bytes. This is not the full recovered 26-test suite.

The first allocation-witness compile attempt failed Werror misleading indentation; original source/errors are retained and the formatting correction was confined to the witness. Earlier model event argument naming failure is preserved as well. Only final successful receipts qualify this core.

## Limits / acceptance meaning

Fresh receipts allow subsequent source-bridge integration against exactly the six manifest-bound files. They do not certify arbitrary C callbacks, malicious descriptor pointer validity, all memory safety, all leaks, all OOM paths, unsupported primitives, Once/native choose/loop, broad source coverage, source-emitter integration, old full regression suite, historical M1–M6, whole-GC replacement, optimizer memory savings or speed. Actual observer scope excludes allocator rounding, libc internals, static 65,536-byte observer storage, RSS and total native stack. Scalar outputs initially use heap wrappers. Old-stage receipts remain separate and are not transplanted.
