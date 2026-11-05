{-# LANGUAGE BangPatterns #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Counters (tick, named, reset, snapshot) where

import Prelude
import Data.Int (Int64)
import Data.IORef
import Data.List (sortOn, intercalate)
import System.IO.Unsafe (unsafePerformIO)

-- Only the demanded result thunk triggers an event. In particular tick never
-- inspects its result, an AST, a map, or an action's input. Depth is explicitly
-- threaded along the original recursion, not obtained by walking the input.
data Stat = Stat !Int64 !Int64 !Int64
{-# NOINLINE counters #-}
counters :: IORef [(String, Stat)]
counters = unsafePerformIO (newIORef [])

{-# NOINLINE tick #-}
tick :: String -> Int64 -> a -> a
tick label depth value = unsafePerformIO $ do
  atomicModifyIORef' counters $ \rows ->
    let update [] = [(label, Stat 1 depth depth)]
        update ((key, Stat calls total maximum):rest)
          | key == label = (key, Stat (calls + 1) (total + depth) (max maximum depth)):rest
          | otherwise = let !tailRows = update rest
                        in (key, Stat calls total maximum):tailRows
        !updated = update rows
    in (updated, ())
  pure value

{-# NOINLINE named #-}
named :: String -> String -> Int64 -> a -> a
named family event = tick (family ++ "." ++ event)

reset :: IO ()
reset = writeIORef counters []

snapshot :: IO String
snapshot = do
  rows <- readIORef counters
  let row (key, Stat calls total maximum) = show key ++ ":{\"events\":" ++ show calls ++
        ",\"depth_sum\":" ++ show total ++ ",\"max_depth\":" ++ show maximum ++ "}"
  pure ("{" ++ intercalate "," (map row (sortOn fst rows)) ++ "}")
