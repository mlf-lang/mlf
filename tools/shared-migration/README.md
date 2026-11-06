# Reviewed one-time shared-source migration

This directory is historical migration tooling, **not a normal build dependency**.
The maintained compiler sources are the committed `.hs` files. Neither host
build imports, executes, regenerates, or overlays anything from this directory.
Removing this whole directory must not affect a normal build or its source
identity receipt.

## Scope and provenance

The inventory starts from every library manifest, executable entry, and private
executable module in the root manifest. It also includes six direct-host Async/frontend
tests, copied to stable `MLF.Tests.Async.*` modules while retaining the original
guest fixtures. The four executable entries move to `MLF.Entry.*` paths.

`MLF/Host/{Lexer,Layout,Parser,Syntax}.hs` were copied from the **published, clean**
PR20 tree at `767a5b66172ccf3931e0954c38ca47eb8b4e7a28`, then adapted here as an
offline parser. No work from an unpublished or paused PR20 checkout was used.
`Migrate.hs`, `Main.hs`, and `migrate.py` implement this migration. The parser
keeps original string-token spelling, including escapes and embedded guest
programs; it retains fixed operators as syntax instead of lexical function
references.

The immutable 84-file baseline audit in `evidence/baseline-*` establishes:

- Exactly 89 string-pattern leaves in 17 modules, all in case matrices
- 1,743 ordinary local bindings, each a separate group, with **zero** free own-
  binder capture hazards; actual hazards are still detected and freshened
- Two explicit recursive local groups, both already closed and annotated
- 550 cyclic top-level dependency components, all members explicitly signed
- 13 negative Double expression literals; no Double patterns
- The sole competing syntax-hook definition is `Bootstrap.Std.negate`

Later frontend and builtin changes add source before the final conversion.
`evidence/migration-manifest.json` records each exact final preimage/output hash,
line count, operation, module name, membership, and transformation counters.
`evidence/summary.json` records the tool hashes and pre-migration revision.

## What the transformation proves

The input is parsed to an AST. Lexical environments resolve pattern binders,
sequential local scopes, recursive groups, imports, and the specific
`Bootstrap.Std.negate` rename. Names are retained unless a new recursive scope
would capture an outer reference or a genuinely reserved binder needs changing.
Fresh names exclude **all** original identifier tokens. Ordinary bindings retain
separate nested groups; recursive groups require one closed signature per member.

A matrix containing any string pattern is rewritten as a whole, following
`Bootstrap.Surface.matrix`'s first-row, leftmost-demand ordering. Constructor
specialization exposes only the selected constructor's fields; equality is
checked before later columns are demanded. Generated equality references use
`MLF.Primitive.eqString` / `MLF.Primitive.eqInt`, so local ordinary names cannot
capture them. A facade-hiding conflict is rejected for explicit review.

Refutable do binds become a fresh variable bind followed by an explicit case
containing the remaining statements. Ordinary variable/wildcard binds stay do
syntax. Negative Double literals call the shared `negateDouble` helper, which
toggles the binary64 sign bit and preserves signed zero. Infix operators, do,
if, literals, original ordinary names, and conventional explicit type schemes
remain readable maintained source. No ViewPatterns, global `v_`/`t_` namespace,
or source-to-source step is required by either host build.

The printer writes explicit block braces and retains source comments. Every
output is reparsed and its complete normalized AST is compared with the
transformed AST. This catches precedence, grouping, declaration, and literal
printer bugs. Every original expression string token must remain byte-identical
with at least its original multiplicity; every output string token must occur
in the original expression/pattern token inventory. A matrix may duplicate a
fallback branch, so literal *counts* can grow without any literal changing.
There must be no output string-pattern leaves.

## Reproducing a proposal

Use a frozen pre-migration checkout, never a concurrently edited source tree.
The tool requires GHC's shipped `parsec`, `mtl`, `containers`, and `pretty`.
Build and run it outside normal build directories:

```sh
ghc -O0 -i./tools/shared-migration \
  -outputdir /tmp/mlf-migration-tool -o /tmp/mlf-migrate-shared \
  tools/shared-migration/Main.hs
python3 tools/shared-migration/migrate.py \
  --root /path/to/frozen-pre-migration-checkout \
  --tool /tmp/mlf-migrate-shared --output /tmp/mlf-source-proposal
GHC=ghc MIGRATOR=/tmp/mlf-migrate-shared tools/shared-migration/tests/run.sh
```

Inspect the proposal and evidence before using `--apply`. Applying verifies all
preimage hashes again, refuses existing output paths, writes the checked bytes,
and removes only files marked `rename`. The six direct-test guest sources are
marked `copy` and retained. The affected native manifests receive the same canonical paths and explicit
source-syntax fields. Runtime profile and other manifest semantics are unchanged.

