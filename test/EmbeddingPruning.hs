module EmbeddingPruning (embeddingPruningTests, pruningConformance) where

import Control.Monad (forM_, unless)
import Data.List (subsequences)
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import MLF.Constraint
import qualified MLF.Graph as G
import MLF.Parser (parseExpr)
import qualified MLF.Syntax as S

assert :: Bool -> String -> IO ()
assert predicate message = unless predicate (fail message)

right :: Either String a -> IO a
right = either fail pure

-- These are allocation histories, not a second implementation of pruning.
-- Node 0 contains precisely the declared live edges; other nodes are leaves.
-- Varying present identities independently of live ones includes ID gaps.
histories :: Int -> [(Int, [Int], G.Graph)]
histories limit =
  [ (start, live, G.Graph (IM.fromList ((0, root) : leaves)) IM.empty stop)
  | stop <- [1..limit]
  , present <- subsequences [1..stop-1]
  , live <- subsequences present
  , start <- [0..stop]
  , let root = G.Node (G.Con "Root" live) Nothing S.Rigid
        leaves = [(n, G.Node (G.Con (show n) []) (Just 0) S.Flexible) | n <- present]
  ]

checkHistory :: (Int, [Int], G.Graph) -> IO ()
checkHistory (start, live, after) = do
  let result = pruneEmbedding start 0 after
      old = IM.keys (G.nodes after)
      wanted n = n < start || n == 0 || n `elem` live
  assert (G.nextId result == G.nextId after && G.links result == G.links after)
    "pruning changed the allocator or alias table"
  assert (all (`elem` old) (IM.keys (G.nodes result))) "pruning invented an identity"
  forM_ (IM.toList (G.nodes after)) $ \(n,value) ->
    assert (IM.lookup n (G.nodes result) == if wanted n then Just value else Nothing)
      ("pruning violated identity/value conservation at " ++ show (start,n))
  assert (G.reachable result 0 == G.reachable after 0)
    "pruning changed the embedded type's structural graph"
  assert (pruneEmbedding start 0 result == result) "pruning is not idempotent"

-- A changed old node must survive even though it is not reachable from the
-- embedded root. The root is an old alias; fresh IDs have internal gaps.
gapGraph :: G.Graph
gapGraph = G.Graph (IM.fromList
  [ (0, G.Node (G.Con "ChangedOldValue" []) (Just 2) S.Rigid)
  , (2, G.Node (G.Arr 7 7) Nothing S.Rigid)
  , (4, G.Node G.Bot Nothing S.Flexible)
  , (7, G.Node G.Bot (Just 2) S.Flexible)
  , (8, G.Node (G.Con "UnusedBound" []) Nothing S.Rigid)
  ]) (IM.singleton 3 2) 10

checkGaps :: IO ()
checkGaps = do
  let result = pruneEmbedding 4 3 gapGraph
  assert (IM.keys (G.nodes result) == [0,2,7]) "unused fresh nodes or allocation gaps survived"
  assert (G.nodeAt result 0 == G.nodeAt gapGraph 0) "changed old node was restored or discarded"
  assert (G.nodeAt result 3 == G.nodeAt gapGraph 2) "old root alias changed"
  assert (G.links result == G.links gapGraph && G.nextId result == 10)
    "allocation gap pruning changed alias identities or the next ID"
  assert (pruneEmbedding 10 3 gapGraph == gapGraph) "zero allocation changed the graph"

annotationCases :: [(String, String, Int, Bool)]
annotationCases =
  [ ("unused binder", "(\\x -> x) : forall unused a. a -> a", 2, False)
  , ("alias binder", "(\\x -> x) : forall a (b >= a). b -> b", 2, False)
  , ("bound is root", "(\\x -> x) : forall (a >= forall b. b -> b). a", 2, False)
  , ("unused compound bound", "(\\x -> x) : forall (unused >= Int -> Bool) a. a -> a", 2, False)
  , ("existing root", "(\\x -> x) : exists a. a", 1, True)
  , ("existing root and unused bound", "(\\x -> x) : exists a. forall (unused >= Int -> Bool). a", 1, True)
  , ("shared old child", "(\\x -> x) : exists a. a -> a", 2, False)
  ]

checkAnnotation :: (String, String, Int, Bool) -> IO ()
checkAnnotation (label, source, count, shared) = do
  constraints <- right (parseExpr label source >>= generate)
  let graph = initialGraph constraints
  (domain,result) <- case form (skeleton constraints) of
    Apply coercion _ _ _ -> case form coercion of
      Coercion _ a b -> pure (a,b)
      _ -> fail "annotation did not produce a coercion"
    _ -> fail "annotation did not produce an application"
  assert (IS.size (G.reachable graph domain) == count && IS.size (G.reachable graph result) == count)
    (label ++ ": bound pruning changed the embedded type's nodes")
  assert ((domain == result) == shared) (label ++ ": scoped identity sharing changed")
  assert (all (< G.nextId graph) (IM.keys (G.nodes graph))) "allocator bound is false"
  _ <- right (solve constraints)
  pure ()

embeddingPruningTests :: [(String, IO ())]
embeddingPruningTests =
  [ ("embedding pruning preserves identities and values over allocation histories", mapM_ checkHistory (histories 7))
  , ("embedding pruning preserves old updates, aliases and allocation gaps", checkGaps)
  , ("embedding pruning preserves source bound and existential semantics", mapM_ checkAnnotation annotationCases)
  ]

-- The MLF fixture checks the same declarative invariants independently and
-- emits these labels only after their assertions succeed on each backend.
pruningConformance :: IO ()
pruningConformance = do
  let small = histories 4
  mapM_ checkHistory small
  putStrLn ("allocation histories: " ++ show (length small))
  checkGaps
  putStrLn "old updates, aliases, gaps and zero allocation: ok"
  forM_ annotationCases $ \fixture@(label,_,_,_) -> do
    checkAnnotation fixture
    putStrLn (label ++ ": ok")
