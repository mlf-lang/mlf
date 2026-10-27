# Haskell alignment: additive capability checkpoint

Historical checkpoint: `2916c477`. For the subsequent standard-identity cutover,
see [Haskell standard-core cutover](Haskell-Standard-Core-Cutover.md). The ABI and
pending-work statements below describe that earlier additive snapshot.

This checkpoint is **not the final source migration**. The shared-Haskell
frontend gains managed `HasCallStack`, standard-class patterned `do`, lazy/as
patterns, and typed, catchable IO failure. Legacy source semantics and the
compiler's own collection representation have not yet been cut over.

## Implemented boundary

- `MonadFail.fail` and public `ioError` carry managed call-stack evidence.
  Unsigned definitions do not infer this constraint. Explicit qualified
  signatures forward it. Source sites retain package, module, supplied file
  path and coordinates, including across separately compiled packages.
- Generated shared `do` uses canonical class identities, not locally shadowed
  `fail`/bind names. Refutability uses the complete resolved constructor family,
  including hidden constructors. A non-failing pattern is not necessarily lazy.
- Lazy patterns preserve type and class obligations without forcing an unused
  match. A shared, generalizing match binding plus an undemanded witness keeps
  existing rank-polymorphic fields and richer MLF polymorphic tuple behavior.
  Ordinary let generalization and the target checker are unchanged.
- String-pattern rows are ordered: different literal spellings can overlap
  under lawful `IsString`/`Eq` instances. Complete-family coverage may eliminate
  an impossible generated fallback, but does not relax exhaustiveness checking.
- Typed IO errors are deferred actions, distinct from pure panic. Catch handlers
  preserve scoped handling context and async cleanup. Native source-origin
  stack behavior is tested; GHC-internal implementation frames and complete
  diagnostic envelopes are not claimed byte-identical.

Primitive IDs 103–106 are appended to the prior ABI. Private frame/evidence
constructors reserve IDs 7 and 8; user constructors start at 9. The runtime
Haskell-boundary guard is v2, and interface/query tags are v3. Stale boundary
linkage and cached contracts fail closed.

## Deliberately pending atomic cutover

Canonical unit/list/tuple identities currently coexist with old nominal ADTs.
IO/ST primitives still return legacy Unit, not canonical `()`. The existing
unit Eq demand bug, canonical list class instances, extended tuple inventory
and instances, both-profile standard do/string behavior, and actual shared/
guest corpus migration remain pending. No full Haskell standard-library
instance universe, numeric/defaulting change, or recursion extension is claimed. Numeric string
escapes currently reject surrogate code points: full Haskell `[Char]` literal
parity requires a codepoint-preserving source path rather than a forced opaque
text intermediate, and is not claimed by this checkpoint.

The shared source parser also retains its existing adjacent-signature subset:
nonadjacent signatures fail closed rather than silently attaching to another
binding. Ordinary GHC accepts more declaration orders.

## Qualification scope

The full pinned GHC producer builds all 103 shared modules, audits their actual
inferred schemes, links isolated C objects, checks shared syntax/name resolution,
and authenticates source/tool inputs. This is explicitly a **GHC producer**, not
native bootstrap qualification or all-module actual-MLF typechecking.

Focused fixtures under `tools/shared/fixtures/item4` cover source inference,
interpreter/host/native behavior, artifact reconstruction, package identity,
cache boundaries, and actual separate producer/consumer linking. Host pattern
references use unchanged source bodies with a separate test-only entry wrapper;
MLF-only polymorphism and static-vs-runtime exhaustiveness differences are
recorded rather than disguised as identical GHC behavior. Historical receipts
remain scoped to their exact input hashes. No released native seed, full-corpus
migration, or new native fixed point is qualified by this checkpoint.
