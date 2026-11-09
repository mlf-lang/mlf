# Decoding directly into indexed IO-world arrays

The checked binary graph decoder previously stored decoded nodes in an integer
trie for later lookup. The new path allocates the exact
number of slots after header and checksum validation, validates each entry in
canonical order and writes it directly to an `IndexVec` builder. Child reads
and each node write share one `ST IOWorld` action. A frozen snapshot serves
indexed lookups; legacy value trees are built only when requested. The
caller-supplied `decodeTables` entry retains its previous validation path.

The comparison uses #43 at `dbbd0aec` as the baseline and the dense decoder at
`320844cb` as the candidate. The baseline compiler was built from `14a7c1ce`;
the intervening commits changed tests and benchmark documentation, not compiler
sources. Both complete installations used GHC 9.14.1 with `-O2` on an Apple
M1 Max with 32 GiB and macOS 26.6.2. The native probes used Apple clang 21
with `-O2`. [All samples, hashes and correctness receipts](dense-decoder.json).

## Foundation query compilation

Each observation is a fresh compiler process compiling the same 14 modules
from `c5928b5b`. Each compiler has its own seed cache and builtin, restored
before every warm or edit run. The cold query store is empty but the builtin
is present. Filesystem caches were warm. Order alternated within each pair.
Times are arithmetic mean wall seconds; the last column counts pairs in which
the candidate was faster.

| Query state | Pairs | Before | After | Time change | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Warm, unchanged | 12 | 3.781 | 3.755 | -0.67% | 5/12 |
| One `Bootstrap.Version` edit | 12 | 4.022 | 3.963 | -1.47% | 9/12 |
| Cold query store | 3 | 19.266 | 19.095 | -0.88% | 3/3 |

The warm difference is small relative to the observed variation; three cold
pairs are insufficient to establish a cold-build speedup. The warm runs reused
all 504 query groups, the edit inferred one and reused 503, and cold runs
inferred all 504. Outputs and cache inventories were stable within each arm.

The runtime addition intentionally changes the builtin identity from `:12`
to `:13` and the primitive ABI from `mlf-primitive-133-v8` to
`mlf-primitive-134-v9`. Old builtin caches must therefore be rejected, and
cross-version artifacts need not be byte-identical. After removing only the
generated instance-hash suffix, all 504 query-group memberships matched in
each of the 27 unprofiled pairs; five generated instance groups had different
hashes before normalization. Five independent compiler-shaped programs also
produced byte-identical xMLF, passed checking in both versions, and executed
with the same output.

## Decoder-only measurements

The same candidate compiler and C runtime produced both probes, varying only
the old or new `Bootstrap.Bitstream` source. These numbers isolate decoding,
not native compilation of the compiler. They time multiple decodes of an
already-loaded input using `CodecProbe`'s internal clock; source compilation
and initial file loading are outside this clock. Each cell is the mean of 12
alternating pairs, with the same decoded node/root total checked in every run.

| Backend and input | Nodes / edges | Decodes per sample | Before (ms) | After (ms) | Time change | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Native, Foundation generation | 15,279 / 43,373 | 3 | 2,162.25 | 2,117.17 | -2.09% | 11/12 |
| Native, large result | 3,870 / 5,665 | 12 | 520.67 | 505.67 | -2.88% | 12/12 |
| Native, medium result | 501 / 676 | 40 | 279.25 | 271.17 | -2.89% | 8/12 |
| Native, synthetic distinct integer nodes | 20,000 / 0 | 6 | 1,000.08 | 927.08 | -7.30% | 11/12 |
| Interpreter, medium result | 501 / 676 | 3 | 1,067.25 | 919.33 | -13.86% | 12/12 |

Native before/after probes produced exactly the same detailed output for 110
default-limit valid and invalid wire cases. The candidate also matched an
independent Python reader on acceptance, and valid inputs re-encoded to their
original digest. The interpreted before/after probes matched on 17 selected
cases. Native boundary controls covered maximum depth and expanded work;
the broader IndexVec suite also exercised both backends' world-array aliasing,
snapshot, laziness, callback, region rejection and native GC behavior, as well
as separate-crate compilation.

## Reproduction

Use separate complete installations at `dbbd0aec` and the candidate revision.
Extract the historical Foundation fixture into an empty directory, and choose
a fresh output directory. The harness keeps all individual query reports,
timings, compiler hashes and cache contents under that directory.

```sh
git archive c5928b5b libraries/mlf-foundation | tar -x -C "$FIXTURES"
python3 -B tools/performance/dense-decode/foundation.py \
  "$BEFORE/bin/emlf" "$AFTER/bin/emlf" \
  "$FIXTURES/libraries/mlf-foundation" "$NEW_STUDY"
```

To construct the two decoder probes with the same candidate compiler and
runtime, run from the candidate checkout. `$WORK` must be an empty directory.
Select a generated query-graph file as `$INPUT`; the recorded generation and
result files use schema 6. Different compiler paths or source locations can
produce different content addresses, so compare the recorded input hashes
before treating a rerun as the exact same input.

```sh
mkdir -p "$WORK/before/Bootstrap" "$WORK/after/Bootstrap"
git show dbbd0aec:libraries/mlf-crates/Bootstrap/Bitstream.hs > "$WORK/before/Bootstrap/Bitstream.hs"
cp libraries/mlf-crates/Bootstrap/Bitstream.hs "$WORK/after/Bootstrap/Bitstream.hs"
for side in before after; do
  "$AFTER/bin/emlf" -i "$WORK/$side" -i libraries/mlf-foundation \
    --emit-llvm tests/indexvec/CodecProbe.hs > "$WORK/$side.ll"
  clang -O2 -Wno-override-module "$WORK/$side.ll" runtime/mlf_runtime.c \
    $(pkg-config --cflags --libs gmp bdw-gc) -lm -o "$WORK/$side-probe"
  "$AFTER/bin/emlf" -i "$WORK/$side" -i libraries/mlf-foundation \
    tests/indexvec/CodecProbe.hs > "$WORK/$side.xmlf"
done
python3 -B tools/performance/dense-decode/measure.py --backend native \
  --before "$WORK/before-probe" --after "$WORK/after-probe" --input "$INPUT" \
  --schema 6 --iterations 3 --rounds 12 --output "$WORK/native.json"
python3 -B tools/performance/dense-decode/measure.py --backend interpreter \
  --compiler "$AFTER/bin/emlf" --before "$WORK/before.xmlf" --after "$WORK/after.xmlf" \
  --input "$INPUT" --schema 6 --iterations 3 --rounds 12 --output "$WORK/interpreter.json"
```

The synthetic input can be regenerated with the independent Python fixture
writer as `explicit_document([], [(0, i) for i in range(20000)], list(range(20000)))`
from `tools/shared/artifact_binary_reference.py`; use schema 7 and six decodes.
Run correctness controls with the command documented in
[`docs/indexvec.md`](../../../docs/indexvec.md).
