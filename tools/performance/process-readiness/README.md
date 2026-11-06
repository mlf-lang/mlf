# Process-readiness (W1): finite regression controls

For the separately qualified macOS extension, see [Darwin controls](darwin/README.md)
and [its independent measurements](darwin/MEASUREMENTS.md). The W1 study below
remains the historical Linux study with its original fixtures and expectations.

W1 changes only `host/ghc/cbits/host.c` and `runtime/mlf_system.h`. On an eligible
Linux host it uses a CLOEXEC pidfd for the child just created and polls for up to
the original 10 ms pause. `waitpid` remains the only exit/status authority;
commands, checking, timeouts, process groups and fallback semantics remain.
No global signal disposition is changed. Other platforms keep the original path.

## Status and separate ordinary benchmark

The original private finite controls and this portable adaptation have separate
validation receipts. Run the exact inventory below for the current checkout;
a runtime PASS must never be inherited merely from the earlier private study.
See [all nine observations and qualification limits](MEASUREMENTS.md).

A separate, fixed nine-leg ordinary study used the predeclared order
`GHC/base/W1`, `W1/GHC/base`, `base/W1/GHC`, retaining every leg:

| Median metric | Baseline | W1 |
| --- | ---: | ---: |
| Compiler wall (s) | 82.554497 | 80.028039 |
| Reaped-child CPU (s) | 79.390669 | 80.233337 |

Wall improved **3.060352%**, with W1 faster in **3/3** rounds. CPU **increased
1.061419%**; this is not a CPU improvement. The predeclared optimization gate
was wall improvement >=3%, faster in >=2/3 rounds, and CPU regression <=2%.
All three passed. Plain GHC median wall was 8.233948 s; W1/GHC was **9.719279x**,
so the **<=3x goal was not met**. The earlier single-pair screen was not acceptance.

Scope: Linux x86_64/glibc, the same GHC 9.14.1 O2 producer/toolchain and frozen
14-module target. MLF produced checked xMLF artifacts and fresh query caches;
GHC produced plain O2 objects. Targets were fresh, not OS-cache-cold. These
endpoints are not equivalent work. This suite does not measure speed or rebuild
those target caches. Preserve partial/incomplete private qualification evidence;
raw receipts, host metadata and logs are not publication payloads.

## Inputs and baseline identity

Run from a repository containing this package and the exact W1 implementation.
Supply both complete, authentic ordinary producers; no typecheck-only receipt
or transplanted binary is accepted:

```sh
python3 -B tools/performance/process-readiness/test_controls.py
python3 -B tools/performance/process-readiness/run_controls.py \
  --producer "$W1_PRODUCER" \
  --baseline-root "$BASELINE_SOURCE" \
  --baseline-producer "$BASELINE_PRODUCER" \
  --output "$NEW_EXTERNAL_CONTROL_DIRECTORY"
```

Use the project's normal process-tree resource guard and a serial execution
slot. The output must be new and outside both source roots and both producers.
Keep failed outputs; do not overwrite or silently replace runs. No `-O` or
`PYTHONOPTIMIZE`: these original controls intentionally use assertions.

`--baseline-root` must be the still-present source root named by its producer
receipt. Its committed tree must equal
`2f724d7d623bc76ba6331030bb5d5afa361f0f3b`, from upstream commit
`a700a2893c3ff857faa775af87c0ecd060e11e30`. A different commit ID with this exact
tree is permitted; no incorrect requirement that local HEAD equal upstream's
commit ID is imposed. The tracked baseline must be clean. Frozen test-owned
copies of the original two C inputs, with SHA-256 provenance, are in
`fixtures/baseline/`; they are independently pinned, not regenerated from W1.
The other compiler inputs must match between the two authenticated producers.
Only the two frozen C changes and this package's added tests/docs may differ from
the baseline tree; an unrelated third production change is rejected.

The explicit baseline producer is required to preserve the original proof that
a freshly compiled baseline `host.o` equals the ordinary baseline producer's
object. Frozen C text alone cannot replace this check. The candidate object is
also compared with its ordinary producer. Complete dependency object hashes,
resolved source paths, unmodified compiler commands/toolchain, and C compiler
dependency records are checked. All copied Haskell dependencies remain unchanged;
only the original `Main` and then the test-owned eligibility `Main` are compiled
in the isolated fixture copy. The unmeasured `emlf` relink is a fixture, not a new
qualified producer or a native bootstrap.

## Fixed coverage (no changed expectations)

- **20 transport cases x baseline/candidate = 40 executions:** exits 0/7/124,
  signal termination, failed exec/cwd/stdin, genuine timeout, malformed process
  specifications, invalid timeout/path values, mkdir/mv, shared redirection,
  and exact binary/Unicode write-file behavior. Expected errors/status/bytes
  are the original independently specified values.
- **20 mocked fault/call-order cases:** original wait-before-deadline precedence,
  readiness/HUP/EINTR, single-close ownership including close EINTR, timeout
  cleanup order, poll error/NVAL/ERR fallback, ENOSYS/EMFILE/EPERM open failure,
  SIGCHLD gate failures, wait error, initial clock error and fork error.
- **4 real descendant cleanup cases:** baseline/candidate x supervised/
  unsupervised. Both leader and grandchild must be gone with the original exit
  codes (137 and 124 respectively).
- **Actual GHC eligibility:** 33 attempts, opens and closes; 33 CLOEXEC
  observations; positive real poll count; eligible disposition; equal
  nonnegative before/after FD counts. Counting hooks change no decisions.
- **Missing `SYS_pidfd_open`:** compile and execute the old path, with exact
  expected stdout. Dynamic symbols must contain `syscall@GLIBC_2.2.5` and no
  `pidfd_open` symbol.

This exact full inventory is scoped to Linux x86_64/glibc with working pidfds,
`/proc/self/fd`, eligible SIGCHLD, GCC-compatible dependency output and `readelf`.
Unsupported hosts fail rather than silently skipping required cases. Failure of
this full Linux inventory is not proof that the portable runtime fallback is
broken. macOS/Windows are not qualified by these controls. There is no native
74-module bootstrap, full async CI, inference cache reuse or benchmark timing.

`CONTROL-INVENTORY.json` pins original fixtures and expectation blocks. The
small meta-check checks those pins and Python syntax only. Generated receipts
and logs are local evidence: redact machine-specific paths and metadata before
sharing; do not add raw local output directories to the repository.
