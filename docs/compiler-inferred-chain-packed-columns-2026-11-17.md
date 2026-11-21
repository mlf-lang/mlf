# Inferred chain: packed numeric query columns

No additional compiler change is retained from this experiment. The unsigned
monomorphic `inferred_chain` remains unaccepted under the original
[fixed GHC comparison](compiler-inferred-chain-2026-11-17.md): MLF/GHC OLS
slopes are 0.164411/0.158357 ms/function; the endpoint and paired OLS interval
also fail. The retained earlier template optimization, its evidence, and
unrelated working-tree changes are preserved. No unchanged-source formal GHC
cohort is repeated and no acceptance commit or push is made.

Evidence resides in `.mlf-build/inferred-chain-packed-columns-20261117`.
The starting audit authenticates 303 maintained-source and 4,342 evidence pins
from the preceding map investigation. All builds, controls, elapsed runs,
confirmation, and memory measurements are serialized.

## Exact layout models

Version 3 stores typed query descriptors, read counts, read descriptors, and
payload row positions as generic binary graph values. The experimental version
4 keeps the same declaration/group/evidence/datatype tables and result hashes,
but packs four numeric columns into unsigned lanes of signed 64-bit bit-pattern
values. Read targets become dense row ordinals. No logical read, repetition,
order, expected hash, identity, or payload presence is removed.

A first fixed-width model, using two unsigned 32-bit lanes per word, increases
both size and node count. It is rejected before a compiler implementation.
Its actual-case restore checks are narrow: the original helper does not mask a
negative signed word before extracting its upper lane, so no all-u32 correctness
claim is made for that model.

The adaptive model chooses the minimum bit width for each column, from 1 to 32,
and packs `floor(64 / width)` values per word. Descriptor kind occupies the low
four bits; the remaining bits hold its existing typed table index. Padding is
zero and the width, word count, scalar types, and descriptor namespace are
validated. Independent Python reconstruction restores the complete original
version-3 bytes for each real input, as well as all logical rows and the legacy
projection. The Python model also checks 1,728 binary/direct packing vectors,
including signed high-bit words.

| Functions | Original bytes | Fixed-width bytes | Adaptive bytes | Original / adaptive nodes | Original / adaptive edges |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1,328 | 1,472 | 1,340 | 43 / 45 | 82 / 49 |
| 256 | 53,242 | 58,952 | 50,619 | 1,835 / 1,611 | 5,714 / 2,158 |
| 1024 | 215,983 | 236,088 | 204,467 | 7,211 / 6,557 | 22,610 / 8,749 |

At 1024 functions adaptive packing saves 11,516 bytes (5.33%), 9.07% of
physical nodes and 61.30% of references. Unique UTF-8 symbol bytes remain
159,901, which limits the space benefit from numeric packing. Smaller files
alone do not establish lower compiler allocation, residency, or elapsed time.

## Private reader and writer

The `packed-columns-v2` shadow compiler changes only its private QueryGraph
source. Versions 1, 2 and 3 retain independent typed readers. A version-3
snapshot is marked noncanonical for the experimental writer so that publication
rewrites it to version 4; corrupt packed input is never tried as another format.
This is a private experiment, not a maintained format migration or a regenerated
builtin.

The writer uses the already resolved closure ordinals and checks the exact old
expanded-work cost before packing. On reading, column headers and a projected
minimum work bound are checked before expansion. The exact old descriptor work
is checked before identity reconstruction. Existing identity, hash, closure,
cycle/depth and payload checks remain. Packed widths, word type/count, padding,
key table index, read target range, column lengths and payload order are checked
explicitly. The existing 64 Mi expanded-work policy is not relaxed by compression.

Completed host controls include:

- 1,728 vectors compared byte-for-byte with an independent arbitrary-precision
  integer packing oracle, through real binary encode/decode as well as direct
  column admission. Malformed headers, types, widths, counts and padding reject.
- All twelve descriptor namespaces, Unicode identities, repeated dependencies,
  payload presence, empty indexes, invalid kind/table indices, duplicates,
  out-of-range targets, cycles, read counts, hashes, format and configuration.
