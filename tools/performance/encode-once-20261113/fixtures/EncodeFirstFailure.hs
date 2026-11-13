{-# LANGUAGE OverloadedStrings #-}
module Main where

-- Candidate-only supplement. Calls the actual new helper, not a local copy.
-- The source author has not compiled or run this fixture.
import Prelude
import Control.Exception (evaluate)
import Control.Monad (forM, unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.CrateGraph as C
import qualified Bootstrap.QueryGraph as Q
import qualified Bootstrap.Bitstream as W
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

need label okay = unless okay (errorWithoutStackTrace label)
right label result = case result of
  T.Left message -> errorWithoutStackTrace (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value

-- Frozen original protocol: first a nonpersistent authoritative Input, then
-- a persistent derived node whose sole read is that freshly recorded Input.
oldPair wanted value session = do
  observed <- Q.record (Q.inputKey wanted) [] False value session
  case observed of
    T.Left message -> pure (T.Left message)
    T.Right (leaf,next) -> Q.record wanted [Q.edge leaf] True value next

expectFirstLeft action = do
  answer <- action
  case answer of
    T.Left message -> need "wrong first encoding diagnostic"
      (B.unpack message == "binary constructor tag out of range")
    T.Right _ -> errorWithoutStackTrace "invalid constructor tag was accepted"

nodeSnapshot node =
  (B.unpack (Q.nodeKey node), B.unpack (Q.nodeHash node),
   [(B.unpack k,B.unpack h) | (k,h) <- Q.nodeReads node],
   case Q.nodePayload node of T.Nothing -> Nothing; T.Just h -> Just (B.unpack h))
nodesSnapshot = map nodeSnapshot . M.elems
byteSnapshot bytes = do
  size <- P.lengthByteArray bytes
  forM [0..size-1] $ \i -> do
    byte <- P.readByteArray bytes i
    pure (fromIntegral byte :: Int)
sessionSnapshot (Q.Session path config generation old current pending) = do
  payloads <- forM (M.toList pending) $ \(digest,bytes) -> do
    raw <- byteSnapshot bytes
    pure (B.unpack digest,raw)
  pure (B.unpack path,B.unpack config,B.unpack generation,
        nodesSnapshot old,nodesSnapshot current,payloads)
forceString [] = ()
forceString (x:xs) = x `seq` forceString xs
observe (node,session) = do
  snapshot <- sessionSnapshot session
  let text = show (nodeSnapshot node,snapshot)
  evaluate (forceString text)
  pure text

main = do
  let invalid = W.VNode (-1) (errorWithoutStackTrace "poison children forced")
      poisonedKey = errorWithoutStackTrace "poison key forced"
      poisonedSession = errorWithoutStackTrace "poison session forced"
  expectFirstLeft (oldPair poisonedKey invalid poisonedSession)
  expectFirstLeft (C.recordInputAndDerived poisonedKey invalid poisonedSession)
  putStrLn "PASS\tfirst-encoding-left-before-poison"

  let wanted = Q.key "Datatype" "Finite"
      value = W.VNode 420 [W.VInt 42,W.VText "finite\x03b1\x1f600"]
      initial = Q.Session "no-file-io" "first-encoding-fixture-v1" "" M.empty M.empty M.empty
  old <- oldPair wanted value initial >>= right "frozen finite encoding"
  actual@(node,session) <- C.recordInputAndDerived wanted value initial
    >>= right "candidate finite encoding"
  oldText <- observe old
  actualText <- observe actual
  need "finite exact returned node/session/payload bytes changed" (oldText == actualText)
  let digest = Q.nodeHash node
      expectedInput = Q.QueryNode (Q.inputKey wanted) digest [] T.Nothing
      expectedDerived = Q.QueryNode wanted digest [Q.edge expectedInput] (T.Just digest)
      expectedNodes = M.fromList P.compareString
        [(Q.nodeKey expectedInput,expectedInput),(wanted,expectedDerived)]
  need "finite Input/derived row shape changed"
    (nodesSnapshot (Q.currentNodes session) == nodesSnapshot expectedNodes)
  case session of
    Q.Session _ _ _ previous _ pending -> do
      need "finite previous state changed" (M.size previous == 0)
      need "finite pending digest inventory changed"
        (map (B.unpack . fst) (M.toList pending) == [B.unpack digest])
  putStrLn "PASS\tfinite-success-exact-session-and-bytes"
  putStrLn "SUMMARY\t2\t2"
