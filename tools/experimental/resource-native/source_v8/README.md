# Controlled shared-source fragment experiment

The separate [source-only CLI](README_CLI.md) builds and runs this bounded route
from an actual module snapshot. The diagnostic capture itself remains
non-importable as native authority.

This opt-in experiment connects a freshly built ordinary source compiler to
independent shared-fragment replay, IR8 planning and the real Stage05 runtime.
It does not change the maintained export/2 frontend, v7 route or any default
entrypoint. It is not yet a general shared-polymorphic source bridge.

## Trust boundaries

1. `Main.hs` and `ResourceSharedExport.hs` build a standalone diagnostic producer
   against the repository's real compiler sources. It calls
   `MLF.ResourceModules.compileCaptured`, performs ordinary whole-source checking
   and checked outer-spine projection, then rechecks the retained and normalized
   terms. Normalization requires root-type alpha equality, ordinary erasure
   equality and unchanged declarations. It does not clone a shared RHS for each
   requested type or beta-reduce/in-line ordinary term bodies.
2. The result is explicitly `mlf-shared-source-capture/1`, with status
   `diagnostic-not-runtime-admission`. It is **not** the final
   `mlf-checked-module-export/3` format. Fields saying that checks passed are not
   independent authority to run arbitrary JSON.
3. `tests/validate_shared_capture.py` verifies completed captures against exact
   fixture bytes supplied by its caller. It independently replays module
   custody, projection, binder-origin joins and normalization. Authentication of
   the actual producer build and completed invocation remains the caller's job;
   reading a capture file cannot establish those facts by itself.
4. `module_shared_transport.py` derives/replays the bounded
   `mlf-shared-fragment-replay/1` fragment. `planner_v8.plan_fragment` freshly
   replays that input and produces a candidate IR8 program with correspondence
   rows. Its result still says `source_admitted=false` and
   `ordinary_K_checked=false`; this API is not an ordinary source checker.
5. The independent IR8 resource checker and public runtime emitter check the
   candidate before C generation. The native test compiles and links the seven
   production C translation units, generated packet/body pairs and the real test
   driver. It does not use dummy callbacks or an older runtime fallback.

The supported fragment is deliberately narrow: Int, Bool and arrows; complete
closed Int/Bool vectors at shared rank-1 callable uses; supported scalar
primitives and an Int conditional. Pending shared RHSs, captured callable views,
dead type parameters and curried callable values have separate regression
cases. Bare, partial or open shared uses, recursive/nested generic definitions,
unsupported proofs, higher-rank uses and nominal operations reject. Preserving
declaration syntax does not admit nominal carriers or their runtime operations.

## Fragment and planner tests

From the repository root, with POSIX, Python 3.12 or newer and an existing C11
compiler:

```sh
python3 -B tools/experimental/resource-native/tests/test_module_shared_transport.py

CC=gcc IR8_PLANNER_NATIVE=1 \
IR8_PLANNER_NATIVE_OUTPUT=/tmp/ir8-planner-native-fresh \
python3 -B tools/experimental/resource-native/tests/test_planner_v8.py
```

The fragment suite has 54 unittest cases. The planner suite has 12 unittest cases;
its final test runs five native fragment subcases: pending shared RHS, nested
view capture, a distinct dead-parameter vector, curried sharing and an unselected
arithmetic branch. Without `IR8_PLANNER_NATIVE=1`, that final test is skipped.
Set `CC` explicitly if `gcc-14` is not installed; the planner's default is
`gcc-14`. The retained native output directory must be new.

These tests use synthetic/raw fragments. They check replay, lowering and native
behavior, but do not claim genuine source inference or K-checker acceptance.
The CI fragment job sets the native opt-in and retains logs/generated programs.

## Fresh controlled source-to-native test

This integration test requires **GHC 9.14.1**, Python 3.12 or newer and a C11
compiler. It checks GHC's numeric version and will not silently substitute a
different compiler version. With GHC already installed:

```sh
python3 -B tools/experimental/resource-native/tests/test_shared_source_native.py \
  --ghc /absolute/path/to/ghc-9.14.1/bin/ghc \
  --cc gcc \
  --output /tmp/ir8-shared-source-fresh
```

The output directory must not exist. The runner builds a fresh standalone
producer and captures repository-controlled source fixtures, then performs
exact-custody/replay checks, planning, public IR8 emission and real native runs.
Its positive cases are Int-first sharing, Bool-first sharing and a two-formal
curried `sharedConst`. An unused ordinary type error is a negative control and
must be rejected by the real source compiler before lowering/native execution.
No preserved compiler binary or historical capture replaces the fresh build.

Each full-runner invocation requires its own successful result. Earlier
individual captures, raw-fragment passes or a copied capture file are not a
substitute. Keep the complete output directory on failure and inspect the actual
exit status and logs; timeout, build failure or incomplete capture is not a
successful ordinary type rejection.

The separate CI source job uses the same official GHC 9.14.1 Debian 12 bindist
pattern as the main repository CI, with archive SHA256
`60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841`.
It installs into the runner's temporary directory, verifies the version and
retains setup/test output. It adds no new setup action and does not enable this
source route by default. Local users can use an existing official installation;
the Python test does not install GHC for them.

## Observations and limits

Separate controlled Int-first and Bool-first captures have passed real ordinary
checking, exact custody/projection and independent normalization replay. Each
then returned 42 through the real runtime with zero live ledger after completion,
retaining one shared node while observing opposite actual first-use orders.
Those are finite diagnostic integration results, not general source admission.
Separately, the portable full runner passed locally on 2026-11-04: a fresh
GHC 9.14.1 producer build, all three positive sources including curried
`sharedConst`, and the unused Bool/Int type-error negative control. Each positive
returned 42 with all seven ledger categories balanced and empty, preserving the
shared pending RHS, complete type vectors and the asserted demand/capture order.
The run took about 350 seconds without retries. This is a local test result;
subsequent CI results must be checked on their exact commit.

The initial explicit-`coerce` fixtures passed ordinary source inference and
`K.check`. The independent restricted fragment replay then rejected their
impredicative forall-valued argument. This is fragment/native non-admission, not
an ordinary compiler rejection of those source programs. That boundary is
preserved without weakening either ordinary checking or the fragment rules.

Still unqualified:

- A complete public source-admission/export/3 interface and the full
  polymorphism/representation/runtime-inventory correspondence join.
- Nominal data carriers, callable-valued SUM storage, recursive generic source
  programs, arbitrary imported libraries, higher-rank use and broader MLF.
- Complete independent observation of every Access/Env/Transport transition and
  positive/negative coverage of all 27 runtime guard families.
- Whole-program source/model/runtime equivalence, complete GC replacement,
  maximal resource bounds or a measured performance improvement.

See [Stage05](../resource_ir_v8/README_STAGE05.md) for the raw-IR runtime scope and
[Stage04](../resource_ir_v8/README_STAGE04.md) for the unchanged packet/static
layers. Source/compiler tests here remain explicit and separate from those jobs.
