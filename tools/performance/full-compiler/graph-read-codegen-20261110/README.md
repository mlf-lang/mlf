# Graph read fusion: ordinary code-shape checkpoint

This checkpoint supports a **small ordinary Graph benchmark**, not a measured
compiler speedup. No benchmark or compiler link ran in this capture. Full90
single-crate and split qualifications still failed their600-second guards.
Native self-host A/B and fixed-point campaigns remain paused.

Production inputs are frozen at `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
The candidate changes only54 saturated calls across34 bindings in
`libraries/mlf-inference/Bootstrap/Graph.hs` from `readDense low array identity`
to its definition `readSTArray array (identity - low)`. Public helpers, writes,
the separate parent-replay optimization, Base/Primitive, and flags are unchanged.
The [candidate and semantic recovery checkpoint](https://github.com/mlf-lang/mlf/blob/7d03b4c6278317f743311392d5d4cc3606ab1bc0/tools/performance/graph-read-fusion/README.md)
is separately published. The source candidate SHA256 is
`fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3`.

## Evidence and limits

The exact candidate first passed a41.017-second semantic gate with O0 and O2
controls:12,000 validation outcomes;5,616 public unifications;480 signed/sparse
layouts;20 placement-demand and6 alias controls;120 valid complete normalization
graphs;21 read action/offset/array/cell/sharing controls. This finite corpus is
not a proof that every branch or graph is covered.

Capture01 failed after6.297seconds because one-shot GHC `-c` searches its
`-hidir` for imported interfaces. The original controller had placed those
interfaces only in a separate `-i` directory. No owner object was emitted and
the candidate compile never started. Failure evidence was retained. Reviewed
version2 changed only the private interface layout: the same authenticated
non-owner `.hi` files were copied and hash-checked in each side's `-hidir`.

Capture02 completed in24.718seconds, peak process-tree RSS312.7MB, within the
unchanged180-second guard. Both receipts completed,17 subprocess commands
exited0 with no terminal live descendants, and both locks were independently
reacquired. All20 input,420 borrowed-interface and339 output hashes rechecked.
Both sides used real module name `Bootstrap.Graph`, identical ordinary GHC9.14.1
`-O2 -fpedantic-bottoms -fno-state-hack` flags and imported interfaces. No renamed
semantic object was substituted. The rebuilt baseline `.o` **and** `.hi` were
byte-for-byte identical to the authenticated original producer's artifacts.

- `denseChild1 -> $wdenseContains`: three helper calls become three checked array
  loads with two delayed offsets. The unchanged caller did not acquire replacement
  read-action closures. Along one newly constructed action executing all three
  successful reads once, local owned allocation is statically352→176bytes.
  This excludes arbitrary argument-thunk evaluation and GC. Construction without
  execution instead grows96→104bytes; replay does not have the one-shot total.
- `densePlace`: action construction drops168→120bytes. The checked colours,
  grafted, parents and classes reads are fused inside the action with a shared
  offset rather than recreated helper actions.
- `$wdenseCheckOriginal`: entry allocation stays120bytes. Its later reads fuse,
  but this is not a claim that every entry or whole-function allocation shrinks.
- The already-partly-inlined `$wdenseGetNode` worker still constructs40bytes.
  Public `readDense` and `writeDense` remain with56-byte and64-byte entries.
- Whole-object direct `readDense` jumps fall66→0, only secondary static evidence.
  `.text` grows346,382→354,814bytes (+2.43%); object file size grows
  781,024→794,184bytes. These counts are not dynamic savings or throughput.

`summary.json` gives exact artifact/receipt hashes, caller labels and local dump
line references. Raw Core/Cmm/objdump, full receipts, interfaces and objects stay
local and **are not recoverable from this Git checkpoint**. Hashes are identity
records, not promises that the corresponding large files were uploaded.

## Recovery source and boundaries

`source/run.py` is byte-identical to tested version2. `source/run-v1.py` is the
retained failed version; do not use it as the corrected entry. Their hashes and
the original tested shell's hash are in `source-sha256.json`.

The published `source/run-gate.sh` is **not the tested shell**: its private
absolute lock path was replaced by required environment variable
`MLF_SPRINT_LOCK`. This small portable wrapper has not been executed. No claim
is made that it reproduces the old result without another reviewed run.

Restore the [B0 producer/toolchain](../baseline-20261110/README.md) first. Restore
the candidate checkout and its semantic controls separately. Put the Python
controller and wrapper in sibling directory `compiler-graph-codegen-gate-20261110`
beside `compiler-baseline-20261110`, `compiler-toolchain-20261110`, and
`compiler-graph-read-fusion-20261110`. Do not run the archive in place.

The source intentionally freezes the original producer receipt and semantic
owner hashes. Reconstructed receipts may have different timestamps and hashes;
establish and review a new coherent identity instead of silently weakening checks.
An admitted new capture would use:

```
export MLF_SPRINT_LOCK="$REPRO_ROOT/shared-sprint.lock"
bash "$REPRO_ROOT/compiler-graph-codegen-gate-20261110/run-gate.sh" \
  "$SEMANTICS_ROOT" "$NEW_CAPTURE_ROOT"
```

The new output root must not exist. Retain both serial locks and all original
limits:180seconds total,6GiB address space per process,5GiB tree RSS,3GiB host
available floor,5GiB disk-free floor and4GiB output ceiling. A capture failure
stops the attempt; it does not authorize a retry or larger budget.

Capture completion is not mechanism approval, and mechanism approval is not
permission to execute a benchmark. A separate short Graph experiment can reuse
the semantic probe only after its own authentication and admission. A later
compiler experiment must rebuild affected reverse dependencies; mixing this
owner with stale Solver/Constraint unfoldings is not a valid candidate compiler.
No complete90-module compiler/GHC ratio is available.
