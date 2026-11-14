# putReferences ordinary compiler qualification supplement

This experimental archive preserves the complete source reconstruction,
ordinary producer recipe, completed correctness stages and one fixed benchmark
batch for the narrow reference-writer candidate. It is not a production merge.
The archive parent is `69cba865e7004d287ed52e4407571a6183fc8b1b`; archive ancestry
does not identify either measured compiler source tree or qualify an executable.

**A is the fixed F25 plus putVar baseline, not current main.** B adds only the
reviewed reference-writer change and its actually regenerated canonical builtin.
Nothing here qualifies current main, promotes production code, resumes native
fixed-point work or establishes parity with GHC. Production integration needs a
separate current-main source and toolchain-provenance comparison and appropriate
revalidation.

## Completed ordinary results

One fixed `ABBAABBAABBA` batch completed all 44 commands and twelve samples,
six per side. There were no added experiments, retries or resampling. Each
sample checked 475 fresh queries, zero reused queries, the complete ordered
query sequence, all 14 owners and three byte-equal artifacts against the same
frozen historical semantic oracle. That oracle supplies fixed expected bytes,
not current A timing. Independent final review passed 4,123 unique file pins,
all 36 artifact comparisons, runtime provenance and cleanup.

| Metric | A: F25 + putVar | B: plus putReferences |
| --- | ---: | ---: |
| Whole-process RTS allocated bytes, each of six observations | 59,767,632,472 | 59,579,696,480 |
| Guard wall-time median | 21.515000699000666 s | 21.24393128349766 s |

The within-batch allocation decrease is **187,935,992 bytes, 0.3144444313%**.
Allocation totals are identical across the six observations on each side for
this fixed workload. This is not exclusive allocation attribution to one helper
or a general workload result.

The separate wall medians differ by -1.2599089319%, but **no stable wall-time
speedup is established**. Four adjacent A/B pairs favor B and two favor A. All
twelve original values and all six adjacent pairs are retained, including the
slower cases. The median of pairwise A/B ratios is 1.0170849143579836, while the
ratio of the separate medians is 1.01275985183183; neither proves stable speedup.

Do not add this 0.3144% result to the earlier putVar batch's 0.4563% reduction.
They are different experimental batches with different measured baselines, not
a single end-to-end comparison. In particular, the current A allocation total
is not identical to the previous batch's B allocation total.

The BENCH guard-call envelope, including cleanup, is 331,359,806,755 ns.
The complete six-stage chain is 872,840,906,664 ns. Inner guard elapsed fields
are retained separately and exclude some cleanup; they are not substituted for
the integer envelope or summed as the chain duration.

## Correctness and source provenance

The six distinct stages remain distinct:

| Stage | Cleanup-inclusive duration | Reviewed outcome |
| --- | ---: | --- |
| Preliminary BUILD | 187.174471207 s | Expected stale-source-identity failure; producer remains unqualified |
| Actual canonical regeneration | 8.840708785 s | Actual generator stdout preserved in full |
| Clean formal BUILD | 210.779587016 s | 141 compiled modules, 13 links, 284 object/interface inputs checked |
| CLI CONTROLS | 3.996223552 s | Five exact cases passed |
| A/B VALIDATE | 130.690109349 s | 74 commands, 10 fresh links, both sides passed |
| Fixed BENCH | 331.359806755 s | Twelve samples, final independent review passed |

VALIDATE retained the original 64-command checks and added six reference
semantic commands plus four runtime checks. Each side passed exact codec
controls, eight reference-control groups, 39 direct cases containing 41 public
Unify calls, 23 separate public Unify cases and five CLI cases. The reference
controls use the current ordinary producer; they are not a new focused
allocation screen. Thirty-four actual runtime observations were checked during
VALIDATE, with 18 during BENCH. These finite controls are not a proof of
universal equivalence or native fixed-point qualification.

`evidence/stages.json` and `evidence/bench-review.json` retain bounded review
conclusions and original evidence identities. The original failure is not
relabelled as a successful build. No compiler, generator, test, target helper,
runtime loader or benchmark was executed for publication preparation.

## Reconstruct both complete compiler source trees

Start with public repository `https://github.com/mlf-lang/mlf` at commit
`f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`, tree
`3148203097e7622ced1b272e606bfa892fad746b`. Reuse these already published files
from immutable commit `12a27355827acc360b21b18ee717c4513baca2ff`, under
`tools/performance/codec-putvar-byte-screen-20261114/ordinary-qualification/`:

1. `source/01-public-to-F25-Graph.patch`
2. `source/02-F25-to-putVar-Bitstream.patch`
3. `source/B/bootstrap/MLF/BuiltinPreludeData.hs`

