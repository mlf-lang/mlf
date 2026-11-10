# Allocation attribution: decision and next protocol

Preparation only. No build, compiler execution, timing, download or production
change was performed. Separate implementation/review and execution admissions
remain required. The sprint budget still begins November 10.

## Decision

Use sparse manual GHC cost centres in an exactly reversible, host-only source
mirror of frozen f9bdb40a659bfdff4cbb782d438afbb0417dd2e1. This has higher information
value than more IO timers because thunk-origin stacks survive delayed demand.
Official workspace GHC 9.14.1 already has the required profiling archives for all
23 transitive package units; installation totals are53 `_p.a` and2,212 `.p_hi`.
This is presence evidence, not a successful profiling link.

Build precisely95 non-Main home modules: emlf's90shared+4host, plus
MLF.Entry.BuiltinPrelude, with separate emlf/generator Mains. Generator's own
closure is60. This is a diagnostic union, **not** the full137/4/13 producer.
Rebuild the full union with -prof, original O2/demand/package flags and fresh
objects. No ordinary/profile ABI mixing or automatic/late cost centres. Preserve
-rtsopts=ignoreAll; compile profile/stats options in and archive each fresh report
before another launch. The ordinary full producer remains independently qualified.

## Labels and interpretation

Separate constraint generation, solve, prepared types/evidence, elaboration,
closed check, type agreement/erasure, initial open admission/ownership,
canonicalOpen planning/materialization/final syntax, normalization recheck,
OpenFragment.stamp, free-name construction, encoding, SHA and publication.
Label the actual deferred inventory RHSs and preserve their closed/open context.
Witness fallback receives a distinct label without removing its real proof path.
Exact insertion sites and scope are in PROTOCOL-DETAIL.md.

CheckedTerm's inventory is an independent Either. Right/WHNF is not its complete
check; stamps can be demanded only during encoding. Add no deepseq, seq, eager
inventory extraction, AST retention or semantic bypass. Sparse SCCs themselves
change optimization/layout, so report **profiled source-demand allocation**, not
ordinary exclusive CPU or removable cost. Partition tree-node self allocations
once by nearest semantic label, retain unknown/CAF/RTS residuals, and show raw
stacks. Never add overlapping inherited rows or multiply shares by ordinary60.55GB.

## Gates, in order, separately admitted

1. BUILD <=600s: verify reversible source mapping, actual95-module provenance,
   both distinct Mains, complete profiling libraries/interfaces, original-command
   C reconstruction/equality, exact runtime/input/output pins and cleanup.
2. QUALIFY <=180s: run original --check-shared over all137 frozen shared target
   sources, CLI/identity and42/Unicode positives/type negatives. Run unchanged
   verify_builtin_prelude.py against the frozen source root with the actual new
   profiled emlf and profiled generator: check-candidate and fresh-literal must
   execute, with exact banner/canonical stdout and empty stderr. Authenticate
   the new receipt. No stale builtin identity or old generated output substitute.
3. PROBE-CONTROLS <=120s: actual child/lock cancellation and cleanup; false124,
   hard kill/missing profile, stale/symlink outputs, ignored literal RTS arguments;
   delayed-thunk attribution and independent deferred-inventory/error-demand
   controls. Identify maintained semantic fixtures in implementation review.
4. TARGET-QUALIFICATION <=420s, <=180s/compile: fresh ordinary Q and profiled P,
   same14 frozen modules/173,594bytes, crate identity, ordered successful builtin
   dependency. Require475fresh/0reuse, full ordered query equality and byte-exact
   .mlfci/.mlfco/.queries against each other and retained ordinary Q. Check all14
   owners/builtin through show-crate, runtime/pins and query locks. This profile
   is qualification only.
5. ATTRIBUTION <=240s outer/<=180s compile: exactly one further fresh P run with
   the same binary/inputs and all the same oracles. Keep raw profile/RTS/receipts.
   A timeout is incomplete, not successful attribution; no continuation/retry.

All use <WORKSPACE>/.astra-resource-locks/heavy.lock and required reproduction
lock, verified inode, cross-session descendant accounting and reacquisition.
Limits remain treeRSS5GiB/processAS6GiB/free-disk5GiB/host-available3GiB/output4GiB.
No endpoint exceeds600s. Native A/B, fixed point, main merge/deploy remain paused.

## Reuse and fallback

Archived fa7df4c39897a7dad4d21a44087c5927a12dc8d4 late-profile sources provide the
shutdown/negative-control precedent, not a ready current runner. Update old
paths/locks/receipt identity, RTS parsing, workload and weak tiny-query oracle;
retain current foundation full-three-artifact/full-query checks.

If profiling cannot be linked/built, stop and seek separate admission for an
ordinary host-only getAllocationCounter probe at existing IO/demand boundaries.
No new forcing or quota enabling. That fallback can report raw/record/finish/
publication demand-window allocation, but cannot resolve closed/open/canonical
pure work or call late stamp cost exclusive encoding. Say what remains unresolved.

Detailed protocol: PROTOCOL-DETAIL.md. Exact local recovery evidence:
recovery-inputs.json. Package inventory: toolchain-profiling-inventory.json.
Build source names: proposed-build-closure.json. No executable controller exists.
