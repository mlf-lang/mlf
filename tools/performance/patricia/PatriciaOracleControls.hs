{-# LANGUAGE OverloadedStrings #-}
module PatriciaOracleControls(boundary) where
import Prelude
import Control.Exception(SomeException,try,evaluate)
import Control.Monad(forM_)
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified OracleTypes as R
import qualified FrozenSolver as FS
import qualified SessionOracle as O
import qualified C4TransactionOracle as C

badCount :: T.IntMap a -> T.IntMap a
badCount(T.IntMap(T.IntMapBin n p l r))=T.IntMap(T.IntMapBin(n+1)p l r)
badCount _=error "bad-count fixture requires a branch"
badPrefix :: T.IntMap a -> T.IntMap a
badPrefix(T.IntMap(T.IntMapBin n p l r))=T.IntMap(T.IntMapBin n(p+1)l r)
badPrefix _=error "bad-prefix fixture requires a branch"
reject label action=do
 answer<-try action::IO(Either SomeException ())
 case answer of Left _->pure ();Right _->error("oracle accepted "++label)
boundary :: IO ()
boundary=do
 let g=T.Graph(IM.fromList[(0,T.Node(T.GGen 1)T.Nothing T.Flexible),
             (1,T.Node(T.GArr 2 3)(T.Just 0)T.Flexible),
             (2,T.Node T.GBot(T.Just 1)T.Flexible),(3,T.Node T.GBot(T.Just 1)T.Flexible)])IM.empty 4
 old@(T.Solver graph@(T.Graph ns aliases next) parents bindings scopes)<-O.right "oracle fixture"(FS.prepare g)
 let shuffled=IM.fromList(reverse(IM.toList ns))
 O.assert "canonical Patricia shape is independent of insertion order"(R.sameMap O.sameNode ns shuffled)
 C.checkTransactional "canonical order" old(T.Solver(T.Graph shuffled aliases next)parents bindings scopes)
 let T.ScopeIndex intervals jumps=scopes
     bucket=IS.fromList[1,2,7,20]
     T.IntSet tree=bucket
     broken=case tree of T.IntSetTip n p bits->T.IntSet(T.IntSetTip(n+1)p bits);_->error "expected bitmap tip"
     mutations=[("counter",T.Solver(T.Graph ns aliases(next+1))parents bindings scopes),
      ("alias",T.Solver(T.Graph ns(IM.singleton 99 0)next)parents bindings scopes),
      ("map count",T.Solver(T.Graph(badCount ns)aliases next)parents bindings scopes),
      ("map prefix",T.Solver(T.Graph(badPrefix ns)aliases next)parents bindings scopes),
      ("missing parents",T.Solver graph IM.empty bindings scopes),
      ("missing bindings",T.Solver graph parents IM.empty scopes),
      ("scope contents",T.Solver graph parents bindings(T.ScopeIndex IM.empty jumps))]
 forM_ mutations $ \(label,value)->reject label(C.checkTransactional label old value)
 forM_ [badCount ns,badPrefix ns] $ \value->O.assert "independent map corruption rejection"(not(R.validMap value))
 O.assert "bitmap count corruption rejection"(not(R.validSet broken))
 O.assert "bitmap membership mutation visible"(not(R.sameSet bucket(IS.insert 21 bucket)))
 let payload=error "bridge forced a lazy payload"::Int
     bst=T.MapNode 1 2 payload T.MapEmpty T.MapEmpty
 _<-evaluate(R.validMap(R.wrapMap bst))
 _<-evaluate(case R.unwrapMap(R.wrapMap bst)of T.MapNode _ _ _ _ _->True;_->False)
 reject "different error"(C.checkTransactionalOutcome "error"(T.Left "first")(T.Left "second"))
 putStrLn "PASS Patricia oracle boundary: canonical construction, counts/prefix/bitmap/membership/counter/alias/edge/scope rejection, lazy payload bridge"
