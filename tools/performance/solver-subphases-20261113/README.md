# r16 solver subphase diagnostics

Source preparation against `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
Status November 13: the complete 214-test Python suite (185 unchanged protocol
tests plus 29 new static/report tests) passed in 9.985 seconds. Independent source
review passed, and a fresh actual profiling BUILD has started. No completed
Haskell diagnostic, final allocation split or speedup is reported yet. Runtime
admissions and receipts are maintained separately; this is the reproducible source
package, not a license to skip those gates.
The earlier diagnostic's 58.355229% SOLVE allocation motivates finer measurement;
it does not identify a solver optimization or predict savings.

## Frozen implementation and narrow overlay

`implementation/` reuses the original r13 controller, guard, oracles, coarse
profile reader, runtime pins, controls, statistics reader, seven test modules,
fixtures and foundation inventory without changing their bytes. The 24 reused
files and SHA256 values are in `REUSE-MANIFEST.json`. Historical admissions,
stage outputs and old test receipts were deliberately not imported.

The only instrumentation change is seven complete-RHS SCC prefixes in three
modules. `COARSE-TO-FINE.patch` shows just this delta. All existing coarse SCCs
remain. No new `seq`, helper, branch, cache or reordered validation is introduced.
The source-byte inverse is a constrained transformation check, not a proof that
profiling annotations leave optimization, demand, residency or timing unchanged.

Paths below are relative to `libraries/mlf-inference/Bootstrap/`; lines are the
unchanged source's RHS extents. Exact byte/line spans, distinct site identities,
unique before/after anchors and SHA pins are in
`implementation/insertion-map.json` under `r16_fine`.

| Fine label | Site / RHS lines | What the interval includes |
| --- | --- | --- |
| `SOLVER_PREPARE` | `Graph/Solver.hs:242–256` | Entry graph validation, canonicalization and scope/reverse indices. |
| `SOLVER_STEPS` | `Constraint.hs:185` | Ordered prepared-step fold; nested fine rows are subtracted by the disjoint partition. Initial equality solving is outside. |
| `SOLVER_EXPANSION` | `Graph.hs:2259–2295` | Shared graph expansion/copy core; caller admission and later index publication are outside. |
| `SOLVER_TRANSACTION` | `Graph/Solver.hs:975–1076` and `2135–2157` | Distinct and prepared-fallback transactions; preserve separate source sites under the same label. |
| `SOLVER_LOCAL_UNIFY` | `Graph.hs:1257–1262` | Unchanged local unifier, including entry and final validation. |
| `SOLVER_FINISH_AUDIT` | `Graph/Solver.hs:538–552` | Graph/scope/reverse-index audit. Following final normalization is outside. |

There are 6 fine labels / 7 sites, 27 original / 34 combined annotation edits,
97 source files, a 95-module union, 94 Emlf modules and 60 generator modules.
Those module counts and the original 137-shared-source production oracle remain
unchanged. The original controller has no fixed SCC-label/edit count that needs
to be bypassed: `mirror.py` derives occurrences from the insertion map. Its full
manifest, disk inventory, closure and exact inverse checks are retained.

`preview-mirror/` is only a static preview. Its original-schema manifest was
accepted by the unchanged mirror verifier in this preparation. Its seven new
annotations strip to the exact earlier coarse mirror, then the original coarse
annotations strip to the pinned source, for every one of the 97 files.
`overlay-proof.json` records these byte identities. This is not a runtime plan.
An actual run must prepare a **new absent work directory** so its paths and pins
are freshly bound; do not execute or transplant an old work plan.

## Independent fine partition, original coarse reader unchanged

`implementation/fine_profile.py` SHA-checks and loads the unchanged original
`profile.py`. Its 24-label `LABELS` set is not extended. The raw GHC JSON is
strictly reparsed by that reader, retaining its schema, duplicate-key, stack
structure and total checks.

Each raw stack node contributes its **self allocation once**:

1. Compute the original coarse bucket using only the old label set.
2. In the stack suffix below the deepest old semantic label, select the nearest
   reviewed fine centre. Use `UNLABELLED` when absent. A fine ancestor cannot
   leak through a newer coarse boundary.
3. Add self allocation/ticks/node count to `(coarse, fine)`, and separately to
   `(coarse, source-site)`. Assert every coarse row equals the original parser's
   allocation/ticks/node counts and the matrix totals equal the raw totals.

Do not sum the two parallel matrices. Neither matrix adds inherited allocation.
For `SOLVE → STEPS → TRANSACTION → LOCAL_UNIFY`, that node's self allocation goes
only to `(SOLVE, SOLVER_LOCAL_UNIFY)`. A transaction residual does not mean its
inclusive work was small; STEP residual is not a ground-check-only measurement.

Generation flushes can use the same functions under `CONSTRAINT_GENERATION`;
witness/elaboration paths can expand or unify outside SOLVE. These contexts are
retained, not folded into SOLVE. The matrix is a profile's source-demand account,
not an eager call timeline, exclusive ordinary CPU, live heap or causal savings.

Fine centres must match a reviewed label, module, exact mirror source path and
RHS line extent. Both transaction locations remain distinct. Unknown `SOLVER_`
labels, wrong source/module, CAF fine centres or missing site declarations fail
closed. All seven sites must be **declared**, but a declared unused site may
remain unobserved. Multiple compiler centres for one reviewed site are allowed.
GHC's actual declaration/source-location behaviour is still untested for this
overlay. If optimization removes a declaration, preserve the raw failure and
review that fact; do not invent a centre or silently weaken the gate.

The CLI also verifies all 97 actual mirror source hashes, exact file inventory
and symlink rejection. Exact empty-directory inventory remains the unchanged
stage mirror verifier's responsibility. It requires the SHA-bound original qualified coarse summary to match
a fresh parse of the same raw profile, including every stack row. It validates
the existing byte-evidence shape and toolchain binding but **does not independently
authenticate or rerun the real byte-allocation control**. Its expected hashes
must come from separately authenticated stage receipts. The unchanged stage
mirror/provenance/guard/oracle checks remain authoritative, including patch and
full manifest regeneration. A correct report or caller-supplied digest cannot
grant admission, certify cleanup or prove actual execution.

## Lightweight verification performed

The two new test modules passed **29 tests in 0.354 seconds**, using the resolved
`/usr/bin/python3` executable with `-B`. These are source-byte/static checks and
synthetic JSON reports only. No GHC, Haskell program, subprocess workload, lock
test or profiling stage was started. They cover exact reused bytes, two-level
inverse, the original mirror verifier, metadata spans, corruption rejection,
coarse/fine conservation, both transaction sites, context reset, declaration
versus observation, strict identity and qualified-summary tampering rejection.

An initial authoring run had one test-harness failure: the negative test modified
a shallowly shared stack in both its supplied and expected summaries. The test
now deep-copies the supplied summary, as independent disk JSON inputs would be.
The first log is retained beside the passing log; no production fix was needed.

`tests/new-static-tests.json` is explicitly **not** the controller's complete
fresh test receipt. At authoring time the original 185 protocol tests had not been rerun. The
coordinator subsequently ran and bound all 214 tests and a fresh independent
review before admitting BUILD. Every later phase still needs its own admission
and the completed prior-stage cleanup evidence.

## Next steps for the coordinator, not automatically executed

Let `PACKAGE` name this directory and `SOURCE` the unchanged source checkout.
Use the resolved interpreter identity for tests and subsequent admitted commands:

```sh
PYTHON="$(readlink -f /usr/bin/python3)"
cd "$PACKAGE/implementation"
ASTRA_FROZEN_SOURCE="$SOURCE" "$PYTHON" -B -m unittest -v \
  test_solver_overlay test_fine_profile
