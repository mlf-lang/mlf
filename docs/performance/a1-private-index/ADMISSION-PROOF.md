# A1 direct private admission — unqualified study

## Scope and status

This is ONE bounded experiment from frozen A0, not an accepted optimization.
Only the copied `study/Bootstrap/CrateSession.hs` changes. Its only production
export remains `compileSpecFile`; the copied `Graph/IndexStore.hs` is unchanged.
Public `Graph.Solver.prepare`, generic/raw APIs, old source, old tests, old
evidence and harnesses are not edited. No compiler, test executable, performance
job or bootstrap was run by this source-authoring task. In particular, the
user-cancelled native74 bootstrap must not be restarted.

The surviving A0 profile motivates only the redundant initial outer-map work:
original admission allocated 11,150,046,088 bytes; its narrower insertIndexTree
subtrees allocated 7,205,821,696 bytes, including 3,577,726,320 direct outer
Map.balance OWN bytes. These nested regions must not be added. Replacement
private writes, immutable bucket construction, validation and scopes still cost.
A0's whole-allocation reduction was 3.5872068%, not a measured wall improvement.
This study makes no A1 speedup, runtime bound, 3x-goal or verified-model claim.

## Exact source seam

1. `prepareGraph :: Graph -> Either String Graph` retains the exact expression
   sequence from public `S.prepare` through its three identity guards, including
   messages and lazy Boolean short-circuiting. Its successful result is the same
   lazy `G.canonicalize input`, without constructing the old reverse maps.
2. `solvePrepared` still evaluates that pure guard chain before entering runST.
   It replaces only the S.prepare/openSession admission pair with
   prepareGraph/openPreparedSession. Initial unification, ordered solve steps,
   all mid-session audits, final freeze/finishNormalized and every downstream
   type, term, xMLF, evidence and erasure check are unchanged.
3. `openPreparedSession` allocates a private empty store using the unchanged
   `K.importIndices IM.empty IM.empty`, then traverses exactly
   `IM.toList (G.nodes canonical)` with ST.fold. IntMap.toList is the same
   ascending enumeration used by S.prepare; there is no new node collection,
   reordering, compaction or identity conversion.
4. `addInitialNode` forces the state before delegating to unchanged `addNode`.
   This wrapper matters because S.addNode matches its Solver argument before
   matching the node pair, whereas the old private addNode first matches its
   pair. A bare ST.fold addNode would not document/preserve that ordering.
5. The old openSession helper remains byte-identical for independent controls.
   No new raw adapter is exported. No kernel API, kernel code, inference-cache
   logic, target reuse, compiler flags, manifest or lock was changed.

## Bounded demand/error argument

### Failed guards and the lazy successful result

Both routes first call the literal `G.validateGraph input`. A Left wins before
any overlap/counter test. On success, live/alias overlap wins before the fresh
node test; the fresh node test wins before the fresh alias test. Exactly the old
messages are retained. The graph success payload remains lazy: inspecting just
the outer Right does not canonicalize, index scopes or insert reverse edges.
The region and its private storage are reached only through that Right branch.

This preserves those explicit failure choices without claiming that finite
tests prove all possible exception orderings of arbitrary forged lazy graphs.
The production caller does not accept such graphs: its only exported entry
reads the specification and source/dependency files, parses/decodes them,
prepares/lowers their source groups and invokes the existing C.generateProgram.
The changed admission receives C.initialGraph of those internally generated
constraints. That genuine file origin and the earlier checks remain intact.

### Node-list spine before initial state

S.prepare's `L.foldlStrict` inspects the canonical node-list spine before its
initial accumulator. The new `ST.fold` does the same. Do NOT put a seq on the
mkSession initial value before that fold: it could move scope demand before the
first list-spine demand. Canonicalization itself is the unchanged strict graph
constructor and node mapper.

For a nonempty stream, S.addNode first forces the initial mkSolver. mkSolver
forces strictGraph, both empty reverse-map roots and strictScopes in that order.
The new addInitialNode first forces mkSession, which calls the same strictGraph
and S.strictScopes. Both omitted immutable reverse-map roots are literal
IM.empty (total); the replacement private empty-store import also consumes
literal empty roots. Thus the genuine graph roots/fresh counter and scope roots
are required before the first node's fields/edge edits, as before. The pair is
matched only after that state force.

S.strictScopes is not reimplemented or strengthened: it forces the intervals
map root and jumps list spine, not an invented deep normal form. The original
S.indexScopes computes exactly the same ScopeIndex value from canonical.

### Empty graph and completed folds

