# Graph54 read fusion: bounded experiment

Semantic/raw gates pass. Foundation has mixed pairs; Async has two positive timing pairs with higher RSS. Neither establishes stable gain or merge evidence.

Baseline commit: `fc300bc9fdc389b585cbef0630fc8915d53e89c5`.
The patch mechanically unfolds 54 fully saturated internal calls in 34 functions of Bootstrap.Graph to the original readSTArray RHS. Public readDense signature/body/arity, all writes and primitives remain unchanged. Arguments are single identifiers used once; no new strictness, pragma, algorithm or representation. The reversible byte proof and independent source review preceded execution.

The real Graph corpus uses actual Graph/Solver, not an extracted wrapper. Its host adaptation preserves the repository GraphDense corpus and four-line expected output. Main adds 14 silent state/demand cases, including shared action across writes, ignored-result bounds errors, payload laziness, array/index/low demand and signed Int64 wrap. Both baseline/candidate passed O0/O2 with 16 modules each. This is selected coverage, not a universal runtime proof.

Ordinary code shows genuine local fusion with **+8432 bytes (+2.4343%) .text**. Conditional denseContains closure accounting drops 352→176 bytes on the specified fresh successful path; this is not measured heap allocation or savings. Other paths already fused or retain offset boxes. Full 95-module candidate Graph.o is byte-identical to the independently inspected single-object result.

One fixed Foundation 15 **C-A-A-C** window completed with four fresh query caches. Every leg matched original A raw CI/CO and ordered 532 groups / 539 members / 14 owners; whole-query byte comparison is an additional observation. Two pairs point in opposite directions; first A has elevated system time, with unknown cause. No sample was dropped, adjusted or followed by additional samples. See JSON for wall, CPU, user-only and RSS arithmetic. No stable benefit, significance, general regression or merge conclusion follows; no selective retries or added samples. No comparison with profiling/E-counter timings. Native/fixedpoint remains paused.

A separate fixed **Async 5 A-C-C-A** window compiled the complete `mlf-async/0.3.0/library` crate without executing its task/process APIs. It reused the same ordinary A/C compilers and existing Foundation/builtin interfaces. All four legs matched the new original A raw CI/CO and ordered **86 groups / 87 members / 4 owners**; the fifth module is an import/reexport facade. Both wall-time pairs favored C: C/A **0.913955 / 0.938011**, geometric ratio **0.925905** (a descriptive **7.4095%** reduction). CPU also decreased in both pairs, while maximum RSS increased by **2.4127% / 2.5980%**. Four fresh query caches do not imply cold OS caches. These two pairs are a workload-specific signal, not stable/significant benefit, measured heap-allocation savings or whole-compiler qualification. Foundation remains mixed; the workloads are not pooled. See `results/async-acca.json` for all four unadjusted samples.

Experimental branch: `perf/main-baseline-gap-20261114`, directory `tools/performance/main-baseline-gap-20261114/graph54-read-fusion`. This is an experimental result, not evidence for merging into main or for native/fixed-point qualification.

The bundle contains source, tests and results, with no execution controller. Source and file hashes are in SOURCE-PINS.json.
