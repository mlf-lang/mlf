{-# LANGUAGE BangPatterns #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Prototype.PrefixReasons (observeReason, snapshot, writeCapture) where
import Prelude
import Data.Int (Int64)
import Data.IORef
import Control.Exception (evaluate, throwIO)
import Control.Monad (unless)
import System.IO (withFile,IOMode(WriteMode),hPutStrLn)
import System.IO.Unsafe (unsafePerformIO)
data Counts = Counts !Int !Int !Int !Int
{-# NOINLINE counts #-}
counts :: IORef Counts
counts = unsafePerformIO (newIORef (Counts 0 0 0 0))
{-# NOINLINE observeReason #-}
observeReason :: Int64 -> Int64
observeReason answer = unsafePerformIO $ do
  reason <- evaluate answer
  unless (reason >= 0 && reason <= 2) (throwIO (userError "invalid prefix reason"))
  accepted <- atomicModifyIORef' counts $ \old@(Counts total no conflict hole) ->
    if total >= 1000000 then (old,False)
    else let !next = case reason of
               0 -> Counts (total+1) (no+1) conflict hole
               1 -> Counts (total+1) no (conflict+1) hole
               _ -> Counts (total+1) no conflict (hole+1)
         in (next,True)
  unless accepted (throwIO (userError "prefix reason count cap"))
  pure reason
snapshot :: IO (Int,Int,Int,Int)
snapshot = do
  Counts a b c d <- readIORef counts
  pure (a,b,c,d)
writeCapture :: FilePath -> IO ()
writeCapture path = do
  (a,b,c,d) <- snapshot
  unless (a>0 && a==b+c+d) (throwIO (userError "empty or inconsistent prefix counts"))
  withFile path WriteMode $ \h -> do
    hPutStrLn h "prefix-reasons-v1\tcalls\toriginal_false\tmapping_conflict\told_bottom_hole"
    hPutStrLn h ("complete\t"++show a++"\t"++show b++"\t"++show c++"\t"++show d)
