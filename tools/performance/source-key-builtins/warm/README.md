# Where a Foundation warm read spends time

The biggest cost inside a source query hit is decoding the MLFBIN symbol table.
Across all 504 groups this took 5.762 s, compared with 0.155 s for checking the
xMLF term and re-inferring its bindings. The reader also spends 1.723 s on the
wire CRC. Outside the group hits, preparing the Prelude takes 6.897 s of the
same warm compile.

## Setup and calibration

PR #29 head `948483ae0f8837d41b43f2c619b6bfc98d0fb844` (base
`c5928b5be73cd78d194405e734aa012415570e1a`) contains the merged query v7.
Its source tree is identical to the earlier `92d29051` study. Apple M1 Max,
32 GiB, macOS 26.6.2, GHC 9.14.1 at -O2. All 14 input module contents match
the earlier study. Absolute paths and executable identity differ between the
old study and this reproduction.

The earlier 10.683 s was one inclusive observation. In the primary run the
same coarse interval averaged **10.348 s** (10.172–10.630). The detailed
interval averaged **10.833 s** (10.341–11.369). Detailed probes added 4.69%
relative to coarse on this interval. Whole-process warm times averaged
**23.039 s plain**, **23.082 s coarse** and **23.878 s detailed**. Every process
reused all 504 groups. Cache record/carrier bytes and inode/size/mtime,
builtin files, ordered group reports and complete interface/object bytes
matched. The following partitions use the detailed arm's actual clock.
[Protocol](PROTOCOL.md) · [All samples and ranges](observations/summary.json) · [Raw nested timers](observations/spans.tsv).

## The hit interval

| Exclusive operation, over 504 hits | Mean s | % of hit |
| --- | ---: | ---: |
| Decode wire tables and typed structures, including CRC | 8.520 | 78.65 |
| Render and check object fingerprints | 1.041 | 9.61 |
| Bounded file acquisition | 0.688 | 6.35 |
| Syntax, interface, ownership and layout checks | 0.336 | 3.10 |
| xMLF type check and binding re-inference | 0.155 | 1.43 |
| Key projection, reconstruction, comparisons and context proof | 0.069 | 0.63 |
| SHA of shared context bytes | 0.005 | 0.04 |
| Remaining hit work | 0.019 | 0.18 |

* The decoder spent 5.762 s in the symbol table, 1.723 s on CRC, 0.629 s in
  node tables and 0.322 s reconstructing typed raw bodies. The symbol table
  contains interned UTF-8 strings. Across the 504 records, the compact key
  fields reference 27,972,722 of 30,741,928 symbol bytes (91.0%, counted once
  per distinct referenced symbol per record, including any shared with the
  payload). The byte counts describe storage. The timer covers the entire symbol table. The large fields include observed contracts, external bindings and
  prepared-group metadata.
* File acquisition includes 0.184 s in the actual bounded C read calls and
  0.503 s in host-side acquisition, copies and file existence checks. The
  readers opened 504 query records (31,818,154 B) and loaded 138 shared
  contexts (618,343 B). Replaying the eight-entry window independently from
  the on-disk references matched the observed context-read count. These are
  warm filesystem reads with normal OS caching.
* The full-key comparison itself spent 0.0017 s after charging deferred key
  text reconstruction to the latter. Expected-key projection/canonicality
  was 0.0120 s and stored-key restoration plus its deferred text was 0.0159 s.
  Re-encoding/comparing user datatypes, comparing carriers, window selection
  and reference checks account for the rest of the key category. Constructing,
  writing and hashing the current scratch key precede entry to the hit timer.
* xMLF term checking took 0.107 s and binding re-inference 0.048 s. The
  separate 1.041 s fingerprint row includes checking the body and the full unit
  and materializing the reconstructed interface fingerprint. Syntax, type and
  integrity checks all stayed enabled.

## Whole warm compile

