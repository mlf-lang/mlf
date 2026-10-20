# Crate compilation migration

Status: accepted on 2026-10-20. The crate implementation, all six native test
groups, fresh self-host fixed point and isolated performance acceptance are
complete for the R11 source and tool configuration. The
[validation record](crate-validation.json) binds actual command exits, source
hashes, native tools, profiles, test coverage, baseline preservation and measured
results. The [native-only cleanup record](native-only-validation.json) remains
evidence for the earlier tree.

## Evidence and semantic boundary

The pre-migration tree, native tools, and source hashes are frozen under `.mlf-build/crate-migration/baseline/`. `native-cleanup.patch` and `source-hashes.json` distinguish the authorized cleanup from this migration. The isolated baseline is complete, with exact commands and inputs in that directory's `summary.json` and `README.md`.

| Baseline sample | Wall seconds | Peak process RSS bytes |
| --- | ---: | ---: |
| Cold native compiler and manager build | 428.04 | 2,878,701,568 |
| No-op build | 6.15 | 588,546,048 |
| One type/behavior-preserving declaration body edit | 221.55 | 2,347,728,896 |
| 100 / 500 / 2000 independent declarations, source-to-type | 0.01 / 0.23 / 3.47 | 58,523,648 / 587,399,168 / 589,037,568 |

These are single observations, not statistical speedup claims. The body edit left the semantic interface fingerprint and resulting compiler binary unchanged, but changed encoded interface bytes and unnecessarily re-inferred `Main`. All frozen sources were restored byte-for-byte. Post-migration samples must use the same frozen workload and measurement boundary. Concurrent development probes are not performance samples.

Before migration, the source linker already renamed all declarations before `Surface.bindValues` built value SCCs. Its loader/export fold and the package manager nevertheless imposed module topology. `Separate.compileUnit` added a true per-module inference boundary. The migration removes these distinct assumptions independently.

The existing supported recursion rule requires a closed signature for each recursive value, including polymorphically recursive groups. Acyclic declarations infer without signatures and retain their individual generalization. The thesis, section 12.1.1 (`papers/these-finale-english.txt` around line 9375), explains why unrestricted inferred polymorphic recursion is undecidable. Its acyclic constraint-instantiation graph is not a module-import graph. This migration preserves the existing recursion rule; it does not impose signatures on module-import SCCs or claim a new unsigned-recursion inference rule.

Nominal datatype/kind declarations are predeclared before field validation, so mutually recursive datatypes can span modules after crate-wide resolution. Actual superclass cycles and invalid instance overlap remain semantic errors.

## Architectural decisions

- A package library is one crate. Each executable/native test target is a crate containing its entry/private modules and depending on the package library and direct dependency libraries.
- The package/crate dependency graph remains acyclic. Module namespace relationships and declaration value/type dependencies are separate graphs.
- Resolve namespaces to a fixed point before renaming bodies. Retain import selection/hiding, re-export identity, ambiguity diagnostics, lexical scope and defining-module instance visibility.
- Definition identity includes crate identity, module path, namespace/role and declaration spelling. Allocation-order graph IDs are not persistent cache identities.
- Perform class coherence/lowering with defining scopes, then infer lowered declaration SCCs independently using closed predecessor schemes. Preserve graph solving, checked elaboration, inferred-type agreement, source-erasure agreement and independent target checking.
- Persist checked, externally parameterized xMLF fragments and normalized schemes. Cache keys include resolved syntax, actual value schemes, required nominal layouts/kinds, dictionary/class/instance semantics and compiler format. They exclude predecessor implementation digests.
- Cross-crate `.mlfci` metadata supplies exported module namespaces and semantic definitions. `.mlfco` contains checked implementation fragments. Downstream inference reads metadata, not upstream source or implementation bodies.
- Dependency implementation identities remain link/codegen inputs. Runtime object caching is independent. The existing whole-program LLVM optimizer and constructor numbering require an explicit ABI/optimization boundary before finer native object reuse can be claimed; measurements and the acceptance ledger must state the actual implemented granularity.

