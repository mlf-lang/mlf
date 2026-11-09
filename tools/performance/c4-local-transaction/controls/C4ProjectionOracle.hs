{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
-- P3 projection oracle. Calls only complete frozen Solver/Graph helpers;
-- never constructs an expected local graph with a candidate projection helper.
module C4ProjectionOracle where
import Prelude
import Data.List (foldl')
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified FrozenGraph as FG
import qualified FrozenSolver as FS

data Projection = Projection
  { localGraph :: T.Graph
  , localEquations :: [(Integer,Integer)]
  , originalEntries :: [(Integer,T.Node)]
  , fullSelected :: T.Map Integer T.Node
  , projectedScopes :: T.IntMap (T.Maybe Integer)
  , hiddenStubs :: T.IntMap Integer
  }

bind :: T.Either a b -> (b -> T.Either a c) -> T.Either a c
bind (T.Left e) _ = T.Left e
bind (T.Right a) f = f a

-- Literal semantic transcription of exact P3 solverUnify/unifyDistinct up to
-- its G.unify call. Local bindings are named for audit; the COMPLETE original
-- implementation remains an additional independent end-to-end oracle.
project :: [(Integer,Integer)] -> T.Solver -> T.Either B.String Projection
project equations solver =
  let current = FS.graph solver
      canonical = [(FG.resolve current a,FG.resolve current b) | (a,b) <- equations]
      identities = concatMap (\(a,b) -> [a,b]) canonical
      pending = filter (uncurry (/=)) canonical
  in bind (FG.mapE_ (\n -> bind (FG.require current n) (\_ -> T.Right ())) identities) $ \_ ->
     bind (FS.componentCanonicalNodesVisit solver IM.empty IS.empty
       (map (FG.resolve current) (concatMap (\(a,b) -> [a,b]) pending))) $ \(connected,boundaries) ->
     let scopes = FS.projectScopes (FS.scopeIndex solver) boundaries
         selected = foldl' (\found n -> if IM.member n found then found
                      else IM.insert n (IM.get n (FG.nodes current)) found) connected (IM.keys scopes)
         originals = IM.toList selected
         count = toInteger (length originals)
         forward = case selected of T.IntMap tree -> tree
         compact n = FS.rankIdentity (FG.resolve current n) 0 forward
         hidden = filter (\(_,v) -> case FG.tag v of
                    T.GGen root -> not (IM.member root selected)
                    _ -> False) originals
         stubs = IM.fromDistinctAscList (zip (map fst hidden) [count .. count + toInteger (length hidden) - 1])
         existing = FS.projectCanonicalNodes forward scopes stubs 0 originals
         placeholders = [(stub,FG.mkNode T.GBot (T.Just (FS.rankIdentity original 0 forward)) T.Flexible)
                        | (original,stub) <- IM.toList stubs]
         local = FG.mkGraph (FG.nodesFromDistinctAscList (existing ++ placeholders)) IM.empty
                   (count + toInteger (length hidden))
     in T.Right (Projection local [(compact a,compact b) | (a,b) <- pending]
          originals forward scopes stubs)

-- Extra, hand-written compact topology for the mutable-bottom base fixture.
-- The global hidden Gen(0) root receives stub 9. The new equation is (5,2).
baseLocalLiteral :: T.Graph
baseLocalLiteral = T.Graph (FG.nodesFromDistinctAscList
  [(0,T.Node (T.GGen 9) T.Nothing T.Flexible)
  ,(1,n (T.GGen 2) 0),(2,n (T.GArr 3 4) 1)
  ,(3,n T.GBot 2),(4,n T.GBot 2)
  ,(5,n (T.GArr 6 7) 1),(6,n (T.GArr 8 8) 5)
  ,(7,n T.GBot 5),(8,n T.GBot 6),(9,n T.GBot 0)]) IM.empty 10
 where n t b = T.Node t (T.Just b) T.Flexible