```

After independent review and the fresh full-test inventory, the original
preparation command is unchanged and itself launches no compiler:

```sh
"$PYTHON" -B "$PACKAGE/implementation/controller.py" prepare \
  --source "$SOURCE" --work "$NEW_ABSENT_WORK"
```

Bind current locks/epoch, toolchain, ordinary producer, environment and review
to the new plan. The ordinary reference must be the original frozen-source
producer, **not** the separately edited ENCODE candidate. The existing r14
ordinary producer can only be reused through the unchanged authenticity checks.
There is no protocol bypass for reuse. Five separately admitted stages retain
the original budgets: BUILD 600s, QUALIFY 180s, PROBE-CONTROLS 420s,
TARGET-QUALIFICATION 420s, ATTRIBUTION 240s, with the original per-compile and
resource limits. No automatic retry or continuation is added. Preserve all
fresh-artifact, ordered-query, target, semantic/demand, unit and cleanup checks.

Only after those stages succeed, run the read-only postprocessor on the final
archived P profile and its original `allocation-raw-partition.json`:

```sh
"$PYTHON" -B "$PACKAGE/implementation/fine_profile.py" \
  --profile "$ARCHIVED_RAW_PROFILE" --profile-sha256 "$RAW_SHA256" \
  --coarse-summary "$ORIGINAL_QUALIFIED_SUMMARY" \
  --coarse-summary-sha256 "$SUMMARY_SHA256" \
  --mirror-root "$NEW_ABSENT_WORK/mirror" \
  --mirror-manifest-sha256 "$MANIFEST_SHA256" \
  --toolchain-sha256 "$ACTUAL_GHC_SHA256" \
  --output "$NEW_REPORT_PATH"
```

The output path must not exist. The CLI requires some observed SOLVE subdivision
in addition to all seven declarations. No historical real profile is relabelled
as a fine run. New coarse totals need not equal the earlier 35,598,371,704 SOLVE
bytes: SCCs can perturb the diagnostic. Artifact equality, not guessed timing
or byte equality to the old profiling build, is the semantic control.

Native A/B and fixed-point experiments are not enabled by this package.
