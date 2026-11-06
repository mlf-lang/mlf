{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
module SessionTests where
import Prelude
import Control.Monad (forM_)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Bootstrap.Constraint as C
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Graph.IndexStore as K
import qualified FrozenSolver as FS
import qualified FrozenConstraint as FC
import qualified SessionUnderTest as N
import qualified SessionGraftFixtures as A
import qualified SessionFieldFixtures as F
import SessionOracle

constraints :: T.Graph -> [(Integer,Integer)] -> [T.SolveStep] -> T.Constraints
constraints g es ss=T.Constraints g(errorWithoutStackTrace "unused typed skeleton")es ss
instanceStep :: Integer -> Integer -> T.SolveStep
instanceStep a b=T.Instantiate(T.Edge a b)
step :: N.Session s -> T.SolveStep -> P.ST s(T.Either B.String(N.Session s))
step s action=case action of
 T.Instantiate(T.Edge a b)->N.instantiateClosed a b s
 T.ProjectCase fields->N.projectCaseFields fields s
-- Every snapshot is observed only after the complete region has finished.
-- Test-only freezes are not part of production timing or the proposed algorithm.
data Trace = Trace [T.Solver] (T.Either B.String T.Solver)
tracePrivate :: T.Solver -> [T.SolveStep] -> Trace
tracePrivate old actions=P.runST $ do
 s<-N.openSession old
 first<-N.freezeSession s
 go s [first] actions
 where
  go s saved []=do
   lastState<-N.freezeSession s
   pure(Trace(reverse saved)(T.Right lastState))
  go s saved(action:rest)=do
   answer<-step s action
   case answer of
    T.Left message->pure(Trace(reverse saved)(T.Left message))
    T.Right next->do
     captured<-N.freezeSession next
     go next(captured:saved)rest
compareTrace :: String -> T.Solver -> [T.SolveStep] -> Trace -> IO ()
compareTrace label old actions(Trace snapshots result)=case snapshots of
 []->errorWithoutStackTrace "missing initial detached snapshot"
 initial:rest->do
  checkSolver(label++"/delayed P0")False old initial
  walk old actions rest
 where
  walk current [] saved=do
   assert(label++"/exact snapshot count")(null saved)
   checkOutcome(label++"/terminal")False(T.Right current)result
  walk current(action:pending)saved=case FC.evaluateStep current action of
   T.Left message->do
    assert(label++"/no snapshot after rejection")(null saved)
    checkOutcome(label++"/same first rejection")False(T.Left message)result
   T.Right next->case saved of
    []->errorWithoutStackTrace(label++"/missing successful transition snapshot")
    captured:rest->checkSolver(label++"/delayed transition")False next captured >> walk next pending rest
runCase :: (String,T.Graph,[(Integer,Integer)],[T.SolveStep]) -> IO ()
runCase(label,g,es,ss)=do
 let input=constraints g es ss; expected=FC.solvePrepared input
 checkOutcome(label++"/unchanged public route")True expected(C.solvePrepared input)
 checkOutcome(label++"/private closed final route")False expected(N.solvePrepared input)
 case FS.prepare g of
  T.Left _->pure()
  T.Right prepared->case FS.solverUnify es prepared of
   T.Left _->pure()
   T.Right initial->compareTrace label initial ss(tracePrivate initial ss)

bottom :: T.Graph
bottom=T.Graph(IM.fromList
 [(0,T.Node(T.GGen 1)T.Nothing T.Flexible),
  (1,T.Node(T.GCon "Unit" [])(T.Just 0)T.Rigid),
  (2,T.Node(T.GGen 3)(T.Just 0)T.Flexible),
  (3,T.Node T.GBot(T.Just 2)T.Flexible),
  (4,T.Node(T.GGen 5)(T.Just 0)T.Flexible),
  (5,T.Node T.GBot(T.Just 4)T.Flexible)])IM.empty 6
bottomExpected :: T.Graph
bottomExpected=T.Graph(G.nodes bottom)(IM.singleton 6 5)7
shaped :: T.Graph
shaped=A.replace 8(A.node(T.GArr 9 10)7 T.Flexible)
 (A.replace 9(A.node T.GBot 8 T.Flexible)
 (A.replace 10(A.node(T.GArr 9 11)8 T.Rigid)
 (A.replace 11(A.node(T.GCon "Int" [])10 T.Rigid)A.poly)))
ground :: T.Graph
ground=A.replace 3(A.node(T.GCon "Int" [])2 T.Rigid)(A.without[4,5,6]A.poly)
groundAlready :: T.Graph
groundAlready=A.replace 8(A.node(T.GCon "Int" [])7 T.Flexible)ground
fieldCases :: [(String,T.Graph,[(Integer,Integer)],[T.SolveStep])]
fieldCases=
 [("selected field",F.base,[],[T.ProjectCase[(2,4)]]),
  ("empty field selection",F.base,[],[T.ProjectCase[]]),
  ("ineligible field shared",G.setNode 2(T.Node(T.GArr 3 5)(T.Just 0)T.Flexible)F.base,[],[T.ProjectCase[(2,4)]]),
  ("later descriptor error",F.base,[],[T.ProjectCase[(2,4),(2,999)]]),
  ("repeated descriptor error",F.base,[],[T.ProjectCase[(2,4),(2,4)]]),
  ("replayed field error",F.base,[],[T.ProjectCase[(2,4)],T.ProjectCase[(2,4)]])]
cases :: [(String,T.Graph,[(Integer,Integer)],[T.SolveStep])]
cases=[(label,g,[],[instanceStep 2 8])|(label,_,g)<-A.cases]++
 [("ground graft",ground,[],[instanceStep 2 8]),
  ("ground instance no allocation",groundAlready,[],[instanceStep 2 8]),
  ("congruent retained target",shaped,[],[instanceStep 2 8]),
  ("congruent guard fallback",A.replace 9(A.node T.GBot 7 T.Flexible)shaped,[],[instanceStep 2 8])]++
 fieldCases++
 [("initial reflexive",A.poly,[(4,4)],[instanceStep 2 8]),
  ("initial merge",A.poly,[(4,8)],[instanceStep 2 8]),
  ("initial missing",A.poly,[(999,4)],[instanceStep 2 8]),
  ("ordered missing",A.poly,[(999,4),(998,4)],[instanceStep 2 8])]

literalControls :: IO ()
literalControls=do
 initial<-right "literal prepare"(FS.prepare bottom)
 let answer=P.runST $ do
       s<-N.openSession initial
       expansion<-N.expanded 2 5 s
       case expansion of
        T.Left e->pure(T.Left e)
        T.Right(root,copies,frontier,p1)->do
         snapshot<-N.freezeSession p1
         graft<-N.freshBottomGraft 6 5 root frontier p1
         case graft of
          T.Nothing->pure(T.Left "literal graft unexpectedly declined")
          T.Just p2->do
           final<-N.freezeSession p2
           pure(T.Right(root,copies,frontier,snapshot,final))
 (root,copies,frontier,p1,p2)<-right "literal expansion and graft"answer
 assert "literal root/copies/frontier/full fresh budget"(root==6&&mapEntries copies==[(3,6)]&&null frontier&&G.nextId(S.graph p1)==7)
 assert "literal root alias and original graph"(sameGraphLogical(S.graph p2)bottomExpected)
 old<-right "literal frozen instantiate"(FS.instantiateClosed 2 5 initial)
 checkSolver "literal complete final state"False old p2
 (_,_,_,oldP1)<-right "literal frozen expansion"(FS.expanded 2 5 initial)
 checkSolver "literal delayed P1 survives graft"False oldP1 p1
 fieldInitial<-right "literal field prepare"(FS.prepare F.base)
 let Trace _ projected=tracePrivate fieldInitial[T.ProjectCase[(2,4)]]
 fieldFinal<-right "literal selected field"projected
 assert "literal field full graph/two fresh IDs"(sameGraphLogical(S.graph fieldFinal)F.expected&&G.nextId(S.graph fieldFinal)==8)
 putStrLn "PASS session handwritten copies aliases field graph and delayed P1"

failedProbes :: IO ()
failedProbes=do
 initial<-right "P0 prepare"(FS.prepare A.poly)
 let (declined,after)=P.runST $ do
       s<-N.openSession initial
       probe<-N.groundGraft 2 8 s
       snap<-N.freezeSession s
       pure ((case probe of {T.Nothing->True;T.Just _->False}),snap)
 assert "ground probe prescribed Nothing"declined
 checkSolver "failed ground probe keeps exact P0"False initial after
 let bad=A.replace 8(A.node(T.GBotK(T.KArrow T.Star T.Star))7 T.Flexible)A.poly
 before<-right "P1 prepare"(FS.prepare bad)
 (root,copies,frontier,expectedP1)<-right "P1 frozen expand"(FS.expanded 2 8 before)
 assert "all four prescribed P1 probes decline"
  (isNothing(FS.freshBottomGraft 9 8 root frontier expectedP1)&&
   isNothing(FS.frontierIdentityGraft 9 8 root frontier expectedP1)&&
   isNothing(FS.frontierBottomGraft 9 8 root frontier expectedP1)&&
   isNothing(FS.congruentExpansionGraft 9 8 root frontier expectedP1))
 let answer=P.runST $ do
       s<-N.openSession before
       expansion<-N.expanded 2 8 s
       case expansion of
        T.Left e->pure(T.Left e)
        T.Right(r,cs,fs,p1)->do
         saved<-N.freezeSession p1
         a<-N.freshBottomGraft 9 8 r fs p1
         b<-N.frontierIdentityGraft 9 8 r fs p1
         c<-N.frontierBottomGraft 9 8 r fs p1
         d<-N.congruentExpansionGraft 9 8 r fs p1
         unchanged<-N.freezeSession p1
         fallback<-N.solverUnify(fs++[(r,8)])p1
         result<-case fallback of T.Left e->pure(T.Left e);T.Right p2->fmap T.Right(N.freezeSession p2)
         pure(T.Right(r,cs,fs,[isNothing a,isNothing b,isNothing c,isNothing d],saved,unchanged,result))
 (r,cs,fs,declines,saved,unchanged,result)<-right "P1 private probes"answer
 assert "exact P1 root/copy/frontier receipt"(r==root&&mapEntries cs==mapEntries copies&&fs==frontier)
 assert "all private recoverable failures declined"(and declines)
 checkSolver "captured P1"False expectedP1 saved
 checkSolver "four failures did not mutate P1"False expectedP1 unchanged
 checkOutcome "fallback uses P1 not P0"False(FS.solverUnify(frontier++[(root,8)])expectedP1)result
 putStrLn "PASS session failed P0 and P1 probes preserve fallback epochs"
 where isNothing T.Nothing=True;isNothing(T.Just _)=False

frontierCapture :: IO ()
frontierCapture=do
 let original=A.replace 7(A.node(T.GGen 9)0 T.Flexible)
       (A.replace 9(A.node(T.GArr 8 3)7 T.Flexible)
       (A.replace 3(A.node(T.GSkolem 42 T.Star)0 T.Rigid)(A.without[4,5,6]A.poly)))
 before<-right "frontier prepare"(FS.prepare original)
 let first=G.nextId original
 (root,copies,frontier,oldP1)<-right "frontier frozen expansion"(FS.expanded 2 8 before)
 assert "hand frontier first/root/receipt"(first==10&&root==10&&mapEntries copies==[(3,10)]&&frontier==[(3,10)])
 oldP2<-case FS.frontierBottomGraft first 8 root frontier oldP1 of
  T.Nothing->errorWithoutStackTrace "authored frontier graft must succeed"
  T.Just result->pure result
 let actual=P.runST $ do
       s<-N.openSession before
       expanded<-N.expanded 2 8 s
       case expanded of
        T.Left e->pure(T.Left e)
        T.Right(r,_,fs,p1)->do
         captured<-N.readBucket K.Structural 8 p1
         saved<-N.freezeSession p1
         result<-N.frontierBottomGraft first 8 r fs p1
         case result of
          T.Nothing->pure(T.Left "private frontier graft unexpectedly declined")
          T.Just p2->do
           final<-N.freezeSession p2
           currentBucket<-N.readBucket K.Structural 8 p2
           pure(T.Right(captured,currentBucket,saved,final))
 (captured,currentBucket,saved,actualP2)<-right "frontier capture"actual
 assert "delayed old parent bucket detached from mutated slot"(setEntries captured==[9]&&null(setEntries currentBucket))
 checkSolver "frontier delayed P1 snapshot"False oldP1 saved
 checkSolver "frontier old-parent rewrite"False oldP2 actualP2
 let g=S.graph actualP2
 assert "hand original aliases/counter/parent rewrite"(mapEntries(G.links g)==[(8,3),(10,3)]&&G.nextId g==11&&sameTag(G.tag(G.nodeAt g 9))(T.GArr 3 3))
 putStrLn "PASS session captured frontier bucket and old-parent rewrite"

-- Explicit TEST-ONLY fault injection through the all-export renamed copy.
-- These valid-shaped but inconsistent indices cannot enter the production file factory.
auditControls :: IO ()
auditControls=do
 good<-right "audit field prepare"(FS.prepare F.base)
 let forged=T.Solver(S.graph good)(IM.insert 999(IS.singleton 0)(S.structuralParents good))(S.bindingChildren good)(S.scopeIndex good)
     answer=P.runST $ do
      s<-N.openSession forged
      noOp<-N.projectCaseFields[]s
      emptySnapshot<-case noOp of T.Left e->pure(T.Left e);T.Right a->fmap T.Right(N.freezeSession a)
      selected<-N.projectCaseFields[(2,4)]s
      selectedResult<-case selected of T.Left e->pure(T.Left e);T.Right a->fmap T.Right(N.freezeSession a)
      pure(emptySnapshot,selectedResult)
     (emptySnapshot,selectedResult)=answer
 noOp<-right "empty selection must not audit"emptySnapshot
 assert "empty selection retains injected inconsistent bucket"(sameGraphPhysical(S.graph forged)(S.graph noOp)&&indexEntries(S.structuralParents forged)==indexEntries(S.structuralParents noOp))
 checkOutcome "selected ProjectCase retained original audit"False(FS.projectCaseFields[(2,4)]forged)selectedResult
 let final=P.runST $ do s<-N.openSession forged;N.finishNormalized s
 checkOutcome "final original audit rejects inconsistency"False(FS.finishNormalized forged)final
 assert "literal original index-audit error"(case final of T.Left e->B.unpack e=="incremental graph index disagrees with the graph";T.Right _->False)
 putStrLn "PASS session empty versus selected and final original audits"

witnessCopies :: T.Either B.String(T.IntMap Integer,T.Solver) -> T.Either B.String T.Solver
witnessCopies answer=case answer of T.Left e->T.Left e;T.Right(_,s)->T.Right s
witnessControls :: IO ()
witnessControls=do
 -- Witness is an elaboration proof for an ALREADY SOLVED instance edge.
 -- Empty constraints leave target 8 as a bottom which normalize rigidifies;
 -- that old presolution correctly rejects an arrow witness.
 let solvedInput=constraints A.poly[][instanceStep 2 8]
 old<-right "old final presolution"(FC.solvePrepared solvedInput)
 new<-right "private final presolution"(N.solvePrepared solvedInput)
 assert "hand solved presolution paid four fresh copies"(G.nextId(S.graph old)==13&&G.nextId(S.graph new)==13)
 let first=FS.witness 2 8 new
     second=FS.witness 2 8 new
     expected=FS.witness 2 8 old
 checkOutcome "first detached witness"False(witnessCopies expected)(witnessCopies first)
 checkOutcome "independent second detached witness"False(witnessCopies expected)(witnessCopies second)
 checkSolver "witness base remains immutable"False old new
 case(expected,first,second)of
  (T.Right(a,sa),T.Right(b,sb),T.Right(c,sc))->do
   let expectedCopies=[(3,13),(4,14),(5,15),(6,16)]
   assert "hand witness copies and independently unchanged receipts"(mapEntries a==expectedCopies&&mapEntries b==expectedCopies&&mapEntries c==expectedCopies)
   assert "each sibling starts at same detached fresh frontier"(all ((==17).G.nextId.S.graph)[sa,sb,sc])
  _->errorWithoutStackTrace "authored witness unexpectedly rejected"
 putStrLn "PASS session detached final Solver supports independent witnesses"

main :: IO ()
main=do
 assert "fixed existing graft fixture inventory"(length A.cases==14)
 assert "fixed finite trace inventory"(length cases==28)
 literalControls
 forM_ cases runCase
 putStrLn "PASS session 28 finite full-state traces and unchanged public route"
 failedProbes
 frontierCapture
 auditControls
 witnessControls
 putStrLn "{\"complete\":true,\"groups\":6,\"trace_cases\":28,\"candidate_output_used_for_expectations\":false,\"private_raw_faults_test_copy_only\":true}"
