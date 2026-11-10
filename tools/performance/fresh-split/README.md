# Fresh split strategy (B2)

Reviewed candidate with a passed small fixture, not a measured optimization. No production code or package API
changes. Original B0 remains the single-crate, 90-module build that exhausted its
600-second guard before producing checked artifacts. This experiment changes the
build strategy and crate identities; it is not a same-implementation algorithm
speedup, and it does not replace B0. Stock `mlfpkg build --target emlf` compiles 98
modules and is deliberately not used here.

## Frozen input and target

`prepare.py --kind compiler90` consumes the original B0 workload file and source
checkout. It intersects that exact import closure with existing package ownership:

- foundation 14, language-core 4, frontend 11, xmlf 6, inference 11
- interpreter 2, llvm 13, crates 21, package-core 2, entry 6

Exactly 90 unique source modules, 5,233,364 bytes, original source hashes and paths,
entry `MLF.Entry.Emlf`, only external source import `MLF.Primitive`. The plan checks
package ownership, original direct package dependencies, unique source/module
ownership, dependency topology, and an independent recursive source-import walk.
No source is rewritten. Source module exports remain unchanged. All nine libraries
and the entry crate are target work. The compiler is built by the authenticated
ordinary GHC O2 producer using its existing public `--compile-crate` entrypoint.

## One endpoint, one budget

`run.py` authenticates the unchanged producer and existing fixed setup. It neither
rebuilds them nor adds target artifacts to setup. Static plan creation, source and
tool pin preflight and producer authentication are excluded, like B0's preparation.
Additional static slice planning is explicit experiment setup, not hidden reusable
compilation. The setup's original builtin pair and producer identities must match. Inherited
`MLF_QUERY_PROFILE`, `MLF_QUERY_SEMANTIC_AUDIT` and `MLF_QUERY_FAILPOINT` are rejected
even when set to an empty string, and their absence is recorded. The original helper
still removes all `MLF_DIAGNOSTIC_*` variables from child environments.

One `H.Runner` launches `with_scope.py -> worker.py`, with the same 600-second wall,
5 GiB sampled process-group RSS, 6 GiB per-process address space, 4 GiB work-directory
cap, 5 GiB free-disk floor and 3 GiB available-memory floor. Every subprocess inherits
that process group and scope. There is no nested Runner or per-slice timeout reset.
The worker's total endpoint includes:

1. Checking input pins and creating each new spec/query directory.
2. All ten fresh source compilations, library serialization and all dependency reads.
3. Fresh-query assertions, artifact hashes, public `--show-crate` checks of each
   slice's module ownership, direct dependency identity and exact dependency path.
4. Final ordinary `--crate-to-llvm-gc` without cache. This still links all checked
   bodies, runs production whole-program validation and the unchanged LLVM backend.
5. The original one-job Clang `-O2 -Wno-override-module`, same runtime and setup libs,
   then exact authored `--version` and `--implementation-identity` checks.
6. One independent interpreted program with authored output and one rejected type error,
   executed by the new compiler. These extra named stages are included in the same
   600-second budget. B0 did not include these checks; their costs remain explicit.
7. Final input/artifact pin rechecks and stage receipt writing.

The final producer authentication is an untimed integrity check, not target work.
The whole qualification endpoint is the one outer process lifetime, never a sum
of successful stages. The unchanged guard logic also records its original monotonic
start/end timestamps. The worker records the instant Clang returns, the completion
of CLI checks, and semantic-check start/end. The final receipt reports:

- `source_to_runnable_seconds`: outer launch through Clang completion.
- `source_to_cli_seconds`: same launch through both version/identity checks.
- `semantic_validation_seconds`: the two extra checks, separately measured.
- `whole_qualification_scope_seconds`: the original exact-child wait4 total.

B0's compiler endpoint stops after its worker finishes Clang and exits; CLI checks
are untimed postchecks there. Compare runnable boundaries, not the extra checks.
The B2 marker stops at Clang return rather than B0 worker teardown, a small explicit
transport-boundary difference, so retain both raw timestamps and do not claim a
precise paired speedup from a single qualification run. Per-stage clocks are descriptive only. Sampling can miss short RSS peaks.
A failed/guarded attempt retains logs and partial artifacts, with `complete=false`.
The output directory must not exist; there is no restart/resume or completed-slice
reuse. A retry requires a brand-new output directory and rebuilds every target.

The compiler-only run checks the build, CLI, one small interpreted program and one
type rejection, not full compiler semantics. It
never asks the resulting compiler to build a compiler, compare compiler generations
or find a native fixed point. It does not compare another compiler generation and
does not run `llvm-memory/check_native.py`. Its only semantic-check commands are:

```
new-compiler --run --expr 'main = do { printInt 42; putStrLn "split λ" }'
new-compiler --type --expr 'stringLength 1'
```

