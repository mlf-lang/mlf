from pathlib import Path
import hashlib,json,difflib
p=Path('/tmp/solver-direction'); base=(p/'Solver.hs').read_text()
marker='  expandedGraphPrepared :: Int ->\n'
helper='''  -- PRIVATE prepared-Solver route only. prepare establishes fresh-ID separation;
  -- prior operations preserve it. Public G.expandWithScopes remains unchanged.
  -- Keep its traversal, kind prepass, allocation and ordered strictNode demands.
  -- Build the fresh ascending map once, instead of inserting each fresh node
  -- into the progressively larger old graph and resolving known-fresh IDs.
  expandPreparedBulk :: IntMap ((,) Int Int) -> Int -> Int -> Graph ->
    Either String ((,) ((,,) Int (IntMap Int) ([] ((,) Int Int))) Graph);
  expandPreparedBulk intervals generalization destination old =
    let { source = G.genRoot old generalization } in
    case G.expansionVisitCached old generalization intervals ((,) IS.empty IM.empty)
           ((:) source []) of {
      (,) visited scopes -> let { originals = IS.toList visited } in
        G.bindE (G.kindsAt old originals) (\\kinds ->
          case G.allocateCopies old originals of {
            (,) copies allocated ->
              let { copy = G.copyIdentity old copies;
                    entries = L.map (\\n -> (,) (copy n)
                      (G.expansionNode old generalization destination source copies kinds scopes n)) originals;
                    fresh = G.nodesFromDistinctAscList entries;
                    result = G.mkGraph (IM.union fresh (G.nodes allocated))
                      (G.links allocated) (G.nextId allocated);
                    frontier = L.filter (\\n -> L.not (IM.findWithDefault False n scopes)) originals
              } in Right ((,) ((,,) (copy source) copies
                   (L.map (\\n -> (,) n (copy n)) frontier)) result)
          })
    };
'''
assert base.count(marker)==1
candidate=base.replace(marker,helper+marker)
start=candidate.index(marker); before=candidate[:start]; tail=candidate[start:]
old='(G.expandWithScopes (scopeIntervals (scopeIndex solver)) source destination'
assert tail.count(old)==1
candidate=before+tail.replace(old,'(expandPreparedBulk (scopeIntervals (scopeIndex solver)) source destination',1)
(p/'Solver.candidate.hs').write_text(candidate)
(p/'candidate.patch').write_text(''.join(difflib.unified_diff(base.splitlines(True),candidate.splitlines(True),fromfile='a/libraries/mlf-inference/Bootstrap/Graph/Solver.hs',tofile='b/libraries/mlf-inference/Bootstrap/Graph/Solver.hs')))
(p/'source-pins.json').write_text(json.dumps({'main':'fc300bc9fdc389b585cbef0630fc8915d53e89c5','solver_git_blob':'ac4807fa23c0763ba83a0f9c52c1c734cc059720','original_sha256':hashlib.sha256(base.encode()).hexdigest(),'candidate_sha256':hashlib.sha256(candidate.encode()).hexdigest(),'status':'SOURCE_DRAFT_NOT_COMPILED'},indent=2)+'\n')
print((p/'source-pins.json').read_text())
