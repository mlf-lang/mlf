# F3 fixed-runtime sample proposal

Executed once as admitted F3-samples-02, with all checks passing. See
`sample-02-summary.json`. The pre-run plan SHA was a2a9a312895d130d69c0016bcde42493f32d2ff0311170dfa87999f9b3db8690.
This restoration record does not authorize another run.
The original sample.py (64913a6b) and failed F3-samples-01 remain unchanged.
That attempt launched zero target processes and has no Graph timing result.

## Changed authentication boundary

The finished O2 controls-probe is the only Haskell executable in this scope.
Main's bench branch reads argv, uses its compiled corpus, computes, and prints;
it does not read source/crate files or execute a compiler or external program.
The original three semantic receipts, two codegen receipts and mechanism review
remain exact SHA-pinned historical provenance. Keep all 15 semantic inputs,
the current binary, this controller, original helper/scope wrapper and Python
executable pinned before and after. Do not rescan unused GHC installations,
borrowed objects/interfaces, or raw codegen dumps. Explicitly report those
historical build environments as NOT reauthenticated during this scope.

The old LD_LIBRARY_PATH tail and injection environment were not recorded.
This is a new runtime qualification, not a claim to reproduce that old runtime.
Use an explicit allowlist environment: only PATH=/usr/bin:/bin, the single
specified runtime library directory, C.UTF-8 locale, TZ=UTC, GHC_ENVIRONMENT=-,
empty GHCRTS, and single-thread OMP/OpenBLAS/Make settings. In particular no
inherited LD tail, PRELOAD/AUDIT, GLIBC_TUNABLES, allocator settings, LIBRARY_PATH,
GCONV/LOCPATH or other injection settings survive into loader or target children.

A bounded ELF64/x86-64 PT_INTERP reader requires the known system loader
/lib64/ld-linux-x86-64.so.2. Invoke that trusted loader with --list on the
SHA-authenticated binary under exactly the target environment. GNU loader
resolution is transitive; retain requested names, resolved paths, realpaths and
SHA256 for every reported file-backed library and the loader. Record vDSO as a
kernel mapping, not a hashable file. Hash the loader cache when present and
reject a nonempty system-wide preload file. Parse failures or unresolved names
stop. Repeat resolution and byte checks after the cohort, require the identical
mapping (addresses excluded), and retain both listings. Kernel/Python/CPU-affinity
context is recorded; this is not a fully byte-pinned OS/container claim.

## Qualification and unchanged sample contract

Before any warmup, run the same binary with no arguments under the fixed
environment. Require exit 0, empty stderr and the original exact seven-line
O2 control inventory. This separately recorded runtime-controls item has a
15-second child ceiling and is excluded from performance statistics. No rebuild,
relink, O0 rerun, RTS change, allocation statistics, or pilot is allowed.

CLI argument parsing, creating the fresh output directory, and loading/checking
the original guard helper and scope wrapper occur before outer Popen as
controller bootstrap. Both fixed identities are checked again inside the worker. All target/runtime preflight, resolver
runs, runtime-controls, two warmups, eight samples and postchecks are inside one
original 60-second guarded scope. The unchanged
resource floors and both locks apply. Every child has a 15-second ceiling.
Monotonic phase begin/end records and pending child commands/PIDs provide failure
boundaries. Do not reset the overall budget, retry failures, reduce N or add
replacement samples. Runtime resolution/controls costs are part of qualification,
not individual sample wall times. Existing 0.314-second O2 controls are only
capacity context and do not guarantee the fixed cohort fits.

Use N=32, 179712 operations per process. Warmups: base, candidate.
Formal order: base, candidate, candidate, base, base, candidate, candidate, base.
Keep all eight walls, each side's median, candidate/base median ratio, geometric
means and the two predeclared ABBA block ratios. No outlier removal or significance
claim. Summarize only a complete cohort with successful postchecks and the outer
scope complete/exit 0/reason null/no surviving descendants.

The same renamed dual-module O2 executable selects base/candidate at runtime.
Each batch translates graph IDs, performs public unification and fully consumes
serialized result characters into a weak checksum. Checksum equality is NOT
exact serialized graph equality; exact semantics were checked separately.
Timing includes startup, oracle input filtering, rename, unify, serialization and
checksum. No compiler throughput, native MLF speed, or allocation claim follows.
The eight normalization read sites are outside this sample; the other 46 sites
are only a static reachability upper bound, not a dynamic coverage assertion.

## Proposed fixed invocation

Use absolute paths in all variables and execute from the F3 checkout. The team
lock is the already established shared resource.lock; the runtime library
directory is the toolchain's single private Debian usr/lib/x86_64-linux-gnu path,
with no inherited suffix. OUTPUT must be a fresh F3-samples-02 directory.

    flock -n "$MLF_SPRINT_LOCK" python3 -B "$F3_ROOT/tools/performance/graph-read-fusion/sample-runtime.py" \
      --producer-source "$BASELINE_SOURCE" --semantics "$SEMANTICS" \
      --codegen "$CODEGEN" --mechanism "$MECHANISM" \
      --runtime-library-dir "$RUNTIME_LIBRARY_DIR" --output "$OUTPUT"

No run is authorized by this template or by the mechanism eligibility JSON.
Obtain the coordinator's new admission after independent final-code reviews.