The focused fixture suite covers poisoned tails/heads, equation and case demand,
fallback aliases, sequential capture, pattern shadowing, closed mutual recursion,
constructor-do continuation, equality-hook capture, lexical comments/string gaps,
and rejected nonexhaustive/unreachable/unsigned recursive forms. It does not
replace the whole raw-source dual-host qualification campaign.

The separately maintained `Audit.hs` and `audit-scope.py` provide a second scope
check. Build `Audit.hs` against the parser, feed it `MODULE<TAB>SOURCE` rows, and
feed its TSV output to `audit-scope.py INPUT.tsv REPORT.json`. The final 91-module
preimage has 571 cyclic top-level SCCs / 788 bindings; every runtime-cyclic
binding has an explicit closed signature. The added shared frontend contains
two more string-pattern leaves, so the final migration has 91, while the fixed
84-file comparison baseline remains exactly 89.

## Post-cutover Haskell-first adjustment

The original `migration-manifest.json`, baseline audits, and final migration
fixtures are immutable historical receipts. They describe the initial cutover,
which still used `RebindableSyntax`; they are not claims about later source bytes.
The approved Haskell-first adjustment removes that extension and uses the actual
standard `Functor`, `Applicative`, and `Monad` identities from the host facade.
`Hierarchy.hs` is used by both the latest initial-proposal tool and `Adjust.hs`.
It converts each legacy `return`/`bind` instance into three standard instances:
`fmap` maps through the old bind and pure computation; `<*>` sequences the
function action before the argument action; `pure` keeps the old return
computation; the only defined Monad method is `(>>=)`, preserving the old bind.
Standard defaults supply `return` and `(>>)`. Nontrivial method equations are
lifted unchanged into closed, explicitly signed helpers. In particular,
`Generate` keeps its explicit state `seq` in `generateBind`.

`Adjust.hs` changes only the original pragma and legacy-instance token spans,
leaving every other source byte intact. It reparses and checks the complete AST
against the intended transformation and checks the exact expression-string token
multiset, including multiplicity. `adjust.py` rechecks preimage hashes before
applying and writes a separate `standard-hierarchy-adjustment.json` receipt.
That operation checked 93 modules: the original 91 were changed; the two new
production BuildReceipts test modules, already standard Haskell, were unchanged.
Its receipt is an adjustment record, not a replacement for the initial migration
provenance or the later whole-corpus dual-host qualification.

```sh
ghc -O0 -i./tools/shared-migration \
  -outputdir /tmp/mlf-adjustment-tool -o /tmp/mlf-adjust-shared \
  tools/shared-migration/Adjust.hs
python3 tools/shared-migration/adjust.py \
  --tool /tmp/mlf-adjust-shared --output /tmp/mlf-standard-hierarchy-proposal
```

The latest focused fixtures additionally exercise standard fmap/pure/application,
Monad return/sequence defaults, compatibility bind, and poisoned ignored payloads.
The frozen legacy bridge archive is intentionally unchanged.

### Observed literal type generalization

A successful ordinary GHC typecheck alone does not prove that inferred exported
interfaces agree with native fixed literal types. A subsequent actual
`-ddump-types` run found 41 generalized definitions in 19 source files: 39
`IsString` cases and two `Num` cases, with no `Fractional` case. The reviewed
`literal-signatures.json` maps precisely those observed schemes to ordinary
`String`/`Int` signatures, retaining every unrelated type variable. There is no
global defaulting rule, overlapping class instance, or inferred blanket annotation.
`LiteralSignatures.hs` keeps the latest one-time proposal aligned with this plan.

`literal-annotation-adjustment.json` records the exact 41 insertions and old/new
file hashes. Removing the inserted signature lines recovers every original byte,
so this adjustment cannot change embedded literals or executable expressions.
`standard-inferred-types-{before,after}.{json,log}` preserve the actual GHC
inferred interfaces. The after run checked all 94 modules and found zero shared
top-level `Num`, `Fractional`, or `IsString` constraints; its source hashes were
unchanged throughout compilation. The generic audit can be repeated on a fresh
type dump with `audit-inferred-types.py LOG shared-sources.json REPORT
--require-concrete`. These are explicit post-cutover receipts, separate from the
original byte-retention migration claim.

The final additional `MLF.Tests.PRQuickMain` source-smoke entry is a direct,
editable copy of the retained `tests/PRQuickMain.emlf` fixture. Its 45 string
literals are byte-identical and its argument contract is unchanged. See
`shared-source-smoke-copy.json`; the static inventory now has 94 modules and
12 executables, including the two separately introduced BuildReceipts helpers.
