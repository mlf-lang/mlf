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
