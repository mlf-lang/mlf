{-# LANGUAGE OverloadedStrings #-}
module Main where
import qualified MLF.Host.Base as B
import MLF.Host.IO (runEntry)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Std as L
import qualified Bootstrap.Map as M
import qualified Bootstrap.X.Syntax as X
import qualified MLF.Tests.SharedFrontend as S
import GHC.Clock (getMonotonicTimeNSec)
import System.CPUTime (getCPUTime)
import System.Environment (getArgs)
import System.IO (hFlush,stdout)
import qualified Control.Exception as E
import Data.List (foldl')
import Data.Char (ord)
main :: IO ()
main = runEntry $ do
  args <- getArgs
  case args of
    [file,kind] -> do
      input <- readFile file
      E.evaluate (length input)
      let source = B.literal input
          expected = if kind == "int" then T.XCon "Int" [] else T.XCon "Bool" []
      startWall <- getMonotonicTimeNSec
      startCPU <- getCPUTime
      result <- S.recursiveRight "probe compilation" (L.mapLeft C.prettyError (C.compileWithPrelude T.NoImplicitPrelude (B.literal file) source))
      term <- S.recursiveCompilation "probe" result expected
      prepared <- S.recursiveRight "probe prepare" (R.prepare False term)
      let value = R.evaluate (L.fst prepared) (R.REnv M.empty) (X.erase term)
          correct = case value of
            T.Right (R.RInteger n) -> kind == "int" && n == 42
            T.Right (R.RBoolean b) -> kind == "bool" && b
            _ -> False
      S.check "probe exact result" correct
      -- Force the display payload too; all advertised compiler outputs used here
      -- are consumed inside this single total bundle, never assigned lazy phases.
      E.evaluate (foldl' (\acc c -> acc + ord c) (0 :: Int) (B.unpack (C.sourceType result)))
      endCPU <- getCPUTime
      endWall <- getMonotonicTimeNSec
      putStrLn (unwords ["PASS",file,"wall_ns=" ++ show (endWall-startWall),"cpu_ps=" ++ show (endCPU-startCPU)])
      hFlush stdout
    _ -> error "usage: probe FILE int|bool"
