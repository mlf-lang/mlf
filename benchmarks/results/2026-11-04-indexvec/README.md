# Dependency graph compilation on the installed driver

The single-pass SCC, shared reach sets and incremental publication were measured against both #29 and the original #43. [Foundation query study](foundation-graphs.md). The follow-up carries resolver-issued declaration IDs into those graphs. [Resolver ID measurements](resolver-ids.md). The next comparison places those IDs on resolved expressions and selects each query group by its member IDs. [Resolved-expression benchmark](resolved-expressions.md). The decoder then builds indexed graphs directly using IO-world arrays. [Dense decoder measurements](dense-decoder.md). The current compiler shares the checked raw content address with small finalization receipts. [FinishScc measurements](finish-receipts.md).

This comparison measures the public `emlf SOURCE -o PROGRAM` endpoint. The
#29 installation (`8c455641`) and the IndexVec installation
(`ff7c8c6c`, implementation through `f46943ab`) both identify
their compiler host as `MLF/shared-haskell-v1 GHC`. Both generate native user
executables and use a prebuilt native standard library and runtime.
All 108 serial compilation commands passed. Every executable matched its independent behavioral oracle on three inputs (324 checks).

The two windows ran on an Apple M1 Max with 32 GiB of memory and
macOS-26.6.2-arm64-arm-64bit-Mach-O. Tooling was GHC 9.14.1 and
Apple clang version 21.0.0 (clang-2100.1.1.101). Both installations used GHC `-O2` to build the
compiler. MLF freshly checked every user invocation, emitted LLVM IR, compiled
it with Clang `-O2` and linked installed objects. GHC used `--make -j1 -O2` and
a fixed registered host primitive package. Filesystem caches were left warm.
Concurrent self-host processes were suspended while the timing windows ran.

## Wall-time medians

Each median has three samples in a predeclared alternating order.
`After / before` compares MLF installations. `After / GHC` compares the corrected
installation with GHC. Times are seconds.

| Window | Workload | Target | #29 | After | GHC | After / before | After / GHC |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| standard | Declaration chain | fresh | 0.3785 | 0.3660 | 0.5636 | 0.967 | 0.65 |
| standard | Declaration chain | warm | 0.3567 | 0.3640 | 0.0846 | 1.021 | 4.30 |
| standard | Wide fan-out | fresh | 0.3628 | 0.3765 | 0.5731 | 1.038 | 0.66 |
| standard | Wide fan-out | warm | 0.3707 | 0.3706 | 0.0849 | 1.000 | 4.37 |
| standard | Recursive ring | fresh | 0.3717 | 0.3908 | 0.5515 | 1.051 | 0.71 |
| standard | Recursive ring | warm | 0.3746 | 0.3890 | 0.0862 | 1.038 | 4.51 |
| standard | Module diamond | fresh | 0.3395 | 0.3404 | 0.6097 | 1.002 | 0.56 |
| standard | Module diamond | warm | 0.3324 | 0.3439 | 0.0876 | 1.035 | 3.93 |
| standard | Compiler Unicode | fresh | 0.4635 | 0.4448 | 0.5990 | 0.959 | 0.74 |
| standard | Compiler Unicode | warm | 0.4463 | 0.4531 | 0.1077 | 1.015 | 4.21 |
| incremental | Module diamond | fresh | 0.3682 | 0.3567 | 0.6390 | 0.969 | 0.56 |
| incremental | Module diamond | edited | 0.3450 | 0.3616 | 0.6590 | 1.048 | 0.55 |

In the standard window, candidate/GHC ratios were 0.56–0.74
on fresh outputs and 3.93–4.51 on no-edit repeats.
GHC could reuse user modules on a no-edit repeat. The installed MLF command
recompiled the user target. The incremental window used a separate fresh build
per round, then changed one addition in `Shared.hs`. Both arms of the diamond
had to reflect the edit in the user executable. The edited-program candidate/GHC
ratio was 0.55. Independent formulas checked outputs
both before and after this edit.

The five xMLF outputs also matched byte for byte and passed cross-checking by both compiler versions. [Correctness results](checks.json).

