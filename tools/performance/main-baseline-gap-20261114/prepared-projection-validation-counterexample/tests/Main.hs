{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
module Main where
import Prelude
import Control.Exception (Exception, evaluate, throw, try)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Bootstrap.IntMap as IM
import qualified Prototype.LocalSnapshot as D

data Probe = Probe String deriving (Eq,Show,Typeable)
instance Exception Probe
assert label ok = if ok then pure () else error label
right value = case value of T.Right x -> x; T.Left m -> error (P.textToChars m)
node t b = G.mkNode t b T.Flexible
bot = node T.GBot (T.Just 0)
graph pairs aliases n = G.mkGraph (G.nodesFromDistinctAscList pairs) (IM.fromDistinctAscList aliases) n
root n = node (T.GGen n) T.Nothing
plain n = right (D.layout [] 0 n [])
render g = show [(i,P.textToChars (G.tagDescription (G.tag v)),binder (G.binder v),flag (G.flag v)) | (i,v)<-IM.toList (G.nodes g)]
  ++"|"++show (IM.toList (G.links g))++"|"++show (G.nextId g)++"\n"
  where binder T.Nothing=Nothing; binder (T.Just i)=Just i
        flag :: T.Flag -> String
        flag T.Flexible="Flexible"; flag T.Rigid="Rigid"
same a b = render a==render b
outcome result = case result of T.Left e -> "Left "++show (P.textToChars e)++"\n";T.Right g -> "Right "++render g
saveCheck label wanted actual = do
  writeFile (label++".actual") actual
  writeFile (label++".expected") wanted
  assert label (wanted==actual)
  writeFile (label++".result") "PASS\n"
pass label ok = saveCheck label "True\n" (show ok++"\n")
leftMessage result = case result of T.Left e -> P.textToChars e; T.Right _ -> "UNEXPECTED RIGHT"
admission label message result = saveCheck label ("NotEligible "++message++"\n")
  (case result of T.Left e -> "NotEligible "++P.textToChars e++"\n";T.Right _ -> "Eligible\n")
-- An admission rejection is NOT an old G.unify semantic Left.
oracle label expected input eqs = do
  let snapshot=right (D.capture (plain (G.nextId input)) input)
      a=G.unify eqs input
      c=G.bindE (D.solve eqs snapshot) (T.Right . D.rebuild)
  saveCheck (label++"-A") expected (outcome a)
  saveCheck (label++"-C") expected (outcome c)
  pass (label++"-source-snapshot") (same input (D.rebuild snapshot))
expectProbe label expected action = do
  got <- try (evaluate action) :: IO (Either Probe ())
  saveCheck label ("Probe "++expected++"\n")
    (case got of Left (Probe s)->"Probe "++s++"\n";Right _->"RETURNED\n")
forceEither x = case x of T.Left _ -> ();T.Right _ -> ()

-- One new finite counterexample record. The expected text is a hand literal,
-- never computed by asking either old solver path for its error.
projectionCounterexampleExpected :: String
projectionCounterexampleExpected = unlines
  [ "prepare=Right"
  , "solverUnify-empty=Right"
  , "solver-graph-unchanged=True"
  , "groundGraft=Nothing"
  , "groundInstance=False"
  , "expanded=Right"
  , "expanded-root=10"
  , "copies=[(5,10),(6,11),(7,12)]"
  , "frontier=[]"
  , "expanded-nextId=13"
  , "expanded-shape=True"
  , "stage-eligible=True"
  , "prefix-rejected=True"
  , "projection=Right"
  , "old-originals=[0,1,2,3,8,9]"
  , "fresh-originals=[10,11,12]"
  , "stubs=[]"
  , "local-equations=[(6,2)]"
  , "local-nextId=9"
  , "local-shape=True"
  , "local-root-binder=Just 1"
  , "local-binder-contains-root=False"
  , "capture=Right"
  , "capture-roundtrip=True"
  , "local-validation=Left \"a type binder must structurally contain its node\""
  , "local-unify=Left \"a type binder must structurally contain its node\""
  , "instantiate=Left \"a type binder must structurally contain its node\""
  , "prepared-snapshot-unchanged=True"
  ]

projectionCounterexampleActual :: String
projectionCounterexampleActual =
  let g=graph
        [(0,root 1),(1,node (T.GArr 2 3) (T.Just 0)),
         (2,node (T.GArr 8 9) (T.Just 1)),(3,node T.GBot (T.Just 1)),
         (4,node (T.GGen 5) (T.Just 0)),(5,node (T.GArr 6 7) (T.Just 4)),
         (6,node (T.GTyCon "Int" T.Star) (T.Just 5)),(7,node T.GBot (T.Just 5)),
         (8,node T.GBot (T.Just 2)),(9,node T.GBot (T.Just 2))] [] 10
      summary value=case value of T.Left e->"Left "++show (P.textToChars e);T.Right _->"Right"
      handExpanded=graph (IM.toList (G.nodes g)++
        [(10,node (T.GArr 11 12) (T.Just 1)),
         (11,node (T.GTyCon "Int" T.Star) (T.Just 10)),(12,node T.GBot (T.Just 10))]) [] 13
      handLocal=graph
        [(0,root 1),(1,node (T.GArr 2 3) (T.Just 0)),
         (2,node (T.GArr 4 5) (T.Just 1)),(3,node T.GBot (T.Just 1)),
         (4,node T.GBot (T.Just 2)),(5,node T.GBot (T.Just 2)),
         (6,node (T.GArr 7 8) (T.Just 1)),
         (7,node (T.GTyCon "Int" T.Star) (T.Just 6)),(8,node T.GBot (T.Just 6))] [] 9
  in case S.prepare g of
    T.Left e -> "prepare=Left "++show (P.textToChars e)++"\n"
    T.Right prepared -> "prepare=Right\n"++case S.solverUnify [] prepared of
      T.Left e -> "solverUnify-empty=Left "++show (P.textToChars e)++"\n"
      T.Right solver -> unlines
        ["solverUnify-empty=Right","solver-graph-unchanged="++show (same g (S.graph solver)),
         "groundGraft="++(case S.groundGraft 4 2 solver of T.Nothing->"Nothing";T.Just _->"Just"),
         "groundInstance="++show (S.groundInstance (S.graph solver) 4 2)]++
        case S.expandedGraphPrepared 4 2 solver of
          T.Left e -> "expanded=Left "++show (P.textToChars e)++"\n"
          T.Right (copyRoot,copies,frontier,current) ->
            let first=G.nextId (S.graph solver)
                fresh=S.allocatedNodes first (G.nextId current) (G.nodes current)
                oldTarget=G.resolve current 2
                equations=frontier++[(copyRoot,2)]
                images=IM.fromList [(proxy,original) | (original,proxy)<-frontier]
            in P.seq (G.strictGraph current) (unlines
              ["expanded=Right","expanded-root="++show copyRoot,"copies="++show (IM.toList copies),
               "frontier="++show frontier,"expanded-nextId="++show (G.nextId current),
               "expanded-shape="++show (same handExpanded current),
               "stage-eligible="++show (S.fallbackStageEligible first copyRoot oldTarget frontier current),
               "prefix-rejected="++show (P.seq (S.forceExpansionEdges fresh)
                   (S.fallbackPrefixRejected current first images [(copyRoot,oldTarget)]))]++
              case S.preparedFallbackProjection solver current first fresh equations of
                T.Left e -> "projection=Left "++show (P.textToChars e)++"\n"
                T.Right (local,eqs,originals,(_,_,stubs)) ->
                  let oldIds=[i | (i,_)<-originals,i<first]
                      freshIds=[i | (i,_)<-originals,i>=first]
                      binder=case G.binder (G.nodeAt local 6) of T.Nothing->Nothing;T.Just i->Just i
                  in unlines
                    ["projection=Right","old-originals="++show oldIds,"fresh-originals="++show freshIds,
                     "stubs="++show (IM.toList stubs),"local-equations="++show eqs,
                     "local-nextId="++show (G.nextId local),"local-shape="++show (same handLocal local),
                     "local-root-binder="++show binder,
                     "local-binder-contains-root="++show (G.structurallyContains local 1 6)]++
                    case D.layout oldIds first (G.nextId current) (IM.keys stubs) of
                      T.Left e -> "layout=Left "++show (P.textToChars e)++"\n"
                      T.Right layout -> case D.capture layout local of
                        T.Left e -> "capture=Left "++show (P.textToChars e)++"\n"
                        T.Right snapshot -> unlines
                          ["capture=Right","capture-roundtrip="++show (same local (D.rebuild snapshot)),
                           "local-validation="++summary (G.validateGraph local),
                           "local-unify="++summary (G.unify eqs local),
                           "instantiate="++summary (S.instantiateClosedPrepared 4 2 solver),
                           "prepared-snapshot-unchanged="++show (same g (S.graph prepared) && same g (S.graph solver))])

main = do
  let empty=D.rebuild (right (D.capture (plain 0) G.emptyGraph))
  pass "empty-roundtrip" (same empty G.emptyGraph)
  let ids=right (D.layout [-9,7] 100 102 [7])
      rank i=right (D.localRank ids i)
      origin :: P.Int -> (String,P.Int)
      origin i=case right (D.origin ids (rank i)) of
        D.Old x->("old",x);D.Fresh x->("fresh",x);D.Stub x->("stub",x)
  saveCheck "old-fresh-stub-map" (show ([("old",-9),("old",7),("fresh",100),("fresh",101),("stub",7)] :: [(String,P.Int)])++"\n")
    (show (map origin [0..4])++"\n")
  admission "stub-inverse-reject" "scope placeholder escaped local unification" (D.originalId ids (rank 4))
  admission "unsorted-old-reject" "local snapshot: old identities not strictly ascending below first" (D.layout [7,-9] 100 102 [])
  admission "duplicate-old-reject" "local snapshot: old identities not strictly ascending below first" (D.layout [7,7] 100 102 [])
  admission "bad-hidden-owner" "local snapshot: invalid hidden owners" (D.layout [7] 100 102 [8])
  admission "interval-before-list-demand" "local snapshot: invalid fresh interval" (D.layout (throw (Probe "old-list")) 4 3 [])
  admission "capacity-before-allocation" "local snapshot: capacity limit" (D.layout [] 0 4097 [])
  let chain=graph [(0,root 1),(1,bot),(3,bot)] [(2,4),(4,3)] 6
      chainSnapshot=right (D.capture (plain 6) chain)
  pass "alias-chain-hole-nextId-roundtrip" (same chain (D.rebuild chainSnapshot))
  let small=graph [(0,root 1),(1,bot),(2,bot)] [] 3
      merged=graph [(0,root 1),(1,bot)] [(2,1)] 3
  oracle "merge" ("Right "++render merged) small [(1,2)]
  let chainMerged=graph [(0,root 1),(1,bot)] [(2,4),(3,1),(4,3)] 6
  oracle "alias-chain-merge" ("Right "++render chainMerged) chain [(1,3)]
  let intNode=node (T.GCon "Int" []) (T.Just 0)
      boolNode=node (T.GCon "Bool" []) (T.Just 0)
      mismatch=graph [(0,root 1),(1,intNode),(2,boolNode)] [] 3
      mismatchError="type constructor mismatch: Con \"Int\" [] versus Con \"Bool\" []"
  oracle "constructor-mismatch" ("Left "++show mismatchError++"\n") mismatch [(1,2)]
  oracle "all-equations-before-mismatch" "Left \"missing graph node 9\"\n" mismatch [(1,2),(9,1)]
  let invalid=graph [(0,root 1),(1,node (T.GArr 9 9) (T.Just 0))] [] 2
  oracle "graph-error-before-equations" "Left \"missing graph node 9\"\n" invalid (throw (Probe "equations"))
  let skolem=graph [(0,root 1),(1,node (T.GSkolem 999 T.Star) (T.Just 0))] [] 2
  oracle "skolem-label-is-not-rank" ("Right "++render skolem) skolem []

  -- Forged raw Patricia trees keep traversal-looking keys, but are rejected
  -- structurally. Values and later alias tree are deliberately bottom.
  let T.IntMap goodTree=IM.fromList [(0,throw (Probe "node0")),(1,throw (Probe "node1"))]
      variants=case goodTree of
        T.IntMapBin _ prefix a b -> [T.IntMapBin 99 prefix a b,T.IntMapBin 2 0 a b,T.IntMapBin 2 prefix b a]
        _ -> error "fixture must have a branch"
  mapM_ (\(i,t)->admission ("raw-tree-reject-"++show i) "local snapshot: noncanonical node map"
        (D.capture (plain 2) (T.Graph (T.IntMap t) (throw (Probe "alias-map")) 2))) (zip [0::Int ..] variants)
  admission "nextId-before-map-demand" "local snapshot: nextId mismatch"
    (D.capture (plain 2) (T.Graph (throw (Probe "node-map")) (throw (Probe "alias-map")) 3))
  admission "bad-alias-tree" "local snapshot: noncanonical alias map"
    (D.capture (plain 2) (T.Graph (IM.singleton 0 (throw (Probe "node")))
      (T.IntMap (T.IntMapBin 0 0 T.IntMapNil T.IntMapNil)) 2))
  admission "key-before-node-demand" "local snapshot: key out of bounds"
    (D.capture (plain 2) (T.Graph (IM.singleton 2 (throw (Probe "node"))) IM.empty 2))
  admission "alias-cycle-reject" "local snapshot: alias chain does not end live"
    (D.capture (plain 3) (T.Graph (IM.singleton 0 (throw (Probe "node"))) (IM.fromList [(1,2),(2,1)]) 3))
  expectProbe "strict-node-ascending-demand" "node0-child" (forceEither
    (D.capture (plain 2) (T.Graph (IM.fromList
      [(0,T.Node (T.GArr (throw (Probe "node0-child")) 1) T.Nothing T.Flexible),
       (1,throw (Probe "node1"))]) IM.empty 2)))
  let original=graph [(0,root 1),(1,intNode),(2,bot)] [] 3
      snapshot=right (D.capture (plain 3) original)
      rank2=right (D.localRank (plain 3) 2)
      (frozenBefore,changed)=right (D.forkReplace rank2 boolNode snapshot)
      changedResult=D.solve [(1,2)] changed
  saveCheck "changed-then-failed-no-publication" ("Left "++show mismatchError++"\n")
    (outcome (G.bindE changedResult (T.Right . D.rebuild)))
  pass "old-and-before-snapshot-isolation" (same original (D.rebuild snapshot) && same original (D.rebuild frozenBefore))
  pass "new-snapshot-really-changed" (same mismatch (D.rebuild changed))
  let outside=right (D.localRank (plain 4) 3)
  admission "bounds-before-replacement" "local snapshot: rank out of bounds"
    (D.forkReplace outside (throw (Probe "replacement")) snapshot)
  let aliasRank=right (D.localRank (plain 6) 2)
  admission "alias-before-replacement" "local snapshot: replacement needs a live slot"
    (D.forkReplace aliasRank (throw (Probe "replacement")) chainSnapshot)

  -- Actual selected fallback projection, no renamed/synthetic Graph solver.
  -- Root 0 has hidden root 1; component 2 and fresh 3/4 produce a stub.
  let global=graph [(0,root 1),(1,bot),(2,bot)] [] 3
      prepared=right (S.prepare global)
      fresh=[(3,bot),(4,bot)]
      current=graph (IM.toList (G.nodes global)++fresh) [] 5
      equations=[(2,3)]
      (local,eqs,originals,(forward,scopes,stubs))=right
        (S.preparedFallbackProjection prepared current 3 fresh equations)
      exactLayout=right (D.layout [i | (i,_)<-originals,i<3] 3 5 (IM.keys stubs))
      localSnapshot=right (D.capture exactLayout local)
      localA=right (G.unify eqs local)
      localC=right (D.solve eqs localSnapshot)
      restored solved=G.bindE
        (G.mapE_ (\stub->G.check (S.matchesNode (G.nodes solved) stub (G.nodeAt local stub) && G.resolve solved stub==stub)
          "local unification changed a hidden scope root") (IM.elems stubs)) $ \_ ->
        G.bindE (G.mapE_ (S.checkPreservedScope current solved forward scopes) originals) $ \_ ->
          S.restoreExpandedProjection prepared current 3 originals forward (fromIntegral (length originals)) solved
      expectedSolver=right (S.unifyPreparedFallback equations prepared current 3 fresh)
      roundtrippedSolver=right (restored (D.rebuild localC))
      directRestore=right (restored localA)
      resultGraph=S.graph roundtrippedSolver
      handRestored=graph [(0,root 1),(1,bot),(2,bot),(4,bot)] [(3,2)] 5
  pass "real-projection-has-stub-and-fresh" (IM.toList stubs==[(0,4)] && map fst originals==[0,2,3,4] && G.nextId local==5)
  pass "real-projection-reconstructed" (same local (D.rebuild localSnapshot))
  pass "real-local-unify-exact" (same localA (D.rebuild localC))
  pass "real-restore-exact" (same (S.graph expectedSolver) resultGraph && same (S.graph directRestore) resultGraph && same handRestored resultGraph)
  pass "old-root-fresh-alias-nextId" (G.nextId resultGraph==5 && G.resolve resultGraph 3==2 && IM.member 4 (G.nodes resultGraph)
    && G.equalNode (G.nodeAt resultGraph 0) (G.nodeAt global 0))
  saveCheck "restored-index-audit" (outcome (S.finish expectedSolver)) (outcome (S.finish roundtrippedSolver))
  assert "restored-index-audit must Right" (case S.finish roundtrippedSolver of T.Right _->True;_->False)
  pass "global-rollback-old-snapshot" (same global (S.graph prepared) && same local (D.rebuild localSnapshot))
  -- A distinct own-publication rejection: raw G.unify can merge the stub,
  -- but neither the real fallback guard nor prototype may publish it.
  let stubEq=[(1,4)]
      stubSolved=right (G.unify stubEq local)
      oldGuard=G.mapE_ (\stub->G.check (S.matchesNode (G.nodes stubSolved) stub (G.nodeAt local stub)
                && G.resolve stubSolved stub==stub) "local unification changed a hidden scope root") (IM.elems stubs)
  saveCheck "stub-authority-guard" "local unification changed a hidden scope root\n"
    (leftMessage oldGuard++"\n")
  saveCheck "stub-prototype-no-publication" "local unification changed a hidden scope root\n"
    (leftMessage (D.solve stubEq localSnapshot)++"\n")
  saveCheck "prepared-projection-invalid-binder" projectionCounterexampleExpected projectionCounterexampleActual
  putStrLn "PASS typed local snapshot representation and old unify oracle only"
