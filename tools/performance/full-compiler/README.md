# Complete compiler endpoints and private projection views

Follow-up: the [2026-11-02 UTF-8 host fix](../llvm-memory/README.md) resolves the
LLVM-command memory failure and establishes a complete native MLF/GHC endpoint
comparison. The observations below remain the original, separate cohort.

Baseline is PR #25 at `5172c4ade3b3141da2e64593c383892575b36699`.
This replaces the earlier 14-module/711-group **screen** with the complete
recursive shared-source import closure of `MLF.Entry.Emlf`: 81 modules and
3,549,918 source bytes. Foundational, internal and generated target modules
are freshly compiled too. Other entrypoints, tests and unreachable modules
are excluded. The only external source import is `MLF.Primitive`.

## Complete workload and endpoint qualification

These are separate **single pilot observations**, not a repeated comparison
between equivalent compilation endpoints:

| Compiler | Endpoint | Fresh target | Wall seconds |
| --- | --- | --- | ---: |
| GHC 9.14.1 | Typechecked interfaces, `-fno-code -fwrite-interface` | 81 shared modules + original five-line Main | 4.601 |
| GHC 9.14.1 `-O2 -j1` | Runnable compiler, including link | Same 81 + Main | 53.418 |
| Ordinary GHC-built MLF | Checked MLF/xMLF crate | 3,710 groups / 0 reused | 281.199 |
| Same MLF | Checked crate to LLVM | Same complete checked input | Failed at existing 5 GiB RSS ceiling |

The checked qualification's ordered query members cover all 80 value-bearing
modules; the remaining `Bootstrap.Types` is datatype-only. No unknown or
outside-module member was counted. Fixed primitive/host adapters, installed
GHC packages and builtin/runtime dependencies may be reused. Target query and
object caches may not replace fresh compilation.

The checked stage recorded 273.014s user and 7.137s system CPU, with 281.131s
stage wall (281.199s exact outer child wall). This is coarse CPU evidence, not
an exclusive phase breakdown or an exact estimate of I/O waiting. Checked
artifacts were 5,844,550 bytes `.mlfci` and 168,003,628 bytes `.mlfco`; its fresh
query cache occupied 1,673,402,522 bytes.

A logging-only audit on the second LLVM attempt observed process-group RSS
5,369,446,400 bytes against the unchanged 5,368,709,120-byte limit. The initial
SIGKILL succeeded. Existing Darwin cleanup then mistook transient `?E`/zero-RSS
state for a live descendant, and a later EPERM obscured the original RSS error.
The audit retains both events; no matching descendant remained and no LLVM IR
was produced. The first attempt also overlapped a qualifier-only edit and is
not valid timing evidence. Resource bounds were not raised. **Complete native
MLF compilation, self-bootstrap and a same-endpoint MLF/GHC ratio have not
been established.** Ordinary serial Clang `-O2` remains the native policy.

## Projection and restoration cost map

An independent diagnostic producer recompiled the affected closure and counted
work at ST continuations with CSE/full-laziness disabled. Its full 3,710/0 task
and direct raw-byte comparison against the accepted reference passed. It saw:

- 530,445 projection/restoration operations;
- 18,703,451 selected nodes and 17,261,857 remaining local nodes;
- 6,249,440 node-map updates: 4,011,499 replacements and 2,237,941 deletions.

The sum of global map sizes across those operations is 37,853,823,056. This is
**not** a count of globally visited nodes, a CPU share or evidence of quadratic
scanning. These source-level quantities locate repeated materialization work;
they do not establish which phase dominates ordinary execution.

The first candidate used bulk Patricia difference/union for at least eight
updates. Its fixed full-task ABBA window passed all fresh/raw checks but slowed
from geometric 279.208s to 280.416s: **-0.4325%** point improvement. It was
rejected without extra samples or conditional guard runs. Its complete source,
controls, failed build preflight and closed data are retained separately.

The retained candidate is much smaller: use the selected map's cached
cardinality instead of traversing `originals`, and fold the solved map directly
into its ascending filtered list instead of allocating `toList` followed by
`filter`. Ordinary O2 Core inspection confirms `length originals` became
`sizeTree` and the intermediate filtered list is absent. No removal of checks,
node comparisons, restoration, delta computation, per-key graph updates,
index writes or scope checks is involved. No cache crosses operations.

## Closed structural-change screen

The second candidate and its protocol were frozen before four **new** full-task
executions, ABBA. Each run inferred 3,710 fresh / 0 reused groups, checked ordered
group identities and directly compared `.mlfci` and `.mlfco` raw bytes with the
independent accepted-baseline output. Primary statistic: mean of two adjacent
paired log B/A ratios. Acceptance requires strictly positive **unrounded** point
gain, according to the user's structural-change rule. No sample was excluded,
replaced, pooled with the rejected candidate, or added.

| Input | A/B executions | Geometric A/B seconds | Point improvement |
| --- | ---: | ---: | ---: |
| Complete frozen compiler | 2 / 2 | 279.025345 / 278.983135 | 0.015128% |
| flat_functions-512 | 2 / 2 | 3.726857 / 3.765070 | -1.025343% |
| higher_order_chain-128 | 2 / 2 | 0.911603 / 0.932648 | -2.308531% |

