# Fresh ordinary producer qualification

Executed once as admitted F3-producer-01. The original actual-generator gates
verified the complete canonical bytes. See producer-01-summary.json. The admitted
pre-run plan SHA256 was c030b0e65bfae2b32bd88fa6227cd7e1b8f913d3b72075911078ee5691aa4bf3.
This restored plan does not authorize another build.

## Source boundary

This separate checkout starts at the preserved F3 checkpoint 9c9d2fe0. The old
Graph-only source and all previous receipts remain unchanged. Relative to f9:

- Bootstrap.Graph retains the 54 read-action expansions, SHA256
  fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3.
- MLF.BuiltinPreludeData was prepared as an unverified derived candidate, SHA256
  c0d4205ebfe8fde9fddf7ab63442558ada389056916fa2fe41dfc94b90297be8.
  Only its unique first RawPrelude source-identity string changes. The original
  2,220,407-byte canonical SHA256 is
  4b9d52fa6fa2108cc3dc1a6d04e06f18486abff4f2e682f633bddeb674c03692.
  Inverse replacement must restore every original byte.

The unchanged official identity algorithm follows exactly 56 nongenerated
modules. Only Graph differs. The old identity suffix is
7190a5739fd1a1f55dbb0762a9129b83aeb0a6ca81e518cd2e8ca598cd845620;
the new one is
dc560ede03721d9bff79319b3cc8c3de81110c2acbe4e8a7c1186d7db79a0214.
This correct derived value is not an actual-generator claim until the original
fresh verification succeeds. No manifest, host adapter, compiler flag, builtin
validator, generation function, or build driver changes.

## Build and original gates

build-producer.py is a thin transport around unchanged tools/shared/build.py:

    python3 -B tools/shared/build.py --bootstrap-only --optimization 2 \
      --ghc "$QUALIFIED_GHC" --cc "$QUALIFIED_CC" --build-dir "$OUTPUT/producer"

The original build forces all 137 shared and four host modules with GHC --make,
-j1 and -fforce-recomp, records their actual paths and inferred interfaces, and
links all 13 executables. The output is fresh; no .o/.hi is borrowed. Ordinary
-fpedantic-bottoms/-fno-state-hack and package isolation remain unchanged.
bootstrap-only avoids the default native installation flow. It is not a compiler
generation A/B test, native bootstrap campaign or fixed-point operation.

The unchanged check-candidate reconstructs the complete fresh Prelude structure
and object. The unchanged fresh-literal command then generates real stdout from
the nongenerated source closure and requires the entire output to equal the
candidate canonical bytes. Any failure stops without replacing expected data or
retrying. Only these complete gates can verify the derived candidate.

After normal build completion, authenticate the entire fresh producer, confirm
all source/host/config inventory sets and toolchain/installed dependencies and
Python identity, and compare ordinary flags modulo owned source/output paths.
Run fixed CLI version/identity checks, one positive expression producing 42 and
Unicode text, and one invalid stringLength 1 expression requiring exit 1 and the
specific type-constructor mismatch diagnostic. Reauthenticate after these checks.
These small tests qualify this producer, not compiler throughput or the frozen
inference11 workload's artifact compatibility.

## Supervision and environment

Reuse unchanged f9 resource_watchdog.py, SHA256
5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f.
Its tracked PID/start_ticks and PPID descendant closure covers the existing
builtin verifier's separate sessions. Do not modify subprocess grouping or the
validator's timeout/kill behavior. One total 600-second scope contains source
preflight, build, original builtin gates, CLI/semantic checks and final producer
authentication. AS=6144 MiB per process, tracked RSS=5120 MiB, host free floor=3 GiB,
disk free floor=5120 MiB, output ceiling=3072 MiB. Keep external team flock and the
baseline producer lock. A failure is preserved and never automatically retried.

Build and CLI children share an explicit environment: PATH is the qualified GHC
bin directory plus /usr/bin:/bin; LD_LIBRARY_PATH and LIBRARY_PATH each contain
only the supplied private Debian library directory. GHC_ENVIRONMENT=-, GHCRTS is
empty, LANG/LC_ALL=C.UTF-8, OMP/OpenBLAS threads=1, MAKEFLAGS=-j1, and Python bytecode
is disabled. Nothing else is inherited into these children. No unknown LD tail
or injection/allocator variable is silently treated as historical equivalence.
The bootstrap Python/helper/scope/watchdog identities are recorded separately.

## Proposed command and handoff

All arguments must be absolute, and OUTPUT must not exist. Run from this final
source checkout. This command is a preparation record, not execution permission.

    flock -n "$MLF_SPRINT_LOCK" python3 -B tools/performance/graph-read-fusion/build-producer.py \
      --baseline-source "$BASELINE_SOURCE" --baseline-producer "$BASELINE_PRODUCER" \
      --runtime-library-dir "$RUNTIME_LIBRARY_DIR" --output "$OUTPUT"

The intended fresh basename is F3-producer-01. Success requires the outer
bounded-receipt.json, worker receipt.json and producer/receipt.json all complete,
original builtin fresh evidence complete, successful independent CLI/semantic
checks, all pins unchanged, no descendants and both locks released. Raw receipts
and tool/object tables are local evidence, not this public design document.

B0's later slice still compiles the frozen f9 inference11 sources with the original
f9 builtin and dependencies. Those inputs do not become candidate source. Actual
consumption and exact artifact/group equality are required in that later gate;
compatibility is not assumed merely because the derived delta is metadata-only.
