module Main (main) where

import Control.Exception (SomeException, displayException, try)
import Control.Monad (forM, unless)
import Data.List (nub)
import System.Exit (exitFailure)
import System.IO (BufferMode (..), hSetBuffering, stdout)
import Backends
import BackendCases (backendTests)
import IOTests (ioTests)
import PreludeTests (preludeTests)
import Snake (snakeTests)
import NativeOptimization (nativeOptimizationTests)

main :: IO ()
main = do
  hSetBuffering stdout LineBuffering
  withBackends $ \backends -> do
    let suite = ioTests backends ++ preludeTests backends ++ snakeTests backends ++ backendTests backends ++ nativeOptimizationTests backends
        labels = map fst suite
    unless (length labels == length (nub labels)) (fail "duplicate backend fixture labels")
    results <- forM suite $ \(label,action) -> do
      result <- try (inCase backends label action) :: IO (Either SomeException ())
      case result of
        Left err -> putStrLn ("FAIL " ++ label ++ "\n  " ++ displayException err) >> pure False
        Right () -> pure True
    audit <- try (auditBackends backends) :: IO (Either SomeException ())
    case audit of
      Left err -> putStrLn ("FAIL backend coverage audit\n  " ++ displayException err)
      Right () -> pure ()
    let failures = length (filter not results) + either (const 1) (const 0) audit
    putStrLn (show (length suite) ++ " shared IO/prelude/backend fixtures; " ++ show failures ++ " failures")
    unless (failures == 0) exitFailure
