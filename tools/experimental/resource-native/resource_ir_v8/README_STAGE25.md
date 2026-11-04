# Stage25: closed scalar computations inside a shared generalized lambda

**Finite local qualification is complete.** The two formerly rejected programs now
produce 42 with balanced native ledgers. The ordinary matrix, sanitizers, focused
Instance guards and legacy native reports pass. Full retained source/event observation and the final new two-case
fresh-source qualification pass. This isolated candidate is
based on Stage24; it is not acceptance of the newly advanced target branch.
Nothing enables this experimental route by default or establishes general MLF,
GC replacement, a speedup or a comparison with Perceus.

## Bounded language change

A shared rank-1 direct lambda may compute with ordinary closed Int/Bool captures.
Its fully saturated scalar operations are `addInt`, `subInt`, `mulInt`, `eqInt`
and `ltInt`; its retained conditional must return Int. Both branches are checked,
including a branch not selected at runtime. The complete checked type computation,
root type, erasure and outer-first normalization remain authoritative. The source
producer is unchanged. Complete use vectors, including unused coordinates, remain
present, with one shared definition rather than per-type body clones.

The source checker and planner propagate the original Scheme scope through the
primitive or conditional body and both branch carriers. Closed ordinary captures
retain their original node and memo. The effectful body and its newly allocated
values use the particular closed Instance Env. A closed scalar operation does not
make its enclosing callable signature monomorphic or scalar-only.

This does not admit partial/aliased builtins, open scalar operations, a Bool-result
conditional, callable or nominal imports, nested/recursive generalization or
arbitrary evaluation during generalization. The Stage24 capture requirements,
64-import bound and alias ownership rules remain. Explicit type annotations are
not a substitute for the inferred source cases.

## Closed-entry proof and runtime boundary

Resource checking derives `instance-only-scoped-scalars/1` for an effectful
Scheme. It proves one direct sealed closure, the exact root Site/Code, the complete
same-Scheme Code closure and its effect instructions. Extra neutral allocations,
helper roots, pending neutral application roots and unreachable same-Scheme
functions are rejected. `new_below` inside this effectful introduction is also
rejected by this deliberately bounded proof slice. It is not asserted to be
intrinsically unsafe. The tested imported sources fall back to coarse ownership
for the relevant introduction under the optional groups strategy.

Metadata independently reconstructs the proof from raw and derived Code
inventories. Neutral CodeExecution and SiteExecution type/representation rows
remain; only invocation coverage is Instance-only for this proof. This is not
removal of dead Code checking or a source-provided promise. The fixed native packet
format does not gain a per-Code effect/import whitelist.

For the new scoped operation allowance, native FORCE, PRIM2 and SELECT entry
checks authenticate the actual Instance
frame, Code, execution, Env, Scheme, capsule, activation and home, with no active
introduction. Public FORCE in that Instance execution additionally requires the
actual operand to have a
closed intrinsic scalar type and matching physical representation/principal type.
Existing private callable forcing is unchanged. Generic construction remains
non-evaluating; neutral invocation of all three operations still fails. Global
publication, neutral memo/origin rules, Fill, allocator accounting and the default
retain-on-fault policy are not relaxed.

## Genuine unannotated programs

Both fixtures have an unused SharedPoly import for the retained producer route;
its annotated identity is projected away. The local `k` is inferred in each case.
There is no identity-specific implementation.

- `mixed-scalar`: `bonus = addInt 20 1`, `flag = ltInt bonus 22`, and
  `k = \x -> if flag then bonus else 0`. `addInt (k true) (k 0)` returns 42.
  Actual checked normalization has two `/1` steps. The original bonus and flag
  are each memoized once. Two closed Instance bodies select their own then branch;
  the unselected callback bodies do not execute.
- `alias-scalar`: `bonus = addInt 5 5`, `other = bonus`, and
  `k = \x -> addInt bonus other`. `addInt 2 (addInt (k true) (k 0))` returns 42.
  Actual normalization has zero `/1` steps. Two lexical capture slots keep
  distinct ownership while pointing to one original pending bonus node. Each
  Instance body computes 20 after the original bonus has been computed once.

These exact sources and their earlier Stage24 FRAGMENT refusals are preserved.
The active Stage24 portable suite replaces only those two now-admitted negative
slots with a Bool-result conditional and a callable import. The former is rejected
at the exact PRIMITIVE boundary, the latter at the exact CAPTURE boundary, before
planning or native compilation. Old positive cases and all historical source
strings are unchanged.

## Finite validation and limitations

The first mixed and alias native reports return 42/fault0 with all seven terminal
memory categories zero. Mixed has 190 events, work 8,979,298, allocated/freed
16,952 bytes and peak 8,480 bytes. Alias has 172 events, work 7,578,422,
allocated/freed 15,544 bytes and peak 8,576 bytes. These are ledger/work observations,
not elapsed-time or RSS measurements. Guard mask 117440495 excludes projected
transport and Fill; neither is claimed covered by these cases.

Eight ordinary conditions cover both sources, coarse/groups and O0/O2. Two first
pairs are reused and six are new. Four O0 ASan/UBSan conditions, with LSan disabled,
match the full corresponding ordinary reports, including every work field.
The groups reports have different work/allocation figures from coarse, so only
matching placement/optimization conditions are compared for equality.

