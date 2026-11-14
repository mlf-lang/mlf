# putVar ordinary compiler qualification supplement

This supplement preserves the complete source changes and actual generated
builtin literals for the ordinary F25 versus putVar comparison. It is an
experimental evidence archive, not a production merge. Archive ancestry does
not identify either measured source tree.

## Current reviewed stages

The formal putVar producer's ordinary BUILD passed in 231.642454 seconds,
followed by five CLI CONTROLS in 3.923026 seconds. Independent review verified
141 compiled modules, 13 links, the actual regenerated builtin, the complete
284 object/interface input inventory and the ordinary producer handoff.

The subsequent A/B VALIDATE stage passed in 109.706295 seconds with all 64
commands independently checked. Each current ordinary producer passed exact
codec controls, 39 direct cases with 41 public Unify calls, 23 separate public
Unify cases and five CLI cases. Eight fresh links and 30 recorded runtime
observations were checked. These are finite semantic controls, not universal
equivalence, native fixed-point qualification or a speed result.

The fixed twelve-sample BENCH batch and its final independent review passed.
The review checked 3,961 unique pins, all 44 commands, twelve samples, all 36
artifact byte comparisons, all 14 owners and 18 runtime observations. Only the
completed batch is summarized below; no intermediate samples were used. GHC is
the common host toolchain, not a separately timed competing compiler. Nothing
here establishes GHC parity. See `evidence/bench-review.json` for the bounded
review conclusions and original evidence hashes.

## Completed ordinary allocation and timing observations

The single batch used the original `ABBAABBAABBA` order, six runs per side, and
completed all 44 commands in 324.934464 seconds with cleanup. There were no
added samples, retries or resampling. Each sample checked 475 fresh queries,
zero reused queries, the complete ordered query sequence, all 14 owners and
three byte-equal artifacts against the frozen historical oracle.

| Metric | A, ordinary F25 | B, putVar | B relative to A |
| --- | ---: | ---: | ---: |
| Whole-process RTS allocated bytes, every sample | 60,041,191,800 | 59,767,241,312 | -273,950,488 bytes, -0.4562709% |
| Guard wall-time median | 20.780483427 s | 20.669687405 s | -0.5331735% |

The small allocation reduction occurs in all six observations per side on
this fixed workload. **No stable wall-time speedup is demonstrated:** only two
of the six adjacent A/B pairs are faster for B; four are slower. The median of
adjacent A/B time ratios is 0.983263526, unlike the ratio of separate medians
(1.005360314). Neither statistic justifies a general speed claim.

`bench/samples.json` retains all twelve samples and complete parsed RTS fields;
`bench/statistics.json` retains the original metric values and all adjacent
pairs. All twelve `bench/raw-rts/*.sanitized.rts.txt` files preserve every
numeric/log byte after the command-header line. Only that first line has its
machine-specific paths replaced with logical placeholders; original and
published file hashes are recorded separately. `bench/guards.json` preserves
all 44 command completion/time/bound records and the outer guard, omitting
absolute paths and machine/process identities.

RTS allocation is a whole-process total, not the focused current-thread counter
or profiled self-allocation. Guard wall duration and rounded RTS CPU/elapsed
times are separate accounting domains. The raw printed `%GC` field is retained
even when inconsistent and is not interpreted as measured GC share. Maximum
residency is sampled major-GC liveness, not peak RSS; RTS memory-in-use is not
total process memory. This one workload/batch does not establish exclusive
attribution, statistical significance, broad compiler speedup or GHC parity.

## Reconstruct both complete source trees

Start with public repository `https://github.com/mlf-lang/mlf` at commit
`f9bdb40a659bfdff4cbb782d438afbb0417dd2e1` in two fresh, separate checkouts.
The expected public tree is `3148203097e7622ced1b272e606bfa892fad746b`.

For **A**, apply `source/01-public-to-F25-Graph.patch`, then copy the exact
archived `source/A/bootstrap/MLF/BuiltinPreludeData.hs` to that same
repository-relative location. This reconstructs F25 source tree
`4d2f8e37b1cc3eb2497cf17b62917009af3e6c25`.

For **B**, first perform A's reconstruction, then apply
`source/02-F25-to-putVar-Bitstream.patch` and replace the builtin with the exact
archived `source/B/bootstrap/MLF/BuiltinPreludeData.hs`. This reconstructs the
formal putVar source tree `703052cd990d7f8e7d68cef856f6417cafbf0ffc`.

Always use `git apply --check` before applying a patch. Both full canonical
builtin files are included, each 2,220,407 bytes. They were copied from the
actual measured source snapshots, not created by replacing an identity token
for publication. B's file is byte-identical to the actual candidate generator
stdout, SHA256
`59e86f76049a60b50602533037b42246ce5f8d403d44b07f9f53c95ec4c9d050`.
All expected source identities, file hashes, modes and tree identities are
described by `source-manifest.json`.

For a static full-tree check, run:

```sh
python3 verify-source-reconstruction.py --repository /path/to/mlf
```

This uses a temporary index and object store to reconstruct both exact Git
trees from the public base. It does not modify the supplied repository's
working tree or index, create a commit, compile, generate or benchmark.
Exact tree equality binds all 3,872 tracked paths, file bytes and modes, not
only the three changed files. The local provenance commits recorded in the
manifest are not assumed to be available remotely.

## Preserve generation and the original failed stage

The preliminary candidate build stopped at its intended stale-source-identity
check after 187.252988 seconds. Its actual error was
`prepared Prelude build source identity is stale`. That producer was not
qualified, and its later success tail and controls were not run.

The candidate's own real generator was subsequently run in a separate bounded
stage. It completed in 8.399597 seconds and emitted the archived B builtin.
Independent whole-file comparison found only the source-identity token changed
relative to the original canonical literal, but this is a comparison result,
not a substitute for generation. A clean formal source then used that actual
output; the formal BUILD and builtin checks passed independently. The original
failed stage remains failed. `evidence/stages.json` records these distinct
outcomes and their report hashes.

## Reproduction boundaries

The archive makes both exact compiler source trees reconstructible from a
public commit. Building them still requires the ordinary checked pipeline and
the toolchain/dependency setup summarized in the stage evidence. It does not
bundle installed packages, compiled objects, a complete machine image or the
historical semantic oracle. Source reconstruction is not a claim that the
entire measured environment is reproduced by one command.

No compiler, generator, test or benchmark was rerun for publication preparation.
No production source is overwritten in this experimental branch. Do not infer
stable wall-time gains, native-generation/fixed-point qualification or GHC
parity from the focused allocation screen or these correctness stages.
