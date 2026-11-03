# Foundation source crate compilation

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
The wire limits and the checked legacy readers are unchanged.

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
