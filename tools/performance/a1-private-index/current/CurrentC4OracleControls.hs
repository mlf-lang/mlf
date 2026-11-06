{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
-- Extra comparator controls, not regenerated expectations or A1 algorithm edits.
module CurrentC4OracleControls where
import Prelude
import Control.Exception (SomeException, try)
import Control.Monad (forM_)
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified FrozenSolver as FS
import qualified SessionOracle as O
import qualified CurrentC4TransactionOracle as C4

-- Handwritten well-scoped graph; no candidate solver supplies its expected state.
graph :: T.Graph
graph = T.Graph (IM.fromList
  [(0,T.Node (T.GGen 1) T.Nothing T.Flexible),
   (1,T.Node (T.GArr 2 3) (T.Just 0) T.Flexible),
   (2,T.Node T.GBot (T.Just 1) T.Flexible),
   (3,T.Node T.GBot (T.Just 1) T.Flexible)]) IM.empty 4

otherShape :: T.Map Integer a -> T.Map Integer a
otherShape tree = case O.entries tree of
  [(a,x),(b,y)] -> case tree of
    T.MapNode _ k _ _ _ | k == a ->
      T.MapNode 2 b y (T.MapNode 1 a x T.MapEmpty T.MapEmpty) T.MapEmpty
    _ -> T.MapNode 2 a x T.MapEmpty (T.MapNode 1 b y T.MapEmpty T.MapEmpty)
  _ -> tree

rebalanceIndex :: T.IntMap T.IntSet -> T.IntMap T.IntSet
rebalanceIndex (T.IntMap tree) = T.IntMap (otherShape (buckets tree))
 where
  buckets T.MapEmpty = T.MapEmpty
  buckets (T.MapNode n k (T.IntSet values) l r) =
    T.MapNode n k (T.IntSet (otherShape values)) (buckets l) (buckets r)

badSize :: T.IntMap a -> T.IntMap a
badSize (T.IntMap (T.MapNode n k v l r)) = T.IntMap (T.MapNode (n+1) k v l r)
badSize value = value

badBucketSize :: T.IntMap T.IntSet -> T.IntMap T.IntSet
badBucketSize (T.IntMap (T.MapNode n k (T.IntSet (T.MapNode m j v a b)) l r)) =
  T.IntMap (T.MapNode n k (T.IntSet (T.MapNode (m+1) j v a b)) l r)
badBucketSize value = value

reject :: String -> IO () -> IO ()
reject label action = do
  result <- try action :: IO (Either SomeException ())
  case result of
    Left _ -> pure ()
    Right _ -> errorWithoutStackTrace ("C4 comparator accepted mutation: " ++ label)

main :: IO ()
main = do
  old@(T.Solver g@(T.Graph ns aliases next) parents bindings scopes) <-
    O.right "independent comparator fixture" (FS.prepare graph)
  let changed = T.Solver g (rebalanceIndex parents) (rebalanceIndex bindings) scopes
  O.assert "fixture actually changes allowed reverse representation"
    (not (O.sameSolverPhysical old changed))
  C4.checkTransactional "allowed reverse rebalance" old changed
  C4.checkTransactionalOutcome "same exact error" (T.Left "first") (T.Left "first")
  let T.ScopeIndex intervals jumps = scopes
      graphCounter = T.Solver (T.Graph ns aliases (next+1)) parents bindings scopes
      graphAlias = T.Solver (T.Graph ns (IM.singleton 99 0) next) parents bindings scopes
      graphNodes = T.Solver (T.Graph (badSize ns) aliases next) parents bindings scopes
      scopeCounts = T.Solver g parents bindings (T.ScopeIndex (badSize intervals) jumps)
      missingParents = T.Solver g IM.empty bindings scopes
      missingBindings = T.Solver g parents IM.empty scopes
      parentCount = T.Solver g (badSize parents) bindings scopes
      binderBucket = T.Solver g parents (badBucketSize bindings) scopes
  forM_ [("counter",graphCounter),("alias",graphAlias),("node tree",graphNodes),
         ("scope tree",scopeCounts),("structural edges",missingParents),
         ("binder edges",missingBindings),("index cached size",parentCount),
         ("bucket cached size",binderBucket)] $ \(label,value) ->
    reject label (C4.checkTransactional label old value)
  -- Self-comparison cannot mask malformed representation: equality alone passes.
  reject "self index cached size" (C4.checkTransactional "self size" parentCount parentCount)
  reject "self bucket cached size" (C4.checkTransactional "self bucket" binderBucket binderBucket)
  reject "different error" (C4.checkTransactionalOutcome "error" (T.Left "first") (T.Left "second"))
  reject "accepted error" (C4.checkTransactionalOutcome "accept" (T.Left "first") (T.Right old))
  reject "rejected success" (C4.checkTransactionalOutcome "reject" (T.Right old) (T.Left "first"))
  putStrLn "PASS current C4 comparator: allowed reverse rebalance, exact errors, 13 authored rejections"
