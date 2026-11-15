# IntRank zero-contribution experiment

**Frozen narrow result: O0 and O2 each passed 18,525 fixture checks once. No acceleration claim.** This archive records a narrow emitted-code result at source commit `fc300bc9fdc389b585cbef0630fc8915d53e89c5`, using official GHC 9.14.1. It does not alter production sources.

## Result and costs

`candidate.patch` changes only `mapRankTree`: a zero-contribution branch passes the old offset instead of constructing `offset + 0`. In actual optimized Core/STG, both outer zero branches and both zero branches in all four reachable recursive joins pass the original offset directly. The accumulator thunk, addition and reboxing at those specific edges disappear. Contributing branches still lazily force offset before sibling size, add and box. Solver's actual rank consumers remain connected. This does **not** make rank allocation-free or establish workload importance.

The candidate moves the sign test before descent, including missing-key and Maybe-constructor-only observations that can leave the old offset thunk unforced. Recursive code is duplicated into four local joins. Actual whole-module `IntRank.o` `.text` increases **21,414 → 24,366 bytes (+13.785%)**; object file bytes increase 49,216 → 52,808. These are not function-only sizes. Dynamic effects and whole-compiler performance remain unknown. Compilation elapsed time is not used as a performance result.

## Evidence boundaries

- Baseline GHC compilation exited 0 for the 14-module Solver dependency closure, but the original capture remains **INCONCLUSIVE**. GHC wrote dumps beside absolute source filenames rather than in the expected dump directory. The original location/file-set checks failed.
- A separate posthoc identity and exact-recovery check recovered 42 dumps (14 modules × three dump kinds). It does not retroactively make that original capture pass.
- Candidate compilation used fresh objects and stdout dump capture. Its status is **PASS_CANDIDATE_DUMP_CAPTURE_ONLY**. Neither code-dump phase linked or executed a target.
- `core-witness.txt` and `stg-witness.txt` are small annotated selections of the actual dumps/stdout slices, not reconstructed or synthetic compiler output. Code lines retain their original content; relative source labels and line prefixes are export annotations. Original whole-file hashes and line ranges are included.
- `object-sizes.txt` normalizes only stage labels from actual read-only `size -A` output. `results.json` is a sanitized summary, **not an original run receipt**. Original complete successful and failed run evidence is retained separately.
- The unchanged archived fixture was actually compiled and run **once at O0 and once at O2**. Each returned exit 0, exactly the original frozen `18525 checks` golden stdout, and empty stderr. Actual compilation mappings identify the baseline `Bootstrap.IntRank`, renamed `IntRankCandidate`, and this `Main` source. Actual ELF binaries and byte-identical backups were verified. Six planned core steps and two dependency-metadata substeps completed. These are finite fixture results, not a general semantic proof, CI qualification, or whole-compiler result.
- The first semantic attempt remains **INCONCLUSIVE**, with **zero semantic executions**: its live output sampler encountered a disappearing transient GHC file and triggered cleanup after linking progress. Its original receipt SHA-256 is `dfef7148dc66cadfeda649bcf8bd863bc2b8177ee6246f4c6431cf97b2085da5`. The successful second attempt uses a separate new run directory; it does not overwrite or relabel the failure.
- Actual semantic evidence came from a separate bounded execution controller. **The public reproduction recipe below has not been executed or validated by running this export.** Results and hashes are recorded in `results.json`; full original binary/runtime and failed/successful evidence is retained separately.

## Files and licenses

`fixture/IntRankCandidate.hs` is the complete candidate module with only its module name changed for side-by-side testing. Original GHC/containers notices are retained. `fixture/Main.hs` is a narrow semantic probe adapted in part from the repository's Patricia design controls, not a benchmark. `LICENSES.txt` includes the repository and containers licenses; the candidate module retains its full embedded notice. The fixture catches only explicit synchronous `HostError`, not arbitrary or asynchronous exceptions.

`MANIFEST.json` hashes every payload file and deliberately excludes itself. It freezes the ten-file export only, not a producer qualification or an original-run seal.

## Reproduction recipe (not executed from this export)

