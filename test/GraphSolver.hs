module GraphSolver (graphSolverTests) where

import Control.Monad (foldM, forM, forM_, unless)
import Control.Monad.State.Strict (get, lift)
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import MLF.Classes (lowerClassesWithImports)
import MLF.Constraint
import MLF.Elaborate (reference, schemeType)
import qualified MLF.Graph as G
import qualified MLF.Graph.Solver as Solver
import MLF.Parser (parseProgram)
import MLF.Prelude (PreludeMode (..), withPrelude)
import MLF.Syntax (Flag (..))
import qualified MLF.X.Type as T

graphSolverTests :: [(String,IO ())]
graphSolverTests =
  [ ("component solver matches every full-graph inference step", do
      counts <- forM fixtures $ \file -> do
        c <- constraints file
        solver <- right (Solver.prepare (initialGraph c))
        first <- right (Solver.unify (equalities c) solver)
        (_,expected) <- right (G.runBuild (initialGraph c) (G.unify (equalities c)))
        sameGraph expected first
        _ <- foldM (\(g,s) edge -> do
          (_,g') <- right (G.runBuild g (expandAndSolve False edge))
          s' <- right (Solver.instantiate (fromGen edge) (toNode edge) s)
          sameGraph g' s'
          pure (g',s')) (expected,first) (instances c)
        pure (length (instances c) + 1)
      putStrLn ("Component inference: " ++ show (sum counts) ++ " complete graph/index comparisons"))
  , ("component witnesses preserve separate frontier solving and identities", do
      counts <- forM fixtures $ \file -> do
        c <- constraints file
        g <- right (solve c)
        solver <- right (Solver.prepare g)
        let nonreflexive edge = not (T.alphaEq (schemeType g (fromGen edge)) (reference g (toNode edge)))
            edges = filter nonreflexive (instances c)
        forM_ edges $ \edge -> do
          (expectedCopies,expected) <- right (G.runBuild g (expandAndSolve True edge))
          (copies,result) <- right (Solver.witness (fromGen edge) (toNode edge) solver)
          unless (copies == expectedCopies) (fail "witness lost original-to-copy identity")
          sameGraph expected result
        pure (length edges)
      unless (sum counts > 100) (fail "vacuous witness comparison")
      putStrLn ("Component witnesses: " ++ show (sum counts) ++ " full-graph comparisons"))
  , ("component solver includes incoming references and protected siblings", do
      initial <- right (Solver.prepare scopedGraph)
      first <- right (Solver.unify [(4,8)] initial)
      (_,expected) <- right (G.runBuild scopedGraph (G.unify [(4,8)]))
      sameGraph expected first
      -- The merged rigid bottom is now shared by two sibling scopes. Both
      -- reverse edges must be updated, and its rigidity must be retained.
      reject (Solver.unify [(8,9)] first)
      -- Node 5 is protected by the rigid function node in the other scope.
      reject (Solver.unify [(5,9)] first))
  , ("component solver rejects malformed disconnected input", do
      let broken = scopedGraph { G.nodes = IM.adjust (\v -> v { G.tag = G.Gen 99 }) 0 (G.nodes scopedGraph) }
      reject (Solver.prepare broken)
      initial <- right (Solver.prepare scopedGraph)
      reject (Solver.unify [(4,99)] initial)
      reject (Solver.unify [(99,99)] initial))
  , ("component solver preserves deep branching scopes and separate type components", do
      let parent n | n == 0 = Nothing
                   | n == 401 = Just 0
                   | n == 301 = Just 20
                   | otherwise = Just (n-1)
          g = G.Graph (IM.fromList (concat
            [[(2*n,G.Node (G.Gen (2*n+1)) (fmap (*2) (parent n)) Flexible)
             ,(2*n+1,G.Node G.Bot (Just (2*n)) Flexible)] | n <- [0..500]])) IM.empty 1002
          points = [0,1,20,31,127,255,300,301,400,401,500]
      initial <- right (Solver.prepare g)
      forM_ [(a,b) | a <- points, b <- points, a < b] $ \(a,b) -> do
        let equations = [(2*a+1,2*b+1)]
        case (G.runBuild g (G.unify equations),Solver.unify equations initial) of
          (Left _,Left _) -> pure ()
          (Right (_,expected),Right actual) -> sameGraph expected actual
          (Left err,Right _) -> fail ("component accepted a rejected scope merge: " ++ err)
          (Right _,Left err) -> fail ("component rejected a valid scope merge: " ++ err))
  , ("expansion checks the exact fresh identity budget before allocation", do
      let expandFrom next = G.runBuild (scopedGraph { G.nextId = next }) (G.expand 2 0)
      case expandFrom (maxBound-2) of
        Left "graph identity space exhausted" -> pure ()
        other -> fail ("expected identity exhaustion, got " ++ show other)
      ((_,copies,_),expanded) <- right (expandFrom (maxBound-3))
      unless (IM.size copies == 3 && G.nextId expanded == maxBound)
        (fail "expansion did not use exactly its three reserved identities")
      right (G.validateGraph expanded))
  , ("closed-instance optimization preserves all original schemes", do
      counts <- forM (fixtures ++ ["benchmarks/" ++ name ++ "/mlf/main.emlf" |
          name <- ["binary-trees","pidigits","n-body","fannkuch-redux"]]) $ \file -> do
        c <- constraints file
        initial <- right (Solver.prepare (initialGraph c) >>= Solver.unify (equalities c))
        exact <- right (foldM (\s e -> Solver.instantiate (fromGen e) (toNode e) s) initial (instances c)
          >>= Solver.finish)
        optimized <- right (solve c)
        let expected = G.normalize exact
            gens = [n | (n,v) <- IM.toAscList (G.nodes (initialGraph c)), G.Gen _ <- [G.tag v]]
        forM_ gens $ \gen -> unless (T.alphaEq (schemeType expected gen) (schemeType optimized gen))
          (fail (file ++ ": changed scheme at " ++ show gen ++ "\n" ++
                 show (schemeType expected gen) ++ "\n" ++ show (schemeType optimized gen)))
        pure (length gens)
      putStrLn ("Closed instances: " ++ show (sum counts) ++ " independent scheme comparisons"))
  , ("closed-instance matching checks repeated, rigid and frontier variables", do
      let graph fieldFlag fieldBinder rightName = G.Graph (IM.fromList
            [(0,G.Node (G.Gen 1) Nothing Flexible), (1,G.Node (G.Con "Unit" []) (Just 0) Rigid)
            ,(2,G.Node (G.Gen 3) (Just 0) Flexible), (3,G.Node (G.Arr 4 4) (Just 2) Flexible)
            ,(4,G.Node G.Bot (Just fieldBinder) fieldFlag)
            ,(5,G.Node (G.Gen 6) (Just 0) Flexible), (6,G.Node (G.Arr 7 8) (Just 5) Flexible)
            ,(7,G.Node (G.Con "Int" []) (Just 6) Rigid), (8,G.Node (G.Con rightName []) (Just 6) Rigid)]) IM.empty 9
          run g = Solver.prepare g >>= Solver.instantiateClosed 2 6 >>= Solver.finish
      reject (run (graph Flexible 2 "Bool"))
      reject (run (graph Rigid 2 "Int"))
      result <- right (run (graph Flexible 0 "Int"))
      unless (G.tag (G.nodeAt result 4) == G.Con "Int" [])
        (fail "external frontier was mistaken for a quantified variable")
      _ <- right (run (graph Flexible 2 "Int"))
      pure ())
  ]

fixtures :: [FilePath]
fixtures =
  [ "examples/snake.emlf"
  , "examples/monad-state-do.emlf"
  , "examples/monad-maybe.emlf"
  , "examples/contextual-instance.emlf"
  , "examples/partial-annotation.emlf"
  ]

constraints :: FilePath -> IO Constraints
constraints file = do
  source <- readFile file
  parsed <- right (parseProgram file source)
  let (imports,program) = withPrelude ImplicitPrelude parsed
  (lowered,_) <- right (lowerClassesWithImports imports program)
  right (generateProgram lowered)

expandAndSolve :: Bool -> Edge -> G.Build (IM.IntMap G.NodeId)
expandAndSolve separately edge = do
  -- This path deliberately uses the original full-graph operations and
  -- never calls the component solver or uses its reverse-edge indexes.
  g <- get
  let target = G.resolve g (toNode edge)
  destination <- maybe (lift (Left "missing target binder")) pure (G.binder (G.nodeAt g target))
  (root,copies,frontier) <- referenceExpand (fromGen edge) destination
  if separately then do
    unless (null frontier) (G.unify frontier)
    G.unify [(root,target)]
  else G.unify (frontier ++ [(root,target)])
  pure copies

-- The original uncached expansion is an independent oracle for both the
-- component solver and the shared scope/kind analysis in production expand.
referenceExpand :: G.NodeId -> G.NodeId -> G.Build (G.NodeId,IM.IntMap G.NodeId,[(G.NodeId,G.NodeId)])
referenceExpand gen destination = do
  g <- get
  let source = G.genRoot g gen
      visit seen x
        | IS.member n seen = seen
        | not (G.underBinder g n gen) = IS.insert n seen
        | otherwise = foldl visit (IS.insert n seen) (G.children (G.tag (G.nodeAt g n)))
        where n = G.resolve g x
      originals = IS.toList (visit IS.empty source)
  copies <- IM.fromList <$> mapM (\n -> do c <- G.freshId; pure (n,c)) originals
  let copy n = IM.findWithDefault (G.resolve g n) (G.resolve g n) copies
      root = copy source
      frontier = [n | n <- originals, not (G.underBinder g n gen)]
      copyTag t = case t of
        G.Arr a b -> G.Arr (copy a) (copy b)
        G.Con c ns -> G.Con c (map copy ns)
        G.Gen n -> G.Gen (copy n)
        G.TyApp a b -> G.TyApp (copy a) (copy b)
        _ -> t
  forM_ originals $ \n -> do
    k <- lift (G.kindAt g n)
    let v = G.nodeAt g n
        new | n `elem` frontier = G.Node (G.bottomTag k) (Just destination) Flexible
            | n == source = G.Node (copyTag (G.tag v)) (Just destination) Flexible
            | otherwise = G.Node (copyTag (G.tag v))
                (fmap (\b -> if G.resolve g b == G.resolve g gen then root else copy b) (G.binder v)) (G.flag v)
    G.setNode (copy n) new
  pure (root,copies,[(n,copy n) | n <- frontier])

sameGraph :: G.Graph -> Solver.Solver -> IO ()
sameGraph expected solver = do
  actual <- right (Solver.finish solver)
  unless (actual == expected) (fail ("component graph differs\nexpected: " ++ show expected ++ "\nactual: " ++ show actual))

right :: Either String a -> IO a
right = either fail pure

reject :: Either String a -> IO ()
reject (Left _) = pure ()
reject (Right _) = fail "unexpected success"

scopedGraph :: G.Graph
scopedGraph = G.Graph (IM.fromList
  [(0,G.Node (G.Gen 1) Nothing Flexible)
  ,(1,G.Node (G.Con "Unit" []) (Just 0) Rigid)
  ,(2,G.Node (G.Gen 3) (Just 0) Flexible)
  ,(3,G.Node (G.Arr 4 5) (Just 2) Rigid)
  ,(4,G.Node G.Bot (Just 3) Rigid)
  ,(5,G.Node G.Bot (Just 3) Flexible)
  ,(6,G.Node (G.Gen 7) (Just 0) Flexible)
  ,(7,G.Node (G.Arr 8 9) (Just 6) Flexible)
  ,(8,G.Node G.Bot (Just 7) Flexible)
  ,(9,G.Node (G.Con "Int" []) (Just 7) Rigid)]) IM.empty 10
