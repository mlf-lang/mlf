{-# LANGUAGE OverloadedStrings #-}
-- Compare two readers of the same addressed records. File acquisition and
-- object admission are outside the timer. Both readers check the payload SHA.
module Main where

import Prelude
import Control.Monad (forM, forM_, unless)
import GHC.Clock (getMonotonicTimeNSec)
import System.CPUTime (getCPUTime)
import System.Environment (getArgs)
import System.Mem (performGC)
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as P

main = do
  [manifest, arm, state] <- getArgs
  paths <- lines <$> readFile manifest
  unless (length paths == 504 && arm `elem` ["full","early"] && state `elem` ["hit","wrong"]) (fail "probe inputs")
  inputs <- forM paths $ \path -> do
    let key = H.literal (reverse (take 64 (drop 5 (reverse path))))
    unless (Q.validSourceContextDigest key) (fail "invalid cache address")
    (err,bytes) <- P.readByteFileOrError (H.literal path) (W.maxBytes W.defaultLimits)
    unless (err == "") (fail (H.unpack err))
    pure (key,bytes)
  let neighbor = map fst (tail inputs ++ take 1 inputs)
  performGC
  start <- getMonotonicTimeNSec
  cpu <- getCPUTime
  forM_ (zip inputs neighbor) $ \((actual,bytes),wrong) -> do
    unless (actual /= wrong) (fail "repeated record")
    let expected = if state == "hit" then actual else wrong
    graph <- if arm == "early"
      then W.decodeGraphWithGate W.defaultLimits 2 (Q.sourceAddressGate expected) bytes
      else W.decodeGraph W.defaultLimits 2 bytes
    matched <- case graph of
      T.Left "cached query key mismatch" | arm == "early" -> pure False
      T.Left err -> fail (H.unpack err)
      T.Right g -> case Q.binaryQuery g of
        T.Right (Q.LocalQuery key _ _) -> pure (key == expected)
        _ -> fail "invalid source envelope"
    unless (matched == (state == "hit")) (fail "lookup result changed")
  cpuEnd <- getCPUTime
  end <- getMonotonicTimeNSec
  print (fromIntegral (end-start)/1e9 :: Double, fromIntegral (cpuEnd-cpu)/1e12 :: Double)
