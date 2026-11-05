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
dict = [hashA, hashB, "leaf", "root"]
none = W.VNode 4 []
just value = W.VNode 5 [value]
refs k h = W.VNode 2 [W.VInt k, W.VInt h]
row k h reads location = W.VNode 413 [W.VInt k, W.VInt h, W.VNode 1 reads, location]
leafRow = row 2 0 [] none
rootRow = row 3 1 [refs 2 0, refs 2 0] (just (W.VInt 0))
rows = [leafRow, rootRow]
v2 strings records = W.VNode 412 [W.VText "MLF-CRATE-QUERY-GRAPH-2",
  W.VText "config", W.VNode 1 (map W.VText strings), W.VNode 1 records]
base = v2 dict rows
decode value = do
  graph <- W.planGraph W.defaultLimits [value]
  Q.decodeIndex "config" graph
snapshot node = (B.unpack (Q.nodeKey node), B.unpack (Q.nodeHash node),
  [(B.unpack k, B.unpack h) | (k,h) <- Q.nodeReads node],
  case Q.nodePayload node of T.Nothing -> Nothing; T.Just h -> Just (B.unpack h))
snapshots = map snapshot . M.elems
same label expected actual = need label (snapshots expected == snapshots actual)
legacyNode k h reads location = W.VNode 410
  [W.VText k, W.VText h, W.VNode 1
    [W.VNode 2 [W.VText key,W.VText digest] | (key,digest) <- reads], location]
legacy records = W.VNode 411 [W.VText "MLF-CRATE-QUERY-GRAPH-1",W.VText "config",W.VNode 1 records]
withWork n (W.Limits a b c d e f g _) = W.Limits a b c d e f g n
work value = do
  (_, stats) <- W.planMeasured W.defaultLimits [value]
  T.Right (W.resourceExpandedWork stats)
mutateNode position replacement (W.VNode 413 fields) =
  W.VNode 413 (take position fields ++ [replacement] ++ drop (position + 1) fields)
mutateNode _ _ _ = error "fixture node"
decodeReject label expected value = reject label expected (decode value)
chain count dependencyFirst =
  let key i = txt ("chain/" ++ replicate (5 - length (show i)) '0' ++ show i)
      predecessor i = if dependencyFirst then i - 1 else i + 1
      leaf i = if dependencyFirst then i == 0 else i == count - 1
      node i = Q.QueryNode (key i) hashA
        (if leaf i then [] else [(key (predecessor i),hashA)]) T.Nothing
  in M.fromDistinctAscList [(Q.nodeKey (node i),node i) | i <- [0..count-1]]