- The exact 64 Mi projected version-3 work boundary and one additional UTF-8
  byte. The latter rejects before semantic reconstruction, although the packed
  physical graph still fits. The boundary fixture intentionally uses a later
  invalid group to distinguish successful work admission from semantic admission.
- The actual 0/256/1024-function generation files. Haskell writer bytes equal
  the independent Python layout exactly; the new reader restores identical
  logical rows and version-3 bytes. Legacy projections are unchanged.
- Existing declaration/cache tests for slot drift, candidate addition/deletion,
  current authority/read-list guards, direct finalization and repeated warm reuse.
- Existing index/publication controls for 4096/4097 depth, referenced/codec work
  boundaries, cold/warm publication, failpoints, and payload/generation hashes.

The first private build used unavailable `elemIndex`/`div` names; the corrected
shadow uses an explicit bounded kind search and the shared `quotInt` primitive.
The first added control did not compile because its optional snapshot comparison
required an unavailable Eq instance; a separately saved control represents the
optional payload as a zero-or-one-element list. A screen launcher initially
pointed at the failed build and was rejected by authentication before compiling
any case. These failed artifacts remain recorded; none is presented as a passing
run. No compiler logic was changed after the successful candidate build.

## Elapsed confirmation and memory

The first screen uses one warmup and six alternating measured pairs per size.
A single separately declared confirmation uses one warmup and twelve alternating
measured pairs. Both use fresh query/output directories. The cohorts are kept
separate; there is no repeated confirmation after seeing its result.

| Functions | First compiler before / after, s | Confirmation compiler before / after, s | Confirmation compiler + Clang sum before / after, s |
| ---: | ---: | ---: | ---: |
| 0 | 0.127441 / 0.133368 | 0.133395 / 0.131066 | 0.268444 / 0.265161 |
| 256 | 0.170291 / 0.170857 | 0.169672 / 0.172024 | 0.306219 / 0.310062 |
| 1024 | 0.304729 / 0.295580 | 0.305071 / 0.305531 | 0.440937 / 0.439528 |

The initial N1024 compiler improvement is not reproduced. In confirmation,
compiler-only time rises slightly at N1024 and more at N256. The approximately
1.4 ms lower combined N1024 sum comes from the downstream subprocess portion;
it does not demonstrate an improved compiler growth curve. These sums are
screening diagnostics, not the formal full-worker endpoint with launch overhead.

Three separate alternating RTS pairs at N=0/1024 use `-s -F4`; these instrumented
executables are not used in the elapsed cohorts. N1024 median values are bytes:

| Metric | Before | Packed candidate |
| --- | ---: | ---: |
| Cumulative allocated heap | 862,889,416 | 855,212,016 |
| Maximum live heap | 11,233,248 | 11,233,296 |
| Maximum individual process RSS | 61,669,376 | 61,620,224 |

Allocation falls by 7,677,400 bytes (0.89%); live heap and RSS are essentially
unchanged. At N0 allocation rises slightly, from 269,577,816 to 269,586,632 bytes.
Space and allocation savings are real but small relative to the complete compile.
They do not justify the extra format and read/write implementation in this study
without a reproducible elapsed or residency improvement. The candidate is rejected.

All 120 screen/confirmation compiles preserve exact interface, object and LLVM
bytes and produce 360 checked native arithmetic results. All twelve separate
memory compiles preserve the same artifacts and LLVM. The successful primary
control runner records thirteen actions; the namespace/Unicode runner records
three more. These are host checks only. Native self-bootstrap, installed CLI,
and the prior native-codec/QuerySnapshotProbe gaps remain unqualified.

The next investigation should return to the larger measured costs of package
construction and generic graph planning, using caller-attributed allocation to
find repeated construction that can be removed without another storage format.
This is a direction for investigation, not a verified optimization. The shape
and original GHC acceptance rules remain unchanged; finite fitted exponents are
not asymptotic complexity proofs.
