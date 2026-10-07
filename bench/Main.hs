module Main (main) where

import Control.Monad (unless)
import System.Directory (doesFileExist, findExecutable)
import System.Environment (getArgs)
import System.Exit (die, exitWith)
import System.Process (rawSystem)

-- Cabal builds the internal emlf tool dependency and adds it to PATH. Reuse
-- the process-based drivers so compiler builds and Cabal startup stay outside
-- their measured regions, and every timed compilation remains a fresh process.
main :: IO ()
main = do
  arguments <- getArgs
  compiler <- requireTool "emlf" "Run this benchmark with cabal bench."
  python <- requireTool "python3" "The benchmark drivers require Python 3."
  let (script,defaults,options) = case arguments of
        "compare-revisions":rest ->
          ("scripts/benchmark-compiler.py",
           ["--after",compiler,"--output","dist-newstyle/benchmarks/revisions.json"],rest)
        _ ->
          ("scripts/benchmark-snake.py",
           ["--emlf",compiler,"--output","dist-newstyle/benchmarks/snake.json"],arguments)
  exists <- doesFileExist script
  unless exists (die ("Cannot find " ++ script ++ "; run cabal bench in the source package."))
  -- Defaults precede user options, allowing --output and other driver options
  -- to be overridden through Cabal's --benchmark-options without a shell.
  rawSystem python (["-u",script] ++ defaults ++ options) >>= exitWith
  where
    requireTool name hint = findExecutable name >>= maybe (die (name ++ " not found. " ++ hint)) pure
