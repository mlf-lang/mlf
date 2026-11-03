# Complete compiler: bounded LLVM generation and native endpoint comparison

2026-11-02, PR #25 parent `9dfcd6625775819568eaaa5065f8dd1431df52f8`.
This closes the memory failure in the [previous complete-compiler study](../full-compiler/README.md).
The production change is confined to `host/ghc/MLF/Host/Base.hs`.

## Cause and change

The command called “checked to LLVM” exceeded the unchanged 5 GiB process-tree
RSS limit **while decoding the full compiler object**, before linking the
checked terms or generating LLVM. A renamed Main linked to the ordinary
producer objects reached interface loading and builtin object decoding, then
failed before the full object returned. The preserved failure sampled
5,389,058,048 bytes RSS. This is phase localization, not an exclusive cost profile.

The old GHC host String stored strict UTF-8 Text, its Unicode scalar length,
and a lazy boxed `Array Int Char`. An all-ASCII text used direct byte access;
one Unicode literal in a large object made indexing/slicing force the entire
boxed scalar array. Nested framed fields reconstructed large strings through
lists of boxed characters and could materialize further arrays. The diagnostic
object was 168,003,628 bytes / 167,988,512 scalars. Reading it and indexing just
its first character alone peaked at 1,857,601,536 bytes; that first-index probe
did **not** by itself explain the 5 GiB failure.

The private host representation now stores one unboxed UTF-8 byte offset per
256 scalars. An ASCII block uses direct offset arithmetic; a mixed block scans
at most 255 scalar leads from its checkpoint. Slicing translates scalar bounds
to byte offsets and copies Text directly, instead of constructing a character
list. The whole-text ASCII path, scalar semantics, argument strictness order,
bounds checks, primitive signatures, and integer semantics are preserved.
The index is still lazy; first non-ASCII access builds it with a linear pass.
This trades bounded local scanning for a much smaller index. It is a GHC-host
representation fix, not a change to shared inference algorithms or the native
C runtime's String implementation.

With this change, the same staged diagnostic decoded both objects, linked the
checked terms and emitted 66,263,039 LLVM bytes in 74.859 seconds, peaking at
2,681,716,736 bytes. These diagnostic runs are not ordinary performance samples.
An initial fresh full native qualification also completed: 397.184 seconds,
3,711 fresh / 0 reused groups, sampled peak 3,091,988,480 bytes.

## Fixed ordinary native comparison

`compare_native.py` froze a four-run **MLF / GHC / GHC / MLF** order before
execution. There were no exclusions, replacements or extensions. The initial
qualification and diagnostic runs are outside this cohort. The primary result
is the geometric MLF/GHC ratio of the two adjacent pairs, reported descriptively.

Both endpoints now compile the complete recursive shared-source closure of
`MLF.Entry.Emlf` (81 modules) to a runnable compiler, including native linking.
MLF is the ordinary GHC-built compiler. Each MLF run infers all 3,711 groups
fresh, reuses zero target groups and compares both checked artifacts' **raw
bytes** and ordered group identities against the independent pre-change output.
Each GHC run builds all 81 target modules plus the original five-line Main
wrapper afresh. Fixed primitive/host libraries, builtin objects and runtime
dependencies are reusable; target query/object caches cannot substitute for
the work. The two languages' checking/backend pipelines still differ.

| Order | Compiler | Whole endpoint seconds | Sampled peak RSS GiB |
| ---: | --- | ---: | ---: |
| 1 | MLF | 419.945 | 2.607 |
| 2 | GHC | 59.669 | 1.151 |
| 3 | GHC | 59.513 | 1.209 |
| 4 | MLF | 433.156 | 2.630 |
| Geometric mean | MLF / GHC | **426.499 / 59.591** | — |

The complete native-task ratio is **7.157×**. Two observations per side do not
establish a confidence interval, stability across machines or a general
language ranking. The previous implementation did not complete this endpoint
under the resource cap, so no percentage native speedup over it is claimed.

| MLF stage | First run seconds | Second run seconds |
| --- | ---: | ---: |
| Source to checked crate | 300.293 | 310.894 |
| Checked crate to LLVM | 73.519 | 74.421 |
| LLVM to executable | 46.060 | 47.752 |

The checked stage is about 72% of these complete-task wall observations. This
identifies the larger remaining stage, not the cause of its cost or the
exclusive contribution of projection/restoration. Stage sums differ slightly
from exact outer wall because of worker startup and bookkeeping.

All runs retain ordinary single-job Clang `-O2`, GHC 9.14.1 `-O2 -j1`,
`-fpedantic-bottoms -fno-state-hack`, 5 GiB process-tree RSS, 5 GiB free disk and
3 GiB estimated available host memory floors. Full native endpoints have the
existing 600-second limit. On this macOS machine RSS is sampled at 100 ms and
can miss short peaks; the 6 GiB per-process address-space limit is enforced on
supported Linux hosts, not Darwin. No resource protection was disabled or raised.

## Validation and reproducibility

- `run_controls.py`: complete frozen old host owner versus current owner, plus
  an independent Prelude character-list oracle. Both O0 and O2 pass 94 Unicode
  fixtures, every scalar, slices around 256-scalar boundaries, supplementary
  characters, combining sequences, empty inputs and exact bounds errors.
- `test_contract.py`: exact full-owner inverse to Git, full forward transition,
  corrupted manifests and changes outside the String regions fail closed.
- `host-delta.json` adds a pinned host-only transition to the existing source
  admission chain; no old semantic oracle or source contract is removed.
- `check_native.py`: exercises each generated compiler on datatype/polymorphic
  Unicode source, interpreter execution, LLVM emission, ordinary Clang O2
  execution and a type error. Its results and the complete integration gate
  inventory are recorded in `results.json`.
- CI retains the focused Unicode controls, contract tests and raw evidence.

Raw local evidence is under `.mlf-build/llvm-memory-20261102/`: the unsuccessful
old `stage-probe`, successful `compact-stage-probe`, `controls-o0`, `controls-o2`,
`native-qualification-01`, the closed `native-comparison`, integration `gates`,
and native compiler behavior checks. `results.json` binds those receipts and
key source/artifact identities. The comparison plan and controller/worker
copies are preserved in the cohort directory; its underlying endpoint
qualifiers retain `performance_samples: 0` because they are qualifications,
while the enclosing frozen plan explicitly designates their four ordinary wall
observations as this descriptive endpoint comparison.

Reproduce focused checks against an authenticated ordinary O2 producer:

```sh
python3 -B tools/performance/llvm-memory/test_contract.py
python3 -B tools/performance/llvm-memory/run_controls.py \
  --producer .mlf-build/shared-ghc --optimization 2 \
  --output .mlf-build/llvm-memory-fresh-controls
```

For a new full comparison, prepare the current 81-module workload and fixed
dependency setup with the existing full-compiler/compiler-shapes tools, then
invoke `compare_native.py` with `--producer`, `--workload`, `--setup`,
`--reference-prefix` and a fresh `--output`. The reference must be independent
pre-change checked output for those exact shared sources. Existing completed
cohorts are immutable and must not be extended.
