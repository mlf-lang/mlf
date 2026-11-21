# Inferred chain: body sharing and owned writer experiments

The unsigned monomorphic `inferred_chain` shape remains unaccepted. This
investigation retains no additional compiler change. The fixed comparison in
[the retained study](compiler-inferred-chain-2026-11-17.md) is still authoritative:
MLF/GHC OLS slopes are 0.164411/0.158357 ms/function. The endpoint slope and
paired OLS interval also fail. No unchanged-source formal GHC cohort was rerun,
and no acceptance commit, push or transition to another shape occurred.

Evidence is under `.mlf-build/inferred-chain-shared-bodies-20261117`.
The current ordinary producer and preceding audit (301 source pins and 1,872
evidence pins) were authenticated. Builds, controls, elapsed screens and memory
runs were serialized. The previous current-source profile identifies package
creation and query-index encoding as growing costs; this investigation does not
claim a new profile.

## Body sharing estimate

An independent Python reader opens the current schema-8 objects. The experiment
normalizes each function body's XName occurrences to local ordinals, stores the
original exact names in a separate table, and pools normalized bodies. Decoding
and restoring the simulated layout reproduces every original fragment tree.
This is a format-size estimate, not a production schema or compiler benchmark.

| Functions | Fragments / distinct bodies | Existing / simulated bytes | Existing / simulated nodes |
| ---: | ---: | ---: | ---: |
| 0 | 3 / 3 | 1,338 / 1,377 | 73 / 81 |
| 256 | 259 / 5 | 74,257 / 70,704 | 3,409 / 2,657 |
| 1024 | 1,027 / 5 | 302,673 / 286,906 | 13,393 / 10,337 |

At N=1024, size falls by 5.21% and the codec's expanded-work count falls from
2,403,545 to 1,950,650. Work counts are not resident-memory measurements. The
existing generic node DAG already shares much of the representation. These
results alone do not justify introducing typed restoration and a new resource
admission path. The simulated schema-9 files are private diagnostic artifacts;
the production writer and reader remain unchanged.

The initial Python assertion compared a list with the reader's tuple. Its driver
is preserved; the corrected comparison and an independent final restoration
check pass. This was not a compiler or object corruption failure.

## Two writer alternatives

`bulk-fields-v2` supplies width/value pairs to one private GHC-host IO loop.
The helper checks field bounds and writes little-endian bytes directly to the
existing array. It is a diagnostic helper, not an adopted portable primitive.
The field list replaces per-field continuation calls but introduces allocation.

`cursor-packed` uses only existing primitives and shared source syntax. Explicit
cursor constructors replace entry-field continuations, traversing the planned
entries directly without a field or byte list. Planning, budgets, layout,
symbols, checksum and all wire bytes remain unchanged in both prototypes.

Each fixed screen has one warmup and six alternating measured pairs at
N=0/256/1024, with fresh query/output directories. The measured boundary below
is compiler-plus-Clang subprocess sum, excluding formal-worker overhead.
Screens are separate and are not pooled with the GHC cohort.

| Candidate | N=0 before / after, s | N=256 before / after, s | N=1024 before / after, s |
| --- | ---: | ---: | ---: |
| bulk-fields-v2 | 0.252347 / 0.250370 | 0.285499 / 0.285240 | 0.410722 / 0.418157 |
| cursor-packed | 0.252296 / 0.254739 | 0.284531 / 0.285808 | 0.414561 / 0.410538 |

Separate memory measurements use three alternating pairs at N=0/1024 with
`-s -F4`. N=1024 medians are bytes:

| Candidate | Allocated before / after | Maximum live heap before / after | Process RSS before / after |
| --- | ---: | ---: | ---: |
| bulk-fields-v2 | 862,886,696 / 918,693,408 | 11,233,248 / 12,534,112 | 61,472,768 / 64,700,416 |
| cursor-packed | 862,885,904 / 861,722,024 | 11,233,248 / 11,322,912 | 61,456,384 / 61,652,992 |

The bulk helper adds 55,806,712 allocated bytes and increases both live heap and
RSS; the large-case compiler-only median rises from 0.285361 to 0.292032 s.
It is rejected. The cursor reduces the large-case compiler-only median from
0.288540 to 0.284540 s, while the small and middle cases are slower. Allocation
falls by only 1,163,880 bytes (0.135%), with slightly higher live heap and RSS.
This diagnostic improvement is insufficient to retain the additional cursor
state machine. It is also rejected, without claiming an acceptance-level
speedup or a change in fitted complexity.

## Checks and limits

The bulk helper passes 3,640 single-field cases and 120 field sequences against
an independent target-bit setup and the unchanged generic writer. The checks
include sentinels, offsets, widths 0 through 64, invalid widths/positions,
overflow-before-value demand, delayed IO demand and zero-width lazy values.
They do not qualify the mutated-buffer state after an invalid later field.

Both candidates pass 5,104 entry/offset/width cases and 186 complete wire and
admission comparisons against the original encoder. The cursor fixture calls
the new cursor path directly. The existing field (10,920 states), byte (65,280
states) and artifact constructor/admission/base64/source/bounds controls also
pass. For the cursor, the existing field/byte controls exercise the unchanged
helpers; the direct entry and whole-wire checks exercise the new implementation.
There are 21 successful bulk-control actions and 18 cursor-control actions.

Across the two screens, all 84 compiler runs preserve exact interface, object
and LLVM bytes; all 252 native outputs match the independent arithmetic result.
All 24 separate memory runs preserve those bytes as well.

Two bulk-control setup failures are retained. The first helper build needed
explicit local IO type signatures. The first byte oracle then incorrectly
compared an overwriting helper with a generic writer that ORs partial bytes.
The corrected oracle independently clears only the target bit range, preserving
outside sentinels, before calling that original writer. Only the subsequent
completed controls are counted as passing.

No maintained compiler, builtin, lock, primitive ABI or wire-format change is
introduced by this investigation. Earlier uncommitted inferred-chain work and
unrelated lifecycle files are preserved. Native compiler self-bootstrap,
installed CLI and the previously documented native-codec/QuerySnapshotProbe
gaps remain outside qualification. Finite-range fitted exponents are not proofs
of asymptotic complexity.

Further work remains on this shape. These two writer designs and the earlier
field/byte-stream designs should not be repeated without a materially different
hypothesis; their results do not justify another unchanged formal GHC cohort.
