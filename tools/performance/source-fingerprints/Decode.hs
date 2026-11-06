{-# LANGUAGE OverloadedStrings #-}
-- The new envelope is opaque to either wire decoder. Both arms consume the
-- same root and its arity. No file reads, key hashing or object admission are
-- inside this deliberately wire-only timer.
module Main where

import Prelude
import Control.Monad (forM, forM_, unless)
import System.CPUTime (getCPUTime)
import System.Environment (getArgs)
import System.Mem (performGC)
import GHC.Clock (getMonotonicTimeNSec)
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as P

main = do
  [manifest] <- getArgs
  paths <- lines <$> readFile manifest
  unless (length paths == 504) (fail "expected 504 active cold records")
  inputs <- forM paths $ \path -> do
    (err,bytes) <- P.readByteFileOrError (H.literal path) (W.maxBytes W.defaultLimits)
    unless (err == "") (fail (H.unpack err))
    pure bytes
  performGC
  start <- getMonotonicTimeNSec
  cpu <- getCPUTime
  forM_ inputs $ \bytes -> do
    result <- W.decodeGraph W.defaultLimits 2 bytes
    case result of
      T.Left message -> fail (H.unpack message)
      T.Right graph -> case reverse (W.graphRoots graph) of
        root:prefix | length prefix <= 1 -> case W.lookupGraphNode graph root of
          T.Right (W.GNode 303 refs) | length refs == 5 -> pure ()
          _ -> fail "wrong envelope"
        _ -> fail "wrong root count"
  endCpu <- getCPUTime
  end <- getMonotonicTimeNSec
  print (fromIntegral (end-start)/1e9 :: Double, fromIntegral (endCpu-cpu)/1e12 :: Double)
