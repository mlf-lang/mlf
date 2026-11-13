# r17: four Graph.unify allocation intervals

Diagnostic-only extension against unchanged source `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
**All five actual stages completed with final cleanup/lease clearance.**
All 217 static/protocol tests passed, and all eleven fine source sites were
verified in a real GHC profile. See [the checked result](results/unify-summary.json).
No production optimization or native-generation A/B/fixed-point test is claimed.

The local-unify family accounts for 27.59% of total source-demand allocation.
Its disjoint components in this run are:

| Component | Allocated bytes | Share of local unify | Share of total |
| --- | ---: | ---: | ---: |
| SOLVER_UNIFY_REBIND | 8830980432 | 52.46% | 14.48% |
| SOLVER_UNIFY_INPUT_VALIDATION | 3789266920 | 22.51% | 6.21% |
| SOLVER_UNIFY_OUTPUT_VALIDATION | 3598422640 | 21.38% | 5.90% |
| SOLVER_UNIFY_FIRST_ORDER | 615404440 | 3.66% | 1.01% |
| SOLVER_LOCAL_UNIFY | 329808 | 0.00% | 0.00% |

These are profiling allocation shares, not ordinary CPU or predicted savings.
All three raw artifacts matched the same-batch ordinary reference exactly;
cross-batch interface equality is not claimed because builtin paths can differ.

The completed r16 report assigns 16,834,404,240 bytes to
`(SOLVE, SOLVER_LOCAL_UNIFY)`: 47.289800% of SOLVE and 27.595320% of all reported
allocation. That is source-demand allocation in a profiling build, not ordinary
exclusive CPU, live heap, or a prediction of available savings. See `REVIEW.md`
for the narrowly scoped source review and the reasons to measure before changing
validation or caches.

## Four prefixes, one file, unchanged expression order

`R16-TO-R17.patch` modifies only the following **existing parenthesized arguments**
in `libraries/mlf-inference/Bootstrap/Graph.hs:1257–1262`:

| Label | Existing complete expression |
| --- | --- |
| `SOLVER_UNIFY_INPUT_VALIDATION` | `validateGraph before` |
| `SOLVER_UNIFY_FIRST_ORDER` | `checkedFirstOrder equations before` |
| `SOLVER_UNIFY_REBIND` | `rebind before (canonicalize skeleton)` |
| `SOLVER_UNIFY_OUTPUT_VALIDATION` | `validateGraph rebuilt` |

Only `{-# SCC "LABEL" #-} ` prefixes are inserted. Existing parentheses, binds,
continuations, error ordering, public API, fields, validation and `seq` calls are
unchanged. The original outer `SOLVER_LOCAL_UNIFY` remains to collect residual
work outside the four argument expressions. The rebind interval deliberately
includes the existing, lazily demanded `canonicalize skeleton` argument; it is
not an eager canonicalization timer. No argument is forced or extracted into a
helper to obtain cleaner attribution.

The combined map retains 27 coarse and 7 r16 fine edits and adds exactly 4:
**38 edits, 11 fine sites, 10 fine labels, 97 source files, 95-module union,
94 Emlf modules and 60 generator modules.** Each site has a unique exact anchor,
source byte/line extent, module/path and hashes in
`implementation/insertion-map.json`. Its `r16_fine` key/schema is retained for
compatibility, with `extension: "unify-r17"`; the reader's expected site/label
inventory is explicitly extended, not relaxed.

Static inversion establishes three identities:

1. Remove only four r17 prefixes to recover the exact r16 source bytes.
2. Remove all eleven fine prefixes to recover the exact original coarse mirror.
3. The unchanged original inverse recovers every pinned f9 source byte.

`preview-mirror/` is a static preview, not an admitted runtime work directory.
Its full original-schema manifest, patch, source inventory and inverse were
checked with the unchanged original mirror verifier. Actual execution requires
a newly prepared absent work directory and fresh path-bound plan/admissions.

## Reuse and unchanged validation chain

The original 24 r13 files listed in `REUSE-MANIFEST.json`, including controller,
guard, oracles, coarse `profile.py`, original seven test modules, fixtures and
foundation inventory, remain byte-identical. `R16-REUSE-MANIFEST.json` separately
records the unchanged and modified r16 implementation files. Only these four
implementation files differ from r16:

- `insertion-map.json`: four prefixes and recomputed metadata/pins;
- `fine_profile.py`: exact four-site inventory extension and a parallel family
  rollup, without changing the original coarse reader or nearest-fine algorithm;
- `test_fine_profile.py`: eleven-site expectation and two nested-family tests;
- `test_solver_overlay.py`: explicit 38-edit/11-site/10-label counts, nested
  prefix-aware span inverse, and the r17-to-r16 inverse test.

No historical admissions, cleanup receipts or test-success claims are imported.
No validation is weakened to accommodate a count. The controller does not
hard-code SCC counts; mirror occurrences derive from the reviewed map. Original
closure/provenance counts, producer identity, source pins and all stage checks
remain unchanged.

## Disjoint attribution and LOCAL_UNIFY rollup

The original 24 coarse labels remain unchanged. Each raw stack node's **self**
allocation/ticks/node count goes once into the original coarse bucket and the
nearest fine label below its deepest coarse boundary. A new coarse boundary
resets inherited fine context. Every coarse row and the global totals must
match a fresh strict parse by the unchanged coarse reader. Inherited allocation
is never summed into the partition.

The four new child labels replace part of the former LOCAL_UNIFY cell. Add
their disjoint cells and the residual `SOLVER_LOCAL_UNIFY` cell to obtain the
new report's local-unify family. The reader emits this parallel presentation as
`local_unify_family_by_coarse`, with its five exact labels in
`local_unify_family_labels`. **Do not add that rollup to the main matrix.** It
does not assert equality to the old r16 byte total. SCCs can change optimization,
allocation, residency and attribution. Separate generation/elaboration and
other coarse contexts are retained rather than attributed to SOLVE.

All eleven sites must be declared with matching label, module, exact mirror
path and reviewed RHS line extent; some may be unobserved. Missing declarations,
unknown `SOLVER_` labels, mismatched source/module, CAF fine centres and malformed
raw reports still fail closed. Actual GHC source locations/declarations for all eleven sites were
verified in this completed batch; missing declarations still fail closed.

The fine CLI checks mirror source hashes, exact file/directory inventory and
symlink rejection, and reconstructs the exact original qualified summary from
the raw JSON. Original stage mirror validation also regenerates the complete
manifest/patch. Supplied expected hashes must come from authenticated stage
evidence. The fine CLI does not authenticate or rerun a real unit control,
certify cleanup, grant admission, or establish actual execution by itself.

## Historical author-stage source tests

**32 new static/synthetic tests passed in 0.439 seconds**, with the resolved
`/usr/bin/python3` executable and `-B`. The original r16 29 test methods remain,
with explicit expected inventory/span adaptations. Three additional methods
cover four-child disjoint conservation/rollup, generation plus coarse-context
reset, and exact r17-to-r16 inversion. At that historical source-only checkpoint, no GHC, Haskell fixture, heavyweight
runner, subprocess workload or lock experiment had started. The later coordinator
ran all 217 tests and the complete five-stage experiment reported above.

`tests/new-static-tests.json` explicitly has `complete: false` and
`full_protocol_admission_qualified: false`. It is a receipt for these 32 tests,
not a substitute for fresh completion of the original 185 protocol tests and
new tests bound to current code pins, independent review and separate admissions.

## Reproduction commands and mandatory gates

With `PACKAGE` naming this directory and `SOURCE` the unchanged source checkout:

```sh
PYTHON="$(readlink -f /usr/bin/python3)"
cd "$PACKAGE/implementation"
ASTRA_FROZEN_SOURCE="$SOURCE" "$PYTHON" -B -m unittest -v \
  test_solver_overlay test_fine_profile
```

After independent review and the fresh full test receipt, prepare a **new absent**
work directory using the unchanged controller (preparation launches no compiler):

```sh
"$PYTHON" -B "$PACKAGE/implementation/controller.py" prepare \
  --source "$SOURCE" --work "$NEW_ABSENT_WORK"
```

The coordinator must bind current locks/epoch, authentic original f9 ordinary
producer, toolchain, exact environment, new plan and fresh review/test inventory.
Do not use the separately edited ENCODE candidate as the ordinary reference.
The original separately admitted stage budgets remain BUILD 600s, QUALIFY 180s,
PROBE-CONTROLS 420s, TARGET-QUALIFICATION 420s and ATTRIBUTION 240s, with the same
per-compile/resource limits, no automatic retry, all semantic/demand controls,
real byte-unit control, fresh artifacts/ordered queries and cleanup gates.

After successful actual stages, use the final archived profile and its original
qualified `allocation-raw-partition.json` with independently verified hashes:

```sh
"$PYTHON" -B "$PACKAGE/implementation/fine_profile.py" \
  --profile "$ARCHIVED_RAW_PROFILE" --profile-sha256 "$RAW_SHA256" \
  --coarse-summary "$ORIGINAL_QUALIFIED_SUMMARY" \
  --coarse-summary-sha256 "$SUMMARY_SHA256" \
  --mirror-root "$NEW_ABSENT_WORK/mirror" \
  --mirror-manifest-sha256 "$MANIFEST_SHA256" \
  --toolchain-sha256 "$ACTUAL_GHC_SHA256" --output "$NEW_REPORT_PATH"
```

The output must not exist. Failure or missing centres requires investigation,
not synthetic profile repair. This package does not enable native A/B or fixed-point work. The completed
focused semantic/artifact controls are reported above, not a full compiler90
regression, production runtime speedup or latest-main integration pass.
