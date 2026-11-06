{-# LANGUAGE OverloadedStrings #-}
module Probe (writeKey, hashKey, readRecord, admit) where
import Prelude
import Control.Exception (evaluate)
import GHC.Clock (getMonotonicTimeNSec)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
import System.IO (hPutStrLn, stderr)

-- Emit after the measured region. The key's strict Text and cached scalar
-- count are forced by stringLength. writeFile retains its normal UTF-8/host
-- call. Do not pre-encode another ByteString just to count bytes.
writeKey :: B.String -> B.String -> IO ()
writeKey file key = do
  start <- getMonotonicTimeNSec
  size <- evaluate (P.stringLength key)
  forced <- getMonotonicTimeNSec
  P.writeFile file key
  written <- getMonotonicTimeNSec
  hPutStrLn stderr (unwords ["key", show size, show (forced-start), show (written-forced)])

timed label action = do
  start <- getMonotonicTimeNSec
  result <- action
  end <- getMonotonicTimeNSec
  hPutStrLn stderr (unwords [label, show (end-start)])
  pure result

hashKey path = timed "read+sha" $ do
  digest <- P.fileDigest path
  _ <- evaluate (P.stringLength digest)
  pure digest

-- Force Either through wire, raw object validation and PreparedRaw admission.
-- The rest of finalization/inference stays at its original demand site.
readRecord readInput = timed "read+decode" $ do
  result@(_, _, admission) <- readInput
  _ <- evaluate admission
  pure result

admit action = timed "prepared" $ do
  result@(_, admission) <- action
  _ <- evaluate admission
  pure result