Apply both patches, then install that complete canonical builtin. This
reconstructs A, provenance commit `250e495d93de5fad975fb61c6e23a1ad1a964640`,
exact source tree `703052cd990d7f8e7d68cef856f6417cafbf0ffc`.

For B, additionally apply this supplement's
`source/03-putVar-to-putReferences-Bitstream.patch` and replace the builtin with
the included `source/B/bootstrap/MLF/BuiltinPreludeData.hs`. This reconstructs
formal provenance commit `9f2a1b16b9a997e78ea80912e1e4b55baa8264b5`, exact tree
`f768e86abbaba0a11bdcd66d3a7829943bd67b00`.

Both trees contain 3,872 tracked files. Only
`libraries/mlf-crates/Bootstrap/Bitstream.hs` and
`bootstrap/MLF/BuiltinPreludeData.hs` differ between A and B. All other 3,870
paths, bytes and modes remain unchanged. Always use `git apply --check` first.
The new patch is the exact full-index source-commit Git diff. Source provenance
commits are not assumed remotely available; the public base and archived bytes
are sufficient to reconstruct the source trees.

The A canonical is already archived in full and is reused by exact path/hash,
not uploaded again. The new B canonical is the full 2,220,407-byte actual
generator stdout, SHA256
`b1dc97803cc6c43efc623ed08640ca8c6896f8db121b389997285af13f816ad3`.
It equals the saved generated output, formal working file and committed blob.
The observed identity-token-only difference is a comparison result, not a
substitute for generation. No canonical file was manufactured by token editing.

`source-manifest.json` binds all reused and new source bytes. The included
static verifier reconstructs both complete Git trees in a temporary index and
object store without modifying the supplied repository:

```sh
python3 verify-source-reconstruction.py --repository /path/to/mlf
```

The archive checkout must contain the earlier putVar supplement. Otherwise
provide `--prior-archive /path/to/prior/ordinary-qualification`. The recorded
static check matched both complete trees, including every tracked path and mode.

## Producer and measured-binary recipe

`producer-recipe.json` contains both actual producer build commands, sanitized
environments, every producer command argv in its original order, flags,
toolchain/version identities, dependency package names, output hashes and the
four actual compile/link commands for the measured ordinary `emlf` relinks.
Only local path strings are replaced by labeled placeholders. Bind separate
`${A_SOURCE}`, `${B_SOURCE}`, `${A_BUILD}` and `${B_BUILD}` directories, plus the
listed toolchain and temporary-directory placeholders. The underlying source
build driver is `tools/shared/build.py`; its pinned invocation is:

```sh
"$PYTHON" -B "$SOURCE/tools/shared/build.py" --bootstrap-only --optimization 2 --build-dir "$BUILD"
```

The measured producers used GHC 9.14.1, Python 3.13.5 and GCC 14, `-O2`,
`-fpedantic-bottoms`, `-fno-state-hack`, the recorded explicit package database
and package flags, and a single-threaded build environment. This is an ordinary
non-profiled comparison. The measured `emlf` binaries are fresh relinks with
compiled-in RTS `-s` output and `-rtsopts=ignoreAll`, not simply the original
producer's executable. Follow the exact recorded argv when recreating that
distinction; hashes alone do not recreate omitted binaries.

The 14 workload source modules and their public source identities are listed in
`bench/workload.json`. Each original sample spec and measured binary has its own
hash in `bench/samples.json`. The full historical builtin/artifact oracle and
machine-specific length-prefixed crate specs are not bundled, so this archive
does not claim one-command reproduction of the complete measured environment.

## Evidence format and limits

`bench/samples.json` preserves all twelve samples, parsed RTS fields, artifact
identities and command guards. `bench/samples.csv` is the exact independent
review CSV. `bench/statistics.json` retains both original final and independently
recomputed statistics, including all six pairs. In each of the twelve raw RTS
files only the first command-header line is replaced with logical paths; every
following byte is unchanged, and original/public hashes are recorded separately.
`bench/guards.json` retains all 44 command completion, timing and resource-bound
records, omitting local paths and process/coordination identities.

Whole-process RTS allocation, focused current-thread allocation and profiled
self-allocation are different accounting domains. Guard wall time is not RTS
CPU or elapsed time. RTS times are rounded; the raw printed `%GC` field is
retained even when inconsistent and is not treated as measured GC share.
Maximum residency is sampled major-GC live data, not peak RSS; RTS memory-in-use
is not total process memory.

Installed dependency/toolchain files, compiled objects, large IR, complete
historical oracles and private coordination records are not published. Review
hashes cannot reconstruct omitted evidence. The preceding focused screen's
Bitstream object growth of 13,728 bytes remains disclosed there; no ordinary
code-size or exclusive helper-attribution conclusion is inferred here. This
single workload and fixed batch establish neither statistical significance,
stable wall gains, broad compiler speedup nor GHC parity.