pureTests = do
  decoded <- right "v2 baseline" (decode base)
  need "exact fields/order/repetition/location" (snapshots decoded ==
    [("leaf",B.unpack hashA,[],Nothing),
     ("root",B.unpack hashB,[("leaf",B.unpack hashA),("leaf",B.unpack hashA)],Just (B.unpack hashA))])
  encoded <- right "production v2 encoder" (Q.encodeIndexV2 "config" decoded)
  right "v2 roundtrip" (decode encoded) >>= same "v2 exact roundtrip" decoded
  bytes <- W.encode W.defaultLimits 6 [encoded] >>= right "v2 binary encode"
  graph <- W.decodeGraph W.defaultLimits 6 bytes >>= right "v2 binary decode"
  wire <- right "v2 actual wire read" (Q.decodeIndex "config" graph)
  same "wire fields" decoded wire
  again <- right "canonical reencode value" (Q.encodeIndexV2 "config" wire)
  bytes2 <- W.encode W.defaultLimits 6 [again] >>= right "canonical reencode bytes"
  Storage.sameBytes bytes bytes2 >>= need "canonical v2 bytes"
  right "legacy index reader" (decode (Q.encodeIndex "config" decoded)) >>= same "legacy compatibility" decoded
  empty <- right "empty v2 writer" (Q.encodeIndexV2 "config" M.empty)
  right "empty v2 reader" (decode empty) >>= (need "empty nodes" . M.null)
  let first = Q.QueryNode "first" hashA [] T.Nothing
      second = Q.QueryNode "second" hashB [] T.Nothing
      ordered = Q.QueryNode "ordered" hashA [Q.edge second,Q.edge first,Q.edge second] T.Nothing
      orderedMap = M.fromList P.compareString [(Q.nodeKey n,n) | n <- [first,second,ordered]]
  orderedValue <- right "distinct read ordering writer" (Q.encodeIndexV2 "config" orderedMap)
  right "distinct read ordering reader" (decode orderedValue) >>= same "distinct read order exact" orderedMap
  pass "legacy and v2 exact roundtrip, order, repeated reads, independent location"

  let bad label expected strings records = decodeReject label expected (v2 strings records)
      changeFirst field value = [mutateNode field value leafRow, rootRow]
  forM_ [(-1),4,9223372036854775807] $ \id ->
    bad "hash ID range" "ID out of range" dict (changeFirst 1 (W.VInt id))
  forM_ [W.VText "0",W.VBits 0,W.VNode 1 []] $ \value ->
    bad "ID exact integer type" "Int" dict (changeFirst 1 value)
  bad "read ID negative" "ID out of range" dict
    [leafRow,row 3 1 [refs (-1) 0] (just (W.VInt 0))]
  bad "read hash ID range" "ID out of range" dict
    [leafRow,row 3 1 [refs 2 4] (just (W.VInt 0))]
  bad "payload ID negative" "ID out of range" dict
    [leafRow,row 3 1 [refs 2 0] (just (W.VInt (-1)))]
  bad "payload ID bits" "Int" dict
    [leafRow,row 3 1 [refs 2 0] (just (W.VBits 0))]
  bad "hash ID ordinary string" "digest" dict (changeFirst 1 (W.VInt 2))
  bad "read hash ordinary string" "digest" dict
    [leafRow,row 3 1 [refs 2 2] (just (W.VInt 0))]
  bad "payload hash ordinary string" "digest" dict
    [leafRow,row 3 1 [refs 2 0] (just (W.VInt 2))]
  bad "invalid hash text" "digest" ["a",hashB,"leaf","root"] rows
  bad "duplicate dictionary" "dictionary" [hashA,hashA,"leaf","root"] rows
  bad "unordered dictionary" "dictionary" [hashB,hashA,"leaf","root"] rows
  bad "unused dictionary" "unused" (dict ++ ["unused"]) rows
  bad "duplicate node" "duplicate/unordered" dict [leafRow,leafRow,rootRow]
  bad "unordered nodes" "duplicate/unordered" dict (reverse rows)
  bad "missing dependency" "unpublished" dict [rootRow]
  bad "stale expected hash" "stale" dict
    [leafRow,row 3 1 [refs 2 1] (just (W.VInt 0))]
  bad "cycle" "cyclic/deep" dict [row 2 0 [refs 3 1] none,rootRow]
  bad "self cycle" "cyclic/deep" dict
    [leafRow,row 3 1 [refs 3 1] (just (W.VInt 0))]
  bad "read pair constructor" "indexed query read" dict
    [leafRow,row 3 1 [W.VNode 3 [W.VInt 2,W.VInt 0]] (just (W.VInt 0))]
  bad "payload constructor" "indexed query location" dict
    [leafRow,row 3 1 [refs 2 0] (W.VNode 5 [])]
  bad "row constructor" "indexed query node" dict [W.VNode 410 [],rootRow]
  let header f c d e = W.VNode 412 [f,c,d,e]
  decodeReject "dictionary element type" "String"
    (header (W.VText "MLF-CRATE-QUERY-GRAPH-2") (W.VText "config")
      (W.VNode 1 [W.VInt 0]) (W.VNode 1 []))
  decodeReject "wrong version" "version mismatch"
    (header (W.VText "MLF-CRATE-QUERY-GRAPH-1") (W.VText "config") (W.VNode 1 []) (W.VNode 1 []))
  decodeReject "wrong configuration" "version mismatch"
    (header (W.VText "MLF-CRATE-QUERY-GRAPH-2") (W.VText "other") (W.VNode 1 []) (W.VNode 1 []))
  two <- right "two roots plan" (W.planGraph W.defaultLimits [base,base])
  reject "two index roots" "root count" (Q.decodeIndex "config" two)
  let oldLeaf = legacyNode "leaf" hashA [] none
      oldRoot = legacyNode "root" hashB [("leaf",hashA)] (just (W.VText hashA))
  decodeReject "legacy duplicate" "duplicate" (legacy [oldLeaf,oldLeaf,oldRoot])
  decodeReject "legacy bad hash" "digest" (legacy [legacyNode "leaf" "wrong" [] none])
  decodeReject "legacy missing" "unpublished" (legacy [oldRoot])
  decodeReject "legacy stale" "stale"
    (legacy [oldLeaf,legacyNode "root" hashB [("leaf",hashB)] none])
  decodeReject "legacy cycle" "cyclic/deep" (legacy [legacyNode "leaf" hashA [("leaf",hashA)] none])
  pass "typed IDs, dictionary/row canonicality, closure, hashes, legacy rejection"

  forM_ [False,True] $ \dependencyFirst -> do
    accepted <- right "4096-node writer" (Q.encodeIndexV2 "config" (chain 4096 dependencyFirst))
    right "4096-node reader" (decode accepted) >>= (need "4096 retained" . (==4096) . M.size)
    if dependencyFirst
      then right "legacy historical done-first depth compatibility"
        (decode (Q.encodeIndex "config" (chain 4097 True))) >> pure ()
      else decodeReject "legacy original forward depth limit" "cyclic/deep"
        (Q.encodeIndex "config" (chain 4097 False))
    reject "4097-node writer rejects all key orders" "cyclic/deep"
      (Q.encodeIndexV2 "config" (chain 4097 dependencyFirst))
    let allNodes = M.elems (chain 4097 dependencyFirst)
        strings = hashA : map Q.nodeKey allNodes
        keyID i = fromIntegral i + 1
        dependency i = if dependencyFirst then i - 1 else i + 1
        isLeaf i = if dependencyFirst then i == 0 else i == 4096
        records = [row (keyID i) 0
          (if isLeaf i then [] else [refs (keyID (dependency i)) 0]) none | i <- [0..4096]]
    decodeReject "4097-node reader rejects all key orders" "cyclic/deep" (v2 strings records)
  pass "actual 4096/4097 depth boundary independent of key order"

  dictionary <- right "budget dictionary" (Q.indexDictionary dict)
  let numeric = [Q.IndexNode 2 0 [] T.Nothing,
                 Q.IndexNode 3 1 [(2,0),(2,0)] (T.Just 0)]
  sizes <- mapM (right "row projected work" . Q.indexNodeWork 67108864 dictionary) numeric
  inlineWork <- right "independent inline codec work" (work (Q.encodeIndex "config" decoded))
  need "exact projected row work" (sizes == [73,280])
  need "exact projected total work" (inlineWork == sum sizes + 4 + 23 + 6)
  right "exact row/total budgets" (Q.validateIndexWork 280 inlineWork "config" dictionary numeric)
  right "source budget exact" (Q.validateIndexSourceWork 280 inlineWork "config" (M.elems decoded))
  reject "source row one unit short" "referenced-work"
    (Q.validateIndexSourceWork 279 inlineWork "config" (M.elems decoded))
  reject "source total one unit short" "referenced-work"
    (Q.validateIndexSourceWork 280 (inlineWork-1) "config" (M.elems decoded))
  reject "row one unit short" "referenced-work" (Q.validateIndexWork 279 inlineWork "config" dictionary numeric)
  reject "total one unit short" "referenced-work" (Q.validateIndexWork 280 (inlineWork-1) "config" dictionary numeric)
  right "empty header exact decoder" (Q.validateIndexWork 0 33 "config" M.empty [])
  right "empty header exact writer" (Q.validateIndexSourceWork 0 33 "config" [])
  reject "empty header one short decoder" "limit" (Q.validateIndexWork 0 32 "config" M.empty [])
  reject "empty header one short writer" "limit" (Q.validateIndexSourceWork 0 32 "config" [])
  reject "negative custom budget" "invalid query" (Q.validateIndexWork (-1) inlineWork "config" dictionary numeric)
  utf <- right "UTF-8 dictionary" (Q.indexDictionary [hashA,"λ😀"])
  utfWork <- right "UTF-8 exact row budget" (Q.indexNodeWork 75 utf (Q.IndexNode 1 0 [] T.Nothing))
  need "UTF-8 bytes not codepoints" (utfWork == 75)
  right "source UTF-8 exact work"
    (Q.indexSourceNodeWork 75 (Q.QueryNode "λ😀" hashA [] T.Nothing)) >>= need "source UTF-8 parity" . (==75)
  reject "source UTF-8 truncated-byte budget" "limit"
    (Q.indexSourceNodeWork 10 (Q.QueryNode "λ😀" hashA [] T.Nothing))
  reject "UTF-8 one below" "referenced-work" (Q.indexNodeWork 74 utf (Q.IndexNode 1 0 [] T.Nothing))

  -- A tiny wire graph can describe >64 Mi of repeated key text. It is rejected
  -- by both writer and reader before string-key Session operations begin.
  let longKey = txt (replicate 32700 'z')
      rootKey n = txt (replicate n 'r')
      references = replicate 2048 (longKey,hashA)
      leaf = Q.QueryNode longKey hashA [] T.Nothing
      repeated n = M.fromDistinctAscList
        [(rootKey n,Q.QueryNode (rootKey n) hashA references T.Nothing),(longKey,leaf)]
      rawLong n = v2 [hashA,rootKey n,longKey]
        [row 1 0 (replicate 2048 (refs 2 0)) none,row 2 0 [] none]
  exact64 <- right "actual 64 Mi row writer" (Q.encodeIndexV2 "config" (repeated 1979))
  admitted64 <- right "actual 64 Mi row reader" (decode exact64)
  same "repeated long-key semantics at boundary" (repeated 1979) admitted64
  reject "actual row 64 Mi plus one writer" "referenced-work" (Q.encodeIndexV2 "config" (repeated 1980))
  decodeReject "actual row 64 Mi plus one reader" "referenced-work" (rawLong 1980)
  compactWork <- right "compact exact work" (work exact64)
  need "64 Mi row represented below 64 Ki work" (compactWork < 65536)
  reject "legacy whole-index actual 64 Mi remains" "work limit"
    (W.plan W.defaultLimits [Q.encodeIndex "config" (repeated 1979)])
  boundaryGraph <- right "codec exact smaller budget"
    (W.planGraph (withWork compactWork W.defaultLimits) [exact64])
  right "codec exact smaller budget reader" (Q.decodeIndex "config" boundaryGraph) >> pure ()
  reject "codec one unit short" "work limit"
    (W.plan (withWork (compactWork-1) W.defaultLimits) [exact64])

  -- Sum is exact 256 Mi: three max-sized rows, one shorter row, leaf, header.
  let key c n = txt (replicate n c)
      leafWork = 5 + 32700 + 64
      headerWork = 4 + 23 + 6
      lastLength = fromIntegral (67108864 - leafWork - headerWork - 2047*32767 - 69)
      keys = [key 'b' 1979,key 'c' 1979,key 'd' 1979,key 'e' lastLength]
      indexRows = [row i 0 (replicate (if i == 4 then 2047 else 2048) (refs 5 0)) none | i <- [1..4]]
        ++ [row 5 0 [] none]
      totalExact = v2 (hashA : keys ++ [longKey]) indexRows
      totalOver = v2 (hashA : take 3 keys ++ [key 'e' (lastLength+1),longKey]) indexRows
  totalNodes <- right "actual 256 Mi index reader" (decode totalExact)
  right "actual 256 Mi index writer" (Q.encodeIndexV2 "config" totalNodes) >> pure ()
  decodeReject "actual 256 Mi index plus one reader" "referenced-work" totalOver
  let tooMuch = M.fromDistinctAscList
        [(k,Q.QueryNode k hashA (replicate (if i == (4 :: Int) then 2047 else 2048) (longKey,hashA)) T.Nothing)
          | (i,k) <- zip [1..] (take 3 keys ++ [key 'e' (lastLength+1)])]
        -- Insert leaf without disturbing the four canonical root keys.
      overTable = M.insert P.compareString longKey leaf tooMuch
  reject "actual 256 Mi index plus one writer" "referenced-work" (Q.encodeIndexV2 "config" overTable)

  -- Repeated alternating long-prefix keys specifically model the downstream
  -- Map.lookup attack; small limits exercise identical production checks.
  let prefix = replicate 512 'q'
      attackKeys = map (Q.key "Compute" . txt) [prefix++"a",prefix++"b","root"]
      attackStrings = M.keys (M.fromList P.compareString [(s,()) | s <- hashA:attackKeys])
      attackIDs = M.fromDistinctAscList (zip attackStrings [0..])
      ident key = M.get P.compareString key attackIDs
      a = ident (attackKeys !! 0)
      b = ident (attackKeys !! 1)
      r = ident (attackKeys !! 2)
      h = ident hashA
      attack = M.elems (M.fromList compareID
        [(a,Q.IndexNode a h [] T.Nothing),(b,Q.IndexNode b h [] T.Nothing),
         (r,Q.IndexNode r h (concat (replicate 16 [(a,h),(b,h)])) T.Nothing)])
      compareID a b = if a < b then -1 else if a > b then 1 else 0
  attackDict <- right "attack dictionary" (Q.indexDictionary attackStrings)
  reject "alternating long-prefix references" "referenced-work"
    (Q.validateIndexWork 1024 65536 "config" attackDict attack)
  tinyWork <- right "tiny work" (work base)
  tinyBytes <- W.encode (withWork tinyWork W.defaultLimits) 6 [base] >>= right "tiny exact encode"
  W.decodeGraph (withWork tinyWork W.defaultLimits) 6 tinyBytes >>= right "tiny exact decode" >> pure ()
  W.decodeGraph (withWork (tinyWork-1) W.defaultLimits) 6 tinyBytes
    >>= reject "wire decoder one unit short" "work limit"
  need "production codec still 64 Mi" (W.maxExpandedWork W.defaultLimits == 67108864)
  byte <- P.readByteArray tinyBytes 76
  P.writeByteArray tinyBytes 76 (P.xorInt byte 1)
  W.decodeGraph W.defaultLimits 6 tinyBytes >>= reject "wire CRC" "checksum"
  pass "referenced and codec budgets, exact 64/256 Mi boundaries, long-prefix attack"