## Acceptance ledger

| Requirement | Accepted evidence |
| --- | --- |
| Crate compilation and resolution | Libraries and executable/test targets are crates; cyclic module namespaces resolve before declaration inference; crate dependency cycles fail |
| Declaration dependencies | Deterministic SCC ordering, cross-module recursive types and values, unrelated declarations and inventory permutations are exercised |
| Existing MLF semantics | Shared graph inference, solving, checked elaboration and independent target checking; principal/first-class polymorphism and closed-signature recursion regressions pass |
| Semantic incremental reuse | Persistent checked SCC queries use consumed schemes and nominal/class/instance dependencies; body-only reuse, semantic invalidation and corruption recovery pass |
| Generated metadata | Source-free upstream use, visibility/reexports, ownership, stale contracts, malformed objects and checked linking pass |
| Code generation | Checked whole-program entry/erased/optimized queries; clean/incremental behavior and exact frozen compiler/manager LLVM and binary comparisons pass |
| Native package integration | 18 resolver checks and 26 integration cases, including profile-content invalidation, failure recovery and target isolation |
| Complete tests | Unit, packages, parity, backends, port and self-host each have fresh execution, a complete native report and a genuine successful outer exit |
| Performance | Identical frozen build/edit/scaling inputs and all nine native workloads; three samples, compilation at most 3x C and runtime at most 2x C |
| Cleanup and maintenance | Obsolete module compilation and Haskell/Python compiler/test paths retired; native workflows, artifact contracts and limitations documented |

## Final native verification

The immutable snapshot contains 3086 hashed paths.
All executable sources and inputs match the live tree. Each native group also
checks the same 332-file verification manifest and compiler hash.
Documentation closeout is recorded separately from that tested snapshot.

- Unit: 702 checks; independent Algorithm W over 6,712 closed terms;
  126 annotation cases; 43 Figure 12 expressions, 36 controls and 57 harness methods.
- Packages: 18 resolver checks and 26 integration cases.
- Parity: 7,086 cases, 3,204 accepted and 3,882 rejected; 80 runtime rows on both backends.
- Backends: 523 fixtures and 575 rows on each backend, separately under standard and compact-GC layouts.
- Port: 26 fixtures and 26 rows on each backend and layout, with independent reference programs and generated-source checks.
- Self-host: a fresh empty next-stage build reproduces complete LLVM and native compiler bytes using the recorded profile and Clang identity.

Compiler SHA-256: `41c6608db69e0a8960dd697f8f1f85e63ff24934a1bdccfce25538a5b1398781`.
Manager SHA-256: `784eee44d814541c35500303711469fe0234c5cead126507588ddf45be049d61`.

The build starts from genuine native construction artifacts; copied test caches
come from R2. Existing compiler/profile identities and receipts are unchanged.
The manager validates every actual input, and every test process executes anew.
Self-host and performance builds use fresh empty directories. The earlier R2 port
controller lost its outer exit record; its completed child reports and unknown
outer status remain historical and are not substituted for R11 execution.

## Native compiler construction

R11 uses optional, explicit native PGO at the existing O2 level. The
[construction script](../scripts/build-compiler-pgo.sh) trains the compiler and
runtime on fifteen fixed existing language examples through stdin. Benchmark
and Snake inputs are excluded. Two independent training/build rounds reproduce
the merged profile, complete LLVM, both native objects and complete executable
bytes. The ordinary construction still reproduces R10's compiler exactly.

The native manager records the selected root target, canonical profile path,
profile contents, actual flags and native tool inputs in the cache keys. Other
targets and inference/emission cache identities retain their ordinary behavior.
Changed profiles invalidate native stages; incompatible profiles fail without
replacing a working executable. Unchanged profiles can reuse genuine entries.
Independent training reproduction and fresh source self-hosting are separate
checks, both recorded in the acceptance evidence.

