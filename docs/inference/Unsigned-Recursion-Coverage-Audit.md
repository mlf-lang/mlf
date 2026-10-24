# Focused false-negative and annotation-boundary audit

This follow-up asks whether expected ordinary-recursive programs were missed,
not merely whether some annotations remain meaningful. It is a finite audit,
not a claim that every inferable program is accepted. No compiler implementation
changed during the audit.

## Ordinary recursive combinations

An independent audit checked 79 sources using the final O0 and O2 compilers:
76 accepted, and three expected unannotated higher-rank parameter cases rejected
(two recursive forms plus their nonrecursive control). Both optimization levels
produced matching results. Coverage includes nested let/rec capture, distinct
export telescopes, dependent peer bounds, outer frontiers through bounds,
aliases, branches, and partial or higher-rank local annotations.

Eight accepted representatives were serialized and checked again with the
production CLI at both levels (16 target checks). The separate frozen checker
was **not** run on these additional scratch samples; its coverage belongs to
the maintained 53-case focused suite, not this audit. Exact sources, commands,
logs, targets and comparison data are included in the handoff's
`evidence/false-negative-audit/` directory.

No new in-scope false negative was found in these samples. That conclusion does
not establish minimum-annotation inference or principal completeness.

## Inherited polymorphic constructor-field revelation gap

This small nonrecursive source is rejected:

```text
data Poly = Poly (forall a. a -> a);
case Poly (\x -> x) of { Poly g -> g 1 }
```

The error is `cannot raise a protected type variable`. Revealing the already
known polymorphic field type locally makes it pass with `Int`:

```text
data Poly = Poly (forall a. a -> a);
case Poly (\x -> x) of { Poly g -> (g : forall a. a -> a) 1 }
```

A mutual recursive body using the same pattern-bound field behaves identically:
full signatures on both recursive functions do not remove this field-revelation
requirement, whereas the local full-`forall` annotation does. Annotating only the
use as `Int -> Int` does not reveal the polymorphism and still rejects.

`Constraint.patternBindings` binds pattern variables as `Mono`; `buildBranch`
embeds constructor fields with `Rigid` attachment. Those blocks are unchanged
from pinned PR #22. Existing `Tests.Datatypes` cases explicitly reveal
polymorphic fields in this way. Fourteen exact paired probe results, including signed,
unsigned, nonrecursive and local-revelation controls, are preserved in the
handoff's `evidence/constructor-field-revelation-audit.json`.

A stronger annotation-free paired control localizes the missed instantiation:
`(case Poly (\x -> x) of { Poly g -> g }) 1` passes as `Int`, while moving
that same application into the branch, `case Poly (\x -> x) of { Poly g -> g 1 }`,
rejects. The unboxing function retains a bound of `forall a. a -> a` in its
inferred result and can be used later at both Int and Bool. A plain local alias
inside the branch does not fix it. Full type information is therefore present;
implicit instantiation becomes available at the case-result boundary but not at
the branch binding. These pairs are retained as repair-regression candidates.

This is an inherited ergonomic inference boundary, not evidence of a new
unsigned-SCC regression. Its being inherited does not prove that the behavior is
correct or that the annotation is theoretically necessary. Recasting MLF section 2.3 explains the rigid-abstraction/explicit-
revelation mechanism, but does not specify this repository's datatype-pattern
extension. A manually constructed xMLF term for the exact rejected minimal source checks
as `Int` with the final production checker. Its erasure was inspected to match
the computational source syntax modulo binder names: type abstraction/application
erases, and no additional term-level coercion lambda is inserted. This was not
an automated erasure comparison or a frozen-checker run. The target and exact
checker result are included as `constructor-field-manual-valid.xmlf` and
`constructor-field-target-check.json` in the handoff evidence.

Thus a known valid elaboration is missed by automatic field inference. Calling
it inherited does not make the missing propagation harmless or theoretically
necessary. This recursion patch does not silently repair that separate source
inference gap.

## Confirmed inherited signature-propagation inconsistency

The final compiler rejects this explicitly signed **nonrecursive** binding with
an Int/Bool mismatch:

```text
let use : (forall a. a -> a) -> Bool =
  \g -> let n : Int = g 1 in (g true : Bool)
in use (\x -> x)
```

Prefixing only the unused declaration
`class Dummy a where { dummy : a -> Bool };` makes the same body pass as `Bool`.
Making `use` an explicitly signed recursive binding also passes. An irrelevant
class declaration changing acceptance is a concrete frontend consistency issue,
not dismissed merely because earlier code contains the same routes.

Static comparison with pinned #22 finds the same class-free `SProgram` bypass
and the class-enabled signed-let checking route. The likely distinction is pure
`SAnn` versus `SChecked`, whose directed checking propagates known function
domains into lambda annotations. A fresh GHC host probe compiled from a pristine archive of pinned #22 reproduces
all three outcomes, and the final O0/O2 compilers match them exactly. All baseline
source bytes were checked against pinned Git blobs. Exact sources, compiler
identity, command, output and hashes are in the handoff's
`evidence/signature-baseline-audit/`. No change to this behavior is included in the
verified recursion implementation snapshot.

## Other boundaries are not missed ordinary recursion

- A genuinely polymorphic recursive call may need a closed signature on the
  relevant member, while unsigned peers can still infer against that interface.
- An unannotated lambda parameter used at several types needs its higher-rank
  information supplied locally, as in the nonrecursive language too.
- Class ambiguity is not defaulted merely because one instance exists. A mutual
  `Convert Int b` example rejects at an unconstrained `f 0` and accepts when only
  that use is annotated `(f 0 : Bool)`; the recursive functions need no signatures.
- Intra-crate cross-module SCCs infer. Cycles among separately compiled crate
  dependency artifacts remain rejected by the existing crate dependency graph;
  adding signatures does not make that build-graph feature supported.
- A regular monomorphic data knot such as `ones = Cons 1 ones` infers `List Int`.
  This does not imply unrestricted cyclic-data inference or termination.
