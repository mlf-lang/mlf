# Stage26: ready concrete callable imports into shared lambdas

**Bounded opt-in implementation on the accepted integration base.** Original source capture and host admission/refusal checks are complete. The two positive native cases have passed eight ordinary conditions and four sanitizer conditions, and the final graph observer has passed all 12 retained reports. The enabled observer is composed onto the accepted advanced-target base, where all six fresh source pipelines have also passed. Exact-head CI remains separate.

## Bounded capability

The opt-in IR8 source route may retain an ordinary, directly bound concrete helper lambda inside a top-level shared rank-1 direct lambda. The helper's complete type must be a finite Repeat/unknown arrow whose recursive leaves are exactly Int or Bool. Nested scalar-arrow arguments and results are admitted, but nominal leaves, open types, Scheme/view captures, pending function-valued applications, and forced or returned callable provenance are not.

The helper is one existing ready closure, not a body copied into every instantiation. It may already own lawful captures, including a pending scalar. Those slots remain inside the helper with their original owners and Accesses. The new generic import does not flatten or force them. Complete ordered Bool/Int use vectors, including unused coordinates, remain intact. Original K checking, lexical binding/type computation, erasure, normalization witnesses and the ordinary term graph remain mandatory.

Raw checking establishes exact allocated CONCRETE/E0 CLOSURE provenance, full Type/Code identity, owned MONO state and Down support. Explicit imports retain fresh child aliases after generic begin; the parent stays live and child aliases are discharged before seal. At most 64 import entries are allowed, with aliases counted separately. Type depth 32, type size 4096 and all existing work/capture bounds are unchanged. Optional `--data-groups` preserves actual support and falls back when only Down, rather than strict Below, is proved.

The new `instance-only-concrete-callable-imports/1` proof is independently required even for an application-only callback with `effects=[]`. It binds the directly sealed root, all same-Scheme Code declarations and exact callable import owners. Neutral typing rows remain, but invocation coverage for that proved scope is Instance-only. See the Stage26 section in CORE_CONTRACT.md for the full schema and rejection obligations.

Native admission changes only CAPTURE. It authenticates the target's own ready closure, registered Site/Code/E0 Access and recursively closed scalar-arrow contract. Canonical CodeSpec resolution and the helper's physical legacy `@signature` representation are separately checked against the same full type; their representation IDs need not be equal. The existing identity transport preserves the helper's E0 Access. Its invocation home is a dynamic call authority and must not be inferred from the helper's allocation Env or source name. Neutral application, memo, return, Fill, general publication, allocator accounting and retain-on-fault defaults are unchanged.

Source/resource rejection of forced or returned provenance is not a claim that runtime reconstructs source history. Public events also do not expose every acquired owner Access, capsule or authority-owner association. Exact static joins, actual visible events and focused private guard controls provide distinct evidence; none is a runtime source-import whitelist.

## Genuine sources and preserved refusals

Each case uses the real `SharedPoly` module/import route. Its imported identity is projected away; the local `k` is inferred, not recognized by name or specialized.

Direct helper:

```text
import SharedPoly
let helper = \n -> addInt 21 n in
let k = \x -> helper 0 in
addInt (k true) (k 0)
```

Captured helper:

```text
import SharedPoly
let bonus = addInt 20 1 in
let helper = \n -> addInt bonus n in
let k = \x -> helper 0 in
addInt (k true) (k 0)
```

Both positive originals have ordinary checked Int roots and zero-step `shared-rank1-callable/1` normalization. Fresh independent host replay admits their exact graphs and full [Bool], [Int] uses. The captured helper retains one ordinary pending bonus inside its own closure. The final graph observer now checks the recorded graph and invocation/memo events separately from the basic terminal results; it does not turn unexposed owner Access or capsule facts into observed trace claims.

The separately captured pending-callable negative uses `helper = maker 21`, where `maker = \z -> \n -> addInt z n`. Ordinary source checking succeeds, but current replay still rejects at the actual helper occurrence with CAPTURE: a callable import requires a directly bound ordinary lambda. That refused fragment has no completed independent normalization admission and never reaches native planning.

The original scalar-only CAPTURE reports remain historical evidence, including the old direct-helper refusal. The current portable scalar-capture suite replaces only that now-admitted direct-helper negative with the authenticated pending-callable case. Its two scalar positives and Bool-result conditional refusal remain. Older primitive-refusal source strings are preserved as history, not silently rewritten as current failures.

## Completed local evidence and remaining qualification