| Disjoint interval | Mean s |
| --- | ---: |
| Hit processing | 10.833 |
| Prepare/load Prelude dependency | 6.897 |
| finishGroup | 3.502 |
| Write final interface and object, including encode and publication | 0.986 |
| Assemble and validate the final crate before writing | 0.561 |
| Construct, write and SHA the current scratch keys | 0.543 |
| Write the query report | 0.085 |
| Other driver work, input/group preparation and process overhead | 0.471 |
| Whole detailed process | 23.878 |

finishGroup accounted for 0.808 s planning raw object graphs, 0.823 s
planning canonicalizer graphs, and 1.050 s checking or materializing
fingerprints. This last duration includes 0.358 s from a raw-return fingerprint
whose thunk is first demanded during finalization. There were 1,024 final
object admissions and 504 canonicalizer graph plans for the 504 groups.

The final object writer used the ordinary v1 route. Of its 0.986 s, 0.647 s
was binary encoding exclusive of CRC, 0.078 s was its CRC and 0.254 s went
into selecting the representation. After that choice, the object took 0.661 s
and the interface took 0.072 s, inclusive of their encoding and publication.
The staged byte-write interval including
the C transport was about 0.0025 s. The final interface was 313,386 B and the
object 1,234,131 B. Before that writer, assembly spent 0.319 s forming pooled
text and 0.229 s fingerprinting it. The query report has its own interval.

## Inside the two hotspots

The focused full-compile run used the same absolute Foundation sources and
installed builtin pair, with a newly populated cache for its own executable.
Both final files were byte-identical to the primary run. Its readings belong
to its own two timed detailed samples. The focused hit interval averaged
10.712 s versus 10.328 s coarse (+3.72%). End-to-end detailed wall averaged
23.920 s versus 23.303 s plain (+2.65%). Both studies stayed within the
prespecified 10% perturbation threshold.
[Focused samples](focused-observations/summary.json) · [Focused raw timers](focused-observations/spans.tsv).

* **Within cache hits**, symbol-table decoding took **5.916 s**. Executing
  the UTF-8 byte reader accounted for **4.727 s**. Materializing the decoded
  text from the reversed character list accounted for **0.979 s**, charged
  where the text was demanded. Together these accounted for about **96%** of
  symbol-table time. Symbol uniqueness lookup exclusive of deferred work
  took 0.048 s. This includes both record and shared-context symbol tables.
  The underlying code is `Bootstrap.Bitstream.getSymbolsAt` →
  `getUtf8At` → `getBits 8` for each byte.
* **Outside those hits**, preparing the Prelude took **7.008 s**. Every process
  entered `Crate.ensureBuiltin` once and demanded `Artifact.builtinPrelude`
  before comparing the installed interface. Building that reference object
  took **6.641 s**. Inside it, `CompilerCore.finishCompilation` took
  **6.117 s**, including **5.756 s** at `C.solvePrepared constraints`
  (5.565–5.947 s). The installed object read took 0.306 s and comparison of
  the actual encoded interfaces took 0.013 s. The 0 inferred / 504 reused
  counters cover Foundation's source groups. The separate Prelude solve ran
  once per process with the installed files present and identical in every sample.

## Reproduce

Run serially with fresh run directories. The probes live in generated GHC-only
copies. The plain arm links the ordinary session, and all arms of each study
hash the very same executable. The raw timers record inclusive and exclusive
nanoseconds at actual demand sites. Every parent reconciles to its timed
children plus its own residual. These are GHC-hosted fresh-process Foundation
reads. The 46- and 80-module native workloads were not run for this profile.

```sh
w=tools/performance/source-key-builtins/warm
python3 -B "$w/build.py" .mlf-build/warm/build
python3 -B "$w/run.py" .mlf-build/warm/build/study .mlf-build/warm/foundation
python3 -B "$w/summarize.py" .mlf-build/warm/foundation .mlf-build/warm/report
python3 -B "$w/build.py" .mlf-build/warm/focus-build --focus
python3 -B "$w/run.py" .mlf-build/warm/focus-build/study .mlf-build/warm/focus .mlf-build/warm/foundation
python3 -B "$w/summarize.py" .mlf-build/warm/focus .mlf-build/warm/focus-report
```
