module GraphValidation (graphValidationTests, smallGraphs) where

import Control.Monad (forM_, unless)
import Data.Either (isRight)
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import MLF.Graph
import MLF.Kind
import MLF.Syntax (Flag (..))

graphValidationTests :: [(String, IO ())]
graphValidationTests =
  [ ("graph validation agrees with uncached reference", do
      let graphs = smallGraphs
          accepted = length (filter (isRight . referenceValidation) graphs)
      unless (accepted > 25 && accepted < length graphs)
        (fail ("vacuous graph corpus: " ++ show accepted ++ " valid"))
      forM_ graphs $ \g -> unless (isRight (validateGraph g) == isRight (referenceValidation g))
        (fail ("graph validation disagrees with reference: " ++ show g))
      putStrLn ("Graph validation: " ++ show (length graphs) ++ " graphs; " ++ show accepted ++ " valid"))
  , ("graph validation checks deeply nested binding scopes", do
      let g = nestedGraph 1000
      either fail pure (validateGraph g)
      -- The root now bypasses node 2, so node 3's binder no longer dominates
      -- every structural path to it, although its binding tree is acyclic.
      let invalid = g { nodes = IM.adjust (\v -> v { tag = Arr 2 3 }) 1 (nodes g) }
      unless (not (isRight (validateGraph invalid))) (fail "accepted scope escape"))
  , ("graph validation checks shared higher-kinded subgraphs", do
      let g = Graph (IM.fromList
            [(0,Node (Gen 1) Nothing Flexible)
            ,(1,Node (Arr 2 2) (Just 0) Rigid)
            ,(2,Node (TyApp 3 4) (Just 1) Rigid)
            ,(3,Node (TyCon "F" (KArrow Star Star)) (Just 2) Rigid)
            ,(4,Node Bot (Just 2) Flexible)]) IM.empty 5
      either fail pure (validateGraph g)
      let invalid = g { nodes = IM.adjust (\v -> v { tag = BotK (KArrow Star Star) }) 4 (nodes g) }
      unless (not (isRight (validateGraph invalid))) (fail "accepted kind mismatch"))
  ]

-- Enumerate binding roots, cycles, absent parents, scope escapes, missing
-- structural nodes, structural cycles, sharing, and valid/invalid kinds.
-- Aliased structural references exercise resolution as well as direct IDs.
smallGraphs :: [Graph]
smallGraphs =
  [ Graph (IM.fromList
      [(0,Node (Gen 1) Nothing Flexible)
      ,(1,Node top parent Flexible)
      ,(2,Node left leftParent Flexible)
      ,(3,Node right rightParent Rigid)]) aliases 6
  | top <- [Arr 2 3, Arr 2 2, TyApp 2 3, Con "Pair" [2,3], Arr 5 3]
  , left <- [Bot, TyCon "F" (KArrow Star Star), Arr 3 3, Gen 3]
  , right <- [Bot, TyCon "G" (KArrow Star Star), Arr 2 2, Arr 9 9]
  , parent <- [Nothing, Just 0, Just 2]
  , leftParent <- [Nothing, Just 0, Just 1, Just 3, Just 9]
  , rightParent <- [Nothing, Just 0, Just 1, Just 2, Just 9]
  , aliases <- [IM.empty, IM.fromList [(5,4),(4,2)]]
  ]

nestedGraph :: Int -> Graph
nestedGraph depth = Graph (IM.fromList
  ((0,Node (Gen 1) Nothing Flexible) :
    [(n,Node (if n == depth then Bot else Arr (n+1) (n+1))
       (Just (n-1)) Flexible) | n <- [1..depth]])) IM.empty (depth+1)

-- Deliberately simple reference: no kind memoization or ancestry index.
-- Keeping the original per-node walks here checks the optimized analyses
-- against the graph invariants without relying on their implementation.
referenceValidation :: Graph -> Either String ()
referenceValidation g = do
  mapM_ (kind IS.empty) (IM.keys (nodes g))
  unless (length [() | v <- IM.elems (nodes g), binder v == Nothing] == 1) (Left "roots")
  forM_ (IM.toList (nodes g)) $ \(n,v) -> do
    bindingPath IS.empty n
    case binder v of
      Nothing -> case tag v of Gen _ -> pure (); _ -> Left "root tag"
      Just b -> case tag (nodeAt g b) of
        Gen _ -> pure ()
        _ -> unless (IS.member n (reachable g b)) (Left "containment")
  forM_ (IM.toList (nodes g)) $ \(p,v) -> do
    case tag v of
      Gen _ -> unless (flag v == Flexible) (Left "gen flag")
      _ -> pure ()
    forM_ (children (tag v)) $ \c -> do
      case tag (nodeAt g c) of Gen _ -> Left "gen child"; _ -> pure ()
      case binder (nodeAt g c) of
        Just b -> unless (b == p || underBinder g p b) (Left "domination")
        Nothing -> Left "unbound child"
  where
    bindingPath seen n
      | IS.member n seen = Left "binding cycle"
      | otherwise = do
          v <- maybe (Left "missing binder") pure (IM.lookup n (nodes g))
          maybe (pure ()) (bindingPath (IS.insert n seen)) (binder v)
    kind seen original = do
      let n = resolve g original
      unless (IS.notMember n seen) (Left "structural cycle")
      v <- maybe (Left "missing node") pure (IM.lookup n (nodes g))
      let child = kind (IS.insert n seen)
      case tag v of
        Bot -> pure Star
        BotK k -> pure k
        TyCon _ k -> pure k
        Skolem _ k -> pure k
        Gen s -> child s
        Arr a b -> do
          ka <- child a
          kb <- child b
          unless (ka == Star && kb == Star) (Left "arrow kind")
          pure Star
        Con _ ns -> do
          ks <- mapM child ns
          unless (all (== Star) ks) (Left "constructor kind")
          pure Star
        TyApp f a -> do
          kf <- child f
          ka <- child a
          applyKind kf ka