The first must output `42` and `split λ` on separate lines with empty stderr.
The second must exit 1 with `type constructor mismatch`; a crash or signal is failure.

## Small independent prerequisite

`--kind fixture` uses the same worker with two libraries and a main crate. A public
ADT, polymorphic Box/unbox and class cross crate boundaries; an orphan instance
lives in Facade and is used both there and from Main. Explicit exports hide `hidden`.
The final linked native program must print `split λ`, `42`, `42` on separate lines.
Three fresh negative roots must reject a private export, an invalid argument type,
and an unavailable direct dependency (transitive source visibility is insufficient).
A separate intact copy of the main interface/object must first link to byte-identical
LLVM. Only then is that copy corrupted; it must fail ordinary checked linking with
a checksum/SHA-mismatch diagnostic, not a relocation or dependency error.
Valid target artifacts and the fixed builtin are never modified. This fixture is
not the compiler target and not a compiler-generation A/B test. It has a separate
control window and its time is not included in a later compiler sample.

Python contract tests exercise positive inventory and negative ownership, hash,
topology, count, fresh-query and interface checks. They start no compiler processes.
The real fixture passed on 2026-11-10 using source commit `135a31331713baad0ddc4c22a09fd0ea312dc258`: all seven groups fresh, the exact native output, intact-copy LLVM equality and all four targeted rejection controls passed. Its complete outer guarded scope was 5.160891106 seconds. See `fixture-results.json` for the portable summary and evidence limits. The small prerequisite is not a compiler speed measurement. A subsequent strict 90-module attempt exhausted its unchanged 600-second guard during the seventh library; see the result below.

## Commands

Source the same externally provisioned toolchain environment as B0. Paths below are
caller-supplied examples, not machine-specific defaults. Use the coordinator's shared
flock around each complete `run.py` command, and only after receiving its CPU token.
The script also acquires the authenticated producer's `.reproduction.lock`.

```
python3 -B tools/performance/fresh-split/test_contract.py
python3 -B tools/performance/fresh-split/prepare.py --kind fixture --output FIXTURE_PLAN
python3 -B tools/performance/fresh-split/run.py --plan FIXTURE_PLAN \
  --setup ORIGINAL_SETUP --producer ORIGINAL_PRODUCER \
  --producer-source ORIGINAL_SOURCE --output NEW_FIXTURE_OUTPUT

python3 -B tools/performance/fresh-split/prepare.py --kind compiler90 \
  --source ORIGINAL_SOURCE --workload ORIGINAL_B0_WORKLOAD --output FROZEN_SPLIT_PLAN
python3 -B tools/performance/fresh-split/run.py --plan FROZEN_SPLIT_PLAN \
  --setup ORIGINAL_SETUP --producer ORIGINAL_PRODUCER \
  --producer-source ORIGINAL_SOURCE --output NEW_COMPILER_OUTPUT
```

Do not publish raw local receipts or plans without specific approval: they contain
absolute input paths and host/tool metadata. A source-only checkpoint can reproduce
new evidence, but a summary/hash cannot restore raw evidence lost after restart.

## Guard instrumentation provenance

The independent experimental checkout's `a1-private-index/helper.py` has one added
record-update line: `started_monotonic_ns=begin, completed_monotonic_ns=end`. Its
original SHA256 is `0d11b29419a32fc9832096951aa085cc317c8a304b9db110ee96ba411a4ce7cc`.
The instrumented SHA256 is `03e12fd51ae1e5587d400a59ebbe160d9f21fe0dccf22b6ce24ab693f465a126`.
Neither the frozen B0 checkout nor another worker's files are changed. No guard,
start time, wait4, exit handling, environment or resource-limit logic is changed.

## Strict 90-module qualification outcome

The single admitted full attempt used checkout `9c0bea5847b995334e3bdd2b588509d45f0111e1`,
whose executable harness bytes remain the reviewed `135a31331713baad0ddc4c22a09fd0ea312dc258`.
It failed the original 600-second wall guard at 600.039880246 seconds, while compiling
`mlf-crates`. Six completed libraries cover 59 modules and 2,807 newly inferred groups.
No final entry, whole-program LLVM, runnable compiler, CLI or small compiler semantic
check was reached, so there is no runnable time, qualified compiler ratio or speedup.

Closed library compile stages total 346.093917351 seconds and the six explicit
interface checks total 0.684103539 seconds. The final 252.8775535-second open window
starts at the last completed interface command and ends at termination; it chiefly
contains unfinished crates compilation, not an inferred 253 seconds of wrapper
overhead. Its exact exclusive stage duration was not persisted. The original B0
single-crate failure remains visible and unchanged. There was no retry or longer
budget. See `compiler90-results.json` for portable phase/partial-artifact identities,
resource observations, cleanup limitations and raw-evidence persistence limits.
