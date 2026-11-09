# Foundation source crate compilation

## Foundation comparison with PR 33

The November 4 comparison uses the 14 PR 25 Foundation modules, 504 input
SCCs and one edit from Version 0.3.0 to 0.3.1. PR 33 at `17d36c32` is arm
A. The candidate is built from PR 29 on a separate branch. Both use the
same GHC 9.14.1 release producer and flags. Each compilation is a new
ordinary CLI process. The two installed-Prelude pairs use A, B, B, A with an
empty query cache for each cold run, followed by its warm and edited runs.
A separate A, B, B, A starts each cold run with both stores empty. The
decision rule requires two paired wins and at least a 2% mean wall reduction
in each state. Every observation and the recorded compiler and input
identities are in the [comparison data](pr33-comparison.json).

The initial PR 29 head was `e4f6e42b`. During qualification it advanced to
`3283899e`, on the same base `c5928b5b`. The three changed files are the CI
workflow and its private C3 test adapter and regression. Both executable
identities were reauthenticated after aligning the branch with that head.

The repeat on the aligned head used the same source paths, executables and
cache states. Times below are arithmetic means on an Apple M1 Max. Each
of the two matched pairs favored the candidate in every state.

| State | #33 wall s | Candidate wall s | Wall reduction | CPU s, #33 / candidate | Peak RSS MiB, #33 / candidate |
|---|---:|---:|---:|---:|---:|
| Cold, installed Prelude | 20.001 | 19.562 | 2.20% | 19.49 / 19.16 | 116.6 / 103.6 |
| Warm | 4.048 | 3.367 | 16.83% | 3.61 / 3.30 | 164.5 / 103.7 |
| Version edit | 3.711 | 3.424 | 7.73% | 3.60 / 3.39 | 158.5 / 113.8 |
| Cold, both stores empty | 20.232 | 19.551 | 3.37% | 19.85 / 19.24 | 119.5 / 103.8 |

Both cold series inferred 504 groups. Warm runs reused all 504, and the edit
inferred one and reused 503. The installed cold and warm query caches were
104,216,375 B on #33 and 4,323,425 B on the candidate. After the edit they
were 104,573,241 B and 4,343,056 B. The 312,221 B interface and 1,232,955 B
object matched the original #29 output byte for byte. The edited object grew
by one byte. An independent replay checked all 505 raw group versions and 83
contexts against their full v7 inputs. The two compiler families agreed on
511 exported binding schemes and evaluated both Version values.

Separate diagnostic runs enabled the timers in off/on/on/off order on a
single binary. Every run produced the same 597 physical cache records,
reports and formal artifacts. Control and timed means were 19.74 / 19.56 s
cold, 3.52 / 3.51 s warm and 3.66 / 3.56 s after the edit. Timers are nested
and force only the observed boundary. On warm reads, key lookup took 0.290 s
including 0.134 s forcing the key length. Reading and admitting 504 groups
took 1.602 s, including 0.080 s acquiring the bytes and 0.726 s decoding.
The diagnostic executable's 17 sampled ICH checks took 0.025 s. On cold
builds, inference took 15.357 s. Encoding and hashing source records took
1.091 s, writing their buffers took 0.120 s, and 16 publication batches took
0.137 s. Buffer writes include user-space work. UTF-8 and SHA sub-timers
cover only the three keys that took the in-memory path. All 504 keys are
included in the aggregate lookup span.

The 46-module modular native compile, LLVM emission, link and checked
execution passed. The 80-module native cold build was not repeated.

The compiler still checks raw xMLF, binding ownership, parameter types and
evidence before reuse. A private receipt pairs the checked term with the
actual admitted interface. The common small-object finalization path proves
its wire bounds before editing the same XThen forests as the full graph path.
Large or deep objects use the full planner. Both paths independently check
rewritten terms and checksums. The binary reader indexes exact decode shapes
by validated node ID. Small complete keys are forced and hashed in memory
under the usual cache lock.

The query writer hashes and patches one canonical record template. POSIX
writers stage at most 32 checked records in a newly claimed private directory
under the cache lock and publish them with ordinary same-filesystem renames.
Failure flushes preceding successful SCCs. An occupied staging name and
Windows use the existing per-file publication path. The prepared Prelude
generator emits the two ordinary binary artifacts. The official build
independently regenerates both from the checked builtin. A normal installation
hit compares the exact bytes of both bounded files under the lock. A mismatch
takes the formal reader and repair path. Full ICH mode retains that formal
installation check. [Source fingerprint format](../source-fingerprints/README.md).

On the GHC host the right operand of strict integer operations depends on
the left, preserving error order while allowing direct arithmetic and branches.
ST and IO array indexing uses a checked unsigned range on the validated
array size. These changes leave the source-language primitive ABI unchanged.

## Historical Foundation comparison with PR 25

This study compares the ordinary GHC-hosted `emlf --compile-crate` entry
point on the same 14 Foundation modules from PR 25. PR 25 was
`c5928b5be73cd78d194405e734aa012415570e1a`. The candidate starts at
PR 29 head `e996809a73ae16c676cd6516794021d89a278498` with PR 25 as its
base. The preceding PR 29 profile at `948483ae` has the same production
sources. The intervening commit changed the P2 test harness and CI.

