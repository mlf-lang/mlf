# Current-entry migration validation

This is a validation protocol for the existing `tools/bench` entry, not another
benchmark implementation. Static checks do not establish executable correctness.

1. Run `python3 tools/bench/check-migration.py`. Review the source diff: only
   current list/tuple/unit syntax, entry/dependency paths, matching manifest pins,
   documentation and the explicit correctness-only mode may change. C sources,
   default/check inputs, output oracles, performance limits and backend flags
   remain unchanged. Retain the source commit and tool/build receipts.
2. Build the current GHC-hosted `emlf` and `mlfpkg`, scheduler helper and existing
   bench target using README commands in fresh directories. Pin GHC 9.14.1,
   Clang, runtime, GC/GMP and **PCRE2 10.49**. Missing or mismatched dependencies
   stop validation; no omitted workloads, version substitution or fallback.
3. Exercise CLI rejection controls in fresh directories: missing arguments,
   incomplete limits, invalid sample count, `--check-only` followed by a workload
   or limit, and mixed limits plus `--check-only` must fail; a failed/missing PCRE2
   dependency must not produce successful correctness or performance status.
   Do not interpret these expected refusals as completed workload checks.
4. Use the reviewed additive `--check-only` mode on all ten workloads, with the
   same new compiler in both compiler slots if testing current compatibility:
   `bench COMPILER COMPILER OUTPUT 3 CLANG --check-only`. Expected terminal
   fields are `status=correctness-passed`, `mode=check-only`, `runs=0`,
   `performance_checked=false`, and `performance_checks=[]`.
   It must build fresh C/baseline/candidate objects and run all existing manifest
   check sizes and fixture/oracle checks, including regex. Do not run unchanged
   default-size performance loops for this migration smoke gate. A correctness
   success must be explicitly non-performance, with no fabricated timing ratios
   or performance-limit PASS. Any failure stops and retains artifacts.
5. The unchanged full command (README) remains the actual performance gate:
   odd samples >=3, original default inputs, fresh builds, checked executable
   warmups, all measured samples, unrounded requested limits. Do not infer its
   outcome from check-only success.

For cloud validation, run exclusively under the existing process-group watchdog:
1800 seconds total for the fixed correctness cohort, 1800 seconds per existing
runner command as already coded (the tighter outer deadline wins), 6 GiB address
space / 3 GiB RSS, 1 GiB retained output and 2 GiB free-disk floor. Stop and retain
an incomplete receipt if any cap fires; no automatic retry or sample expansion.
Producer/runner setup is separately bounded and is not benchmark compilation.
Inspect guard and process-group cleanup receipts before declaring CPU clear.
These are validation resource limits, not changes to the official benchmark CLI.

The regex C implementation remains PCRE2, not the separate experimental
same-algorithm NFA comparator. The experimental installed-Prelude consumer is not
used. Normal benchmark timing still includes fresh runtime C compilation and
source/LLVM/link process costs; overlapping stages must not be added together.