- The callable resource suite has 20 tests. The final combined resource/metadata regression passed 365 tests with no skips. The latest source/planner focused run passed 28 tests, including both new retained captured-helper/pending-callable originals. Ordinary CI runs the synthetic tests; retained-artifact and old-baseline comparisons require their explicit environment paths and otherwise skip.
- The sanitized emitter rerun passed 128/128. The first attempt stopped at the exact stale `runtime_emit_body.py` custody pin before any case ran. That pretest failure is preserved; only the reviewed implementation pin changed before the separate successful run.
- Both positive native cases passed coarse/groups × O0/O2, eight conditions total. Each matrix reused its initial coarse/O0 report and added three pairs. Complete O0/O2 reports agree within each placement. All return Int42, fault0 and seven zero-live ledger categories.
- Four O0 ASan/UBSan conditions passed with LSan disabled. Complete reports, including work fields, equal their ordinary counterparts.
- Synthetic callable guard fixtures passed both optimization levels with exact JSONL equality: 51 controls per run for the helper with a pending scalar capture, and 59 for the nested scalar-arrow contract. The nested fixture checks admission and capture transport but deliberately does not invoke that helper. These are raw-IR controls, not additional original-source examples.
- The 44 retained legacy native reports remain exact to the Stage25 baseline. This is separate from the new source/observer qualification.

Observed deterministic work and memory are diagnostic accounting, not a speed comparison:

- Direct helper, coarse/groups: work 5,625,728 / 5,487,815; allocated 14,608 / 16,272 bytes; peak 7,984 / 7,904 bytes.
- Captured helper, coarse/groups: work 7,261,231 / 7,148,763; allocated 16,680 / 17,512 bytes; peak 8,600 / 7,960 bytes.

The first direct native attempt remains a real fault8 failure from the too-strong canonical-versus-physical representation comparison; the correction was reviewed before its separate successful run. The first callable guard attempt also remains failed evidence: its wrong-representation mutant rejected with fault8 and retained/retired the same 3,416 bytes, but the test expected the wrong rejection location. That oracle was corrected to the bounded representation-table lookup's exact unregistered-reference failure. Later runs do not erase either failure or turn the original records into passes. Final observer review and integrated fresh-source qualification are complete. Intermediate observer files are not substituted for the final current-byte twelve-report check or the fresh integrated results.

## Reproduction commands

Run from the checkout root. Use new output paths outside the checkout; helpers refuse to overwrite their output directories. These commands are instructions, not executions performed while drafting.

```sh
base=tools/experimental/resource-native
PYTHONHASHSEED=0 python3 -B -S "$base/tests/test_ir8_generic_callable_imports.py"
PYTHONHASHSEED=0 python3 -B "$base/tests/test_module_shared_generic_callables.py"
PYTHONHASHSEED=0 python3 -B "$base/tests/test_planner_v8_generic_callables.py"
```

The 20 resource methods include one optional retained Stage25 comparison. To reproduce it, set `IR8_GENERIC_CALLABLE_BASELINE` to the retained Stage25 `tools/experimental/resource-native` directory. Source/planner saved-evidence options are `IR8_GENERIC_PRIMITIVE_DIAGNOSTICS_ROOT` for the first direct-helper original, `IR8_GENERIC_CALLABLE_DIAGNOSTICS_ROOT` for the captured-helper/pending-callable originals, and `IR8_GENERIC_PRIMITIVES_ROOT` for Stage25 complete-plan/generated-file comparisons. Do not populate these variables with unrelated artifacts just to eliminate skips.

```sh
# Set out to a new external parent directory.
PYTHONHASHSEED=0 python3 -B "$base/tests/prepare_generic_callable_guard_fixture.py" \
  --output "$out/captured-fixture"
python3 -B "$base/tests/test_generic_callable_capture_guards.py" \
  --generated "$out/captured-fixture" --output "$out/captured-guards" \
  --cc cc --expected-scalar 42 --require-helper-captures
PYTHONHASHSEED=0 python3 -B "$base/tests/prepare_generic_callable_guard_fixture.py" \
  --nested --output "$out/nested-fixture"
python3 -B "$base/tests/test_generic_callable_capture_guards.py" \
  --generated "$out/nested-fixture" --output "$out/nested-guards" \
  --cc cc --expected-scalar 42
```

The fixture builder performs host checks and C emission only. The guard runner compiles and executes the real supplied pair at O0/O2, preserving its existing per-process limits: compilation wall60/CPU30 seconds and 1 GiB, execution wall60/CPU40 seconds and 512 MiB. It retains failures and does not invoke a source compiler.

