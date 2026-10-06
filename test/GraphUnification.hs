module GraphUnification (graphUnificationTests) where

import Control.Monad (foldM, forM, forM_, unless)
import Data.Either (isRight)
import qualified Data.IntMap.Strict as IM
import MLF.Constraint
import MLF.Graph
import MLF.Parser (parseExpr)
import MLF.Syntax (Flag (..))
import GraphValidation (smallGraphs)
import GraphUnificationReference (referenceUnify)

graphUnificationTests :: [(String, IO ())]
graphUnificationTests =
  [ ("indexed unification agrees with map-based reference", do
      outcomes <- forM cases $ \(g,eqs) -> compareUnifiers g eqs
      let successes = length (filter isRight outcomes)
      unless (successes > 100 && successes < length cases - 100)
        (fail "unification corpus lacks successful and rejected merges")
      putStrLn ("Graph unification: " ++ show (length cases) ++ " cases; " ++ show successes ++ " accepted"))
  , ("indexed graph analysis preserves sparse and negative identities", do
      forM_ (take 80 cases) $ \(g,eqs) -> do
        expected <- compareUnifiers g eqs
        forM_ [(\n -> n * 100000), (subtract 30), (+ (maxBound - 20)), (+ (minBound + 1))] $ \rename -> do
          let shifted = renameGraph rename g
          actual <- compareUnifiers shifted [(rename a,rename b) | (a,b) <- eqs]
          unless (fmap (renameGraph rename) expected == actual || (not (isRight expected) && not (isRight actual)))
            (fail "unification depends on numeric identity layout"))
  , ("indexed unification agrees on successive scoped expansions", do
      forM_ programs $ \(source,accepted) -> do
        c <- either fail pure (parseExpr "<unification reference>" source >>= generate)
        initial <- compareUnifiers (initialGraph c) (equalities c)
        result <- foldM step initial (instances c)
        unless (isRight result == accepted) (fail ("unexpected reference outcome: " ++ source)))
  , ("dependency traversal rejects structural cycles created by merging", do
      let g = Graph (IM.fromList
            [(0,Node (Gen 1) Nothing Flexible)
            ,(1,Node (Arr 2 3) (Just 0) Flexible)
            ,(2,Node Bot (Just 1) Flexible)
            ,(3,Node Bot (Just 1) Flexible)]) IM.empty 4
      result <- compareUnifiers g [(1,2)]
      unless (not (isRight result)) (fail "occurs check accepted a self-cycle"))
  ]
  where
    step result edge = case result of
      Left err -> pure (Left err)
      Right g -> do
        let target = resolve g (toNode edge)
        destination <- maybe (fail "missing target binder") pure (binder (nodeAt g target))
        ((root,_,frontier),expanded) <- either fail pure (runBuild g (expand (fromGen edge) destination))
        compareUnifiers expanded (frontier ++ [(root,target)])

compareUnifiers :: Graph -> [(NodeId,NodeId)] -> IO (Either String Graph)
compareUnifiers g eqs = do
  let actual = snd <$> runBuild g (unify eqs)
      expected = snd <$> runBuild g (referenceUnify eqs)
  case (actual,expected) of
    (Left _,Left _) -> pure ()
    (Right a,Right b) | a == b -> pure ()
    _ -> fail ("unification differs\n" ++ show g ++ "\n" ++ show eqs ++
          "\nactual: " ++ show actual ++ "\nreference: " ++ show expected)
  pure actual

cases :: [(Graph,[(NodeId,NodeId)])]
cases =
  [ (g { nodes = IM.mapWithKey (\n v -> v { flag = case n of
        1 -> a; 2 -> b; 3 -> c; _ -> flag v }) (nodes g) },eqs)
  | g <- filter (isRight . validateGraph) smallGraphs
  , a <- [Flexible,Rigid], b <- [Flexible,Rigid], c <- [Flexible,Rigid]
  , eqs <- [[],[(1,2)],[(1,3)],[(2,3)],[(2,2)],[(0,1)],
            [(1,2),(2,3)],[(2,3),(1,2)],[(3,2),(2,1)]]
  ]

renameGraph :: (NodeId -> NodeId) -> Graph -> Graph
renameGraph f g = Graph
  (IM.fromList [(f n,v { tag = renameTag (tag v), binder = fmap f (binder v) }) | (n,v) <- IM.toList (nodes g)])
  (IM.fromList [(f n,f p) | (n,p) <- IM.toList (links g)]) (f (nextId g))
  where
    renameTag t = case t of
      Arr a b -> Arr (f a) (f b)
      Con c ns -> Con c (map f ns)
      TyApp a b -> TyApp (f a) (f b)
      Gen n -> Gen (f n)
      _ -> t

programs :: [(String,Bool)]
programs =
  [ ("\\x -> x",True)
  , ("\\x -> x x",False)
  , ("\\f x -> f x",True)
  , ("let id = \\x -> x in let a = id 42 in id true",True)
  , ("(\\(f : forall a. a -> a) -> f f) (\\x -> x)",True)
  , ("let choose = ((\\x y -> x) : forall a. a -> a -> a) in let id = \\x -> x in let g = choose id in g g",True)
  , ("(\\x -> x) : forall (a >= forall b. b -> b). a -> a",True)
  , ("(\\x -> x) : Int -> Bool",False)
  ]
