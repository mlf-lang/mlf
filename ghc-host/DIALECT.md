# Compiler implementation dialect

The input is the existing MLF compiler/package/library implementation. This is
not a general MLF-to-Haskell backend. MLF programs still use the original source
checker, graph solver, dictionaries, xMLF checker, interpreter and LLVM backend.
In particular, guest impredicativity and recursive module semantics do not
depend on GHC accepting equivalent Haskell expressions.

The batch manifest is a closed implementation module inventory derived from the
existing package manifests. Each row is `source<TAB>output<TAB>module`. The last
field gives independent names to executable entry modules. Generation preserves
relative source names with `LINE` pragmas. Generated files are build artifacts.

Supported implementation constructs are ordinary algebraic data types, explicit
kind parameters, ordinary `forall` (including the rank-2 `runST` boundary),
classes/instances, qualified imports and explicit exports/hiding, functions and
pattern equations, annotations, lambda/case/if, total guards, nonrecursive local
bindings, explicit recursive binding groups, and custom `Monad` do notation.
Tuple/list sugar lowers to the original `Unit`, `Pair`/`Triple`/`Quad`, `Nil` and
`Cons` names. No built-in Haskell list/tuple representation is substituted.

Maintenance constraints:

- Keep the host module graph acyclic. The batch converter rejects cycles before
  resolving module re-exports. Guest cyclic imports remain tested by the MLF
  module/crate algorithms.
- Keep host polymorphism expressible with the emitted GHC extensions. There is
  no `ImpredicativeTypes`, `unsafeCoerce`, erased completion payload, or inference
  fallback. A new GHC type error requires analysis of the source pattern and
  explicit semantic tests; do not weaken MLF's checker to resolve it.
- Bounded/rigid quantification, existential declarations, partial guards,
  comprehensions/ranges and implementation syntax outside this grammar are not
  accepted host features. MLF-only types occurring inside guest source strings
  and syntax trees remain ordinary data and are preserved verbatim.
- Use explicit `Cons` for a host expression constructor. The current source
  grammar retains `:` for annotations; it supports `:` in patterns. Compiler
  implementation sources do not require expression cons sugar. The guest
  parser's full Tuple/List rules are unchanged.
- Keep primitive calls behind `MLF.Host.*`. Integer literals mean arbitrary
  precision MLF Int; strings use Unicode scalar indexing. Custom do lowers to
  `v_bind` without Haskell's `MonadFail` or `Applicative` assumptions.
- Ordinary local `let` is sequential and nonrecursive. Its RHS sees the old
  environment. Only `let rec` is recursive. Fresh generated names enforce this.
- Preserve lazy algebraic fields, ST payloads and typed completion payloads.
  The host wrappers explicitly order primitive forcing and action execution.
  Blanket strictness or eta expansion is not a semantic justification.

The parser is a typed AST parser, not a textual substitution pass. GHC remains
the host type checker. The initial supported inventory contains 84 source
modules plus four host modules. All original implementation `.emlf` sources are
unchanged. New constructs require a source/native/GHC differential fixture and
an updated dialect boundary before expanding that inventory.

The OS adapter exchanges owned UTF-8 buffers and bounded integers through C.
It reuses the original POSIX process supervisor/protocol but does not link the
MLF value heap, GMP allocator hooks or BDWGC into GHC. Process cleanup runs on
normal exit and host-language failure. macOS arm64 is the initial qualified
platform; Linux/Windows portability must not be inferred from compilation here.
