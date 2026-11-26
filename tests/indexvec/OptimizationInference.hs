{-# LANGUAGE OverloadedStrings #-}
module OptimizationInference (run) where

import Control.Monad (filterM, forM_, unless)
import Data.Bits (testBit)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified Bootstrap.Elaborate as E
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as Solver
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H

check :: (Eq a, Show a) => String -> a -> a -> IO ()
check label expected actual = unless (expected == actual) $
  fail (label ++ ": expected " ++ show expected ++ ", got " ++ show actual)

right :: String -> T.Either H.String a -> IO a
right label result = case result of
  T.Left message -> fail (label ++ ": " ++ H.unpack message)
  T.Right value -> pure value

-- This oracle uses the input adjacency list and host containers, independently
-- of both the production traversal and the certificate/rank representation.
postorder :: Map.Map H.Int [H.Int] -> H.Int -> [H.Int]
postorder edges root = snd (visit Set.empty root)
  where
    visit seen n
      | Set.member n seen = (seen, [])
      | otherwise = let
          child (prior, done) next = let (visited, suffix) = visit prior next
                                    in (visited, done ++ suffix)
          (visited, children) = foldl child (Set.insert n seen, []) (edges Map.! n)
        in (visited, children ++ [n])

orderingChecks :: IO ()
orderingChecks = do
  check "inference/order-empty-does-not-build-index" []
    (E.orderedBoundCandidates (error "empty built index") (error "empty read graph") 0 IS.empty)
  check "inference/order-singleton-does-not-build-index" [13]
    (E.orderedBoundCandidates (error "singleton built index") (error "singleton read graph") 0
      (IS.singleton 13))
  -- Every four-node DAG, with both edge orders and non-topological identities.
  -- All subsets of the reachable nodes exercise arbitrary binder selections.
  forM_ [0..63 :: Int] $ \mask -> forM_ [False, True] $ \backwards -> do
    let names = [91, -37, 600003, 2]
        pairs = [(a,b) | a <- [0..3], b <- [a+1..3]]
        rows = [(names !! a, order [names !! b | (bit,(x,b)) <- zip [0..] pairs,
                                              x == a, testBit mask bit]) | a <- [0..3]]
        order = if backwards then reverse else id
        edges = Map.fromList rows
        graph = G.mkGraph (IM.fromList [(n,T.Node (T.GCon "Tuple" cs) T.Nothing T.Flexible)
                                     | (n,cs) <- rows]) IM.empty 700000
        index = E.boundOrder graph
    forM_ names $ \root -> do
      let expected = postorder edges root
      forM_ (filterM (const [False,True]) expected) $ \wanted ->
        check "inference/root-local-postorder-for-all-small-dags"
          (filter (`elem` wanted) expected)
          (E.orderedBoundCandidates index graph root (IS.fromList wanted))
  let branchGraph = G.mkGraph (IM.fromList
        [(1,node (T.GArr 3 4)), (2,node (T.GArr 4 3)), (3,node T.GBot), (4,node T.GBot)])
        IM.empty 5
      node tag = T.Node tag T.Nothing T.Flexible
      sharedIndex = E.boundOrder branchGraph
  check "inference/shared-dag-keeps-first-roots-order" [3,4]
    (E.orderedBoundCandidates sharedIndex branchGraph 1 (IS.fromList [3,4]))
  check "inference/shared-dag-keeps-second-roots-reversed-order" [4,3]
    (E.orderedBoundCandidates sharedIndex branchGraph 2 (IS.fromList [3,4]))
  let repeatedGraph = G.mkGraph (IM.fromList
        [(1,node (T.GCon "Tuple" [4,3,4])), (3,node T.GBot), (4,node T.GBot)]) IM.empty 5
      E.BoundOrder repeatedCertificates _ = E.boundOrder repeatedGraph
  check "inference/repeated-structural-edge-selects-exact-fallback" False (IM.get 1 repeatedCertificates)
  check "inference/repeated-structural-edge-is-only-emitted-once" [4,3]
    (E.orderedBoundCandidates (E.boundOrder repeatedGraph) repeatedGraph 1 (IS.fromList [3,4]))
  let low = minBound + 11
      high = maxBound - 11
      graph = G.mkGraph (IM.fromList
        [(77,node (T.GArr 100 42)), (low,node T.GBot), (42,node T.GBot),
         (high,node (T.GGen 77))]) (IM.fromList [(100,101),(101,low)]) 200
      E.BoundOrder certificates _ = E.boundOrder graph
  check "inference/alias-resolved-tree-is-certified" True (IM.get 77 certificates)
  check "inference/signed-sparse-ids-use-structural-order" [low,42,77]
    (E.orderedBoundCandidates (E.boundOrder graph) graph 77 (IS.fromList [77,42,low]))

data TypeShape = Var H.Int | Bot | KindBot String | Arrow TypeShape TypeShape |
  Con String [TypeShape] | Apply TypeShape TypeShape | Forall H.Int TypeShape TypeShape
  deriving (Eq, Show)

typeShape :: T.XType -> TypeShape
typeShape ty = case ty of
  T.XVar (T.XTyVar n) -> Var n
  T.XBot -> Bot
  T.XBotKind kind -> KindBot (kindShape kind)
  T.XArrow a b -> Arrow (typeShape a) (typeShape b)
  T.XCon name children -> Con (H.unpack name) (map typeShape children)
  T.XApply a b -> Apply (typeShape a) (typeShape b)
  T.XForall (T.XTyVar n) bound body -> Forall n (typeShape bound) (typeShape body)

kindShape :: T.Kind -> String
kindShape kind = case kind of
  T.Star -> "*"
  T.KArrow a b -> "(" ++ kindShape a ++ "->" ++ kindShape b ++ ")"

-- A type tree with many two-child binders makes the old per-binder traversal
-- repeatedly visit the remaining chain. Alternate rigid leaves to exercise
-- filtering, and resolve one structural edge through two historical aliases.
quantifiedGraph :: H.Int -> H.Int -> Int -> T.Graph
quantifiedGraph offset stride depth = G.mkGraph (IM.fromList entries) aliases next
  where
    at n = offset + stride * fromIntegral n
    root = (at 0,T.Node (T.GGen (at 1)) T.Nothing T.Flexible)
    final = (at (2*depth+1),T.Node T.GBot (T.Just (at (2*depth-1))) T.Flexible)
    entry i =
      [(at (2*i+1),T.Node (T.GArr (if i == 0 then at (2*depth+4) else at (2*i+2))
                            (at (2*i+3)))
          (T.Just (at (if i == 0 then 0 else 2*i-1))) T.Flexible),
       (at (2*i+2),T.Node (if i `mod` 3 == 2 then T.GCon "Int" [] else T.GBot)
          (T.Just (at (2*i+1))) (if i `mod` 3 == 2 then T.Rigid else T.Flexible))]
    entries = root : final : concatMap entry [0..depth-1]
    aliases = IM.fromList [(at (2*depth+3),at 2),(at (2*depth+4),at (2*depth+3))]
    next = maximum (map fst entries ++ IM.keys aliases) + 1

translationChecks :: IO ()
translationChecks = forM_ [(0,1,9),(0,1,72),(-800003,10007,72)] $ \(offset,stride,depth) -> do
  initial <- right "inference/prepare-quantified-tree" (Solver.prepare (quantifiedGraph offset stride depth))
  solved <- right "inference/normalize-quantified-tree" (Solver.finishNormalized initial)
  let graph = Solver.solverGraph solved
      raw = E.prepareTypes graph
      sparse = E.prepareSolvedTypes solved
      dense = E.prepareValidatedSolvedTypes solved
      bounds context n = [(v,typeShape ty) | (T.XTyVar v,ty) <- E.boundsAtIn context n]
      contexts = [sparse,dense]
      ids = IM.keys (G.nodes graph) ++ IM.keys (G.links graph)
  check "inference/dense-context-selected-only-for-dense-identities"
    (depth >= 64 && stride == 1)
    (case dense of E.DenseTypeContext {} -> True; _ -> False)
  forM_ contexts $ \context -> forM_ ids $ \n -> do
    check "inference/quantifier-identities-flags-bounds-and-order" (bounds raw n) (bounds context n)
    unless (G.isGen (G.tag (G.nodeAt graph n))) $
      check "inference/exact-translated-type-through-historical-aliases"
        (typeShape (E.typeAtIn raw n)) (typeShape (E.typeAtIn context n))
  check "inference/complete-quantified-scheme"
    (typeShape (E.schemeTypeIn raw offset)) (typeShape (E.schemeTypeIn dense offset))

dagTranslationChecks :: IO ()
dagTranslationChecks = do
  let node tag parent flag = T.Node tag parent flag
      input = G.mkGraph (IM.fromList
        [(0,node (T.GGen 1) T.Nothing T.Flexible),
         (1,node (T.GArr 2 3) (T.Just 0) T.Flexible),
         (2,node (T.GArr 4 5) (T.Just 1) T.Flexible),
         (3,node (T.GArr 5 100) (T.Just 1) T.Flexible),
         (4,node T.GBot (T.Just 1) T.Flexible),
         (5,node (T.GCon "Int" []) (T.Just 1) T.Rigid)]) (IM.singleton 100 4) 101
  initial <- right "inference/prepare-shared-quantified-dag" (Solver.prepare input)
  solved <- right "inference/normalize-shared-quantified-dag" (Solver.finishNormalized initial)
  let graph = Solver.solverGraph solved
      raw = E.prepareTypes graph
      prepared = E.prepareSolvedTypes solved
      E.BoundOrder certificates _ = E.boundOrder graph
      bounds context n = [(v,typeShape ty) | (T.XTyVar v,ty) <- E.boundsAtIn context n]
  check "inference/solved-shared-dag-does-not-use-forest-ranks" False (IM.get 1 certificates)
  forM_ [0..5] $ \n ->
    check "inference/solved-shared-dag-preserves-bound-order-flags-and-types"
      (bounds raw n) (bounds prepared n)
  check "inference/solved-shared-dag-preserves-complete-scheme"
    (typeShape (E.schemeTypeIn raw 0)) (typeShape (E.schemeTypeIn prepared 0))

pathChecks :: IO ()
pathChecks = do
  let parents = Map.fromList [(n,if n < 4 then 0 else n `div` 2) | n <- [1..63 :: H.Int]]
      path 0 = []
      path n = n : path (parents Map.! n)
      paths = map path [0..63]
      original left = dropWhile (`notElem` left)
  forM_ paths $ \left -> forM_ paths $ \rightPath ->
    check "inference/linear-common-path-equals-membership-oracle-on-lawful-trees"
      (original left rightPath) (Solver.commonBinderSuffix left rightPath)
  check "inference/equal-head-keeps-lazy-constant-time-path" 7
    (head (Solver.commonBinderSuffix (7:error "forced equal left tail")
      (7:error "forced equal right tail")))
  let gen n parent = (n,T.Node (T.GGen n) parent T.Flexible)
      scopes = Solver.indexScopes (G.mkGraph (IM.fromList
        [gen 0 T.Nothing,gen 5 (T.Just 0),gen 8 (T.Just 5),gen 13 (T.Just 0)]) IM.empty 14)
      inspect (Solver.LocalBinderPath ns scope) = (ns,scope)
  check "inference/different-generalization-scopes-use-scope-lca" ([],0)
    (inspect (Solver.commonLocalBinderPath scopes
      (Solver.LocalBinderPath (error "forced first cross-scope path") 8)
      (Solver.LocalBinderPath (error "forced second cross-scope path") 13)))
  check "inference/ancestor-generalization-scope-is-retained" ([],5)
    (inspect (Solver.commonLocalBinderPath scopes
      (Solver.LocalBinderPath [3,2] 8) (Solver.LocalBinderPath [4] 5)))

-- Instantiate a shared variable at the tips of two deep branches into a tree
-- whose tips have distinct type binders. The actual local quotient must place
-- the merged variable at the common branch root, through commonLocalBinderPath.
localGraph :: H.Int -> H.Int -> H.Int -> (T.Graph,H.Int,H.Int,H.Int)
localGraph offset stride depth = (G.mkGraph (IM.fromList entries) aliases (at (targetBase+width)),at 2,at targetBase,at (targetBase+1))
  where
    at n = offset + stride * fromIntegral n
    width = 4*depth+6
    targetBase = 3+width
    node tag parent = T.Node (G.mapTag at tag) (maybe T.Nothing (T.Just . at) parent) T.Flexible
    tree base shared =
      [(base,node (T.GGen (base+1)) (Just 0)),
       (base+1,node (T.GArr (base+2) (base+2+2*depth)) (Just base))] ++
      concat [branch base shared side | side <- [0,1]] ++
      [(base+2+4*depth,node T.GBot (Just (if shared then base+1 else base+2+2*(depth-1))))] ++
      (if shared then [] else
        [(base+3+4*depth,node T.GBot (Just (base+2+2*depth+2*(depth-1))))])
    branch base shared side = concatMap entry [0..depth-1]
      where
        start = base+2+side*2*depth
        tip = base+2+4*depth + if shared then 0 else side
        entry i = [(start+2*i,node (T.GArr (start+2*i+1)
                                   (if i+1 == depth then tip else start+2*i+2))
                      (Just (if i == 0 then base+1 else start+2*i-2))),
                   (start+2*i+1,node T.GBot (Just (start+2*i)))]
    entries = [(at 0,node (T.GGen 1) Nothing),(at 1,node T.GBot (Just 0))] ++
      [(at n,v) | (n,v) <- tree 2 True ++ tree targetBase False]
    aliases = IM.fromList [(at (targetBase+width-1),at (targetBase+1))]

localSolveChecks :: IO ()
localSolveChecks = forM_ [(0,1,1),(0,1,8),(-1701,1031,12)] $ \(offset,stride,depth) -> do
  let (input,source,destination,target) = localGraph offset stride depth
  initial <- right "inference/prepare-two-deep-binding-branches" (Solver.prepare input)
  (root,_,frontier,expanded) <- right "inference/expand-shared-variable-at-both-tips"
    (Solver.expandedGraphPrepared source target initial)
  let first = G.nextId (Solver.solverGraph initial)
      fresh = Solver.allocatedNodes first (G.nextId expanded) (G.nodes expanded)
      equations = frontier ++ [(root,target)]
      same a b = G.nextId a == G.nextId b &&
        IM.eqIntMap G.equalNode (G.nodes a) (G.nodes b) && IM.eqIntMap (==) (G.links a) (G.links b)
  expected <- right "inference/general-unifier-reference-for-deep-lca" (G.unify equations expanded)
  local <- right "inference/deep-binding-paths-use-actual-local-solver"
    (Solver.unifyExpandedLocally equations initial expanded destination fresh root)
  actual <- right "inference/audit-deep-local-quotient" (Solver.finish local)
  check "inference/local-lca-preserves-complete-graph-links-binders-and-flags" True (same expected actual)

run :: IO ()
run = do
  orderingChecks
  translationChecks
  dagTranslationChecks
  pathChecks
  localSolveChecks