The two compiler pairs point in opposite directions: about 0.126% slower and
0.156% faster. The net saving is only about **0.042 seconds**. This passes the
predeclared positive-point rule but does **not** establish stable acceleration,
significance or a meaningful reduction of the MLF/GHC gap. Both guards are
slower; their roughly 0.038s and 0.021s delays stay below the fixed rejection
rule, which requires both >5% and >0.1s. Both shape cells retain all three
closed-form native execution checks. No independent confirmation was run.

## Semantic domain and qualification

The helper is private. Its callers provide finite canonical maps with strict
integer keys and finite cached counts; Node payloads retain their original
partial-value demand. The complete O0/O2 controls preserve all 63 earlier
physical graph/index/scope traces, exact errors and failure Store epochs, eight
earlier demand observations and 29,160 survivor-delta models. New controls add
720 independent `Data.Map.Lazy` view/cardinality cases over signed/wide IDs,
dense/gapped layouts and cutoff boundaries, plus nine payload-demand/first-error
observations. Dependencies are authenticated ordinary O2; the local owners are
compiled separately at O0 and O2.

An additional, deliberately malformed map with a bottom key **and** bottom count
exposed different O2 exception order (old count first, new key first; O0 agreed).
That input cannot arise at this private callsite: map constructors have forced
the keys and cached cardinality. The failed diagnostic is preserved and no
universal forged-state/partial-argument equivalence is claimed. The final gate
uses canonical finite keys/counts with competing partial Node payloads and
retains all earlier public-path demand controls. This scope was documented
before any ordinary timing of the candidate.

All 16 integration checks passed: the original C3 and survivor gates against
their earlier complete owners, P1–P3, graph/transaction, map balance, validation,
builtin, parsed-file controls, native library (ordinary Clang O0/O2), native
containers, fingerprint, direct compiler/entry tests, frozen optimizer, native
IO, actual `mlfpkg --locked plan`, and static snapshot. The candidate also checked
its **current** complete 81-module source with 3,711 fresh / 0 reused groups;
this is a separate correctness qualification, not an extra performance sample.

Source admission changes only `Bootstrap.CrateSession`; all 127 other shared
identities and all historic manifests/oracles remain intact. A pinned exact
inverse recovers the accepted full owner for historical source proofs only;
runtime candidates remain complete. Builtin regeneration is unnecessary because
its entire preparation closure is unchanged. The source lock was refreshed.
CI retains the O2 controls, source copies and logs plus the five arithmetic
fixtures for the descriptive decision.

The optional framework harness controls exposed an existing macOS temporary-path
alias mismatch, reproduced on the frozen baseline (59 subtest failures/one error).
A canonical `TMPDIR` passed all 31 unchanged methods for both baseline and current
sources. No test body, compiler or resource guard was changed for this issue.

## Reproduction and evidence

With an authenticated ordinary producer and its source checkout, freeze a fresh
workload (this reads imports and hashes sources; it does not compile):

```sh
python3 -B tools/performance/full-compiler/prepare_workload.py \
  --source "$SOURCE" --label "$SOURCE_ID" --output "$WORK/workload.json"
```

Use fixed dependencies prepared by `compiler-shapes/prepare.py`. For GHC's
original Main wrapper its **private** primitive package must expose `MLF.Host.IO`
in addition to `MLF.Primitive`; this task retained the updated private package
configuration and receipt. Do not modify the global package database.

```sh
python3 -B tools/performance/full-compiler/qualify.py \
  --workload "$WORK/workload.json" --setup "$SETUP/setup.json" \
  --producer "$PRODUCER" --producer-source "$SOURCE" \
  --lane mlf-checked --output "$WORK/checked"
```

Other explicitly qualified lanes are `ghc-check`, `ghc-objects`, `ghc-native`,
`mlf-llvm` (requires `--checked-prefix`) and `mlf-native`. Each output directory
must be fresh. The qualifier independently checks import closure and inventory,
source and producer identity, fresh work, exact GHC source compile provenance,
and authored native CLI behavior. Optional `--reference-prefix` performs direct
checked-byte/group comparison. All timing uses the retained exact-child resource
runner; no native result is inferred from a checked result.

For the narrow semantic gate:

```sh
python3 -B tools/performance/full-compiler/run_controls.py \
  --producer "$PRODUCER" --producer-source "$SOURCE" \
  --optimization 2 --output "$WORK/controls-o2"
python3 -B tools/performance/full-compiler/test_contract.py
```

Use a distinct fresh output for optimization 0. Full Git history is required.
The unchanged `process-spawn/compare.py` executes frozen configs and preserves
all raw bytes and freshness/resource receipts; `full-compiler/analyze.py` adds
the fixed four-run descriptive rule, without editing historical analyzers.

[Machine-readable results](results-20261101.json) bind all closed plans and
receipts. Original full task data are under `.mlf-build/full-compiler-20261101/`;
accepted-candidate data are under its `projection-spine-02/` child. The first
candidate's immutable source/tool snapshot is in `rejected-bulk-patch-01/`.
Its build initially aborted correctly when the mutable-size guard scanned the
historical evidence root. A fresh, bounded candidate-only build scope solved
that preparation error with unchanged limits; no timing sample was replaced.
