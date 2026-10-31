# Int64 and Patricia collection qualification

2026-10-31. V7 passed its frozen local acceptance rule and all declared current
qualification gates. [Compact results and evidence pins](../tools/performance/patricia/results-20261031.json)
retain the 24 ordinary timings, summaries, source identities and receipt hashes.
Raw outputs remain under `.mlf-build/patricia-20261031` in the qualification worktree.

## Numeric and representation contract

Language `Int` is signed 64-bit. Literals, signed decimal `readInt`, addition,
subtraction, multiplication and negation wrap as Haskell Int64. The existing
optional-sign/ASCII-digit grammar remains. Minimum Int64 divided by -1 raises
division overflow; its remainder by -1 is zero. Division by zero remains an error.
Explicit `Integer` primitives preserve unbounded pidigits and exact floating-point
conversion. Compiler identity supplies check exhaustion. Native, primitive,
builtin and frontend identities invalidate old caches.

IntMap and IntSet adapt containers 0.8.1 Patricia algorithms and bitmap leaves,
with signed enumeration and cached cardinalities. Constructed keys and spines
are strict; map payloads remain lazy. Empty lookup/deletion retain unused-key
behavior. The upstream archive and sources are pinned in the collection
provenance, and its BSD license is included in release packaging.
This intentionally changes the old public BST representation. It does not claim
that arbitrary partial BST spines have unchanged physical behavior.

## Installation and correctness

The ordinary GHC 9.14.1 O2 producer uses serial ordinary Clang O2. Its SHA256 is
`060771e3273acebdbe1fa9e71eb39f999b6f210067f5136821801503c4cbaee3`.
All 172 production source inputs match the final installed build.
The two owned generated-library modules replace only their checkout stubs and
are independently regenerated and verified.

- P1: 154,072 controls; P2: 2,503 plus **all 1,243 supplemental native-compatibility
  controls**; P3: all 922 old checks plus seven full-width seeds.
- Full retained graph/transaction controls, all 216 heteroinput cases, and private
  export rejections. Nine old BST representation probes are explicitly replaced
  by independent Patricia invariants; the other semantic obligations remain.
- Map balance: 24,649 raw-shape pairs, 400 mutations and 30 demand/order cases.
  Validation reuse, canonical builtin checks, and F1 O0/O2 finite/Core checks pass.
- Host O0/O2 numeric, parsing and conversion controls pass. The native oracle has
  219,284 rows (219,277 distinct; seven literal-show rows overlap two families),
  checked through direct/curried ordinary and UBSan execution. Legacy cases,
  217 actual LLVM-region outputs and both minimum-Int64 division probes pass.
- Both optimization levels pass collection, compiler and malformed kind-routing
  controls. Complete shared compiler source typechecking passes.
- Nine retained file cases agree in raw bytes through both candidate crate routes
  with the frozen Int64 reference. Native collection checks cover 199 signed keys,
  4,072 output lines, six lazy-payload cases and a selected-value error case through
  GHC, standalone LLVM and the default installed-library CLI. All 12 direct
  installed-suite commands pass.
- The shared Windows numeric-width controls and the native arithmetic corpus pass
  with the GMP LLP64 adapter selected, including UBSan. This is a macOS adapter
  test, not Windows OS qualification or a complete LLP64 ABI emulator.

Frozen oracle bodies and manifests remain. Explicit reversible test adapters
handle the numeric and representation change. The historical P1/P2 metadata
refusal tests run against exact historical Git fixtures; current semantic tests
run against the new producer. These two purposes are not conflated.

The final Mac-applicable release suite passes. Its local driver records exactly
five unavailable Linux live-proc watchdog methods; their tests and production
protection are unchanged in CI. This is not a full Linux release-suite claim.

The fixed generated library shares repeated immutable strings and a restricted
set of closed, explicitly typed constructor leaves. Exact expansion restores
raw generator bytes, and independent regeneration checks those bytes. No new
host-specific pragma or optimization flag is introduced. Final installation
construction took 608.699 seconds, with a sampled process-tree peak of
4,143,497,216 bytes under the unchanged 5 GiB guard.
This one-time installation is excluded from fresh user-program compilation.

## Compiler confirmation

The fixed workload is 15 modules and **711 fresh / 0 reused** inference groups.
Every leg checks ordered group identity and original checked MLF/xMLF bytes.
Dependencies may be reused; target inference may not. A is a frozen experimental
Int64 balanced-tree bootstrap producer, qualified for these total workloads.
B is the actual default native installed Patricia producer. Both are GHC O2.
Their installation configuration differs; the effect is not solely attributed
to the data structure. The original unbounded P3 whole-artifact bytes are not
interchangeable across this ABI migration; frozen semantic algorithms remain.