Across the standard fresh cells the after/before ratios ranged from
0.96–1.05. Three observations per cell on one
host do not establish a general speedup attributable to IndexVec.

## Candidate fresh stage medians

The driver does not report frontend CPU time separately. These observed wall
intervals use the completion times of `program.ll`, `program.o` and the linked
program. Start to IR includes driver startup. Link completion precedes final
validation and publication. Medians of intervals need not add to the median of
whole-command wall time.

| Workload | Start to IR (s) | IR to object (s) | Object to linked program (s) |
| --- | ---: | ---: | ---: |
| Declaration chain | 0.247 | 0.036 | 0.052 |
| Wide fan-out | 0.250 | 0.043 | 0.055 |
| Recursive ring | 0.262 | 0.042 | 0.054 |
| Module diamond | 0.230 | 0.032 | 0.053 |
| Compiler Unicode | 0.319 | 0.048 | 0.052 |

## Native-MLF bootstrap

Both installations attempted the ordinary offline, single-job package build
of `emlf` and `mlfpkg` from their owned source trees. Both completed the
Foundation, language-core, frontend, xMLF, inference and LLVM library jobs.
The `mlf-crates` job then exited 1 with `binary expanded-work limit exceeded`.
The compiler had written its interface, object and a local 1,682-group report.
Publication of the query graph follows that report. Its bitstream has a
67,108,864-unit expanded-work bound. Both package build reports have
`complete: false`.

Of the 1,682 reported SCCs, 1,681 had byte-identical member names in the same
positions. The remaining SCC contained the three `Bootstrap.Bitstream` instance
dictionaries. Decoding the two interfaces and formatting the stripped instances
showed identical text after substituting only the encoded builtin owner `:11`
with `:12`. This comparison concerns the compiler's own crate with the new ABI.
The five unchanged user programs produced identical xMLF without substitutions.

A second attempt used the public source-to-executable driver on the compiler
entry module. It was stopped on this 32 GiB host when macOS reported physical
footprints of 51 GB for #29 and 28 GB for the candidate. The sampled RSS
guard did not capture the compressed and swapped pages. The full native-MLF
compiler comparison and the next-generation fixed-point check remain open.
The times above measure the installations identified in the first paragraph.
[Native bootstrap commands, identities, diagnostics and resource observations](selfhost.json).

## Receipts and reproduction

The plans record the schedule, all source and tool hashes, exact commands,
fixed GHC package and native installation configuration. Both installations
were freshly built. The #29 binary SHA-256 was `14b3d7ae3498eb881a7f7b2bbf53cfe83915378cb019c37c08798ddd52e39b1e`.
The corrected binary SHA-256 was `3a8922854f37f0a4bfda7642cc9b96b0b44a0b4531a56b1e8e46b7c0303fa8a8`.

- Standard window. [Plan](standard/plan.json), [all samples](standard/samples.csv), [receipt and medians](standard/receipt.json).
- Shared-leaf edit. [Plan](incremental/plan.json), [all samples](incremental/samples.csv), [receipt and medians](incremental/receipt.json).
- Earlier window, before correcting generated names. [Initial cohort](initial-c98cae57/README.md).

The CSV tables include wall time, user/system CPU and peak RSS in bytes.
`peak_rss_bytes` is the individual peak returned by `wait4`. The additional
process-group RSS is sampled every 100 ms and may miss brief peaks.

Check out the two plan commits in separate worktrees. Build each one with
the first command, then run the two comparisons from the candidate worktree.
Use a fresh output directory for every run.

```sh
python3 -B tools/shared/build.py --build-dir "$PWD/.mlf-build/install"

python3 -B tools/performance/compiler-shapes/bench.py installed \
  --before /absolute/before/.mlf-build/install --after "$PWD/.mlf-build/install" \
  --size 16 --repeats 3 --output "$PWD/.mlf-build/standard"

python3 -B tools/performance/compiler-shapes/bench.py installed \
  --before /absolute/before/.mlf-build/install --after "$PWD/.mlf-build/install" \
  --diamond-edit --repeats 3 --output "$PWD/.mlf-build/incremental"
```
