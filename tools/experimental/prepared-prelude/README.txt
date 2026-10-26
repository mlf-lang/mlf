Compiler-owned full Prelude experiment
=====================================

This directory retains the opt-in experiments that established the prepared
Prelude route. Its build.py executable is separate from the normal compiler.
The normal entry now uses MLF.PreparedCompiler and the canonical generated
MLF.BuiltinPreludeData for eligible standalone roots, with ordinary fallback.
Neither route narrows the Prelude class/instance inventory or caches user programs.

build.py compiles Generate.hs from an immutable snapshot of the current shared
sources. Generate invokes Artifact.builtinPrelude and writes lossless raw AST
constructors plus the complete crate interface. The same source snapshot builds
the consumer. The generated data contains no CheckedTerm constructor or unchecked
evidence. Each fresh consumer process validates the full interface and admits
every raw object through the existing independent checker and linking rules.

The user body remains one whole-root inference problem. The adapter includes the
complete builtin classes and instances, retains ordinary wanted-constraint
closure, and uses existing imported source scheme reconstruction. SourceContract
and protection metadata are retained; protection flags concern managed evidence
contraction, not graph quantifier rigidity. No module-level unsigned-root
compaction is substituted for ordinary whole-root inference.

The final linked program is checked again in full. Root datatype declarations
remain first, preserving ordinary source/constructor order; imported fragments
may confirm those declarations but cannot add an unowned layout. Canonical-name
collisions and roots without a facade reference fall back to the original
compiler. The experimental emission operations reject fallback, so they cannot
silently report an ordinary run as a prepared success. The production adapter
performs cheap admission before forcing the prepared context, including
facade-free, NoImplicitPrelude and collision cases.

Build:
  python3 tools/experimental/prepared-prelude/build.py \
    --ghc /absolute/path/to/ghc --cc /absolute/path/to/clang \
    --output /fresh/output

Operations:
  prepared-emlf --emit-llvm-gc SOURCE
  prepared-emlf --full-emit-llvm-gc SOURCE
  prepared-emlf --direct-emit-llvm-gc SOURCE
  prepared-emlf --ordinary-emit-llvm-gc SOURCE
  prepared-emlf --compare SOURCE
  prepared-emlf --prepared-context

The ordinary emission operation bypasses prepared restoration entirely. The
context-only operation forces raw builtin admission without a user source.
The default experimental operation selects synthetic import parameters after
the unchanged full class lowering, all local RHSs, and complete external scheme
translation. It observes every free value and every wanted evidence candidate;
it does not remove source declarations, instances, or wanted candidates. The
full operation retains all synthetic parameters as an in-process reference.
--imports and --full-imports report these authenticated prefix sizes. Selection
is an internal operation on the freshly generated synthetic prefix, not a
license to delete arbitrary same-name bindings supplied by a caller.
The direct operation additionally omits the authenticated panic RHS constraint
subgraphs, retaining the exact import declarations/Poly environment and one
whole continuation. It checks an explicit target lambda wrapper, verifies every
import scheme, and removes exactly the authenticated parameter count before the
unchanged full graft check. This executable keeps it opt-in; the production
adapter uses the corresponding Bootstrap.ImportedRoot module. --compare-direct
uses the ordinary source route as its principal-scheme/layout/error oracle.
--direct-counts, --selected-counts and --full-counts report initial graph nodes,
equalities, solve steps, and signature-only allocated nodes. The reference count
operations regenerate constraints expressly for diagnosis; never time them as
frontend compilation. Ordinary emission does not evaluate these count thunks.
Only unnamed standalone roots are currently supported; imported modules such
as the regex-redux workload still require the ordinary module pipeline.

Controls:
  python3 tools/experimental/prepared-prelude/test.py \
    --compiler /absolute/path/to/prepared-emlf --output /fresh/controls --benchmarks
  # Add --route direct for the direct-import experiment.
  python3 tools/experimental/prepared-prelude/native.py \
    --compiler /absolute/path/to/prepared-emlf --clang /absolute/path/to/clang \
    --gc-prefix /absolute/path/to/bdw-gc --output /fresh/native-controls

The source controls require positive cases to succeed and selected cases to
actually use the prepared route. They compare inferred target schemes modulo
alpha-renaming and ordered datatype layouts under the exact class-identity map.
Only compiler-owned dictionary type/constructor names are normalized; user
datatype/constructor names and declaration order are compared exactly.

Diagnostic comparison is exact except one explicit ambiguity control. That
control accepts only the identical Resolution/Eq/ambiguity message with one
nonempty generated numeric type-variable suffix renamed. Removing the Prelude
inference prefix changes fresh type-variable numbers; no literal diagnostic
byte-equivalence claim is made for that case. No general digit stripping or
message normalization is used.

Native controls require the exact nine standalone workload names and execute
both routes at O0 and O2. All 36 executions must match manifest-pinned fixture
bytes. This finite test is not a proof for all programs, a native-host compiler
qualification, or a complete native toolchain provenance claim. Build and test
receipts explicitly record these limits. Performance must be measured in a
separate quiet cohort; concurrent correctness command durations are not results.

profile.py can prepare a host-only overlay from an immutable build receipt. Its
Either timers force only the outer constructor at the existing monadic demand
boundary. Types and AST payloads stay lazy, so later phases pay for work they
actually force. Nested counters are inclusive and cannot be summed as disjoint
costs. The deep mode adds Core generation/solving/evidence/elaboration/checking,
graph operations, fragment admission/checksum, and synthetic-import generation
counters. Profiling is diagnostic and never part of a production build.

Production integration: Bootstrap.BuiltinPreludeLiteral supplies the portable
constructor printer, and the builtin-prelude target generates canonical source
without importing existing generated data. The static source/package inventories
include the generated module and normal adapter. Startup compares exact builtin
source witnesses, reconstructs metadata, and independently checks the closed term;
the final full graft check remains. production_controls.py validates the normal
entry, fresh regeneration, semantic/native comparisons and mutation controls.
The current macOS correctness receipt is not Linux/native-host qualification.
Production timing and the complete ten-workload gate remain unfinished. Imported
library preparation is a separate, currently unwired experiment.
