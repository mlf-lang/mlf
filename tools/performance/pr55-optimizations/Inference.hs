{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Exception (evaluate)
import Data.List (foldl')
import GHC.Stats (allocated_bytes, getRTSStats)
import System.CPUTime (getCPUTime)
import System.Environment (getArgs)
import System.Mem (performGC)
import Text.Printf (printf)
import qualified Bootstrap.Elaborate as E
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as Solver
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H

-- Compile this same file against the baseline and candidate source roots. It
-- invokes production entry points in both binaries; there is no copied fast
-- implementation or simulated replacement in the timed path.
right :: T.Either H.String a -> IO a
right result = case result of
  T.Left message -> fail (H.unpack message)
  T.Right value -> pure value

graph :: H.Int -> T.Graph
graph depth = G.mkGraph (IM.fromList entries) IM.empty (2*depth+2)
  where
    node tag parent = T.Node tag parent T.Flexible
    entries = (0,node (T.GGen 1) T.Nothing) :
      (2*depth+1,node T.GBot (T.Just (2*depth-1))) : concat
        [[(2*i+1,node (T.GArr (2*i+2) (2*i+3)) (T.Just (if i == 0 then 0 else 2*i-1))),
          (2*i+2,node T.GBot (T.Just (2*i+1)))] | i <- [0..depth-1]]

digest :: [H.Int] -> H.Int
digest = foldl' (\total n -> total*31+n) 0

prepare :: String -> H.Int -> IO (() -> H.Int)
prepare family size = case family of
  "bounds" -> bounds E.prepareSolvedTypes
  "bounds-dense" -> bounds E.prepareValidatedSolvedTypes
  "local-path" -> do
    -- Two disjoint branches in one lawful binding tree share the final path.
    -- Prepare both lists before timing the commonLocalBinderPath operation.
    let shared = [2*size+1..3*size]
        left = [1..size] ++ shared
        rightPath = [-1,-2..0-size] ++ shared
    _ <- evaluate (length left + length rightPath)
    pure $ \() -> case Solver.commonLocalBinderPath (error "same scope needed an index")
      (Solver.LocalBinderPath left 0) (Solver.LocalBinderPath rightPath 0) of
      Solver.LocalBinderPath path scope -> scope + digest path
  _ -> fail "expected bounds, bounds-dense or local-path"
  where
    bounds context = do
      solver <- right (Solver.prepare (graph size)) >>= right . Solver.finishNormalized
      -- Graph admission, normalization and input materialization are outside
      -- the interval; creating and demanding the translation index are inside.
      _ <- evaluate (foldl' (\count value -> if G.equalNode value value then count+1 else count)
        (0::Int) (IM.elems (G.nodes (Solver.solverGraph solver))))
      _ <- evaluate (sum (map IS.size (IM.elems (Solver.bindingChildren solver))))
      pure $ \() -> let prepared = context solver in sum
        [digest [n | (T.XTyVar n,_) <- E.boundsAtIn prepared parent] | parent <- [0..2*size+1]]

main :: IO ()
main = do
  args <- getArgs
  (family,size) <- case args of
    [family,value] | [(n,"")] <- reads value, n > 0 -> pure (family,n)
    _ -> fail "usage: inference-probe FAMILY POSITIVE_SIZE +RTS -T"
  work <- prepare family size
  performGC
  beforeStats <- getRTSStats
  before <- getCPUTime
  checksum <- evaluate (work ())
  after <- getCPUTime
  performGC
  afterStats <- getRTSStats
  printf "{\"family\":%s,\"size\":%d,\"checksum\":%d,\"cpu_seconds\":%.9f,\"allocated_bytes\":%d}\n"
    (show family) size checksum (fromIntegral (after-before) / 1e12 :: Double)
    (allocated_bytes afterStats - allocated_bytes beforeStats)