## Changes and integrity

* **Prelude.** The crate CLI already contains the compiler's freshly generated
  Prelude literal. The build compares that literal byte for byte with a fresh
  generation from the identified source closure. At runtime
  `checkCompilerPrelude` checks the canonical source witnesses, primitive
  inventory, closed target term, exports, types and metadata. For an installed
  Prelude, the driver acquires the usual lock and reads both formal artifacts
  through their checked readers. It compares the entire canonical installed
  interface, including its object identity, to the checked compiler interface.
  At build time the generator also captures the exact canonical encoding of the
  split formal object and checks it against fresh construction. For installation
  or repair the compiler decodes that bounded literal, checks canonical
  re-encoding, relinks the object, and compares the full rendered witness
  to the checked Prelude. The existing atomic writer publishes the pair.
  A failed embedded admission takes the ordinary from-source path. An installed
  hit never needs to evaluate the split literal.
* **Raw finalization.** A private plan holds the exact bounded tables from
  planning and laying out a specific raw object. Its delayed canonical result
  stays paired with the admitted object. The xMLF checker retains exactly the
  term that it checked. This lets finalization reuse the same tables while
  preserving graph admission, interface and term validation, body checksum,
  dependency protection and scope checks. A changed normalized term still
  undergoes its own layout, typecheck and checksum verification.
* **Binary symbols.** The decoder bounds the symbol slice before accessing
  it. For long source key fields, a hint of matching length can provide the
  already-built text only when every physical byte is ASCII and equals the
  corresponding scalar. Otherwise the reader decodes the actual bytes in wire order. Any
  non-ASCII symbol follows the strict scalar decoder. Header, CRC, duplicates,
  graph canonicality, context identity, full key equality and object admission
  still apply. The encoder uses byte-aligned writes and a table containing
  the same CRC32 remainders as the scalar implementation. The GHC byte-array
  adapter uses bounded, privately owned storage and copies snapshots in bulk.
* **Inferred bindings.** The raw parameterized payload still goes through
  `Checked.check`. Its receipt contains the declaration spine's binding
  names and types from that same independent xMLF check, including the
  closed-type and unit-tail requirements. The group checks the exported names
  against its members. An extra leading lambda in the implementation is
  rejected before the checker peels the external parameters. The source SCC
  fixture compares the receipt with the previous separate spine walk.
* **Datatype environments.** The two builtin maps use the same ordered
  insertions as the original prefix of `M.fromList`. Extending them with the
  user declarations preserves rightmost replacements, including constructors
  with the same name as a builtin. Duplicate, kind and declaration checks
  still use the full user input. Both maps originate from the very same
  `builtinDeclarations` used by inference and the v7 key.

Source keys stay at v7 and the MLFBIN schemas retain their existing encoding.
The running executable's SHA is still in every full key, so a compiler change
recomputes those groups. Identical context blobs retain their content addresses.
The wire limits and the checked legacy readers are unchanged. [Source v7 key and migration](../source-key-builtins/README.md).

## Protocol

Use GHC 9.14.1, `-O2 -fpedantic-bottoms -fno-state-hack`, the actual compiler
CLI and the same absolute source, spec, builtin and cache paths in both arms.
Run the four independent sequences in the order **25, candidate, candidate,
25**. A sequence starts with an empty query cache and a verified installed
builtin. Time cold, warm and an edit of `Bootstrap.Version` from
`0.3.0` to `0.3.1` in fresh processes. Include every sample and use the
arithmetic mean. For the later cold-build comparisons, require a win in both
pairs and at least a 2% mean reduction to describe a cold lead. Capture wall
time, child CPU, peak resident memory, logical
cache bytes and inferred/reused counts. Each child has a 900 s limit. Measure
the first-ever installation separately by starting without either cache.

The recorded run reuses the absolute paths and oracle outputs of the earlier
PR 25/29 comparison. On each stage the final interface/object must equal
the corresponding earlier compiler-family output byte for byte. Require
504/0, 0/504 and 1/503 inferred/reused groups. For the PR 29 family,
independently decode every raw header and body, verify the context SHA and
reconstruct the full key for its address. Only the executable identity may
change in a key. Paths participate in the key, so reproducing the study in a
new directory can change the absolute size of the cache.

Build each revision in its own checkout. The last command creates a fresh
study directory, including isolated installed builtins, and retains the
caches and reports for inspection. Pass `--first-install` with a different
output directory for the empty-builtin series.

```sh
python3 tools/shared/build.py --optimization 2 --bootstrap-only --build-dir .mlf-build/producer
python3 tools/performance/foundation-query/compare.py "$pr25_emlf" "$candidate_emlf" "$pr25_checkout/libraries/mlf-foundation" "$new_directory"
```

For two PR 29-family sequences with the same source and spec paths, compare
the records and formal artifacts directly. The Prelude control uses a fresh
directory and exercises missing, damaged and valid foreign artifacts.