The independently reviewed observer is enabled in the qualified advanced-target candidate. The two-case fresh entry is:

```sh
python3 -B "$base/tests/test_source_v8_generic_callable_captures.py" \
  --ghc /absolute/path/to/ghc-9.14.1 --cc gcc \
  --output /absolute/new/external/source-generic-callables
```

Do not enable it by bypassing `QUALIFICATION_READY`. Its existing CLI child limits remain wall1200/CPU900 seconds, 16 GiB, 1 MiB stdout/stderr and 64 MiB file size, with 15 seconds termination grace. Its internal suite deadline is 1500 seconds; the new CI job has the stricter overall 20-minute ceiling, including toolchain setup. Those are ceilings, not a guarantee that every runner finishes in time.

## CI qualification

`.github/workflows/ir8-host.yml` adds two independent callable jobs. Leave every existing job, step, artifact path and ceiling byte-for-byte unchanged. A separate 10-minute callable host/guard job groups the 20 resource tests, synthetic replay/planner tests, and both synthetic fixture/guard pairs with its own failure-retaining artifact. It uses the hosted runner's existing Python and `cc`, with no installation step. Combined timing on that new hosted job remains unmeasured; the hard 10-minute ceiling is not a guarantee of completion, and no existing runtime-host budget is expanded.

Create a separate 20-minute two-case source job with the pinned official GHC setup and unchanged helper limits. The observer is enabled after independent review and all twelve retained report checks. Integrated fresh-source qualification has completed locally; exact-head hosted CI remains separate. Do not append these cases to the old 26-case/60-minute job or modify any other source job or cap. The guard steps make no additional source captures.

The new job uses only `build-essential`, `libgmp-dev`, `libnuma-dev`, `libncurses-dev`, `pkg-config` and `xz-utils`. The C compiler and make support the existing host/supervisor objects and official GHC installation; the three library packages support that GHC distribution, `pkg-config` supports configuration, and `xz-utils` extracts its pinned archive. `source_build_v8.build_producer` uses GHC 9.14.1 with its existing global packages, the selected `cc`, and those two C objects. It requests neither the LLVM backend nor GC linkage. The `libraries/mlf-llvm` Haskell search-directory entry is not an invocation of LLVM or Clang. Therefore this new job omits `clang` and `libgc-dev`; every existing job's dependency list is unchanged. The GHC download URL, checksum, version check and installation commands are otherwise copied exactly, apart from the new evidence directory. No local installation is performed or unpaused by this proposal.

There are no new packet tables, public ABI changes, default activation, supervision layers or performance claims. This finite extension is not general MLF, GC replacement or Perceus equivalence.


## Advanced-target source requalification

The final candidate preserves the accepted Stage25 plus target-a250 Prelude, lock,
producer and strict migration paths. All six fresh pipelines passed on that actual
combined source: the two older scalar positives and both new callable cases return
Int 42 with seven zero terminal ledger categories. Bool-result conditional and
pending-callable import retain their exact pre-planning refusals. All six raw
captures and all four complete native reports match the completed original and
qualified runtime evidence byte-for-byte. Each new source's four generated files
also match the corresponding independently checked initial native program.
All 44 command records are clean: 42 exit zero and two expected outer source
refusals exit one. No historical producer receipt or native binary was substituted.

The unchanged focused guard runner also passed on both genuine source-generated
programs at O0/O2: 30 copied-packet cases and 21 real-session cases per run. The latter
include two healthy paths and nineteen retained faults, each separately retired
with exact category accounting. These are private-boundary test seams, not public
arbitrary-pointer recovery or evidence that every owner Access is exposed in traces.

The new host-job's exact four shell steps passed locally on this candidate under
the unchanged 600-second ceiling, with no installation: 20 resource tests, 15 source
tests and 13 planner tests, including respectively 1, 3 and 4 explicit optional
retained-evidence skips. Both synthetic fixture/guard suites passed. This local
bundle is not a hosted-runner timing guarantee or exact-head CI acceptance.

Earlier observer-only assumptions about strict group support and the authority
owner ID were corrected against retained reports. An intermediate direct summary
recorded the later file hash rather than its actual saved loaded snapshot. Final
acceptance uses the frozen current-byte twelve-report replay instead. The first
full replay reader's tuple/list comparison failure, a coordinator cwd preparation
failure before any host test, and a post-run readback path error are retained.
No source/native execution was repeated to hide any observation or setup error.
