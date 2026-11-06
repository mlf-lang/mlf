# Darwin child-exit readiness controls

`runtime/mlf_system.h` uses a private `EVFILT_PROC / NOTE_EXIT` kqueue to wake the existing `waitpid(WNOHANG)` loop on macOS. `waitpid` remains the only status and reaping authority. The queue is used only with default `SIGCHLD` disposition and without `SA_NOCLDWAIT`; no signal handler changes are made. Registration, descriptor setup, and wait failures fall back to the existing bounded polling path. Timeout checks, command parsing, exit codes and process-group cleanup retain their existing order. The native and GHC host runtimes share this header.

These controls reuse the independently pinned `../fixtures/Probe.c` and `Tree.c`; the frozen Linux fixture inventory is not modified. The runner authenticates both ordinary GHC 9.14.1 `-O2` producers, recompiles their host objects byte-for-byte, and requires that removing exactly the three Darwin preprocessor arms recovers the baseline header verbatim. All other producer inputs must match. Use an unmodified baseline checkout and producer, plus a separately built candidate checkout and producer.

```sh
python3 -B tools/performance/process-readiness/darwin/run_controls.py \
  --baseline-root /absolute/path/to/baseline \
  --baseline-producer /absolute/path/to/baseline/producer \
  --producer /absolute/path/to/candidate/producer \
  --output /absolute/path/to/new/control-output \
  --gc-prefix /absolute/path/to/bdw-gc \
  --gmp-prefix /absolute/path/to/gmp
```

The suite checks:

- 40 real transport executions: the original 20 process cases on both versions, with Darwin's `/usr/bin/true` path.
- 27 handwritten fault and call-order cases, including notification registration, `EINTR`, unusable events, fallback, signal eligibility, descriptor ownership, first errors, timeout and clock failure.
- An actual GHC-host call chain with 33 child processes: open/register/close/CLOEXEC counters, actual readiness waits, and stable `/dev/fd` count. Only the test Main and C hook objects are changed; dependency objects remain pinned.
- Four supervised/unsupervised timeout descendant-cleanup cases, covering both versions.
- Ten ordinary Clang `-O2` compact native-value ABI cases for success, nonzero exit, explicit 124, signal death and timeout.

The syscall controls are independent, finite examples, not a proof for every OS interleaving. The GHC eligibility executable is an instrumented diagnostic; it is never a performance sample. Linux behavior is guarded by exact source projection and the existing Linux controls, rather than by claiming that macOS executed Linux syscalls.

For performance, run the ordinary executable on fresh target query directories. Keep complete checked outputs and compare their raw bytes with a frozen independently qualified reference; a matching digest alone is insufficient. Keep qualification, microbenchmarks, screening and confirmation data separate. No GC configuration, Clang optimization flag or target inference-cache reuse is part of this change.

The platform API is documented in [Apple's kevent manual](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/kevent.2.html). The reviewed [Apple XNU descriptor implementation](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_descrip.c) toggles only `FP_CLOEXEC` for `F_SETFD` and releases the descriptor table entry before dropping the underlying file object. Cleanup attempts `close` once; it does not retry a descriptor number that could already be reused. These source observations supplement the finite controls, not a proof about every Darwin version.
