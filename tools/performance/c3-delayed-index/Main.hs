{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (forM_,unless)
import Control.Exception (SomeException,try,evaluate,displayException)
import Data.List (isInfixOf)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified LegacySession as F
import qualified CandidateSession as C
import qualified C4Fixtures as Fixtures
import qualified SessionGraftFixtures as A
import qualified SessionOracle as O

data Action = Instance B.Int B.Int | Equality [(B.Int,B.Int)]
data Trace = Trace [T.Solver] (T.Either B.String T.Solver) (Maybe T.Solver)
legacy initial actions = P.runST $ do
  state<-F.openSession initial
  before<-F.freezeSession state
  go state [before] actions
  where
    go state saved []=do
      lastState<-F.freezeSession state
      pure(Trace(reverse saved)(T.Right lastState)Nothing)
    go state saved(action:rest)=do
      answer<-case action of
        Instance a b->F.instantiateClosed a b state
        Equality es->F.solverUnify es state
      case answer of
        T.Left message->do
          failureEpoch<-F.freezeSession state
          pure(Trace(reverse saved)(T.Left message)(Just failureEpoch))
        T.Right next->do
          snapshot<-F.freezeSession next
          go next (snapshot:saved) rest
candidate initial actions = P.runST $ do
  state<-C.openSession initial
  before<-C.freezeSession state
  go state [before] actions
  where
    go state saved []=do
      lastState<-C.freezeSession state
      pure(Trace(reverse saved)(T.Right lastState)Nothing)
    go state saved(action:rest)=do
      answer<-case action of
        Instance a b->C.instantiateClosed a b state
        Equality es->C.solverUnify es state
      case answer of
        T.Left message->do
          failureEpoch<-C.freezeSession state
          pure(Trace(reverse saved)(T.Left message)(Just failureEpoch))
        T.Right next->do
          snapshot<-C.freezeSession next
          go next (snapshot:saved) rest

compareTrace label (Trace old a failedOld) (Trace new b failedNew)=do
  O.assert (label++" snapshot count") (length old==length new)
  forM_ (zip old new) $ \(x,y)->do
    O.checkSolver (label++" full physical graph/index/scope snapshot") True x y
    O.checkSolver (label++" independent reverse-edge and frozen validation") False x y
  O.checkOutcome (label++" exact outcome/first error") True a b
  case (failedOld,failedNew) of
    (Nothing,Nothing)->pure()
    (Just x,Just y)->O.checkSolver (label++" exact legacy failure Store epoch") True x y
    _->errorWithoutStackTrace(label++" changed failure epoch category")

isRight(T.Right _)=True
isRight _=False
traceResult(Trace _ result _)=result

expandedLegacy initial source target=P.runST $ do
  state<-F.openSession initial
  answer<-F.expanded source target state
  case answer of
    T.Left e->pure(T.Left e)
    T.Right(r,cs,fs,next)->do
      frozen<-F.freezeSession next
      pure(T.Right(r,cs,fs,frozen))
expandedCandidate initial source target=P.runST $ do
  state<-C.openSession initial
  answer<-C.expanded source target state
  case answer of
    T.Left e->pure(T.Left e)
    T.Right(r,cs,fs,next)->do
      frozen<-C.freezeSession next
      pure(T.Right(r,cs,fs,frozen))

projectionSelection initial source target=P.runST $ do
  old<-F.openSession initial
  answer<-F.expanded source target old
  case answer of
    T.Left _->pure False
    T.Right(root,_,frontier,indexed)->do
      let current=F.graph indexed;first=G.nextId(S.graph initial)
          fresh=S.allocatedNodes first (G.nextId current)(G.nodes current)
          equations=[(G.resolve current a,G.resolve current b)|(a,b)<-frontier++[(root,target)]]
          pending=filter(uncurry(/=))equations
      a<-F.componentCanonicalNodesVisit indexed IM.empty IS.empty (concatMap(\(x,y)->[x,y])pending)
      before<-C.openSession initial
      b<-C.componentCanonicalNodesVisit before IM.empty IS.empty
        (filter(<first)(concatMap(\(x,y)->[x,y])pending)++S.expandedOldSeeds first fresh)
      pure $ case (a,b) of
        (T.Right(nodes,scopes),T.Right(oldNodes,oldScopes))->
          O.sameMapPhysical O.sameNode nodes(IM.union oldNodes(G.nodesFromDistinctAscList fresh))&&
          O.sameSetPhysical scopes oldScopes
        _->False

fixture f@(Fixtures.Fixture label input source target admitted success literal)=do
  initial<-O.right(label++" prepare") (S.prepare input)
  let one=legacy initial [Instance source target]
      next=candidate initial [Instance source target]
  O.assert(label++" authored success/rejection") (isRight(traceResult one)==success)
  compareTrace label one next
  case (literal,traceResult next)of
    (Just wanted,T.Right actual)->O.assert(label++" handwritten full graph literal")
      (O.sameGraphLogical wanted(S.graph actual))
    _->pure()
  let a=expandedLegacy initial source target;b=expandedCandidate initial source target
  case(a,b)of
    (T.Right(r,cs,fs,x),T.Right(q,ds,gs,y))->do
      O.assert(label++" original expanded descriptor") (r==q&&fs==gs&&O.sameMapPhysical(==)cs ds)
      O.checkSolver(label++" original expanded helper physical state") True x y
      if admitted then O.assert(label++" exact full expanded component selection")
        (projectionSelection initial source target) else pure()
    _->errorWithoutStackTrace(label++" unexpected expansion rejection")
  compareTrace(label++" reused result trace")
    (legacy initial [Instance source target,Equality[(target,target)],Instance source target])
    (candidate initial [Instance source target,Equality[(target,target)],Instance source target])

metadata(T.Solver(T.Graph ns aliases next)parents bindings _)=
  next+sum(map fst(O.mapEntries ns))+sum(map fst(O.mapEntries aliases))+
  sum[sum members|(_,members)<-O.indexEntries parents++O.indexEntries bindings]
observe(T.Left message)=errorWithoutStackTrace("unexpected Left: "++B.unpack message)
observe(T.Right value)=metadata value
capture n=do
  answer<-try(evaluate n)::IO(Either SomeException B.Int)
  pure(case answer of Left e->Left(displayException e);Right x->Right x)
oldOperation initial source target=P.runST $ do
  state<-F.openSession initial
  answer<-F.instantiateClosed source target state
  case answer of T.Left e->pure(T.Left e);T.Right next->fmap T.Right(F.freezeSession next)
newOperation initial source target=P.runST $ do
  state<-C.openSession initial
  answer<-C.instantiateClosed source target state
  case answer of T.Left e->pure(T.Left e);T.Right next->fmap T.Right(C.freezeSession next)

partialControls=do
  initial<-O.right "partial baseline" (S.prepare Fixtures.base)
  forM_ [("source-first",errorWithoutStackTrace "source-first",8),
         ("target-first",errorWithoutStackTrace "source-second",errorWithoutStackTrace "target-first"),
         ("target-first",2,errorWithoutStackTrace "target-first")] $ \(marker,source,target)->do
    a<-capture(observe(oldOperation initial source target))
    b<-capture(observe(newOperation initial source target))
    O.assert(marker++" exact original exception order") (a==b)
    O.assert(marker++" actually demanded") (case a of Left e->marker `isInfixOf` e;_->False)
  forM_ [("prefix-name",A.replace 4(Fixtures.node(T.GCon(errorWithoutStackTrace "prefix-name")[])3)Fixtures.payloadBarrier),
         ("surviving-name",A.replace 11(Fixtures.node(T.GCon(errorWithoutStackTrace "surviving-name")[])6)Fixtures.unchangedSurvivor)] $ \(marker,input)->do
    prepared<-O.right marker(S.prepare input)
    a<-capture(observe(oldOperation prepared 2 8));b<-capture(observe(newOperation prepared 2 8))
    O.assert(marker++" demanded before later work") (case a of Left e->marker `isInfixOf` e;_->False)
    O.assert(marker++" exact original demand") (a==b)
  let unusedName=A.replace 20(Fixtures.node(T.GGen 21)0)
        (A.replace 21(A.node(T.GCon(errorWithoutStackTrace "unused-name")[])20 T.Rigid)Fixtures.base)
      unusedKind=A.replace 20(Fixtures.node(T.GGen 21)0)
        (A.replace 21(A.node(T.GTyCon "Unused"(T.KArrow(errorWithoutStackTrace "unused-domain")
          (errorWithoutStackTrace "unused-result")))20 T.Rigid)Fixtures.base)
      unusedAlias=T.Graph(G.nodes Fixtures.base)(IM.singleton 30(errorWithoutStackTrace "unused-alias"))40
  forM_ [unusedName,unusedKind,unusedAlias] $ \input->do
    prepared<-O.right "unused payload prepare"(S.prepare input)
    a<-capture(observe(oldOperation prepared 2 8));b<-capture(observe(newOperation prepared 2 8))
    O.assert "unused payload is not observed"(case a of Right _->True;_->False)
    O.assert "candidate preserves unused payload demand"(a==b)

main=do
  let originals=Fixtures.fixtures++Fixtures.additionalFixtures++Fixtures.renamedFixtures
      shifted=[Fixtures.renameFixture("offset "++show offset)(+offset) f
        |offset<-[1,16,64,512,-512,2^48,-(2^48)],f<-take 5 Fixtures.fixtures]
  O.assert "all authored/renamed fixture inventory"(length originals==28&&length shifted==35)
  forM_ (originals++shifted) fixture
  putStrLn "PASS 63 physical graph/index/scope traces and legacy failure epochs"
  putStrLn "PASS retained expansion descriptors and exact full component selection"
  putStrLn "PASS repeated instances, reflexive equalities and literal fresh survivors"
  partialControls
  putStrLn "PASS 8 demand, first-exception and unused-payload observations"
