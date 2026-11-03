# Prepared Prelude on the PR 25 crate driver

This branch starts at PR 25 head `c5928b5be73cd78d194405e734aa012415570e1a`,
base `0b738335a62b6f23a5b945da793c939b2b116b88`. It ports the prepared
Prelude used by PR 32 to the ordinary `emlf --compile-crate` command.

Both compilers verify their generated literal against fresh builtin compilation.
For an installed hit, the driver checks both formal artifacts under the existing
lock and compares the canonical installed interface with the compiler witness.
To install or repair, it decodes the bounded split literal, verifies canonical
re-encoding, relinks it, and compares the complete linked witness. A failed
embedded admission falls back to fresh preparation. PR 25 continues to use
its own text writer, source query v6 keys, raw object validation and cache
format. The checked split data is demanded only during installation or repair.

The production source transition has eight shared owners. The manifest binds
the complete 128-module parent and current registries and provides the exact
inverse for the session source used by retained historical controls. The
builtin fixture uses an independently checked target with an additional private
binding and the same identity, exports and interface to exercise rejection.

## Foundation protocol

Use the 14 original PR 25 Foundation modules, GHC 9.14.1 `-O2 -fpedantic-bottoms
-fno-state-hack`, and the normal compiler command in a fresh process for
every stage. Run the following independent comparisons. For each, take both
observations for each arm in the fixed order A, B, B, A.

1. Prepared PR 25 against optimized PR 32. Start with a valid per-compiler
   Prelude installation and an empty query cache. Measure cold compile, warm
   read and a leaf edit of `Bootstrap.Version` from 0.3.0 to 0.3.1.
2. The same pair, cold compile with the builtin installation and query cache
   both absent.
3. Original PR 25 against prepared PR 25, installed, with the same three stages.
4. The same original/prepared pair, first installation.

Record wall time, child CPU, peak RSS and cache bytes. Keep all the runs. Use
the arithmetic mean and require both paired wins and a mean reduction of at
least 2% to describe a cold lead. Source paths enter query keys. The recorded
comparison used the same absolute inputs and active paths as the preceding
PR 25/29 study so that prior per-ABI artifacts could be checked byte for byte.

Build each checkout with `python3 tools/shared/build.py --optimization 2
--bootstrap-only --build-dir .mlf-build/producer`. The portable replayer
ships on the PR 32 branch. Run it with two actual executables and a fresh output
directory, in each case using the original PR 25 Foundation source directory.

```sh
python3 "$pr32/tools/performance/foundation-query/compare.py" "$prepared25" "$optimized32" "$foundation25" "$work/installed"
python3 "$pr32/tools/performance/foundation-query/compare.py" "$prepared25" "$optimized32" "$foundation25" "$work/empty" --first-install
python3 "$pr32/tools/performance/foundation-query/compare.py" "$original25" "$prepared25" "$foundation25" "$work/before-after"
python3 "$pr32/tools/performance/foundation-query/compare.py" "$original25" "$prepared25" "$foundation25" "$work/before-after-empty" --first-install
```

## Measured results

Apple M1 Max, macOS 26.6.2, 4 November 2026. Each wall-time cell gives both
observations in execution order. The primary comparison uses the prepared
PR 25 source at `66208c2b` and the optimized PR 32 source at `84f60997`,
including its byte-action strictness fix, based on the current PR 29 head
`c0fffea2`. [All samples, executable identities, artifact sizes and SHA-256 hashes](results.json).

### Same prepared Prelude on both compilers

Prepared PR 25 took less time in both pairs for all four states. Mean warm
reads were 3.82 s on PR 25 and 9.45 s on PR 32. Cold means with an installed
Prelude were 19.76 s and 25.48 s. PR 32 used less disk space and less peak
memory on warm reads and edits.

| State | PR 25 + Prelude wall s | PR 32 wall s | Change in mean wall, PR 32 vs prepared PR 25 | Mean CPU s, A / B | Peak RSS MiB, A / B |
|---|---:|---:|---:|---:|---:|
| Cold, installed Prelude | 19.58 / 19.95 | 25.21 / 25.74 | +28.9% | 19.40 / 25.16 | 118.0 / 134.0 |
| Warm | 3.76 / 3.88 | 9.15 / 9.75 | +147.6% | 3.49 / 9.17 | 159.3 / 131.5 |
| Version edit | 3.53 / 4.23 | 9.32 / 9.47 | +141.9% | 3.56 / 9.25 | 167.9 / 131.7 |
| Cold, empty installation | 21.44 / 20.12 | 25.65 / 25.77 | +23.7% | 20.15 / 25.43 | 122.1 / 124.6 |

### Effect of the Prelude change on PR 25 alone

In the separate original/prepared comparison, the warm mean fell from
10.33 to 3.67 s and the installed cold mean from 26.38 to 19.73 s.
Each wall-time cell lists both samples from that arm.

| State | Original PR 25 wall s | PR 25 + Prelude wall s | Change in mean wall, prepared vs original PR 25 | Mean CPU s, A / B | Peak RSS MiB, A / B |
|---|---:|---:|---:|---:|---:|
| Cold, installed Prelude | 26.79 / 25.97 | 19.75 / 19.70 | -25.2% | 25.86 / 19.35 | 177.3 / 121.0 |
| Warm | 10.30 / 10.35 | 3.46 / 3.87 | -64.5% | 9.93 / 3.46 | 177.9 / 159.3 |
| Version edit | 10.09 / 10.32 | 3.58 / 3.60 | -64.8% | 9.89 / 3.54 | 177.8 / 169.3 |
| Cold, empty installation | 25.80 / 26.07 | 19.91 / 20.23 | -22.6% | 25.56 / 19.73 | 176.9 / 127.1 |

The logical cold caches occupied 104,053,739 B for the PR 25 family and
32,076,660 B for PR 32. After editing the caches were 104,410,605 B and
32,259,216 B, including the earlier record for the changed group. Each
compiler inferred all 504 groups cold, reused all 504 warm, and inferred one
group and reused 503 after editing.

For each of the 16 sequences, the independent audit reconstructed the full
stored source keys, verified their addresses and actual compiler identities,
and compared raw results with the appropriate compiler-family oracle. Each
installed sequence covered 505 distinct group versions and each first-install
sequence covered 504. Each final interface and object matched its own family
byte for byte. The binary family also matched all 83 context files. The
separate cross-family check matched all 511 binding schemes in 504 groups after
the known builtin ABI and instance-name mapping. Linking and evaluating
`Bootstrap.Version` produced `0.3.0` cold and `0.3.1` after the edit on
both compilers. The complete formal builtin pair matched the installed
reference even when installation started empty.