Focused native controls use actual registered generated objects. Both sources
pass 22 modes at each optimization with complete O0/O2 report equality. Mixed
exercises Instance FORCE and SELECT; alias exercises Instance FORCE and PRIM2.
Neutral-opcode probes and copied frame/operand facts are rejected. Every retained
fault's positive live bytes/blocks equal its separate explicit terminal retirement;
retain is not reported as an empty ledger. This is not arbitrary-pointer recovery,
race safety or a public API mutation guarantee.

The existing native suite passes all 22 cases at O0 and O2, with all 44 full reports
unchanged from the prior qualified stages. The existing five native planner reports also match Stage24 exactly. Standalone
host checks pass 475 and the emitter suite passes 128. Focused source/planner checks pass 25, broad source checks
260, planner host checks 60 and resource/metadata checks 345. The planner host-only invocation does not count its disabled native test;
that five-fragment test was subsequently executed separately.

Seven additional synthetic raw-IR recipes exercise all five primitives and both
conditional directions in actual Instance frames. Both complete Int/Bool views
are demanded at O0/O2. Actual terminal outputs are 23, 11, -42, Bool true, Bool false,
37 and -19; Bool results are not represented by a marker scalar. Fourteen native
runs and 28 clean process records pass, with full optimizer-report equality,
once-only pending APPLICATION memoization, selected callbacks only and seven zero
ledger categories. These are raw-IR tests, not extra original-source qualification.

Full retained source/event observations pass all twelve ordinary/sanitizer reports,
with 510 copied-report and 198 structure controls. Reviewer counterexamples added
exact raw force-variable joins, actual allocation opcode/output/state checks and
shared closure principal type/Scheme checks. The first coordinator graph reader
used the ordinary report filename for a sanitizer directory and stopped after eight
successful observations; its corrected host-only replay passes twelve. Both failures
and old successful evidence remain. No target was rerun to hide an observation error.

The new two-case portable suite completes two additional fresh builds/source calls.
Both return 42 with seven zero terminal ledger categories, and both full native
reports and raw captures are byte-exact to their retained originals. All 16 child
records exit0 with empty stderr and clean termination. Actual source/proof/graph
checks pass 85 copied-report and 33 structure controls. This is a genuine fresh
producer path, not substitution of the saved input or native binary.

The migrated old portable suite has completed four fresh builds/source calls: two
unchanged positives return 42 with seven zero live categories; the Bool-result and
callable-import negatives reject exactly before planning/native. All four captures
are byte-exact to their retained originals, and both full native reports equal
Stage24. All 28 process records are clean, with 26 exit0 and the two expected outer
CLI exit1 refusals. This is qualification on the isolated baseline, not a250.

An emitter regression retained its old exact import allowlist and failed at A13.
The test now explicitly admits the two reviewed constant imports from
`program_schema` and `provenance`; its execution/file-call prohibitions remain.
The original failure is retained. Observer-only mistakes/counterexamples are fixed
against saved reports, never hidden by a native rerun. Public events do not expose
every owner Access or callback capsule; separate focused native controls supply
bounded private-boundary evidence.

## Reproduction

Host-only focused checks:

```sh
python3 -B -S tools/experimental/resource-native/tests/test_ir8_generic_primitives.py
python3 -B tools/experimental/resource-native/tests/test_module_shared_generic_primitives.py
python3 -B tools/experimental/resource-native/tests/test_planner_v8_generic_primitives.py
```

The fresh two-case source runner is enabled after its retained actual source/event
checks and independent review. The final fresh call passes. Its command is:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_generic_primitives.py \
  --ghc /absolute/path/to/ghc-9.14.1 --cc cc --output /absolute/new/primitive-source
```

All existing process bounds and defaults remain. Fresh outputs must be outside the
checkout and absent. The source wrapper has a 1,500-second deadline; each GHC build
uses 600 wall seconds/480 CPU seconds/8 GiB address space, capture uses
180/120/4 GiB, native compilation 60/30/1 GiB and native execution 30/20/1 GiB.
The fixed numeric-version query retains its RTS reservation override. Address-space
limits are not RSS measurements. There is no automatic retry or cap increase.

The workflow adds a separate 20-minute CI source job for the two new inferred
cases and their focused guards, plus the seven-recipe semantics test in the existing
10-minute runtime-host job. All prior job ceilings remain unchanged. The old 26-case/60-minute source job is not extended. The
existing generic-capture job keeps four cases with the two documented replacement
refusals. Exact-commit CI and acceptance on the advanced target remain separate.

## Checked-Prelude target requalification

The same Stage25 implementation was subsequently composed onto the accepted
Stage24 plus target-a250 integration. That base preserves the regenerated Prelude,
maintained lock, strict current and historical migration paths, and producer input
checks. Only the Stage25 delta was applied; the base integration text in the parent
README was retained. No Stage26 implementation is included.

All six fresh source pipelines passed again on that actual combined source:
four healthy native results are Int 42 with seven zero terminal ledger categories,
and the two exact refusals stop before planning or native compilation. All six raw
captures and all four complete native reports match the prior Stage25 evidence
byte-for-byte. Forty-four command records are clean: 42 exit zero and two expected
outer source-refusal exits are one. These are new compiler builds and source calls,
not adoption of old producer receipts. The existing host 475 and emitter 128 checks
also pass, as do the current migration 11 checks under normal and optimized Python.
The earlier baseline-specific qualification paragraphs remain historical records.
Exact-commit CI remains separate; no default behavior or general capability claim
is changed by this integration recheck.