Use a fresh checkout of the exact commit and an official GHC 9.14.1 installation. Use a new output directory, serial execution, fresh objects/interfaces and no inherited package environment. Do not reuse historical build products. The following is an argv recipe, not the original bounded capture controller and not evidence that this export has been run. Apply suitable time/memory/disk limits before using it; preserve failures as well as successes.

Run from the checkout root and set `archive` to this directory. Generate include arguments from the pinned `shared-sources.json`, not a guessed subset:

```bash
set -euo pipefail
src="$PWD"
archive="$src/tools/performance/main-baseline-gap-20261114/intrank-zero-contribution"
ghc=ghc  # independently verify this is official GHC 9.14.1
mapfile -t roots < <(python3 -c 'import json; print("\n".join(json.load(open("shared-sources.json"))["source_roots"]))')
includes=(-i)
for root in "${roots[@]}"; do includes+=("-i$src/$root"); done
flags=(-j1 -fforce-recomp -fpedantic-bottoms -fno-state-hack
       -Werror=incomplete-patterns -Werror=incomplete-uni-patterns -package-env -)
```

For actual Solver closure dumps, `out` must be a fresh directory outside the source checkout. Set `stage=baseline` or `stage=candidate`; create only that stage's new directories. For the candidate only, copy the original `libraries/mlf-foundation/Bootstrap/IntRank.hs` into a disposable overlay with the same relative path, apply `candidate.patch` there, and put `-i$overlay/libraries/mlf-foundation` before the original include roots. Leave the baseline checkout unchanged.

```bash
# baseline: extra=(); candidate: extra=("-i$overlay/libraries/mlf-foundation")
# Require a previously nonexistent output root; do not overwrite old evidence.
mkdir -- "$out"
mkdir -p -- "$out/objects" "$out/stubs"
"$ghc" --make -no-link -O2 "${flags[@]}" -i "${extra[@]}" "${includes[@]:1}" \
  -ddump-spec -ddump-simpl -ddump-stg-final \
  -odir "$out/objects" -hidir "$out/objects" -stubdir "$out/stubs" \
  "$src/libraries/mlf-inference/Bootstrap/Graph/Solver.hs" \
  >"$out/stdout" 2>"$out/stderr"
```

Capture stdout rather than using `-ddump-to-file` with assumptions about dump locations. Inspect baseline output first; stop if the targeted zero cost is already absent. Do not automatically chain compilation into semantic tests or benchmarks.

For separately admitted semantic checking, use the original baseline include roots and the renamed candidate fixture together. Build each optimization level in its own fresh `out` directory; replace `OPT` explicitly with `-O0` or `-O2`. The host FFI requires **both freshly compiled C objects** below. They are not optional, and must not come from a historical build. The captured plan used GNU GCC 14 with these C flags. Package isolation and the six explicit packages match that plan:

```bash
cc=gcc-14  # independently verify the compiler identity
# out must be a different, nonexistent directory for each optimization level.
mkdir -- "$out"
mkdir -p -- "$out/c" "$out/objects" "$out/stubs"
"$cc" -O2 -std=c11 "-I$src/runtime" -c \
  "$src/host/ghc/cbits/host.c" -o "$out/c/host.o"
"$cc" -O2 -std=c11 "-I$src/runtime" -c \
  "$src/runtime/mlf_process_supervisor.c" -o "$out/c/supervisor.o"
packages=(-clear-package-db -global-package-db -no-user-package-db
          -hide-all-packages -rtsopts=ignoreAll
          -package base -package array -package bytestring
          -package text -package containers -package directory)
"$ghc" --make OPT -XHaskell2010 "${flags[@]}" "${packages[@]}" \
  -i "-i$archive/fixture" "${includes[@]:1}" \
  -odir "$out/objects" -hidir "$out/objects" -stubdir "$out/stubs" \
  "$archive/fixture/Main.hs" "$out/c/host.o" "$out/c/supervisor.o" \
  -o "$out/semantic-probe"
# Running semantic-probe is separate. This exported recipe has not been run.
```

Preserve the actual source closure, binary, objects/interfaces, stdout/stderr, exit statuses, toolchain identity and dynamic-library identities. No fixture-only timing should be presented as whole-compiler speedup. End-to-end performance work requires a separate workload and qualification.