The empty S.prepare fold returns its lazy mkSolver, but the old openSession
must inspect structuralParents before completing import, which forces that
mkSolver. ST.fold's empty case alone would merely return its initial thunk.
The explicit `seq prepared (stReturn prepared)` after the new fold closes this
gap: even an empty graph's strict graph and scope roots are demanded before
openPreparedSession returns and before the initial equality list is consumed.
This is an essential admission barrier, not an optional strictness tweak.

For nonempty input the delegated addNode commits its edits and returns the SAME
already-forced Session. The graph and scope values are invariant during initial
index population. Therefore ST.fold cannot carry a newly lazy state into its
next iteration: the state was forced before the step and commit returns it
unchanged. S.addNode's subsequent mkSolver calls only reforce those already
forced graph/scope roots after the newly built bucket roots. This argument
depends on addNode/commit remaining literal; changes there need renewed review.

### Children before binder; bucket demand

The original S.addNode constructs structural parents with a strict left fold
over `G.children (G.tag node)`, and mkSolver forces those parents before the
binding descendants. The private addNode uses lazy L.append to concatenate the
structural InsertMember actions with the binder action. K.commitEdits executes
each structural action, including its forced immutable bucket root, before
demanding the rest of the list; only after the structural list ends can the
binder list be inspected. Both visit child occurrences in their original order,
including duplicates, and then visit the optional binder once.

K.insertMember uses IS.singleton for a new page's first bucket and IS.insert
for an existing slot. An existing page's empty slot uses IS.insert n IS.empty;
by IntSet.insert -> IntMap.insertTree MapEmpty -> Map.singleton this produces
the same singleton tree as IS.singleton n. Later inserts are literally the
same immutable IntSet operation as S.insertIndexTree. Both paths force the
updated bucket root before continuing. No sorting, bulk-set replacement,
deduplication shortcut or mutable bucket representation is introduced.

The page-address calculation and outer directory traversal differ from old
outer-tree traversal by design. The argument is for the reached valid finite
canonical identities, not arbitrary-bottom equivalence of raw map shapes or
malformed/private state. No test-only admission exports may enter production.

## Value invariant / induction

Let E be the exact ascending canonical node stream. Initially both reverse
relations are empty. After each processed node prefix, the store's Structural
bucket at target t is the immutable IntSet obtained by the original ordered
inserts of every processed node identity whose child occurrences equal t. The
Binding bucket analogously contains identities whose binder equals t. Missing
old keys and empty private slots both denote IS.empty. The children-before-
binder step above proves the induction without changing bucket insertion order.

The Session graph is exactly canonical, and its scopes are exactly
S.indexScopes canonical, with the same root demand. No node, alias, ID, fresh
counter, tag, binder, flag, interval or jump value changes. The existing kernel
freeze reads buckets before assembling immutable maps, emits nonempty buckets
in ascending target order, and retains their immutable roots. Its outer map
shape can differ, as already permitted by A0's private representation/freeze;
the public raw Solver APIs are not replaced or reinterpreted.

After admission the existing A0 session invariant and all original solve/audit
checks continue unchanged. This is a local source argument, not an executed
semantic qualification.

## Independent admission-control requirements

Controls must be authored from frozen public prepare/addNode and explicit
fixtures, not by generating expected output from this candidate. A test-only
header may expose prepareGraph, openPreparedSession, addInitialNode and the
existing openSession/freezeSession helpers; the production header must stay
exactly `(compileSpecFile)` and be checked independently.

Required positive coverage: empty graph; singleton/root with no edges; repeated
structural children; distinct and repeated reverse buckets; binder-only edges;
nested Gen scopes; canonicalized structural aliases with links/counter retained;
sparse/negative/page-boundary IDs. Compare graph fields, aliases and counter,
both ordered reverse maps (including bucket members) and full scope values
against frozen S.prepare after actual new admission -> freeze. Retain all old
solver/file/privacy controls and genuine parsed-file fixture/artifact oracles.

Required failures/order: validation failure alone and together with later guard
violations; overlap versus node-counter violation; node-counter versus alias-
counter violation; isolated alias-counter rejection; exact old messages. Probe
successful outer Right laziness separately from forcing its admitted payload.

Selected labelled demand probes should include initial-state failure before
pair failure in addInitialNode, child-tail failure before binder failure, final
empty-state admission demand, and preserved initial graph/scope-root demand
before consuming later equalities. Such artificial local probes support only
their stated observations; they do not enlarge the production origin contract
or prove arbitrary raw-bottom equivalence.

Any full qualification/performance work remains owned by the main task: exact
frozen 14-module target, every existing check, cold 544 fresh / 0 reused groups,
same-host GHC baseline, predeclared ordinary candidate/P3 screen, and retained
negative evidence if replacement overhead defeats the seam. A single pair is
not acceptance. No source manifest/lock regeneration or publication is justified
by this uncompiled study alone.
