{-# LANGUAGE BangPatterns #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
-- Study only. A single-threaded driver owns the stack for one process.
module WarmClock (io, demand, hit, writeKey, dump) where

import Prelude
import Control.Exception (evaluate)
import Control.Monad (unless)
import Data.IORef
import qualified Data.Map.Strict as Map
import Data.List (intercalate)
import Data.Word (Word64)
import GHC.Clock (getMonotonicTimeNSec)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
import System.IO (hPutStr, stderr)
import System.IO.Unsafe (unsafePerformIO)

data Frame = Frame [String] !Word64
data Count = Count !Int !Word64 !Word64
{-# NOINLINE stack #-}
stack :: IORef [Frame]
stack = unsafePerformIO (newIORef [])
{-# NOINLINE totals #-}
totals :: IORef (Map.Map [String] Count)
totals = unsafePerformIO (newIORef Map.empty)

{-# NOINLINE io #-}
io :: String -> IO a -> IO a
io name action = do
  before <- readIORef stack
  let path = name : case before of { [] -> []; Frame parent _ : _ -> parent }
  writeIORef stack (Frame path 0 : before)
  start <- getMonotonicTimeNSec
  result <- action >>= evaluate
  end <- getMonotonicTimeNSec
  let elapsed = end - start
  after <- readIORef stack
  case after of
    Frame current children : rest | current == path && children <= elapsed -> do
      let parent = case rest of
            [] -> []
            Frame key n : others -> Frame key (n+elapsed) : others
          add (Count a b c) (Count x y z) = Count (a+x) (b+y) (c+z)
      writeIORef stack parent
      modifyIORef' totals (Map.insertWith add path (Count 1 elapsed (elapsed-children)))
    _ -> fail "invalid profiling nesting or clock"
  pure result

-- Only runs if the original consumer demands the expression. This helper
-- stays out of the shared language modules and out of the plain/coarse arms.
{-# NOINLINE demand #-}
demand :: String -> a -> a
demand name value = unsafePerformIO (io name (evaluate value))

hit :: IO (a,b,c) -> IO (a,b,c)
hit action = io "hit" $ do
  result@(_,_,decoded) <- action
  _ <- evaluate decoded
  pure result

writeKey :: B.String -> B.String -> IO ()
writeKey file key = do
  _ <- io "scratch.force" (evaluate (P.stringLength key))
  io "scratch.write" (P.writeFile file key)

dump :: IO ()
dump = do
  frames <- readIORef stack
  unless (null frames) (fail "unfinished profiling span")
  stats <- readIORef totals
  hPutStr stderr (unlines [unwords [intercalate "/" (reverse path), show n, show total, show self]
                          | (path, Count n total self) <- Map.toList stats])