```sh
python3 tools/performance/foundation-query/check-raw.py "$pr29_sequence" "$candidate_sequence" "$pr29_emlf" "$candidate_emlf"
python3 tools/performance/foundation-query/check-prelude.py "$candidate_emlf" "$fresh_directory" --producer "$candidate_producer"
```

## Where the time went

In the preceding paired profile, PR 25 and PR 29 took 10.37 and 23.69 s on
warm reads. Reading and admitting cached raw groups grew from 1.85 to 10.74 s.
Group finalization grew from 0.02 to 3.46 s, and writing the final crate
grew from 0.08 to 1.04 s. The executable still inferred zero groups in both
cases. Among the 504 binary records, 30.61 MB of the 31.65 MB was the symbol
section. The nested UTF-8 symbol timing was 5.11 s and the CRC timing was
1.64 s. The key construction and hashing path was already about half a second.
On cold builds actual raw inference took approximately 16.3 s on both PRs.

Preparing the builtin Prelude afresh was a separate cost even with a good
installation. Both PRs paid it. In one PR 29 warm profile, the from-source
step took 6.34 s. The diagnostic build's raw headers, bodies, context files
and final outputs were compared with the plain compiler before using the
timings. The end-to-end results below use plain executables. Phase timings
are nested and differ across runs.

## Measured results

Apple M1 Max, macOS 26.6.2, GHC 9.14.1, 4 November 2026. Each cell lists
the two observations for its arm in execution order. A negative percentage
denotes less wall time. [All samples and executable identities](results.json).

| State | PR 25 wall s | Candidate wall s | Change in mean wall | Mean CPU s, 25 / candidate | Mean peak RSS MiB, 25 / candidate |
|---|---:|---:|---:|---:|---:|
| Cold, installed Prelude | 24.06 / 24.05 | 25.16 / 23.44 | +1.0% | 23.88 / 23.33 | 177.2 / 123.7 |
| Warm | 9.33 / 9.42 | 8.69 / 8.85 | -6.5% | 9.02 / 8.65 | 177.1 / 117.4 |
| Version edit | 9.14 / 9.35 | 8.93 / 8.88 | -3.7% | 9.01 / 8.84 | 177.2 / 120.3 |
| Cold, empty installation | 23.63 / 24.07 | 25.01 / 23.89 | +2.5% | 23.69 / 23.61 | 176.8 / 124.3 |

Both warm pairs and both edit pairs favored the candidate. The two cold pairs
went in opposite directions for each installation state. Neither cold series
met the predeclared threshold.

Each sequence recorded 504 inferred groups on cold compile, 504 reused groups
on warm read, and one inferred plus 503 reused after the edit. The cold query
cache was 104,053,739 B on PR 25 and 32,076,660 B on PR 29 and the candidate.
After the edit those totals were 104,410,605 and 32,259,216 B. The candidate's
original final interface and object were 312,193 and 1,232,927 B. The edited
object was 1,232,928 B. Both states matched the corresponding PR 29
formal output byte for byte. The independent audit also checked all 505
distinct raw group versions and 83 context files in each candidate sequence.

For comparison, the earlier plain PR 29 means were 37.91 s cold, 23.69 s
warm and 23.55 s for the edit. Its paired PR 25 means were 27.37, 10.37 and
10.32 s. The separately measured empty-installation mean before embedding
the formal object was 32.40 s on C6 versus 25.58 s on PR 25. Capturing the split
object increased the generated module by 608,134 B and the GHC executable by 934,128 B.

### Iterations

| Study | PR 25 cold / warm / edit, s | Candidate cold / warm / edit, s |
|---|---:|---:|
| C3, key text hints | 26.35 / 10.29 / 9.85 | 26.67 / 9.64 / 9.49 |
| C4, shared builtin maps | 26.23 / 10.10 / 10.10 | 26.16 / 9.41 / 9.40 |
| C5, GHC inlining trial | 26.06 / 10.03 / 10.09 | 26.73 / 9.54 / 9.40 |
| C6, binding inventory | 25.82 / 10.19 / 9.97 | 25.93 / 9.47 / 9.49 |
| C7, forward symbol scan | 24.87 / 9.39 / 9.43 | 25.08 / 8.92 / 8.80 |
| C8, verified installation | 24.06 / 9.38 / 9.24 | 24.30 / 8.77 / 8.90 |

The three initial development pilots measured only the candidate. The raw
data includes all three, every paired series and both empty-installation
series. C5's adapter inlining was dropped. C7 added an early malformed-prefix
control and kept the legacy scalar reader. The C8 control holds the compiler
identity, interface and exports fixed, inserts a valid private binding in the
linked term and verifies rejection. It also checks the fallback for a damaged
embedded literal.

The local checks included the official optimized bootstrap build and fresh
Prelude regeneration, all 131 modules' shared syntax/name resolution, the
125-case binary corpus, typed admission/bounds, source SCCs, query/session
controls, a real builtin mutation under the same supplied compiler identity,
and a focused codec program emitted to LLVM, linked and executed. The
previous 46-module native success and the 80-module, 900 s timeout belong
to the earlier PR 29 work. Neither full native workload was rerun here.