The protocol froze six blocks, 24 new legs, balanced ABBA/BAAB orders, a minimum
2% point improvement, a positive nominal 95% block-t lower bound, and positive
effects in both orders. There was no sample replacement, extension or early stop.

| Measure | Result |
| --- | ---: |
| Paired block geometric time ratio B/A | 0.915667 |
| Time reduction | **8.43%** |
| Nominal 95% improvement interval | **8.28% to 8.59%** |
| ABBA / BAAB improvement | 8.37% / 8.49% |
| Descriptive A / B wall medians | 51.387 / 47.039 seconds |

The frozen acceptance rule passes. The interval is conditional on the fixed
binaries, workload and this Mac session. Six blocks do not establish independence,
portability or a family-wide guarantee over the optimization search. Medians
are descriptive and are not the primary paired-block estimator.

The separate three-sample anchors use the same 15 source modules. GHC fresh
`--make -j1 -no-link` target objects have a median of 8.368 seconds.
Pre-migration unbounded-Int S2 takes 61.565 seconds, with 711 fresh / 0 reused
and raw equality to its own frozen reference. V7 is descriptively
**5.62x the GHC anchor** and **23.6% below S2**.
These are separate windows and different endpoints: GHC target objects versus
MLF checked crates. They are not paired estimates or a fair language ranking.

## Classification discovery

One balanced block per shape, two observations per side; no confidence or
universal speed claim. The gain column is the descriptive reduction in medians.

| Shape | A seconds | B seconds | Gain |
| --- | ---: | ---: | ---: |
| flat_functions-512 | 3.974 | 3.875 | +2.50% |
| inferred_chain-512 | 4.514 | 4.523 | -0.21% |
| local_functions-512 | 3.892 | 3.810 | +2.09% |

The inferred-chain case remains effectively unchanged in this small screen.
Earlier collection microbenchmarks retained regressions in sparse lookup and
sorted Map construction. Bulk-operation gains do not imply all lookups improve.

## Ten-program check

All 46 independent correctness cases pass on each side (92 total). Three new
samples per workload use the actual default installed CLI, fresh user source,
LLVM, object and executable, one LLVM job, and ordinary MLF Clang O2. The C
baseline retains the existing manifest's ordinary Clang O3, including its
precompiled PCRE2/GMP dependencies. Values below are descriptive medians.

| Workload | Compile C / MLF seconds | MLF/C | Runtime C / MLF seconds | MLF/C |
| --- | ---: | ---: | ---: | ---: |
| binary-trees | 0.087 / 0.475 | 5.46x | 0.587 / 0.478 | 0.82x |
| pidigits | 0.092 / 0.456 | 4.96x | 0.614 / 0.829 | 1.35x |
| n-body | 0.106 / 0.882 | 8.36x | 0.341 / 0.368 | 1.08x |
| fannkuch-redux | 0.097 / 0.624 | 6.43x | 0.460 / 0.503 | 1.09x |
| spectral-norm | 0.096 / 0.550 | 5.74x | 0.442 / 0.408 | 0.92x |
| fasta | 0.104 / 0.810 | 7.82x | 0.449 / 0.571 | 1.27x |
| mandelbrot | 0.089 / 0.599 | 6.73x | 1.180 / 0.855 | 0.72x |
| reverse-complement | 0.090 / 0.726 | 8.03x | 0.463 / 0.580 | 1.25x |
| k-nucleotide | 0.114 / 0.897 | 7.90x | 0.423 / 0.551 | 1.30x |
| regex-redux | 0.096 / 0.519 | 5.44x | 0.789 / 1.694 | 2.15x |

**Only 1/10 compile within 5x C; 9/10 run within 2x C.**
Both global goals remain unmet. Default floating outputs use the repository's
existing finite/token-count/1e-8 comparator after independent small-input checks;
other default outputs use raw comparison (binary-trees whitespace only).

## Rejected attempts and limits

- V5 completed a timing window, but restoring the omitted supplemental P2 suite
  found a first-error-order regression in `Data.distinct`. Its timing result is
  rejected for adoption. V7 explicitly demands the list spine before the Set
  side and passes all 1,243 original controls. **No V5 sample enters V7 analysis.**
- V6 failed the canonical Prelude source-identity check. Fresh generation changed
  exactly that one identity string, and V7 then passed complete installation and
  exact regeneration. The failed V6 receipt remains failed.
- A prior installation exceeded the memory guard; a prior game diagnostic's
  default n-body Haskell oracle also exceeded it. Failed attempts remain separate;
  no completed samples from those windows enter the final window.
- A separate old guest-chain diagnostic reproduces `Con "String" []` versus
  `TyApp 6 5` on S2 and V5 with unchanged Test/Async libraries. It is an existing
  scoped failure, not qualification of the full V7 guest chain. Complete native
  compiler bootstrap, every O0 suite, and a hosted Windows run are not claimed.
