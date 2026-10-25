# Source-owned field normalization

## Scope and boundary

Fresh source datatype declarations use one canonical field layout for inference,
 emitted xMLF declarations, source-query keys and saved crate metadata. The
canonicalizer recursively removes a `Quantified` field binder only when its name
is not free in the already-normalized body. It preserves live quantifiers,
lexical shadowing, datatype parameters and kinds, constructor identity/order,
field order and runtime arity.

Original declarations are validated before any syntax is removed. Invalid kinds,
unknown constructors or unbound variables therefore cannot disappear through
normalization. Checked imported declarations participate in that validation but
are never rewritten. Generic target checking, target equality, imported object
parsing and `CompilerCore.finishCompilation` remain unchanged.

The source-only entry points are:

- direct/legacy/linked source compilation, before class lowering;
- a crate's own resolved declarations, before combining them with checked
  imports and before creating its `SourcePlan` or query inventory;
- the freshly compiled builtin source crate.

This is a source declaration normalization, not a new xMLF arrow-congruence rule
or a cast inserted around constructor values. The canonical declaration is used
consistently by constructor-as-value, partial application, construction and
pattern elimination. No eta expansion or computational wrapper is introduced.

## Validation checkpoint

The first datatype-only candidate was built cleanly at GHC O2. Its producer
receipt SHA256 is
`d9f00320ab07575ccf488d762fefa8cf2004cee8b0847129970a2cd5e4c45c37`.
The focused `--recursive-inference` mode passed in 148.55 seconds with all three
expected completion banners and empty stderr. This includes both target
checkers, serialized target roundtrips, erasure comparisons, 15 added source
positives, five added source negatives, and pure normalization/idempotence tests.
This is an intermediate implementation checkpoint, not a claim that later edits
have the same validation identity.

## Explicit boundaries

The live field `forall a. a` is not a dead quantifier. The existing bare-constructor
case `data Abs = Abs (forall a. a); Abs` remains a named rejection control for a
separate graph/constructor normalization mismatch.

A datatype-only transformation does not fix freshly generated class dictionaries.
Both a leading unused method quantifier and an unused quantifier in a method's
arrow result have independently reproduced the analogous mismatch. Their repair
must canonicalize only freshly owned source class headers after original method
and superclass validation, consistently before selector/dictionary generation
and saved metadata. Imported class headers and dictionary ABI reconstruction must
remain untouched.

Opening known polymorphism supplied through an ordinary datatype parameter is a
separate graph scheduling/evidence change. It must distinguish an exact rigid
interface from a flexible unknown with a polymorphic-looking lower bound, and
must not infer polymorphic recursion or retroactively import a later application's
argument information into an earlier unannotated lambda body.
