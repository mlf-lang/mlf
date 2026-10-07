# binary-trees sources and correspondence

All three baseline submissions and the depth-10 output fixture come from
[Benchmarks Game revision 40296663ed350d5fe4a6ab5e367bab61cb77c219](https://salsa.debian.org/benchmarksgame-team/benchmarksgame/-/tree/40296663ed350d5fe4a6ab5e367bab61cb77c219)
(2025-03-07). The manifest records each HTML source's Git blob identity,
immutable URL, extracted source SHA-256, build source SHA-256, and flags.
`upstream.*` contains the concatenated text of the first HTML `pre` element,
with HTML entities decoded and whitespace preserved. No downloads occur
during a benchmark. Keep the original author comments and the accompanying
[BSD 3-clause license](../LICENSE.BenchmarksGame).

| Language | Pinned submission | Selection and adaptations |
| --- | --- | --- |
| C | `public/program/binarytrees-gcc-1.html`, Kevin Carson | Simple sequential recursion, `malloc`/`free` for each full two-pointer node. Build `c/main.c`: only remove `<malloc.h>`, which macOS lacks; `<stdlib.h>` already declares allocation. `c/adaptation.patch` is the exact change. Clang replaces the historical GCC toolchain. |
| Rust | `public/program/binarytrees-rust-1.html`, Rust Project Developers and TeXitoi | The simplest current Rust traversal. All five current Rust submissions use arenas; #1 also spawns a thread per depth, and #2–5 use Rayon. Build `rust/main.rs`: replace arena references with `Option<Box<Tree>>`, use ordinary recursive ownership/drop, remove thread spawning/join, retain the construction/traversal, depth schedule, iteration count, and output. This necessary allocation/scheduling adaptation permits a comparable sequential per-node test using `rustc` alone. `rust/adaptation.patch` records every change. |
| Haskell | `public/program/binarytrees-ghc-1.html`, Don Stewart | Unchanged sequential source, strict `Node !Int !Tree !Tree`, ordinary heap allocation. #2 is lazy, #3–7 introduce parallelism and/or compact regions. Compile with `-XBangPatterns -fno-full-laziness -fno-cse` in addition to `-O2`: prevent floating `check (make 0 d)` out of repeated work or sharing identical subtrees. These restrictions are workload safeguards, not general GHC defaults. |
| MLF | `mlf/main.emlf`, this repository | Direct recursive ADT construction and traversal with the same depth schedule. Details below. |

The upstream C tree has no payload. The unchanged Haskell tree includes an
unused strict `Int` payload. Rust owns each node; MLF uses a lazy managed runtime
with immediate small integers and GMP for larger values. MLF's general value
allocator reuses fixed-size pages and reclaims individual objects by tracing
reachability; it has no tree-specific arena or bulk tree-lifetime operation.
GHC also uses its ordinary managed allocator. These representation differences
remain visible in the comparison. None uses a workload-specific arena, handwritten SIMD/assembly, a core
algorithm implemented in another language, precomputed checks, or worker
threads. Normal compiler auto-vectorization is permitted. GHC is not linked
with `-threaded` and no `+RTS -N` option is used.

The unchanged upstream C program leaves its final long-lived tree for process
cleanup; Rust drops that tree explicitly through ownership. Haskell and MLF
use their garbage-collected runtimes. These exit/cleanup costs are included
in end-to-end runtime, rather than adjusted or subtracted.

## Work performed by the MLF translation

The specification is the [official binary-trees description](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/binarytrees.html).
Maximum depth is `max(6, input)`. First allocate, traverse, and discard the
stretch tree of depth `maximum + 1`. Fully construct the long-lived tree of
depth `maximum` and retain it while processing depths `4,6,...,maximum`.
At each depth construct and traverse `2^(maximum-depth+4)` distinct trees,
then print their summed checks. Finally traverse the retained tree.

`Node Tree Tree` represents every allocated tree node, including leaves;
`Nil` is the empty pointer below a leaf. `make` forces both child roots before
returning the parent; recursively this fully constructs the tree before
`check` can traverse it. It does not rebuild children or replace subtrees
with cached nodes. `check` recursively counts nodes; the executable never
uses a formula for a tree check. `power2` only computes the iteration count,
using doubling because the primitive set lacks multiplication and shifts.

MLF currently has no native `readInt` or command-line argument primitive.
It reads one decimal depth from stdin, comparing against `showInt` for
0 through 20. Other programs read the same numeric input through argv.
The harness rejects out-of-range inputs and sends canonical decimal text.
This small input adapter is included in runtime timing. Invalid standalone
MLF input falls back to the minimum depth and is outside the harness contract.

The surface language has nonrecursive `let`, so `Rec` supplies a typed fixed
point, as in the existing Snake example. IO and `return` use the standard
prelude. Every accumulated check is forced by `eqInt next next` before an IO
step; it is a demand for evaluation, not a precomputed result. The native
collector only runs at IO boundaries, so this lets each completed temporary
tree become unreachable before the next iteration. The long-lived tree stays
reachable through the continuation. These extra closures, IO actions, and
collections are part of MLF's measured runtime cost.

## Checks against computing less work

The harness checks all four programs against the pinned upstream output for
input 10 and an independent mathematical output oracle at inputs 0, 7, 10,
and the chosen runtime input. Odd depth and minimum-depth clamping are
covered. Only whitespace is normalized. Each measured binary's output is
checked again; bad exit status or mismatched output invalidates the run.

`cabal test` also executes the MLF workload on both the interpreter and LLVM
backend. An **untimed** native runtime probe counts actual `Node` constructor
creation at depths 6, 7, 10, and 16 and requires exactly the stretch, retained,
and all temporary trees' node counts. It catches a translation that shares
trees or substitutes a constant check despite printing the right output.
The measured runtime and binaries do not contain this instrumentation.

The Haskell flags were checked with GHC's untimed `+RTS -s` statistics: the
depth-14 pilot allocated 103,270,968 bytes, and depth 17 allocated 959,269,304
bytes. That agrees with allocation growing with the full workload rather
than one shared tree per depth. This is supporting evidence, not a portable
exact heap-size assertion or a proof about every future GHC optimizer.