Profile SHA-256: `e37ed794fb0c87c40cb86fa8d97bbb48720d1516f1ba13b88f124a5192e38f11`.
See [native construction and reproduction](package-manager.md#native-profile-guided-construction).
These performance results describe this recorded production configuration;
they do not claim that an ordinary, unprofiled compiler passes the same gate.
The complete construction commands and training costs remain in the construction
record. Training is a tool-construction step outside the unchanged workload
compilation boundary; no benchmark runtime object cache is hidden from timing.

## Performance acceptance

The final measurement window starts after all other compiler/test jobs finish.
Frozen sources, toolchain, runtime, edit and scaling inputs match the preserved
baseline. Build rows are single observations, not statistical speedup estimates.
RSS is peak memory of an individual process, not aggregate build memory.

| Identical frozen workload | Baseline seconds | R11 seconds | Time ratio | Baseline peak RSS bytes | R11 peak RSS bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cold compiler + manager | 428.04 | 394.02 | 0.921 | 2,878,701,568 | 2,289,008,640 |
| No-op | 6.15 | 6.14 | 0.998 | 588,546,048 | 588,824,576 |
| Type/behavior-preserving body edit | 221.55 | 211.50 | 0.955 | 2,347,728,896 | 2,303,541,248 |
| 100 declarations | 0.01 | 0.01 | 1.000 | 58,523,648 | 52,248,576 |
| 500 declarations | 0.23 | 0.14 | 0.609 | 587,399,168 | 503,005,184 |
| 2,000 declarations | 3.47 | 1.89 | 0.545 | 589,037,568 | 590,233,600 |

The frozen cold and body-edit observations are below baseline in both wall
time and peak process RSS. The no-op is fully cached. The largest scaling
peak RSS differs from baseline by 0.20%; its observed wall time is lower.
The validation record retains the complete assessment and exact ratios.

No-op artifacts are all cached. The body edit preserves the compiler binary;
its complete LLVM equality result is `false`.
The record retains both identities. On identical frozen sources, both compiler
and manager outputs match the preceding pooled compiler's complete LLVM and
native bytes.

The current-source cold build takes 549.20 seconds with
3,824,599,040 bytes peak process RSS. This larger source workload
is excluded from baseline ratios. It uses ordinary O2 construction with the
tested PGO compiler as input; the fresh profile-use self-host fixed point above
is a separate validation.

All nine unchanged native workloads pass all eighteen compilation/runtime checks
with three samples. Compilation remains limited to 3x C and runtime to 2x C.
The native report retains correctness oracles, source/input hashes, actual exits,
full output checks, samples, medians and ratios. Runtime C is compiled afresh
inside each measured sample. C remains at O3 and the native backend pipeline is
unchanged. Historical Haskell/Rust comparison programs are preserved, not run.

## Reviewed changes and failed revisions

The complete development ledger is archived at
`.mlf-build/crate-migration/final-validation-r11/migration-ledger-before-closeout.md`
(SHA-256 `02e614f9c55f5ba3d6cedcb9cc825484f5e248b511b6ed61840aea86bc23bf0c`). Every failed measurement retains its original
status. R2's 27.20% body-edit regression and 3.112x n-body compilation failed.
R3's entry key reduced unnecessary manager code generation, but its body edit
was still 18.65% slower and n-body was 3.102x C. R4's checked fragments and
composable context checksums retained all verification; n-body still failed at
3.230x. R5 cached immutable lexical analysis inputs and canonical projections;
its body-edit difference fell to 4.70%, but its complete native gate failed at
3.273x. R6 through R10 also failed the unchanged n-body gate (3.188x, 3.059x,
3.107x, 3.078x and 3.120x respectively).

The adopted solver changes preserve complete graph validation, permission and
kind checks, aliases and malformed diagnostics. They use exact index cardinality
and required-edge checks, validated scope intervals, retained discovered nodes,
direct allocation for distinct ascending identities, and validated kind queries
with the preceding general fallback. Permanent controls compare complete graphs,
witnesses and schemes with earlier and independent implementations. Component
timings alone were not treated as whole-compiler acceptance.

Compiler-only PGO still failed the full gate at 3.030x C. Profiling both compiler
and runtime at O2 passed the diagnostic and led to R11's reproducible native
construction. O3 and the other rejected solver/runtime experiments remain
isolated. All earlier measurements are excluded from the final accepted window.

Integration repairs retain independent checking: changing a checked fragment's
body produces a raw fragment requiring a new check; an invalid recursive-signature
fixture now uses known unsaturated `IO` and first confirms independent kind
rejection. No production kind rule changed. The exported-type fixture expects
`stale crate dependency interface`; the corruption assertion requires actual
`malformed crate object framing`, avoiding accidental directory-name matches.

Pooled datatype contexts, compact stamped query reports, validated dependency
receipts, sparse Unicode indexing and normalized-result optimizer indices remain
covered by component evidence and the final suite. Exact wire bytes, restored
contexts, malformed data, complete normalized terms and scoped free-use counts
are checked by their independent controls.

## Code-generation boundary

The existing whole-program optimizer clones and normalizes identities, propagates constructor facts and specializes higher-order calls. Capture/demand analysis and numeric-worker selection also depend on the complete optimized term. Replaying old per-SCC LLVM without recording these facts would be incorrect. The implementation therefore retains this optimizer and adds two checked queries: canonical erased input plus exact datatype/constructor/runtime ABI, then canonical optimized input. Annotation-only changes can skip optimization and generation; dead implementation edits can reuse output after optimization. Native LLVM objects and runtime objects have independent caches. Changing a live optimized program conservatively regenerates that program; this is not a claim of a stable per-function native ABI.

The driver schedules crates and SCCs serially. Independent ready crates/SCCs
provide future parallelism, but no parallel speedup or per-function native ABI
is claimed. Moving dependency artifact paths requires refreshing metadata.

## Oracle migration

The frozen Haskell-seed corpus archive remains unchanged. Exactly two old module-import-cycle rejection rows (`module-reject-000025` and `module-reject-000026`) now have a guarded exporter overlay prescribing acceptance at `Int`. Their archived source text and former diagnostic are asserted, and the fixed literal target `42` is checked by the independent target checker. Other oracle expectations retain their original provenance. Corpus size remains 7086; accepted rows increase from 3202 to 3204, and runtime rows remain 80.

The separately generated port inference fixture has one matching semantic
update: `module-cycle` prescribes acceptance at `Int` for `a = 1`, `b = 2`,
and `main = a` across mutually importing modules. Its original source and every
other expected result, including all Figure 12 cases, remain unchanged.

## Preservation and reproduction

All 2,712 historical files covered by preservation remain unchanged,
excluding the two expressly updated benchmark documentation files. All 72 pins,
the frozen parity archive, archived measurements and independent Snake baseline
are preserved. GHC, Cabal and Python are blocked on PATH and the invocation log
is empty. No commit or push was performed.

Use the [native test workflow](../tests/README.md) and
[package commands](package-manager.md). Saved command records provide the exact
immutable manifest, actual compiler, profile, runtime, output paths and command
exits. Future source or tool changes require fresh matching verification.

## Reference material

The useful Rust principles are compilation at crate boundaries and cached semantic queries, rather than Rust syntax or a wholesale reproduction of rustc internals. See the [Rust compilation model](https://doc.rust-lang.org/reference/crates-and-source-files.html), [crate-wide name resolution](https://rustc-dev-guide.rust-lang.org/name-resolution.html), [query providers](https://rustc-dev-guide.rust-lang.org/query.html), [stable incremental identities and result fingerprints](https://rustc-dev-guide.rust-lang.org/queries/incremental-compilation-in-detail.html), and [library metadata](https://rustc-dev-guide.rust-lang.org/backend/libs-and-metadata.html).

The [GHC recompilation checker](https://downloads.haskell.org/ghc/latest/docs/users_guide/separate_compilation.html#the-recompilation-checker) provides a second reference for recording fingerprints of declarations actually consumed. It is literature for interface design, not a build dependency or a restriction on MLF's module graph.
