{-# LANGUAGE OverloadedStrings #-}
-- Drive actual source inference and cache admission with the compiler identity
-- deliberately held equal between two builds of Bootstrap.Data.
module Main where
import Prelude
import Control.Exception (bracket)
import Control.Monad (unless)
import System.Environment (getArgs)
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Map as M
import qualified Bootstrap.Separate as U
import qualified Bootstrap.SourceInference as S
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B
import MLF.Host.IO (runEntry)
import qualified MLF.Primitive as P

expect (T.Left message) = fail (B.unpack message)
expect (T.Right a) = pure a

main = runEntry $ do
  args <- getArgs
  (mode,path,expected,compiler) <- case args of
    [m,p,e] -> pure (m,p,e,B.literal (replicate 64 'a'))
    [m,p,e,identity] | Q.validSourceContextDigest (B.literal identity) -> pure (m,p,e,B.literal identity)
    _ -> fail "expected MODE PATH HIT-OR-MISS [COMPILER-SHA]"
  let fixed = "MLF-SOURCE-CRATE-QUERY-7"
      cache = B.literal path
  case (mode,U.unpack Q.sourceQueryFormat) of
    ("original",_) | Q.sourceQueryFormat == fixed -> pure ()
    ("changed",T.Right [tag,literal]) | tag == fixed && P.stringLength literal > 0 -> pure ()
    _ -> fail "wrong dictionary for this executable"
  let scopes = M.fromList P.compareString [("answer",IS.empty)]
  T.Just prepared <- expect (S.prepareSourcePlan M.empty [] [] [] scopes [] [("answer",T.Nothing,T.SIntLit 41)])
  plan <- expect (S.initializeProtection prepared M.empty)
  inventory <- expect (Q.prepareData (S.planData plan))
  contracts <- expect (S.initialContracts plan M.empty M.empty)
  (objects,report,_) <- bracket (P.acquireFileLock (cache P.++ "/.lock")) P.releaseFileLock $ \_ ->
    Q.runSourceGroups "builtin-probe" compiler cache inventory plan (S.planGroups plan) contracts [] 0 0 []
      >>= Q.cleanupQueryKey cache >>= expect
  let hits = if expected == "hit" then 1 else 0
  unless (length objects==1 && Q.reusedCount report==hits && Q.inferredCount report==1-hits)
    (fail "unexpected source group reuse")
  putStrLn (B.unpack (Q.reportJSON "builtin-probe" "" report))