publicationTests root = do
  exists <- doesPathExist root
  need "publication requires fresh root" (not exists)
  createDirectory root
  let path = txt root
      current = txt (root ++ "/CURRENT")
  let legacyPath = txt (root ++ "/legacy")
  Q.begin legacyPath "config" >>= right "create legacy cache" >> pure ()
  (legacyHash,legacyBytes) <- Q.encodeHashed (Q.encodeIndex "config" M.empty) >>= right "legacy generation bytes"
  Storage.writeRawAtomic (txt (root ++ "/legacy/generations/" ++ B.unpack legacyHash ++ ".mlfqg"))
    legacyBytes >>= right "legacy generation write"
  Storage.writeAtomic 6 (txt (root ++ "/legacy/CURRENT")) [W.VText legacyHash] >>= right "legacy pointer write"
  oldSession <- Q.begin legacyPath "config" >>= right "legacy begin reader"
  let Q.Session _ _ oldHash _ _ _ = oldSession
  need "legacy generation retained" (oldHash == legacyHash)
  Q.publish oldSession >>= right "legacy migrates to v2" >>= need "legacy migration switches"
  session <- Q.begin path "config" >>= right "begin empty"
  (leaf,s1) <- Q.record (Q.key "Input" "leaf") [] True (W.VText "leaf payload") session
    >>= right "record input"
  (node,s2) <- Q.record (Q.key "Compute" "root") [Q.edge leaf,Q.edge leaf] True
    (W.VText "root payload") s1 >>= right "record root"
  Q.publish s2 >>= right "cold publication" >>= need "cold switches CURRENT"
  baseline <- P.fileDigest current
  reopened <- Q.begin path "config" >>= right "reopen v2"
  let Q.Session _ _ generation old _ _ = reopened
      generationPath = txt (root ++ "/generations/" ++ B.unpack generation ++ ".mlfqg")
  need "cold contains v2 generation" (not (null (B.unpack generation)) && M.size old == 2)
  graph <- Q.readValue generationPath (T.Just generation) >>= right "generation hash"
  rootID <- case W.graphRoots graph of
    [rootID] -> pure rootID
    _ -> errorWithoutStackTrace "publication must have exactly one generation root"
  index <- right "generation root" (W.lookupGraphNode graph rootID)
  case index of W.GNode 412 _ -> pure (); _ -> error "publication must write v2"
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
    (_,next) <- Q.record (Q.key "Compute" (txt point)) [] True (W.VText (txt point)) warm
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
  Storage.write 6 (Q.payloadPath warm (Q.nodeHash node)) [W.VText "corrupt retained payload"]
    >>= right "corrupt own test payload"
  Q.publish warm >>= reject "retained payload hash" "missing/corrupt"
  P.fileDigest current >>= (need "payload failure CURRENT preserved" . (== baseline))
  Q.readValue generationPath (T.Just hashA) >>= reject "index expected SHA" "checksum mismatch"
  pass "cold/warm publication, all failpoints, retained payload SHA, generation SHA"

main = do
  args <- getArgs
  case args of
    ["pure"] -> pureTests
    ["publication",root] -> publicationTests root
    _ -> errorWithoutStackTrace "usage: query-index-tests pure | publication FRESH_ROOT"
