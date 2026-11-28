{-# LANGUAGE OverloadedStrings #-}
module Main where

-- Focused production QueryGraph tests. This does not replace existing gates.
-- "pure" does not write; "publication ROOT" requires a fresh isolated root.
import Prelude
import Control.Monad (forM_, unless)
import Data.List (isInfixOf)
import System.Environment (getArgs, setEnv, unsetEnv)
import System.Directory (createDirectory, doesPathExist)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.QueryGraph as Q
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.ArtifactStorage as Storage
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

need label okay = unless okay (errorWithoutStackTrace label)
right :: String -> T.Either B.String a -> IO a
right label result = case result of
  T.Left message -> errorWithoutStackTrace (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value
reject :: String -> String -> T.Either B.String a -> IO ()
reject label expected result = case result of
  T.Left message -> need (label ++ ": wrong diagnostic: " ++ B.unpack message)
    (isInfixOf expected (B.unpack message))
  T.Right _ -> errorWithoutStackTrace (label ++ ": unexpectedly accepted")
pass label = putStrLn ("PASS " ++ label)
txt = B.literal
hashA = txt (replicate 64 'a')
hashB = txt (replicate 64 'b')
listing = W.VNode 1
bytesFor label value = W.encode W.defaultLimits 6 [value] >>= right label
generationRoot nodes = Q.encodeIndex "config" (M.fromList P.compareString [(Q.nodeKey n,n) | n <- nodes])
admit value = do
  graph <- W.planGraph W.defaultLimits [value]
  Q.admitIndex "config" graph

pureTests = do
  right "scalar-length identity fields" (Q.canonicalFields "1:😊0:1::") >>=
    need "Unicode, empty and colon fields" . (== ["😊","",":"])
  right "raw padded length" (Separate.unpack "01:a") >>= need "raw unpack accepts padding" . (== ["a"])
  reject "canonical padding" "noncanonical query identity" (Q.canonicalFields "01:a0:")
  reject "framing failure after padding" "malformed module artifact framing" (Q.canonicalFields "00:x")
  reject "truncation after padding" "truncated module artifact" (Q.canonicalFields "00:2:a")
  reject "length wider than nine digits" "malformed module artifact framing" (Q.canonicalFields "0000000000:")

  let binding name = Q.key "Binding" name
      leaf = Q.QueryNode (binding "leaf") hashA [] T.Nothing
      root = Q.QueryNode (binding "root") hashB [Q.edge leaf,Q.edge leaf] (T.Just hashB)
      fields = [W.VText "MLF-CRATE-QUERY-GRAPH-3",W.VText "config",listing (map W.VText ["leaf","root"]),
                listing [],listing [],listing [],listing (map W.VInt [0,1]),listing (map W.VText [hashA,hashB]),
                listing (map W.VInt [0,2]),listing (map W.VInt [0,0]),listing [W.VInt 1]]
      authored = W.VNode 412 fields
      change i column = W.VNode 412 (take i fields ++ [column] ++ drop (i+1) fields)
  value <- right "current writer" (generationRoot [root,leaf])
  bytes <- bytesFor "current binary encode" value
  expected <- bytesFor "independent columns" authored
  Storage.sameBytes bytes expected >>= need "column bytes, order, duplicate reads, payload presence"
  graph <- W.decodeGraph W.defaultLimits 6 bytes >>= right "current binary decode"
  (nodes,canonical) <- right "current admission" (Q.admitIndex "config" graph)
  need "canonical row keys" canonical
  need "restored ordered rows" (and (zipWith Q.sameNode [leaf,root] (M.elems nodes)) && M.size nodes == 2)
  (unordered,canonical') <- right "unordered current rows" (admit (W.VNode 412
    (take 6 fields ++ [listing (map W.VInt [1,0]),listing (map W.VText [hashB,hashA]),
                       listing (map W.VInt [2,0]),listing (map W.VInt [0,0]),listing [W.VInt 0]])))
  need "unordered rows republish canonically" (not canonical' && and (zipWith Q.sameNode [leaf,root] (M.elems unordered)))
  reject "configuration mismatch" "version mismatch" (Q.admitIndex "other" graph)
  forM_ [(6,listing [W.VInt 0],"column lengths"), (6,listing (map W.VInt [0,0]),"duplicate query node"),
         (7,listing (map W.VText [hashA,"bad"]),"invalid query graph digest"),
         (8,listing (map W.VInt [-1,0]),"read column length"),
         (9,listing (map W.VInt [0,1]),"cyclic query graph"),
         (9,listing (map W.VInt [0,2]),"unpublished query dependency"),
         (10,listing (map W.VInt [1,1]),"payload row order/range")] $ \(i,column,reason) ->
    reject reason reason (admit (change i column))
  reject "writer payload mismatch" "invalid query graph digest"
    (generationRoot [Q.QueryNode (binding "leaf") hashA [] (T.Just hashB)])
  let stale = Q.QueryNode (binding "root") hashB [(Q.nodeKey leaf,hashB)] T.Nothing
  reject "writer stale read" "stale dependency version" (generationRoot [leaf,stale])
  right "exact identity budget" (Q.checkIdentityBudget 3 ["a","λx"])
  reject "exhausted identity budget" "identity work limit" (Q.checkIdentityBudget 2 ["a","λx"])
  pass "current columns, identity framing, ordered reads, payloads and admission bounds"

-- Each previous layout describes a valid nonempty graph for the same configuration.
-- Publishing a new root and reopening it distinguishes a cache miss from migration.
obsoleteIndexes =
  let name = W.VText (Q.key "Binding" "retired")
      header marker = [W.VText marker,W.VText "config"]
      row key hash = W.VNode 413 [key,hash,listing [],W.VNode 4 []]
  in [("inline", W.VNode 411 (header "MLF-CRATE-QUERY-GRAPH-1" ++
        [listing [W.VNode 410 [name,W.VText hashA,listing [],W.VNode 4 []]]])),
      ("dictionary", W.VNode 412 (header "MLF-CRATE-QUERY-GRAPH-2" ++
        [listing [name,W.VText hashA],listing [row (W.VInt 0) (W.VInt 1)]])),
      ("dense", W.VNode 412 (header "MLF-CRATE-QUERY-GRAPH-2" ++
        [listing [W.VText "retired"],listing [],listing [],listing [],listing [row (W.VInt 0) (W.VText hashA)]]))]

checkObsolete root (label,value) = do
  let dir = root ++ "/" ++ label
      path = txt dir
  Q.begin path "config" >>= right "create cache"
  (digest,bytes) <- Q.encodeHashed value >>= right "obsolete generation encoding"
  Storage.writeRawAtomic (txt (dir ++ "/generations/" ++ B.unpack digest ++ ".mlfqg")) bytes >>= right label
  Storage.writeAtomic 6 (txt (dir ++ "/CURRENT")) [W.VText digest] >>= right label
  session@(Q.Session _ _ previous old _ _) <- Q.begin path "config" >>= right label
  need (label ++ " misses") (previous == "" && M.null old)
  (new,active) <- Q.record (Q.key "Binding" "new") [] False (W.VInt 7) session >>= right label
  Q.publish active >>= right label >>= need (label ++ " rebuild switches CURRENT")
  warm@(Q.Session _ _ current loaded _ _) <- Q.begin path "config" >>= right label
  need (label ++ " rebuilt only the current row") (current /= digest && current /= "" && M.size loaded == 1)
  case fst (Q.validate (Q.nodeKey new) warm) of
    T.Just actual -> need (label ++ " rebuilt row reusable") (Q.sameNode new actual)
    T.Nothing -> error (label ++ ": no rebuilt row")

publicationTests root = do
  exists <- doesPathExist root
  need "publication requires fresh root" (not exists)
  createDirectory root
  let path = txt root
      current = txt (root ++ "/CURRENT")
  mapM_ (checkObsolete root) obsoleteIndexes
  session <- Q.begin path "config" >>= right "begin empty"
  (leaf,s1) <- Q.record (Q.key "Input" (Q.key "Binding" "leaf")) [] True (W.VText "leaf payload") session
    >>= right "record input"
  (node,s2) <- Q.record (Q.key "Binding" "root") [Q.edge leaf,Q.edge leaf] True
    (W.VText "root payload") s1 >>= right "record root"
  Q.publish s2 >>= right "cold publication" >>= need "cold switches CURRENT"
  baseline <- P.fileDigest current
  reopened <- Q.begin path "config" >>= right "reopen current cache"
  let Q.Session _ _ generation old _ _ = reopened
      generationPath = txt (root ++ "/generations/" ++ B.unpack generation ++ ".mlfqg")
  need "cold contains current generation" (not (null (B.unpack generation)) && M.size old == 2)
  graph <- Q.readValue generationPath (T.Just generation) >>= right "generation hash"
  rootID <- case W.graphRoots graph of
    [rootID] -> pure rootID
    _ -> errorWithoutStackTrace "publication must have exactly one generation root"
  index <- right "generation root" (W.lookupGraphNode graph rootID)
  case index of W.GNode 412 fields | length fields == 11 -> pure (); _ -> error "publication must write columns"
  let (deleted,_) = Q.validate (Q.nodeKey node) reopened
      (_,changed) = Q.recordDigest (Q.nodeKey leaf) [] T.Nothing hashA T.Nothing reopened
      (stale,_) = Q.validate (Q.nodeKey node) changed
  case deleted of T.Nothing -> pure (); T.Just _ -> error "missing authoritative input reused"
  case stale of T.Nothing -> pure (); T.Just _ -> error "stale authoritative input reused"
  let (_,fresh) = Q.recordDigest (Q.nodeKey leaf) [] (Q.nodePayload leaf)
        (Q.nodeHash leaf) T.Nothing reopened
      (reused,warm) = Q.validate (Q.nodeKey node) fresh
  case reused of T.Nothing -> error "warm dependency validation"; T.Just _ -> pure ()
  Q.publish warm >>= right "warm publication" >>= (need "warm unchanged" . not)
  P.fileDigest current >>= (need "warm CURRENT preserved" . (== baseline))
  forM_ ["before-results","after-result-staging","after-result-batch","before-index","before-current"] $ \point -> do
    (_,next) <- Q.record (Q.key "Binding" (txt point)) [] True (W.VText (txt point)) warm
      >>= right ("record " ++ point)
    setEnv "MLF_QUERY_FAILPOINT" point
    result <- Q.publish next
    unsetEnv "MLF_QUERY_FAILPOINT"
    reject point "interrupted" result
    P.fileDigest current >>= (need ("CURRENT survives " ++ point) . (== baseline))
    Q.begin path "config" >>= right ("reopen after " ++ point) >>= \opened -> do
      let Q.Session _ _ actual oldAgain _ _ = opened
      need ("old generation survives " ++ point) (actual == generation && M.size oldAgain == 2)
  -- A retained payload corruption prevents switching CURRENT. The hash
  -- mismatch is real on disk, not merely an invalid ID in an in-memory value.
  Storage.write 6 (Q.payloadPath path (Q.nodeHash node)) [W.VText "corrupt retained payload"]
    >>= right "corrupt own test payload"
  Q.publish warm >>= reject "retained payload hash" "missing/corrupt"
  P.fileDigest current >>= (need "payload failure CURRENT preserved" . (== baseline))
  Q.readValue generationPath (T.Just hashA) >>= reject "index expected SHA" "checksum mismatch"
  (_,repaired) <- Q.record (Q.nodeKey node) (Q.nodeReads node) True (W.VText "root payload") warm
    >>= right "recompute payload"
  Q.publish repaired >>= right "repair retained payload" >>= need "repair keeps generation" . not
  P.fileDigest (Q.payloadPath path (Q.nodeHash node)) >>= need "payload restored" . (== Q.nodeHash node)
  Storage.write 6 generationPath [W.VText "corrupt generation"] >>= right "corrupt index bytes"
  cold@(Q.Session _ _ previous missed _ _) <- Q.begin path "config" >>= right "begin after index corruption"
  need "damaged generation misses" (previous == "" && M.null missed)
  (leafAgain,active) <- Q.record (Q.nodeKey leaf) [] True (W.VText "leaf payload") cold >>= right "rebuild input"
  (_,rebuilt) <- Q.record (Q.nodeKey node) [Q.edge leafAgain,Q.edge leafAgain] True (W.VText "root payload") active
    >>= right "rebuild root"
  Q.publish rebuilt >>= right "repair generation" >>= need "republished repaired generation"
  Q.Session _ _ recovered recoveredNodes _ _ <- Q.begin path "config" >>= right "open repaired generation"
  need "generation restored" (recovered == generation && M.size recoveredNodes == 2)
  pass "obsolete and corrupt cache rebuilds, current hits and invalidation, atomic publication"

main = do
  args <- getArgs
  case args of
    ["pure"] -> pureTests
    ["publication",root] -> publicationTests root
    _ -> errorWithoutStackTrace "usage: query-index-tests pure | publication FRESH_ROOT"
