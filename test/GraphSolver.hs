module GraphSolver (graphSolverTests) where

import Control.Monad (foldM, forM, forM_, unless)
import Control.Monad.State.Strict (get, lift)
import qualified Data.IntMap.Strict as IM
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
      reject (Solver.unify [(4,99)] initial))
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
  (root,copies,frontier) <- G.expand (fromGen edge) destination
  if separately then do
    unless (null frontier) (G.unify frontier)
    G.unify [(root,target)]
  else G.unify (frontier ++ [(root,target)])
  pure copies

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
