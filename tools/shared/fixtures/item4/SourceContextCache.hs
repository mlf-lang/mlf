{-# LANGUAGE OverloadedStrings #-}
-- Real production API controls. This program never changes compiler globals.
module Main where
import Prelude
import Control.Monad (unless, forM_)
import Control.Exception (bracket)
import Data.List (sort)
import qualified Data.ByteString as BS
import System.Directory (createDirectory, doesPathExist, listDirectory, renameFile, getModificationTime)
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.SourceInference as SI
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.CrateSession as Session
import qualified Bootstrap.Separate as U
import qualified Bootstrap.X.Syntax as X
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P

-- All callers supply real private POSIX directories and fixed leaf names.
-- Avoid an undeclared filepath package; Windows is not qualified by this gate.
infixr 5 </>
(</>) :: FilePath -> FilePath -> FilePath
parent </> leaf = parent ++ "/" ++ leaf

need label ok = unless ok (error label)
expect label result = case result of
  T.Left message -> error (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value
reject label result = case result of
  T.Left _ -> putStrLn ("PASS " ++ label)
  T.Right _ -> error ("accepted " ++ label)
fields = expect "framing" . U.unpack
literal = B.literal
save p = writeFile p . B.unpack
readText p = literal <$> readFile p
fresh p = do exists <- doesPathExist p; need ("fresh directory " ++ p) (not exists); createDirectory p
sameObject a b = U.encodeInterface (U.objectInterface a) == U.encodeInterface (U.objectInterface b)
              && U.encodeObject a == U.encodeObject b
names = ["value"]
members n = [("value", T.Nothing, T.SIntLit n)]
keyFor context = U.pack ["MLF-SOURCE-CRATE-QUERY-6", "crate:α😀", "compiler",
                        "member:opaque:😀", "bindings", context,
                        "source-group", "observed-contracts", "scope-table:α😀"]
splitKey key = case Q.sourceCacheParts key of
  T.Just pair -> pure pair
  T.Nothing -> error "source v6 not recognized"
newRecord ref compact payload = U.pack ["MLF-QUERY-CACHE-3", ref, compact, payload]
recordParts text = do
  xs <- fields text
  case xs of
    ["MLF-QUERY-CACHE-3",ref,compact,payload] -> pure (ref,compact,payload)
    _ -> error "writer did not produce source CACHE3"
readNew directory key input = Q.readSourceCached (literal directory) key "RawGroup" [] [] names input

helper directory = do
  fresh directory
  bracket (P.acquireFileLock (literal (directory </> ".lock"))) P.releaseFileLock (\_ -> helperLocked directory)
helperLocked directory = do
  object <- expect "raw inference" (I.compileLoweredGroup "RawGroup" [] [] (members 41))
  let context = Q.encodeDatatypeContext []
      key = keyFor context
      path = directory </> "record.mlfq"
      old1 = Q.encodeCached key object
      legacyKey = Q.queryKey "legacy" "compiler" (members 41) [] []
      old2 = Q.encodeCached legacyKey object
  a <- Q.readSourceCached (literal directory) key "RawGroup" [] [] names old1 >>= expect "old CACHE1 reader"
  b <- Q.readSourceCached (literal directory) legacyKey "RawGroup" [] [] names old2 >>= expect "old CACHE2 reader"
  need "legacy exact checked object" (sameObject a object && sameObject b object)
  f1 <- fields old1; f2 <- fields old2
  need "legacy writer formats unchanged" (case (f1,f2) of (tag1:_,tag2:_) -> tag1 == "MLF-QUERY-CACHE-1" && tag2 == "MLF-QUERY-CACHE-2"; _ -> False)
  need "noncanonical source key is not eligible" (case Q.sourceCacheParts ("0" P.++ key) of T.Nothing -> True; _ -> False)
  need "legacy query key is not source CACHE3 eligible" (case Q.sourceCacheParts legacyKey of T.Nothing -> True; _ -> False)
  before <- listDirectory directory
  need "legacy readers did not migrate/write" (sort before == [".lock"])
  Q.writeSourceCached T.Nothing (literal directory) (literal path) key object >>= expect "source write"
  input <- readText path
  (ref,compact,payload) <- recordParts input
  (expectedCompact,expectedContext) <- splitKey key
  need "source parts retain all eight non-context fields" (compact == expectedCompact && context == expectedContext)
  restored <- expect "restore source key" (Q.restoreSourceCacheKey context compact)
  need "full Unicode/scalar key roundtrip" (restored == key)
  let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
  blob <- readText contextPath
  need "canonical context blob" (blob == Q.sourceContextContents context)
  digest <- P.fileDigest (literal contextPath)
  need "context SHA filename" (digest == ref && Q.validSourceContextDigest ref)
  checked <- readNew directory key input >>= expect "source CACHE3 reader"
  need "source checked object preserved" (sameObject checked object)
  stamp <- getModificationTime contextPath
  let pooledPath = directory </> "pooled.mlfq"
  Q.writeSourceCached (T.Just (Q.prepareSourceEncodings [])) (literal directory) (literal pooledPath) key object >>= expect "pooled source write"
  pooled <- readText pooledPath
  stampAfter <- getModificationTime contextPath
  need "pool changes neither bytes nor existing context mtime" (pooled == input && stamp == stampAfter)
  -- Pure decoder mutations isolate each admission boundary from IO routing.
  let decode k n bindings ds ns carrier record =
        Q.decodeSourceCached ref k n bindings ds ns carrier record
  reject "changed group ownership" (decode key "WrongOwner" [] [] names blob input)
  reject "changed declaration ownership" (decode key "RawGroup" [] [] ["other"] blob input)
  reject "changed dependency parameters" (decode key "RawGroup" [("external",T.XCon "Int" [])] [] names blob input)
  reject "different expected datatype layout" (decode key "RawGroup" [] [T.DataDecl "Other" [] [T.ConstructorDecl "Other" []]] names blob input)
  forM_ [0,1,2,3,4,6,7,8] $ \index -> do
    original <- fields key
    let changed = U.pack [if i == index then x P.++ "!" else x | (i,x) <- zip [0..] original]
    reject ("key field " ++ show index ++ " changed") (decode changed "RawGroup" [] [] names blob input)
  reject "context carrier changed" (decode key "RawGroup" [] [] names (Q.sourceContextContents "wrong") input)
  reject "context carrier wrong version" (decode key "RawGroup" [] [] names (U.pack ["WRONG",context]) input)
  reject "context carrier extra field" (decode key "RawGroup" [] [] names (U.pack ["MLF-SOURCE-QUERY-CONTEXT-1",context,"extra"]) input)
  reject "payload truncated" (decode key "RawGroup" [] [] names blob (newRecord ref compact ""))
  reject "record trailing field" (decode key "RawGroup" [] [] names blob (U.pack ["MLF-QUERY-CACHE-3",ref,compact,payload,"extra"]))
  reject "noncanonical record framing" (decode key "RawGroup" [] [] names blob ("0" P.++ input))
  reject "compact key truncated" (decode key "RawGroup" [] [] names blob (newRecord ref "" payload))
  reject "actual context digest differs" (Q.decodeSourceCached (literal (replicate 64 '0')) key "RawGroup" [] [] names blob input)
  forM_ ["../escape", "", literal (replicate 63 'a'), literal (replicate 64 'A'), literal (replicate 64 'g')] $ \bad -> do
    need "invalid digest rejected before path use" (not (Q.validSourceContextDigest bad))
    readNew directory key (newRecord bad compact payload) >>= reject "untrusted context reference"
  renameFile contextPath (contextPath ++ ".saved")
  readNew directory key input >>= reject "missing context"
  renameFile (contextPath ++ ".saved") contextPath
  save contextPath "truncated"
  readNew directory key input >>= reject "corrupt context digest/content"
  save contextPath blob
  readNew directory key input >>= expect "context restored" >> pure ()
  -- Distinct key changes only an unrelated field; one exact context remains.
  keyFields <- fields key
  let secondKey = U.pack [if i == 1 then "another-crate" else value | (i,value) <- zip [0..] keyFields]
  Q.writeSourceCached T.Nothing (literal directory) (literal (directory </> "second.mlfq")) secondKey object >>= expect "shared context second record"
  files <- sort <$> listDirectory directory
  need "one shared context file and no stage temporary" (length (filter (\x -> take 8 x == "context-") files) == 1 && not ("source-context.new" `elem` files))
  -- A mismatched v6 context must retain the established self-contained format.
  Q.writeSourceCached T.Nothing (literal directory) (literal (directory </> "fallback.mlfq")) (keyFor "wrong") object >>= expect "safe fallback write"
  fallback <- readText (directory </> "fallback.mlfq") >>= fields
  need "ineligible source object uses legacy format" (case fallback of tag:_ -> tag == "MLF-QUERY-CACHE-1"; [] -> False)
  Q.writeSourceCached T.Nothing (literal directory) (literal (directory </> "legacy2.mlfq")) legacyKey object >>= expect "legacy CACHE2 write fallback"
  legacy2 <- readText (directory </> "legacy2.mlfq")
  need "non-source writer exact legacy CACHE2 bytes" (legacy2 == old2)
  let boxA = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
      boxB = T.DataDecl "Box" ["b"] [T.ConstructorDecl "Box" [T.Parameter "b"]]
      changedBox = T.DataDecl "Box" ["b"] [T.ConstructorDecl "Box" [T.Parameter "b", T.Parameter "b"]]
      boxMembers = [("value",T.Nothing,T.SApp (T.SConstructor "Box") (T.SIntLit 7))]
      boxKey = keyFor (Q.encodeDatatypeContext [boxA])
      boxPath = directory </> "box.mlfq"
  boxObject <- expect "nonempty datatype raw inference" (I.compileLoweredGroup "RawGroup" [] [boxA] boxMembers)
  need "alpha test setup uses identical complete canonical contexts" (Q.encodeDatatypeContext [boxA] == Q.encodeDatatypeContext [boxB])
  let boxLegacyKey = Q.queryKey "legacy-box" "compiler" boxMembers [] [boxA]
  _ <- Q.readSourceCached (literal directory) boxKey "RawGroup" [] [boxB] names (Q.encodeCached boxKey boxObject) >>= expect "legacy CACHE1 alpha compatibility"
  _ <- Q.readSourceCached (literal directory) boxLegacyKey "RawGroup" [] [boxB] names (Q.encodeCached boxLegacyKey boxObject) >>= expect "legacy CACHE2 alpha compatibility"
  Q.writeSourceCached (T.Just (Q.prepareSourceEncodings [boxA])) (literal directory) (literal boxPath) boxKey boxObject >>= expect "nonempty shared context write"
  boxInput <- readText boxPath
  (boxRef,_,_) <- recordParts boxInput
  need "different complete datatype context has different identity" (boxRef /= ref)
  alpha <- Q.readSourceCached (literal directory) boxKey "RawGroup" [] [boxB] names boxInput >>= expect "alpha-equivalent datatype context remains admissible"
  need "alpha-equivalent metadata preserves canonical layout" (Q.encodeDatatypeContext (U.unitData (U.objectInterface alpha)) == Q.encodeDatatypeContext [boxA])
  Q.readSourceCached (literal directory) boxKey "RawGroup" [] [changedBox] names boxInput >>= reject "same datatype name different layout"
  putStrLn "PASS helper CACHE1/CACHE2/CACHE3, complete-key and corrupt-input controls"

legacyOne directory = do
  files <- sort . filter (\name -> reverse (take 5 (reverse name)) == ".mlfq") <$> listDirectory directory
  file <- case files of x:_ -> pure (directory </> x); _ -> error "missing query record"
  input <- readText file
  (ref,compact,payload) <- recordParts input
  blob <- readText (B.unpack (Q.sourceContextPath (literal directory) ref)) >>= fields
  context <- case blob of ["MLF-SOURCE-QUERY-CONTEXT-1",c] -> pure c; _ -> error "context shape"
  key <- expect "legacy conversion full key" (Q.restoreSourceCacheKey context compact)
  raw <- expect "legacy conversion raw object" (U.decodeContextualObject [] [] payload)
  save file (Q.encodeCached key raw)
  putStrLn "PASS fixture replaced one record with valid old CACHE1"

makePlan value = do
  let own = [("first",T.Nothing,T.SIntLit value),("second",T.Nothing,T.SIntLit 99)]
      scopes = M.fromList P.compareString [(n,IS.empty) | (n,_,_) <- own]
  p <- expect "source plan" (SI.prepareSourcePlan M.empty [] [] [] scopes [] own)
  case p of T.Just plan -> pure plan; _ -> error "unexpected whole-source fallback"
-- Only the synthetic empty-datatype Query fixture has this accounting
-- contract. Reconstruct legacy bytes in memory, never publish a baseline cache.
legacyAccounting directory report = do
  let Q.QueryReport _ _ groups = report
  rows <- mapM measure groups
  pure (U.pack ("MLF-QUERY-LEGACY-BYTES-1" : rows))
  where
    measure (Q.GroupResult groupId memberNames _ _ digest) = do
      input <- readText (directory </> (B.unpack digest ++ ".mlfq"))
      fs <- fields input
      (key,raw) <- case fs of
        ["MLF-QUERY-CACHE-3",ref,compact,payload] -> do
          actualContext <- readText (B.unpack (Q.sourceContextPath (literal directory) ref))
          actualDigest <- P.fileDigest (Q.sourceContextPath (literal directory) ref)
          need "accounting empty datatype context" (actualContext == Q.sourceContextContents (Q.encodeDatatypeContext []))
          need "accounting context digest" (actualDigest == ref)
          key <- expect "accounting full key" (Q.restoreSourceCacheKey (Q.encodeDatatypeContext []) compact)
          raw <- expect "accounting contextual raw" (U.decodeContextualObject [] [] payload)
          pure (key,raw)
        ["MLF-QUERY-CACHE-1",key,iface,payload] -> do
          i <- expect "accounting legacy interface" (U.decodeInterface iface)
          raw <- expect "accounting legacy raw" (U.decodeObject i payload)
          pure (key,raw)
        _ -> error "accounting unsupported synthetic cache representation"
      (_,context) <- splitKey key
      need "accounting full key empty context" (context == Q.encodeDatatypeContext [])
      need "accounting raw interface empty context" (null (U.unitData (U.objectInterface raw)))
      let old = Q.encodeCached key raw
          parameters = [(X.nameHint n,t) | (n,t) <- fst (U.splitParameters (strip (U.objectTerm raw)))]
      oldFields <- fields old
      need "accounting baseline really self-contained CACHE1" (case oldFields of tag:_ -> tag == "MLF-QUERY-CACHE-1"; [] -> False)
      decoded <- expect "accounting old decoder semantic parity" (Q.decodeCached key groupId parameters [] memberNames old)
      need "accounting exact old raw roundtrip" (sameObject decoded raw)
      pure (U.pack [digest, literal (show (BS.length (B.utf8 old)))])

query directory resultFile value = do
  plan <- makePlan value
  (objects,report,_) <- Q.compileParsedSourceGroups "query-context-control" (literal directory) [] M.empty plan >>= expect "Query actual source driver"
  save resultFile (U.pack (map U.encodeObject objects))
  legacyAccounting directory report >>= save (resultFile ++ ".legacy-bytes")
  putStrLn (B.unpack (Q.reportJSON "query-context-control" "test" report))

session directory root value = do
  let sourcePath = root </> "SharedContextProbe.hs"
      specPath = root </> "probe.spec"
      prefix = root </> "probe"
      source = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule SharedContextProbe where { import MLF.Primitive; first :: Int; first = " ++ show value ++ "; second :: Int; second = 99 }\n"
      spec = U.pack ["MLF-CRATE-1","session-context-control","","true",
                     U.pack [U.pack ["SharedContextProbe",literal sourcePath]],U.pack [],literal directory,literal (root </> "builtin")]
  writeFile sourcePath source
  save specPath spec
  Session.compileSpecFile (literal specPath) (literal prefix) >>= expect "Session public file producer"
  readFile (prefix ++ ".queries") >>= putStrLn

strip (T.XWithData _ body) = strip body
strip body = body
rawFinal directory = do
  let int = T.SCon "Int" []
      cls = T.SClassDecl "Tag" [("a",T.Star)] [] [("tag",T.SArrow (T.STVar "a") int)]
      instanceInt = T.SInstanceDecl [] [] "Tag" [int] [("tag",T.SLam "x" T.Nothing (T.SVar "x"))]
      instanceBool = T.SInstanceDecl [] [] "Tag" [T.SCon "Bool" []] [("tag",T.SLam "x" T.Nothing (T.SIntLit 42))]
      tag n = T.SApp (T.SVar "tag") (T.SIntLit n)
      add a b = T.SApp (T.SApp (T.SPrimitive T.PAddInt) a) b
      rhs = T.SLet "known" (T.SSignature (tag 2) (T.SAnnotation [] int)) (add (tag 1) (T.SVar "known"))
      own = [("sameDeps",T.Nothing,rhs)]
      scopes = M.fromList P.compareString [("sameDeps",IS.fromList [0])]
  planMaybe <- expect "raw/final source plan" (SI.prepareSourcePlan M.empty [] [cls] [("tagInt",instanceInt),("tagBool",instanceBool)] scopes [IS.fromList [0,1],IS.fromList [0,1]] own)
  plan <- case planMaybe of T.Just p -> pure p; _ -> error "raw/final unsupported source"
  (objects,cold,_) <- Q.compileSourceGroups "raw-final" (literal directory) [] M.empty plan >>= expect "raw/final cold"
  let Q.QueryReport _ _ reports = cold
  (groupId,digest) <- case [(gid,hash) | Q.GroupResult gid ns _ _ hash <- reports, ns == ["sameDeps"]] of
    [pair] -> pure pair
    _ -> error "expected exactly one sameDeps group"
  finalObject <- case [o | o <- objects, U.unitName (U.objectInterface o) == groupId] of
    [object] -> pure object
    _ -> error "expected exactly one sameDeps final object"
  let file = directory </> (B.unpack digest ++ ".mlfq")
  input <- readText file
  (ref,compact,payload) <- recordParts input
  contextBlob <- readText (B.unpack (Q.sourceContextPath (literal directory) ref)) >>= fields
  context <- case contextBlob of ["MLF-SOURCE-QUERY-CONTEXT-1",c] -> pure c; _ -> error "context shape"
  key <- expect "raw/final full key" (Q.restoreSourceCacheKey context compact)
  let ds = U.unitData (U.objectInterface finalObject)
  raw <- expect "raw contextual object" (U.decodeContextualObject ds ds payload)
  let parameters = [(X.nameHint n,t) | (n,t) <- fst (U.splitParameters (strip (U.objectTerm raw)))]
  _ <- expect "generic validator alone accepts final counterexample" (Q.decodeCached key groupId parameters ds ["sameDeps"] (Q.encodeCached key finalObject))
  need "raw object differs from compact final" (U.encodeObject raw /= U.encodeObject finalObject)
  -- Preserve the real reference and full-key projection: only the object
  -- payload is poisoned. This must not become a trivial envelope mismatch.
  let poisoned3 = newRecord ref compact (U.encodeContextualObject finalObject)
  actualContext <- readText (B.unpack (Q.sourceContextPath (literal directory) ref))
  actualDigest <- P.fileDigest (Q.sourceContextPath (literal directory) ref)
  accepted3 <- expect "CACHE3 generic validator accepts finalized counterexample"
    (Q.decodeSourceCached actualDigest key groupId parameters ds ["sameDeps"] actualContext poisoned3)
  need "CACHE3 final payload actually decoded" (sameObject accepted3 finalObject)
  save file poisoned3
  (repaired3,report3,_) <- Q.compileSourceGroups "raw-final" (literal directory) [] M.empty plan >>= expect "CACHE3 raw/final rejection and reinference"
  need "CACHE3 final-as-raw only reinfers poisoned group" (Q.inferredCount report3 == 1 && Q.reusedCount report3 == fromIntegral (length objects - 1))
  need "CACHE3 final artifact exact after repair" (map U.encodeObject repaired3 == map U.encodeObject objects)
  -- The repaired record must restore the raw payload, not simply preserve the
  -- poisoned cache while returning independently correct final artifacts.
  repairedInput3 <- readText file
  (repairedRef,repairedCompact,repairedPayload) <- recordParts repairedInput3
  need "CACHE3 repair keeps reference/key and restores raw payload"
    (repairedRef == ref && repairedCompact == compact && repairedPayload == payload)
  -- Keep the original legacy representation counterexample as a separate pass.
  save file (Q.encodeCached key finalObject)
  (repaired,report,_) <- Q.compileSourceGroups "raw-final" (literal directory) [] M.empty plan >>= expect "legacy raw/final rejection and reinference"
  need "legacy final-as-raw only reinfers poisoned group" (Q.inferredCount report == 1 && Q.reusedCount report == fromIntegral (length objects - 1))
  need "legacy final artifact exact after repair" (map U.encodeObject repaired == map U.encodeObject objects)
  putStrLn "PASS final payload cannot masquerade as raw source cache"

main = do
  args <- getArgs
  case args of
    ["helper",directory] -> helper directory
    ["query",directory,resultFile,value] -> query directory resultFile (read value)
    ["session",directory,root,value] -> session directory root (read value :: Int)
    ["raw-final",directory] -> rawFinal directory
    ["legacy-one",directory] -> legacyOne directory
    _ -> error "expected helper DIR | query CACHE FINAL VALUE | session CACHE ROOT VALUE | raw-final CACHE"
