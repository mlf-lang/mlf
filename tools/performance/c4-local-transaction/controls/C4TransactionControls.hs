{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
module C4TransactionControls where
import Prelude
import Control.Monad (forM_,when)
import qualified Control.Exception as E
import Data.List (isInfixOf)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Bootstrap.Constraint as C
import qualified FrozenGraph as FG
import qualified FrozenSolver as FS
import qualified FrozenConstraint as FC
import qualified SessionOracle as O
import qualified SessionGraftFixtures as A
import qualified SessionFieldFixtures as Fields
import qualified PublicControls as P
import qualified C4Fixtures as F
import qualified C4ProjectionOracle as L
import C4TransactionOracle

bind :: T.Either a b -> (b -> T.Either a c) -> T.Either a c
bind (T.Left e) _ = T.Left e
bind (T.Right x) f = f x
isRight :: T.Either a b -> Bool
isRight (T.Right _) = True
isRight _ = False
isNothing :: T.Maybe a -> Bool
isNothing T.Nothing = True
isNothing _ = False
sameEntries :: [(Integer,T.Node)] -> [(Integer,T.Node)] -> Bool
sameEntries = O.sameList (\(k,n) (j,m) -> k==j && O.sameNode n m)
checkGraph :: String -> T.Either B.String T.Graph -> T.Either B.String T.Graph -> IO ()
checkGraph label expected actual = case (expected,actual) of
  (T.Left a,T.Left b) -> O.assert (label++" exact first error bytes") (B.v_eqString a b)
  (T.Right a,T.Right b) -> O.assert (label++" exact physical Graph/alias/counter") (O.sameGraphPhysical a b)
  _ -> errorWithoutStackTrace (label++" full frozen outcome disagreement")

projection :: String -> T.Solver -> T.Solver -> T.Graph -> Integer ->
              [(Integer,T.Node)] -> [(Integer,Integer)] -> IO ()
projection label old expanded current first fresh equations = do
  expected <- O.right (label++" complete frozen projection construction") (L.project equations expanded)
  let canonical = [(FG.resolve current a,FG.resolve current b) | (a,b) <- equations]
      pending = filter (uncurry (/=)) canonical
  (local,localEq,originals,(selected,scopes,stubs)) <- O.right
    (label++" actual candidate projection helper")
    (S.preparedFallbackProjection old current first fresh pending)
  O.assert (label++" exact PHYSICAL compact input graph") (O.sameGraphPhysical (L.localGraph expected) local)
  O.assert (label++" exact ordered compact equations") (L.localEquations expected==localEq)
  O.assert (label++" complete ordered original entries") (sameEntries (L.originalEntries expected) originals)
  O.assert (label++" exact projected scope map")
    (O.sameMapPhysical (O.sameMaybe (==)) (L.projectedScopes expected) scopes)
  O.assert (label++" exact hidden-root stub map") (O.sameMapPhysical (==) (L.hiddenStubs expected) stubs)
  let oldEntries = filter ((<first).fst) (L.originalEntries expected)
      total = toInteger (length originals)
      stop = FG.nextId current
  O.assert (label++" independently valid old-only selection tree") (O.validTree selected)
  O.assert (label++" exact old-only selected contents") (sameEntries oldEntries (O.entries selected))
  O.assert (label++" complete contiguous fresh interval") (map fst fresh==[first..stop-1])
  forM_ (zip [0..] originals) $ \(rank,(identity,_)) -> do
    O.assert (label++" compact rank equals original full selected tree")
      (S.expandedCompact first stop selected identity == FS.rankIdentity identity 0 (L.fullSelected expected))
    inverse <- O.right (label++" checked inverse") (S.expandedOriginal first total selected rank)
    O.assert (label++" exact inverse identity") (inverse==identity)
  forM_ [-1,total,total+1,10^40] $ \position ->
    case (FS.selectIdentity position (L.fullSelected expected),S.expandedOriginal first total selected position) of
      (T.Left a,T.Left b) -> O.assert (label++" out-of-range inverse exact error") (B.v_eqString a b)
      _ -> errorWithoutStackTrace (label++" invalid compact inverse accepted")
  forM_ [minimum (map fst originals)-1,stop,stop+1] $ \identity -> do
    a <- captureInteger (FS.rankIdentity identity 0 (L.fullSelected expected))
    b <- captureInteger (S.expandedCompact first stop selected identity)
    O.assert (label++" missing/out-of-range compact exact panic")
      (a==b && case a of Left _->True;_->False)
  checkGraph (label++" full unchanged local validator/unifier outcome")
    (FG.unify (L.localEquations expected) (L.localGraph expected)) (G.unify localEq local)
  when (label=="mutable-old-bottom/fresh-survivor") $ do
    O.assert "hand-authored compact local Graph including hidden stub 9"
      (O.sameGraphPhysical L.baseLocalLiteral (L.localGraph expected))
    O.assert "hand-authored compact equation" (L.localEquations expected==[(5,2)])

fixture :: F.Fixture -> IO ()
fixture (F.Fixture label input source target wantedAdmitted wantedSuccess topology) = do
  old <- O.right (label++" frozen prepare") (FS.prepare input)
  new <- O.right (label++" current prepare") (S.prepare input)
  O.checkSolver (label++" public prepare remains physical") True old new
  O.assert (label++" reaches original expansion after groundGraft") (isNothing (FS.groundGraft source target old))
  O.assert (label++" reaches original expansion after groundInstance") (not (FS.groundInstance (FS.graph old) source target))
  (root,copies,frontier,expanded) <- O.right (label++" frozen full expansion") (FS.expanded source target old)
  (newRoot,newCopies,newFrontier,current) <- O.right (label++" new graph-only expansion")
    (S.expandedGraphPrepared source target new)
  O.assert (label++" full expansion Graph/copies/frontier physical")
    (root==newRoot && O.sameMapPhysical (==) copies newCopies && frontier==newFrontier &&
     O.sameGraphPhysical (FS.graph expanded) current)
  let first=FG.nextId (FS.graph old)
      resolved=FG.resolve current target
      fresh=FS.allocatedNodes first (FG.nextId current) (FG.nodes current)
      images=IM.fromList [(proxy,original) | (original,proxy) <- frontier]
      equations=frontier++[(root,target)]
      actualAdmitted=S.fallbackStageEligible first root resolved frontier current &&
        S.fallbackPrefixRejected current first images [(root,resolved)]
  O.assert (label++" fixed independently authored admission") (actualAdmitted==wantedAdmitted)
  when wantedAdmitted $ do
    O.assert (label++" entire complete frozen graft chain Nothing")
      (isNothing (FS.expansionBottomGraft first target root frontier expanded))
    O.assert (label++" complete frozen congruent walk itself Nothing")
      (isNothing (FS.congruentExpansionMap current first images [(root,resolved)]))
    projection label new expanded current first fresh equations
  let expected=FS.instantiateClosed source target old
      actual=S.instantiateClosedPrepared source target new
  O.assert (label++" authored full success/rejection") (isRight expected==wantedSuccess)
  checkTransactionalOutcome (label++" full prepared operation") expected actual
  -- Old public APIs remain the stricter PHYSICAL oracle, not the new relation.
  O.checkOutcome (label++" unchanged public instantiate physical") True expected (S.instantiateClosed source target new)
  checkTransactionalOutcome (label++" same immutable pre-state retry") expected (S.instantiateClosedPrepared source target new)
  O.checkSolver (label++" failed or successful attempt did not mutate input") True old new
  checkTransactionalOutcome (label++" subsequent reflexive operation from original input")
    (FS.solverUnify [(target,target)] old) (S.solverUnify [(target,target)] new)
  case (expected,actual) of
    (T.Right a,T.Right b) -> do
      case topology of
        Nothing -> pure ()
        Just literal -> O.assert (label++" independent ALL-node/alias/flag/binder/counter literal")
          (O.sameGraphLogical literal (FS.graph a))
      -- Reuse the actual result, not a freshly prepared copy: exercises closure
      -- of the new index representation and fresh-ID lifecycle across calls.
      checkTransactionalOutcome (label++" repeated instance on committed result")
        (FS.instantiateClosed source target a) (S.instantiateClosedPrepared source target b)
      checkTransactionalOutcome (label++" ordinary equality after committed result")
        (FS.solverUnify [(target,target)] a) (S.solverUnify [(target,target)] b)
      when (label=="unchanged-surviving-grandchild") $ do
        O.assert "fresh 16 survived UNCHANGED relative to expanded Graph"
          (O.sameNode (FG.nodeAt current 16) (FG.nodeAt (FS.graph a) 16))
        let T.Solver _ parents bindings _=b
        O.assert "unchanged fresh first structural edge publication" (O.setEntries (IM.get 16 parents)==[15])
        O.assert "unchanged fresh first binding edge publication" (O.setEntries (IM.get 15 bindings)==[16])
    (T.Left e,_) -> putStrLn ("FROZEN ERROR "++label++": "++B.unpack e)
    _ -> errorWithoutStackTrace "outcome discrepancy already checked"
  drivers label input [] [T.Instantiate (T.Edge source target)]

checkFlush :: String -> T.Graph -> [(Integer,Integer)] -> [T.SolveStep] -> IO ()
checkFlush label g es steps =
  case (FC.runGenerate FC.flushGeneration (FC.Generation g (reverse es) (reverse steps)),
        C.runGenerate C.flushGeneration (C.Generation g (reverse es) (reverse steps))) of
    (T.Left a,T.Left b) -> O.assert (label++" exact flush error") (B.v_eqString a b)
    (T.Right ((),FC.Generation old oldE oldS),T.Right ((),C.Generation new newE newS)) -> do
      O.assert (label++" exact physical flush Graph") (O.sameGraphPhysical old new)
      O.assert (label++" both pending work lists drained") (null oldE && null oldS && null newE && null newS)
      _ <- O.right (label++" frozen flush validation") (FG.validateGraph new)
      pure ()
    _ -> errorWithoutStackTrace (label++" flush outcome mismatch")

drivers :: String -> T.Graph -> [(Integer,Integer)] -> [T.SolveStep] -> IO ()
drivers label g es steps = do
  let constraints=T.Constraints g (errorWithoutStackTrace "unused typed skeleton") es steps
  checkTransactionalOutcome (label++" actual solvePrepared driver") (FC.solvePrepared constraints) (C.solvePrepared constraints)
  checkFlush (label++" actual flushGeneration driver") g es steps

traceOne :: (String,T.Graph,[(Integer,Integer)],[T.SolveStep]) -> IO ()
traceOne (label,g,es,steps) = do
  let old=bind (FS.prepare g) (FS.solverUnify es)
      new=bind (S.prepare g) (S.solverUnify es)
  O.checkOutcome (label++" initial unmodified physical state") True old new
  walk 0 old new steps
  drivers label g es steps
 where
  walk :: Int -> T.Either B.String T.Solver -> T.Either B.String T.Solver -> [T.SolveStep] -> IO ()
  walk _ _ _ []=pure ()
  walk i (T.Right a) (T.Right b) (step:rest)=do
    let expected=FC.evaluateStep a step;actual=C.evaluatePreparedStep b step
    checkTransactionalOutcome (label++" step "++show i) expected actual
    checkTransactionalOutcome (label++" retry "++show i) expected (C.evaluatePreparedStep b step)
    checkTransactional (label++" retained previous state "++show i) a b
    walk (i+1) expected actual rest
  walk _ _ _ _=pure ()

admissionControls :: IO ()
admissionControls = do
  let missing=FG.setNode 3 (F.node (T.GArr 4 999999) 2) F.base
      binder=FG.setNode 8 (F.node (T.GArr 9 10) 999999) F.base
      overlap=T.Graph (FG.nodes F.base) IM.empty 1
      escape=A.replace 9 (F.node T.GBot 2) F.base
      liveAlias=T.Graph (FG.nodes F.base) (IM.singleton 8 9) 11
  forM_ [("missing-child",missing),("missing-binder",binder),("counter-overlap",overlap),
         ("scope-escape",escape),("live-alias",liveAlias)] $ \(label,g) -> do
    O.assert (label++" original prepare rejects") (not (isRight (FS.prepare g)))
    O.checkOutcome (label++" public prepare unchanged") True (FS.prepare g) (S.prepare g)
    drivers (label++" rejects before trusted prepared fold") g
      (errorWithoutStackTrace "invalid-driver equations must stay lazy")
      (errorWithoutStackTrace "invalid-driver steps must stay lazy")
  old <- O.right "boundary original" (FS.prepare F.base)
  new <- O.right "boundary candidate" (S.prepare F.base)
  forM_ [(999,998,"missing instance source"),(1,8,"instance source must be a gen node"),
         (2,999,"missing instance target"),(2,0,"instance target has no binder")] $ \(a,b,message) -> do
    let expected=FS.instantiateClosed a b old
    O.assert "literal independent source/target first error"
      (case expected of T.Left e->B.unpack e==message;_->False)
    checkTransactionalOutcome message expected (S.instantiateClosedPrepared a b new)
  checkTransactionalOutcome "valid operation after all rejected descriptors"
    (FS.instantiateClosed 2 8 old) (S.instantiateClosedPrepared 2 8 new)
  O.checkSolver "rejected boundary operations preserve complete input" True old new

mixedProjectControl :: IO ()
mixedProjectControl = do
  let image n=if n==0 then 0 else n+10
      additional=IM.delete 0 (FG.nodes (A.rename image F.base))
      mixed=T.Graph (IM.union additional (FG.nodes Fields.base)) IM.empty 21
      project=T.ProjectCase [(2,4)]
      instanceStep=T.Instantiate (T.Edge 12 18)
  old0 <- O.right "mixed frozen prepare" (FS.prepare mixed)
  new0 <- O.right "mixed current prepare" (S.prepare mixed)
  let expected=FC.evaluateStep old0 project;actual=C.evaluatePreparedStep new0 project
  O.checkOutcome "unmodified ProjectCase physical" True expected actual
  old1 <- O.right "authored materializing ProjectCase succeeds" expected
  new1 <- O.right "current materializing ProjectCase succeeds" actual
  O.assert "descriptor replay rejects independently" (not (isRight (FC.evaluateStep old1 project)))
  checkTransactionalOutcome "ProjectCase rejection before retry"
    (FC.evaluateStep old1 project) (C.evaluatePreparedStep new1 project)
  checkTransactionalOutcome "new fallback after ProjectCase and failed replay"
    (FC.evaluateStep old1 instanceStep) (C.evaluatePreparedStep new1 instanceStep)
  O.checkSolver "rejected replay retains complete source" True old1 new1
  drivers "mixed ProjectCase then prepared fallback" mixed [] [project,instanceStep]

node :: T.GTag -> Integer -> T.Flag -> T.Node
node = A.node

captureInteger :: Integer -> IO (Either String Integer)
captureInteger value=do
  result <- E.try (E.evaluate value) :: IO (Either E.SomeException Integer)
  pure (case result of Left e->Left (E.displayException e);Right n->Right n)
captureUnit :: () -> IO (Either String ())
captureUnit value=do
  result <- E.try (E.evaluate value) :: IO (Either E.SomeException ())
  pure (case result of Left e->Left (E.displayException e);Right n->Right n)
metadata :: T.Solver -> Integer
metadata (T.Solver (T.Graph ns aliases next) parents bindings _) =
  next + sum (map fst (O.mapEntries ns)) + sum (map fst (O.mapEntries aliases)) +
  sum [sum members | (_,members) <- O.indexEntries parents++O.indexEntries bindings]
observe :: T.Either B.String T.Solver -> Integer
observe (T.Left message)=errorWithoutStackTrace ("unexpected Left: "++B.unpack message)
observe (T.Right value)=metadata value
observeExpanded :: T.Either B.String (Integer,T.IntMap Integer,[(Integer,Integer)],T.Solver) -> Integer
observeExpanded (T.Left e)=errorWithoutStackTrace ("unexpected Left: "++B.unpack e)
observeExpanded (T.Right (_,_,_,s))=metadata s

partialControls :: IO ()
partialControls = do
  old <- O.right "partial original prepare" (FS.prepare P.shaped)
  let compareThrow label marker a b=do
        x<-captureInteger a;y<-captureInteger b
        O.assert (label++" exact old public exception") (x==y)
        O.assert (label++" first marker") (case x of Left text->marker `isInfixOf` text;_->False)
  compareThrow "old instantiateClosed partial source" "public-source"
    (observe (FS.instantiateClosed (errorWithoutStackTrace "public-source") 8 old))
    (observe (S.instantiateClosed (errorWithoutStackTrace "public-source") 8 old))
  compareThrow "old instantiateClosed partial target" "public-target"
    (observe (FS.instantiateClosed 2 (errorWithoutStackTrace "public-target") old))
    (observe (S.instantiateClosed 2 (errorWithoutStackTrace "public-target") old))
  let forged=T.Solver (FS.graph old) (errorWithoutStackTrace "public-parent-index")
        (FS.bindingChildren old) (FS.scopeIndex old)
  compareThrow "old expanded partial index" "public-parent-index"
    (observeExpanded (FS.expanded 2 8 forged)) (observeExpanded (S.expanded 2 8 forged))
  -- These partial payloads are deliberately unrelated to the live operation.
  -- Full equality/serialization would itself force them, so these are limited
  -- demand observations, separate from the full total-graph oracle corpus.
  let unusedName=A.replace 20 (node (T.GGen 21) 0 T.Flexible)
        (A.replace 21 (node (T.GCon (errorWithoutStackTrace "unused-string") []) 20 T.Rigid) F.base)
      unusedKind=A.replace 20 (node (T.GGen 21) 0 T.Flexible)
        (A.replace 21 (node (T.GTyCon "Unused" (T.KArrow
          (errorWithoutStackTrace "unused-kind-domain")
          (errorWithoutStackTrace "unused-kind-result"))) 20 T.Rigid) F.base)
      unusedAlias=T.Graph (FG.nodes F.base) (IM.singleton 30 (errorWithoutStackTrace "unused-alias-value")) 40
  forM_ [("unused-string",unusedName),("unused-kind",unusedKind),("unused-alias",unusedAlias)] $ \(label,g)->do
    expected<-captureInteger (observe (bind (FS.prepare g) (FS.instantiateClosed 2 8)))
    actual<-captureInteger (observe (bind (S.prepare g) (S.instantiateClosedPrepared 2 8)))
    O.assert (label++" original premise terminates without payload demand") (case expected of Right _->True;_->False)
    O.assert (label++" prepared observation exact") (expected==actual)
  putStrLn "PASS C4 three old-public partial probes and three prepared unused-payload probes"

forceControls :: IO ()
forceControls = do
  let pass label value=do
        result<-captureUnit value
        O.assert label (result==Right ())
      fails label marker value=do
        result<-captureUnit value
        O.assert label (case result of Left text->marker `isInfixOf` text;_->False)
  pass "force ignores unused name/kind/flag" (S.forceExpansionEdges
    [(1,T.Node (T.GTyCon (errorWithoutStackTrace "force-name") (errorWithoutStackTrace "force-kind"))
       T.Nothing (errorWithoutStackTrace "force-flag"))])
  pass "force empty list" (S.forceExpansionEdges [])
  fails "force child before binder" "child-first" (S.forceExpansionEdges
    [(1,T.Node (T.GCon "X" [errorWithoutStackTrace "child-first"])
       (T.Just (errorWithoutStackTrace "binder-second")) T.Flexible)])
  fails "force complete child spine" "child-tail" (S.forceExpansionEdges
    [(1,T.Node (T.GCon "X" (2:errorWithoutStackTrace "child-tail")) T.Nothing T.Flexible)])
  fails "force binder integer" "binder-id" (S.forceExpansionEdges
    [(1,T.Node T.GBot (T.Just (errorWithoutStackTrace "binder-id")) T.Flexible)])
  putStrLn "PASS C4 five force-edge demand controls (not a proof for forged Solver states)"

oracleBoundaryControls :: IO ()
oracleBoundaryControls = do
  let input=A.replace 20 (node (T.GGen 21) 0 T.Flexible)
        (A.replace 21 (node (T.GCon "Unit" []) 20 T.Rigid) F.base)
  original <- O.right "oracle audit prepare" (FS.prepare input)
  let T.Solver graph parents bindings scopes=original
      leaf k=T.MapNode 1 k () T.MapEmpty T.MapEmpty
      treeA=T.MapNode 4 2 () (leaf 1) (T.MapNode 2 7 () T.MapEmpty (leaf 20))
      treeB=T.MapNode 4 7 () (T.MapNode 2 2 () (leaf 1) T.MapEmpty) (leaf 20)
      wrap tree=T.Solver graph parents (IM.insert 0 (T.IntSet tree) bindings) scopes
      a=wrap treeA;b=wrap treeB
      wrongSize=wrap (T.MapNode 99 2 () (leaf 1) (T.MapNode 2 7 () T.MapEmpty (leaf 20)))
      wrongMembers=wrap (T.MapNode 4 2 () (leaf 1) (T.MapNode 2 7 () T.MapEmpty (leaf 21)))
      T.Graph ns aliases counter=graph
  O.assert "distinct valid bucket shapes really differ" (not (O.sameSolverPhysical a b))
  checkTransactional "oracle allows only valid edge-equivalent shape" a b
  O.assert "logical comparison alone does not validate cached sizes" (sameTransactional a wrongSize)
  O.assert "independent audit rejects same-entry wrong cached size" (not (O.validSolverMaps wrongSize))
  O.assert "changed reverse member cannot be hidden" (not (sameTransactional a wrongMembers))
  O.assert "changed counter cannot be hidden" (not (sameTransactional a
    (T.Solver (T.Graph ns aliases (counter+1)) parents bindings scopes)))
  O.assert "changed alias cannot be hidden" (not (sameTransactional a
    (T.Solver (T.Graph ns (IM.insert 30 8 aliases) counter) parents bindings scopes)))
  O.assert "changed scope tree cannot be hidden" (not (sameTransactional a
    (T.Solver graph parents bindings (T.ScopeIndex IM.empty []))))
  O.assert "changed graph Node cannot be hidden" (not (sameTransactional a
    (T.Solver (A.replace 8 (node (T.GArr 9 10) 7 T.Rigid) graph) parents bindings scopes)))
  let gen=T.Node (T.GGen 1) T.Nothing T.Flexible
      bot=F.node T.GBot 0
      graphA=T.Graph (T.IntMap (T.MapNode 2 0 gen T.MapEmpty
        (T.MapNode 1 1 bot T.MapEmpty T.MapEmpty))) IM.empty 2
      graphB=T.Graph (T.IntMap (T.MapNode 2 1 bot
        (T.MapNode 1 0 gen T.MapEmpty T.MapEmpty) T.MapEmpty)) IM.empty 2
  ga <- O.right "valid alternate Graph shape A" (FS.prepare graphA)
  gb <- O.right "valid alternate Graph shape B" (FS.prepare graphB)
  checkOne "alternate Graph shape A complete validity" ga
  checkOne "alternate Graph shape B complete validity" gb
  O.assert "same ordered Graph entries but changed PHYSICAL shape is rejected"
    (O.sameGraphLogical (FS.graph ga) (FS.graph gb) && not (sameTransactional ga gb))
  putStrLn "PASS C4 comparator nonvacuity: only valid index-shape variation allowed; Graph shape/member/size/node/alias/counter/scope changes rejected"

prefixDemandControls :: IO ()
prefixDemandControls = do
  let graph entries=T.Graph (IM.fromList [(i,T.Node t T.Nothing T.Flexible) | (i,t)<-entries]) IM.empty 20
      barrier a b=graph [(0,T.GArr 1 2),(1,b),(2,T.GBot),
        (10,T.GArr 11 12),(11,a),(12,T.GArr 13 14)]
      cases=[("unknown-name",barrier (T.GCon (errorWithoutStackTrace "unknown-name") []) (T.GCon "Int" [])),
             ("unknown-kind",barrier (T.GSkolem 17 (errorWithoutStackTrace "unknown-kind")) (T.GSkolem 17 T.Star))]
  forM_ cases $ \(marker,g) -> do
    O.assert (marker++" must stop False before later mutation")
      (not (S.fallbackPrefixRejected g 10 IM.empty [(10,0)]))
    old <- captureUnit (case FS.congruentExpansionMap g 10 IM.empty [(10,0)] of
      T.Nothing->();T.Just _->())
    O.assert (marker++" old full congruent traversal actually demands payload first")
      (old==Left marker)
  let forbidden=errorWithoutStackTrace "seeded prefix must not inspect Graph"
  O.assert "seen agreeing image skips unknown Graph"
    (not (S.fallbackPrefixRejected forbidden 10 (IM.singleton 10 0) [(10,0)]))
  O.assert "seen conflicting image rejects before unknown Graph"
    (S.fallbackPrefixRejected forbidden 10 (IM.singleton 10 0) [(10,1)])
  O.assert "complete frozen conflict agrees without Graph demand"
    (isNothing (FS.congruentExpansionMap forbidden 10 (IM.singleton 10 0) [(10,1)]))
  let nameGraph=A.replace 4 (F.node (T.GCon (errorWithoutStackTrace "prepared-prefix-name") []) 3) F.payloadBarrier
      survivorGraph=A.replace 11 (F.node (T.GCon (errorWithoutStackTrace "survivor-equality-name") []) 6) F.unchangedSurvivor
  forM_ [("prepared-prefix-name",nameGraph),("survivor-equality-name",survivorGraph)] $ \(marker,g) -> do
    expected<-captureInteger (observe (bind (FS.prepare g) (FS.instantiateClosed 2 8)))
    actual<-captureInteger (observe (bind (S.prepare g) (S.instantiateClosedPrepared 2 8)))
    O.assert (marker++" authored complete original payload demand") (expected==Left marker)
    O.assert (marker++" candidate preserves exact first payload demand") (actual==expected)
  putStrLn "PASS C4 unknown-prefix/seen-image and full prepared prefix/unchanged-survivor payload demands"

fallbackBoundaryControls :: IO ()
fallbackBoundaryControls = do
  old <- O.right "fallback helper initial" (FS.prepare F.base)
  (root,_,frontier,expanded) <- O.right "fallback helper full old expansion" (FS.expanded 2 8 old)
  let current=FS.graph expanded
      first=FG.nextId (FS.graph old)
      fresh=FS.allocatedNodes first (FG.nextId current) (FG.nodes current)
      equations=frontier++[(root,8)]
  forM_ [[],[(root,root)],[(999999,root)],[(root,999999)],equations] $ \es ->
    checkTransactionalOutcome "canonical/filter/missing equation first error"
      (FS.solverUnify es expanded) (S.unifyPreparedFallback es old current first fresh)
  expected <- O.right "restoration old projection" (L.project equations expanded)
  (local,localEq,originals,(selected,_,_)) <- O.right "restoration actual projection"
    (S.preparedFallbackProjection old current first fresh equations)
  solved <- O.right "restoration old local solver"
    (FG.unify (L.localEquations expected) (L.localGraph expected))
  let count=toInteger (length originals)
      expectedCount=toInteger (length (L.originalEntries expected))
      restore a=FS.restoreProjection expanded (L.originalEntries expected) (L.fullSelected expected) expectedCount a
      newRestore a=S.restoreExpandedProjection old current first originals selected count a
      escaped i=T.Graph (FG.nodes solved) (IM.singleton i 0) (FG.nextId solved)
  checkTransactionalOutcome "direct complete Graph history restoration" (restore solved) (newRestore solved)
  forM_ [-1,expectedCount,expectedCount+1] $ \i -> do
    O.assert "independent inverse escape rejected" (not (isRight (restore (escaped i))))
    checkTransactionalOutcome "restore inverse escaped alias exact rejection"
      (restore (escaped i)) (newRestore (escaped i))
  putStrLn "PASS C4 five canonical/filter/error branches and four frozen direct restoration outcomes"

-- Deliberately partial direct-helper test. A total local solve is completed
-- BEFORE replacing only the original fresh payload. This isolates restoration
-- demand; unlike the whole-route marker, it cannot be attributed to G.unify.
-- This is not claimed to be a pair of states produced by a real unification.
restorePayloadControl :: IO ()
restorePayloadControl = do
  let input=A.replace 11 (F.node (T.GCon "Unit" []) 6) F.unchangedSurvivor
  old <- O.right "restore payload total initial" (FS.prepare input)
  (root,_,frontier,expanded) <- O.right "restore payload total expansion" (FS.expanded 2 8 old)
  let current=FS.graph expanded
      first=FG.nextId (FS.graph old)
      fresh=FS.allocatedNodes first (FG.nextId current) (FG.nodes current)
      equations=frontier++[(root,8)]
  reference <- O.right "restore payload complete projection" (L.project equations expanded)
  (local,es,originals,(selected,_,_)) <- O.right "restore payload candidate projection"
    (S.preparedFallbackProjection old current first fresh equations)
  solved <- O.right "restore payload complete TOTAL local solve"
    (FG.unify (L.localEquations reference) (L.localGraph reference))
  O.assert "force total solved graph before injecting partial payload" (O.sameGraphPhysical solved solved)
  let marker="restore-only-original-name"
      partial=F.node (T.GCon (errorWithoutStackTrace marker) []) 15
      changed=A.replace 16 partial current
      originalsPartial=[(i,if i==16 then partial else n) | (i,n)<-originals]
      expectedOriginalsPartial=[(i,if i==16 then partial else n) | (i,n)<-L.originalEntries reference]
      count=toInteger (length originals)
      expectedCount=toInteger (length (L.originalEntries reference))
      expected=FS.restoreProjection (FS.withGraph changed expanded) expectedOriginalsPartial
        (L.fullSelected reference) expectedCount solved
      actual=S.restoreExpandedProjection old changed first originalsPartial selected count solved
  a <- captureInteger (observe expected)
  b <- captureInteger (observe actual)
  O.assert "frozen restoration alone demands original fresh Name" (a==Left marker)
  O.assert "candidate restoration preserves exact original fresh Name demand" (b==a)
  putStrLn "PASS C4 isolated complete frozen restoreProjection original-fresh payload demand"

main :: IO ()
main = do
  O.assert "fixed independently authored initial fixture count" (length F.fixtures==12)
  O.assert "fixed added mechanism fixtures" (length F.additionalFixtures==6)
  O.assert "fixed sparse/huge-negative layouts" (length F.renamedFixtures==10)
  let fixed=F.fixtures++F.additionalFixtures++F.renamedFixtures
      count predicate=length (filter predicate fixed)
  O.assert "fixed success/rejection categories"
    (count (\(F.Fixture _ _ _ _ _ success _)->success)==19)
  O.assert "fixed admitted/nonadmitted categories"
    (count (\(F.Fixture _ _ _ _ admitted _ _)->admitted)==23)
  mapM_ fixture fixed
  putStrLn "PASS C4 28 authored fixtures: 19 frozen successes, 9 rejections; 23 exact compact projections; physical Graph and full index audits"
  O.assert "all fixed original driver traces retained" (length P.traceCases==28)
  mapM_ traceOne P.traceCases
  putStrLn "PASS C4 28 original traces with prepared retries and both complete frozen drivers"
  admissionControls
  mixedProjectControl
  putStrLn "PASS C4 five invalid-driver admissions, four exact boundary errors, and materializing ProjectCase/rejected replay/fallback sequence"
  fallbackBoundaryControls
  restorePayloadControl
  partialControls
  forceControls
  prefixDemandControls
  oracleBoundaryControls
  putStrLn "{\"complete\":true,\"authored_fixtures\":18,\"renamed_fixtures\":10,\"fixture_successes\":19,\"fixture_rejections\":9,\"admitted_fixtures\":23,\"nonadmitted_fixtures\":5,\"exact_compact_projections\":23,\"literal_full_graphs\":2,\"literal_compact_graphs\":1,\"unchanged_fresh_survivor_assertions\":3,\"original_traces\":28,\"fixture_and_trace_solve_drivers\":56,\"fixture_and_trace_flush_drivers\":56,\"invalid_driver_graphs\":5,\"source_target_error_boundaries\":4,\"mixed_project_sequences\":1,\"fallback_equation_branches\":5,\"direct_restore_outcomes\":4,\"isolated_restore_payload_probe\":1,\"public_partial_probes\":3,\"prepared_unused_payload_probes\":3,\"force_edge_probes\":5,\"prefix_payload_barriers\":2,\"seen_prefix_probes\":2,\"prepared_original_payload_demand_probes\":2,\"oracle_boundary_checks\":9,\"candidate_chooses_expected\":false,\"old_public_physical_oracle_weakened\":false,\"arbitrary_forged_prepared_equivalence_claimed\":false}"

