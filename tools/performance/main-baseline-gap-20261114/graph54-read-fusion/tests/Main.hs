{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import Prelude
import Control.Exception (Exception, evaluate, throw, catch)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as Host
import qualified Bootstrap.Graph as G
import qualified Corpus

data Probe = Probe String deriving (Eq, Show)
instance Exception Probe
poison :: String -> a
poison = throw . Probe
-- Real exported Graph state and functions, not an extracted helper or replica.
state :: P.Int -> P.STArray s P.Int -> P.STArray s P.Int -> G.DenseValidation s
state low starts ends = G.DenseValidation (poison "unused-graph") low (poison "unused-high")
  (poison "unused-table") (poison "unused-descendants") (poison "unused-colours")
  (poison "unused-kinds") starts ends (poison "unused-visited")
ignore :: P.ST s Bool -> P.ST s P.Int
ignore action = P.stBind action (\_ -> P.stReturn 77)
bit :: P.ST s Bool -> P.ST s P.Int
bit action = P.stBind action (\b -> P.stReturn (if b then 1 else 0))
outcome :: P.Int -> IO String
outcome x = (evaluate x >>= \v -> return ("value:" ++ show v))
  `catch` (\(Probe label) -> return ("probe:" ++ label))
  `catch` (\(Host.HostError message) -> return ("host:" ++ message))
expect :: String -> P.Int -> IO ()
expect wanted x = do
  got <- outcome x
  if got == wanted then return () else error ("denseContains expected " ++ wanted ++ ", got " ++ got)
supplement :: IO ()
supplement = do
  -- 1: the DenseValidation match happens, but no field/offset demand at action WHNF.
  _ <- evaluate (G.denseContains (state (poison "low") (poison "starts") (poison "ends")) (poison "ancestor") (poison "n") :: P.ST () Bool)
  -- 2-4: first executed read: array, then ancestor, then low.
  expect "probe:starts" (P.runST (ignore (G.denseContains (state (poison "low") (poison "starts") (poison "ends")) (poison "ancestor") (poison "n"))))
  expect "probe:ancestor" (P.runST (P.stBind (P.newSTArray 1 0) (\a -> ignore (G.denseContains (state (poison "low") a (poison "ends")) (poison "ancestor") (poison "n")))))
  expect "probe:low" (P.runST (P.stBind (P.newSTArray 1 0) (\a -> ignore (G.denseContains (state (poison "low") a (poison "ends")) 0 (poison "n")))))
  -- 5-6: even ignoring Bool executes second/third reads and bounds checks.
  expect "host:array index out of bounds" (P.runST (P.stBind (P.newSTArray 1 0) (\a -> P.stBind (P.newSTArray 0 1) (\e -> ignore (G.denseContains (state 0 a e) 0 0)))))
  expect "host:array index out of bounds" (P.runST (P.stBind (P.newSTArray 1 0) (\a -> P.stBind (P.newSTArray 1 1) (\e -> ignore (G.denseContains (state 0 a e) 0 1)))))
  -- 7: first payload must stay lazy until after an invalid second read fails.
  expect "host:array index out of bounds" (P.runST (P.stBind (P.newSTArray 1 (poison "payload")) (\a -> P.stBind (P.newSTArray 0 1) (\e -> bit (G.denseContains (state 0 a e) 0 0)))))
  -- 8: ignored valid result must not force any cell payload.
  expect "value:77" (P.runST (P.stBind (P.newSTArray 1 (poison "payload")) (\a -> ignore (G.denseContains (state 0 a a) 0 0))))
  -- 9-11: exact signed Int64 endpoints and wrapping offset +1.
  expect "value:1" (boundary minBound minBound)
  expect "value:1" (boundary maxBound maxBound)
  expect "value:1" (boundary maxBound minBound)
  -- 12: wrapping offset -1 remains out of bounds, not a sparse/graph validity premise.
  expect "host:array index out of bounds" (boundary minBound maxBound)
  -- 13: reuse the same real Graph action around a write; no cached read result.
  let pair = P.runST (P.stBind (P.newSTArray 2 0) (\a ->
        P.stBind (P.newSTArray 2 2) (\e ->
          P.stBind (P.writeSTArray a 1 1) (\_ ->
            let action = G.denseContains (state 0 a e) 0 1 in
            P.stBind action (\first ->
              P.stBind (P.writeSTArray e 0 0) (\_ ->
                P.stBind action (\second -> P.stReturn (first, second))))))))
  if pair == (True,False) then return () else error "denseContains shared action cached result"
  -- 14: starts/ends may alias. Re-reading must remain legal, with original comparison.
  expect "value:0" (P.runST (P.stBind (P.newSTArray 1 5) (\a -> bit (G.denseContains (state 0 a a) 0 0))))
  where
    boundary :: P.Int -> P.Int -> P.Int
    boundary low n = P.runST (P.stBind (P.newSTArray 2 0) (\a ->
      P.stBind (P.newSTArray 2 1) (\e -> bit (G.denseContains (state low a e) low n))))
main :: IO ()
main = do
  supplement
  Corpus.main
