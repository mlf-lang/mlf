module Main (main) where

import System.Directory (findExecutable)
import System.Exit (die, exitWith)
import System.Process (rawSystem)

main :: IO ()
main = do
  python <- findExecutable "python3" >>= maybe (die "Benchmark harness tests require Python 3") pure
  rawSystem python ["-m", "unittest", "discover", "-s", "test", "-p", "test_benchmark*.py", "-v"] >>= exitWith
