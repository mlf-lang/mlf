{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Exception (evaluate)
import Data.List (foldl')
import GHC.Stats (allocated_bytes, getRTSStats)
import System.CPUTime (getCPUTime)
import System.Environment (getArgs)
import System.Mem (performGC)
import qualified Bootstrap.Data as Data
import qualified Bootstrap.Fresh as Fresh
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Std as Std
import qualified Bootstrap.Surface as Surface
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H

source n = H.literal $ unlines
  ["-- mlf:syntax shared-haskell-v1",
   "{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}",
   "module Bench where {",
   concat ["f" ++ show i ++ " = (M.+);\n" | i <- [1..n]], "}"]

parseChecksum text = case Parser.parseModuleWithProfile T.SharedHaskellV1 "Bench.hs" text of
  T.Left message -> error (H.unpack message)
  T.Right (T.SourceModule _ _ _ _ _ _ _ values _ _) -> foldl' add 0 values
  where
    add total (_,_,T.SCallSite label (T.SourceSpan packageName owner file sl sc el ec) (T.SVar name)) =
      total + sl + sc + el + ec + fromIntegral (sum (map (length . H.unpack) [label,packageName,owner,file,name]))
    add _ _ = error "unexpected parsed operator shape"

-- Exact append accumulator replaced by 9815b98; the normalizer is otherwise
-- the production function, so this isolates accumulator cost on wide rows.
oldNormalizeRow env values (Surface.MatchRow patterns body rowIndex) = do
  (normalized, rhs) <- Std.foldM
    (\(done,current) (value,pattern) -> do
      (next,updated) <- Surface.normalizePattern env value pattern current
      Fresh.freshPure (done ++ [next],updated)) ([],body) (zip values patterns)
  Fresh.freshPure (Surface.MatchRow normalized rhs rowIndex)

rowChecksum normal width = case Fresh.runFresh []
  (normal Data.emptyDataEnv (replicate width (T.SVar "value"))
    (Surface.MatchRow [T.SIntPattern (fromIntegral i) | i <- [1..width]] (T.SVar "body") 17)) of
  T.Left message -> error (H.unpack message)
  T.Right (Surface.MatchRow patterns _ index) -> foldl' add index patterns
  where
    add total (T.SIntPattern number) = total + number
    add _ _ = error "normalization changed a column"

main = do
  [mode,count] <- getArgs
  let width = read count
      text = source width
  evaluate (length (H.unpack text))
  performGC
  beforeStats <- getRTSStats
  before <- getCPUTime
  checksum <- evaluate $ case mode of
    "parse" -> parseChecksum text
    "rows-before" -> rowChecksum oldNormalizeRow width
    "rows-after" -> rowChecksum Surface.normalizeRow width
    _ -> error "expected parse, rows-before or rows-after"
  after <- getCPUTime
  performGC
  afterStats <- getRTSStats
  putStrLn (mode ++ "," ++ count ++ "," ++ show (fromIntegral (after-before) / 1e12 :: Double) ++
    "," ++ show (allocated_bytes afterStats - allocated_bytes beforeStats) ++ "," ++ show checksum)
