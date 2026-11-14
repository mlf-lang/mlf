# Guarded OpenFragment outer-pack stamp screen, 2026-11-14

**Completed local allocation screen; archived, not promoted.** The candidate only
appears as a patch and source copies below this experiment directory. This commit
does not change production source. No PR, merge, deployment or new compiler run is
part of this publication.

## Result and decision

Both ordinary A/B executables passed the exact 58 controls. All 12 paired stamp
digests matched. Every repetition, including the first, and all 48 empty-window
rows are retained. Empty allocations happened to be zero; none were subtracted.

| Input size | A median allocation | B median allocation | B minus A | Change |
| --- | ---: | ---: | ---: | ---: |
| 8 | 348824 B | 352720 B | +3896 B | +1.116896% |
| 32 | 1383048 B | 1383264 B | +216 B | +0.015618% |
| 128 | 5544880 B | 5529496 B | -15384 B | -0.277445% |
| 512 | 22404920 B | 22326304 B | -78616 B | -0.350887% |

The absolute allocation delta at each size is identical in all three repetitions.
The largest observed local reduction is only **0.350887%**, with regressions at
sizes 8 and 32. This is not a stable wall-time, CPU, Foundation workload or whole
compiler speedup. We chose not to promote it or run a full candidate producer.
See [all 12 samples](results/samples.csv), [unaltered raw output](results/), the
frozen [decision](DECISION.json), and [combined review](review/combined-final.json).

## Baseline and source scope

The actual experiment used the previously qualified **local F25** source commit
`bda8f9807c8b13b5ce14753d0320fa54772e4bc4`, **not current main**. That commit was
not available as a remote Git object when this archive was prepared. This public
branch instead starts from the immutable existing experiment archive commit
`fcccbe7d01584ab897694b5f35734770eacb11b5` (tree
`d5d66eeb5375cccda779f88e12b831579c609156`). All 47 relevant Haskell source blobs
(the production target plus 46 dependencies) and both C source blobs were checked
byte-identical between that public base and actual F25: [source pins](base-sources.json).
This closure-specific fact does not equate the whole public tree to F25, qualify
current main, or grant any compiler/builtin/native fixed-point qualification.

The only candidate production edit is
[`source/candidate.patch`](source/candidate.patch), affecting
`libraries/mlf-crates/Bootstrap/OpenFragment.hs`. The unchanged baseline and
complete candidate target are both included. The guarded fast path avoids the
outer concatenated Text when the bounded field-count calculation fits 1048576;
otherwise the original pack/fingerprint path remains. Inner packing, pretty
printing, scalar hashing and candidate summary/power overhead remain. The 12 fixed
inputs fit the bound by source/emitted analysis, not by a dynamic branch counter.

## Reproduction material and limits

All Haskell, the patch, and the disabled source-stage runner are exact bytes from
the frozen capture package. `source/source-files.json` retains its original source
manifest; `MANIFEST.json` binds this public selection. `source/runner.py` remains
disabled (`READY = False`) and contains historical absolute paths. It is an
audit/reproduction reference, not a portable one-command launcher or reusable
admission. We do not publish or reuse historical claims, lock epochs or credentials.

For a fresh independent reproduction:

1. Check out the public archival base above and verify the 49 relevant source pins.
   Use separate A/B working trees and output directories. Keep A's OpenFragment
   equal to `source/reference/OpenFragment.hs`; apply the archived patch only to B
   (or verify B against the complete archived mirror). Do not alter production
   source merely to browse this archive.
2. Build the recorded dependency closure with the ordinary GHC 9.14.1 settings in
   [`protocol.json`](protocol.json): `-O2 -fpedantic-bottoms -fno-state-hack`, the
   recorded package isolation/selection, no profiling or altered demand flags.
   The actual run reused 46 authenticated dependency modules plus two C objects;
   those binaries are deliberately not bundled. Freshly building them is a new
   experiment and cannot reproduce the old artifact hashes or old qualification.
3. Compile each side's production OpenFragment and four fixture modules freshly
   into that side's directories. Preserve same-invocation Core/final-STG capture
   for production OpenFragment **and Main**. The archived 16 original target
   compile/link/run argv records specify the exact original ordering and flags.
   Remap their historical paths to the fresh scope; do not execute them unchanged.
   Link each side's own 53 objects only, without an old producer Main or cross-side
   target object. Both StampProbe fixtures intentionally contain the candidate
   body for differential controls; production A remains the original target.
4. Run each executable once with `controls` and once with `measure`, retaining
   stdout/stderr. Require the exact 58-case golden stdout, exit zero, empty stderr,
   ordered 36 measurement rows per side, and matching 12 paired digests. Keep
   `GHCRTS` unset/empty and `-rtsopts=ignoreAll`; never subtract the empty windows.
   Original budgets were 180 seconds outer, at most 30 seconds for each side's
   combined controls/measurement and intervening verification, with no retry.
5. Treat any fresh run as a separate observation. The frozen review proves only
   this completed local experiment: actual Main forced the lazy production stamp
   within the allocation/time observer, using the linked target/Main artifacts.
   New builds require their own source, artifact, emitted and lifecycle checks.

The completed run used 30 bounded commands. Final outer cleanup, lock reacquisition
and lease clearance passed, as did original input/runtime authentication and
archive/restored-file checks. The combined review references original receipt,
guard and capture hashes. These JSON statements are evidence summaries, not
substitutes for the original artifacts or authority to run anything new.

## Frozen review chronology and exclusions

`review/raw-lifecycle.json` intentionally says emitted review was pending at that
earlier point. `review/full-emitted.json` and `review/combined-final.json` close
that dependency. `source/RUNNER-NOTES.md` and source-manifest status describe the
earlier disabled source preparation, not the final run. `DECISION.json`'s
`public_publication_completed: false` is the original pre-publication snapshot,
preserved verbatim rather than rewritten. Historical absolute evidence paths in
these files are identifiers, not expected public links.

This small archive excludes object/interface/executable binaries, the generated
builtin, huge recovery bundles, raw Core/STG and full private lifecycle receipts.
Their hashes/review references are preserved, but this public subset alone is not
a complete independent reconstruction of every authentication step. No older
interrupted execution is retroactively declared clean. Native-generation fixed-
point A/B remains paused. The archive is not a current-main or GHC-parity gate.
