-- Source only: run under a separately admitted profiling-controls build.
module Main where
import Control.Exception (evaluate)
import Control.Monad (unless)
import System.Environment (getArgs)

-- Runtime-sized, lazy list; producer does not demand it before returning.
producer n = {-# SCC "TOY_PRODUCER" #-} map (+ 1) [1 .. n :: Int]
consumer xs = {-# SCC "TOY_CONSUMER" #-} sum xs
main = do
  [size] <- getArgs
  let n = read size :: Int
      payload = producer n
      independent = (42 :: Int, error "deferred inventory unexpectedly demanded" :: Either String [Int])
  unless (fst independent == 42) (fail "no-demand control")
  result <- evaluate (consumer payload)
  unless (result == n * (n + 3) `div` 2) (fail "delayed producer result")
  putStrLn "PASS deferred-demand"
