{-# LANGUAGE OverloadedStrings #-}
-- Real production API controls. This program never changes compiler globals.
module Main where
import Prelude
import Control.Monad (unless, forM_)
import Control.Exception (bracket)
import Data.List (sort, isInfixOf)
import System.IO (hFlush, stdout)
import qualified Data.ByteString as BS
import System.Directory (createDirectory, doesPathExist, listDirectory, renameFile, removeFile, getModificationTime)
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

-- Scratch lifecycle controls are additive to the original 18-call suite.
cleanupDirectoryError = "cannot remove query key scratch: path is a directory"
badMembers = [("aGood",T.Nothing,T.SIntLit 1),
              ("zBad",T.Nothing,T.SApp (T.SVar "aGood") (T.SIntLit 2))]
checkBusinessLeft directory result = do
  message <- case result of T.Left e -> pure e; T.Right _ -> error "bad application unexpectedly inferred"
  need "failure is inference, not prevalidation or cleanup" ("type constructor mismatch:" `isInfixOf` B.unpack message)
  files <- listDirectory directory
  need "dependency group was compiled before business Left" (any (\name -> reverse (take 5 (reverse name)) == ".mlfq") files)
  save (directory ++ ".left-message") message
  putStrLn "PASS business Left after held-lock group execution"
leftLegacy directory = Q.compileGroups "scratch-error" (literal directory) [] [] badMembers >>= checkBusinessLeft directory
leftSource directory = do
  let scopes = M.fromList P.compareString [(name,IS.empty) | (name,_,_) <- badMembers]
  maybePlan <- expect "invalid application still forms source plan" (SI.prepareSourcePlan M.empty [] [] [] scopes [] badMembers)
  plan <- case maybePlan of T.Just p -> pure p; _ -> error "business Left fixture fell back before source runner"
  Q.compileParsedSourceGroups "scratch-error" (literal directory) [] M.empty plan >>= checkBusinessLeft directory
leftSession directory root = do
  let sourcePath = root </> "ScratchFailure.hs"
      specPath = root </> "failure.spec"
      prefix = root </> "failure"
      source = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule ScratchFailure where { import MLF.Primitive; aGood :: Int; aGood = 1; zBad = aGood (2 :: Int) }\n"
      spec = U.pack ["MLF-CRATE-1","scratch-failure","","true",
             U.pack [U.pack ["ScratchFailure",literal sourcePath]],U.pack [],literal directory,literal (root </> "builtin")]
  writeFile sourcePath source
  save specPath spec
  Session.compileSpecFile (literal specPath) (literal prefix) >>= checkBusinessLeft directory
emptySuccess directory = do
  (objects,report) <- Q.compileGroups "scratch-empty" (literal directory) [] [] [] >>= expect "empty plan cleanup"
  need "empty plan remains empty" (null objects && Q.inferredCount report == 0 && Q.reusedCount report == 0)
  putStrLn "PASS empty public plan cleans stale scratch"
emptyDirectoryFailure directory = do
  result <- Q.compileGroups "scratch-empty" (literal directory) [] [] []
  case result of
    T.Left message -> need "directory cleanup failure is explicit" (message == cleanupDirectoryError)
    T.Right _ -> error "directory cleanup failure incorrectly reported success"
  putStrLn "PASS directory scratch rejected without recursive deletion"
cleanupDualFailure directory = do
  -- cleanupQueryKey does not own the lock. This helper control uses the real
  -- lock explicitly and does NOT pretend to cover public-entry release itself.
  bracket (P.acquireFileLock (literal (directory </> ".lock"))) P.releaseFileLock $ \_ -> do
    result <- Q.cleanupQueryKey (literal directory) (T.Left "original-business-error" :: T.Either P.String ())
    case result of
      T.Left message -> need "dual failure retains both errors" (message == "original-business-error; " P.++ cleanupDirectoryError)
      T.Right _ -> error "dual failure incorrectly reported success"
  putStrLn "PASS original Left and cleanup Left are both retained"
awaitProbe action = do
  action
  hFlush stdout
  acknowledgement <- getLine
  need "fixed independent probe acknowledgement" (acknowledgement == "PROBE-ACK")

concurrent directory resultFile = do
  putStrLn "READY"
  hFlush stdout
  query directory resultFile 41

main = do
  args <- getArgs
  case args of
    ["memo-helper",directory] -> memoHelper directory
    ["memo-query",directory,root] -> memoQuery directory root
    ["memo-session",directory,root] -> memoSession directory root
    ["helper",directory] -> helper directory
    ["query",directory,resultFile,value] -> query directory resultFile (read value)
    ["session",directory,root,value] -> session directory root (read value :: Int)
    ["raw-final",directory] -> rawFinal directory
    ["legacy-one",directory] -> legacyOne directory
    ["left-legacy",directory,"await-probe"] -> awaitProbe (leftLegacy directory)
    ["left-source",directory,"await-probe"] -> awaitProbe (leftSource directory)
    ["left-session",directory,root,"await-probe"] -> awaitProbe (leftSession directory root)
    ["empty-success",directory] -> emptySuccess directory
    ["empty-directory-failure",directory,"await-probe"] -> awaitProbe (emptyDirectoryFailure directory)
    ["cleanup-dual-failure",directory,"await-probe"] -> awaitProbe (cleanupDualFailure directory)
    ["concurrent",directory,resultFile] -> concurrent directory resultFile
    _ -> error "expected helper DIR | query CACHE FINAL VALUE | session CACHE ROOT VALUE | raw-final CACHE"

-- Invocation-local memo controls: returned states are obtained only from real
-- successful readers. Constructors are not opaque security capabilities.
withMemoLock directory = bracket (P.acquireFileLock (literal (directory </> ".lock"))) P.releaseFileLock
memoAbsent state = case state of T.Nothing -> True; T.Just _ -> False
memoGood label reused prepared raw (next,actual,result) = do
  need (label ++ " branch/state") (actual == reused && not (memoAbsent next))
  object <- expect label result
  checked <- expect (label ++ " prepared raw") (SI.validatePreparedRaw prepared object)
  need (label ++ " complete raw object") (sameObject raw checked)
  pure next
memoBad label reused (next,actual,result) = do
  need (label ++ " branch/state") (actual == reused && memoAbsent next)
  reject label result
memoEntry directory plan (Q.GroupResult groupId memberNames _ _ digest) = do
  input <- readText (directory </> (B.unpack digest ++ ".mlfq"))
  (ref,compact,payload) <- recordParts input
  blob <- readText (B.unpack (Q.sourceContextPath (literal directory) ref))
  need "helper real empty context" (blob == Q.sourceContextContents (Q.encodeDatatypeContext []))
  key <- expect "helper complete key" (Q.restoreSourceCacheKey (Q.encodeDatatypeContext []) compact)
  raw <- expect "helper actual raw" (U.decodeContextualObject [] [] payload)
  prepared <- expect "helper actual prepared" (SI.prepareGroup plan M.empty memberNames)
  _ <- expect "helper original prepared validation" (SI.validatePreparedRaw prepared raw)
  pure (groupId,memberNames,key,input,raw,prepared)
memoRead previous directory (groupId,memberNames,key,input,_,_) =
  Q.readSourceCachedWithContext previous (literal directory) key groupId [] [] memberNames input
memoContextHandshake marker ref acknowledgement = do
  putStrLn (marker ++ " " ++ B.unpack ref)
  hFlush stdout
  answer <- getLine
  need "exact context identity acknowledgement" (answer == acknowledgement)

memoHelper directory = do
  fresh directory
  plan <- makePlan 41
  (_,cold,_) <- Q.compileParsedSourceGroups "memo-helper" (literal directory) [] M.empty plan >>= expect "memo helper cold"
  need "memo helper two cold groups" (Q.inferredCount cold == 2 && Q.reusedCount cold == 0)
  let Q.QueryReport _ _ groups = cold
  (first,second) <- case groups of [a,b] -> pure (a,b); _ -> error "two independent memo groups required"
  withMemoLock directory $ \_ -> do
    firstEntry@(_,_,_,_,rawA,preparedA) <- memoEntry directory plan first
    secondEntry@(gid,ns,key,input,rawB,preparedB) <- memoEntry directory plan second
    memo <- memoRead T.Nothing directory firstEntry >>= memoGood "first verified context" False preparedA rawA
    memoRead memo directory secondEntry >>= memoGood "same context verified reuse" True preparedB rawB >> pure ()
    (ref,compact,payload) <- recordParts input
    let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
        backup = contextPath ++ ".memo-test-backup"
    exists <- doesPathExist backup
    need "fresh private backup" (not exists)
    memoContextHandshake "MEMO-CONTEXT-BEFORE" ref "MEMO-BEFORE-ACK"
    -- Counterfactual only: a private cooperating test holds the actual lock.
    -- This is NOT a public-driver guarantee for lock-ignoring mutations.
    bracket (renameFile contextPath backup) (\_ -> renameFile backup contextPath) $ \_ -> do
      memoRead memo directory secondEntry >>= memoGood "verified memo without context IO" True preparedB rawB >> pure ()
      memoRead T.Nothing directory secondEntry >>= memoBad "empty memo needs context file" False
    memoContextHandshake "MEMO-CONTEXT-AFTER" ref "MEMO-AFTER-ACK"
    let readChanged prev dir k owner bindings ds wanted record =
          Q.readSourceCachedWithContext prev (literal dir) k owner bindings ds wanted record
        readSame k owner bindings ds wanted record = readChanged memo directory k owner bindings ds wanted record
    readSame key gid [] [] ns (newRecord ref compact "") >>= memoBad "memo rejects bad payload" True
    fs <- fields key
    let change i = U.pack [if j == i then value P.++ "!" else value | (j,value) <- zip [0..] fs]
    readSame (change 8) gid [] [] ns input >>= memoBad "memo rejects full scope key change" True
    readSame key "WrongOwner" [] [] ns input >>= memoBad "memo rejects owner change" True
    readSame key gid [("external",T.XCon "Int" [])] [] ns input >>= memoBad "memo rejects parameter change" True
    readSame key gid [] [] ["wrongName"] input >>= memoBad "memo rejects declaration change" True
    readSame (change 5) gid [] [] ns input >>= memoBad "memo rejects context field change" False
    let otherRef = literal (replicate 64 '0')
    need "distinct absent valid digest" (otherRef /= ref)
    absent <- doesPathExist (B.unpack (Q.sourceContextPath (literal directory) otherRef))
    need "no zero digest context" (not absent)
    readSame key gid [] [] ns (newRecord otherRef compact payload) >>= memoBad "memo rejects different digest" False
    readSame key gid [] [] ns (newRecord "../escape" compact payload) >>= memoBad "memo rejects unsafe reference" False
    let otherDirectory = directory </> "different-cache"
    fresh otherDirectory
    withMemoLock otherDirectory $ \_ ->
      readChanged memo otherDirectory key gid [] [] ns input >>= memoBad "memo does not cross cache directory" False
    forM_ [("CACHE1",Q.encodeCached key rawB,key),
           ("CACHE2",Q.encodeCached (Q.queryKey "legacy-memo" "compiler" (members 41) [] []) rawB,
                     Q.queryKey "legacy-memo" "compiler" (members 41) [] [])] $ \(label,legacy,legacyKey) -> do
      (next,reused,result) <- readChanged memo directory legacyKey gid [] [] ns legacy
      need (label ++ " clears context memo") (memoAbsent next && not reused)
      obj <- expect (label ++ " read") result
      checked <- expect (label ++ " prepared") (SI.validatePreparedRaw preparedB obj)
      need (label ++ " exact raw") (sameObject rawB checked)
    putStrLn "PASS legacy readers clear memo without changing raw"
    memoDatatypeControls directory memo
  memoPreparedControl (directory </> "prepared-counterexample")
  putStrLn "PASS memo helper complete"

memoDatatypeControls directory previous = do
  let box = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
      own = [("value",T.Nothing,T.SApp (T.SConstructor "Box") (T.SIntLit 7))]
      scopes = M.fromList P.compareString [("value",IS.empty)]
  maybePlan <- expect "box plan" (SI.prepareSourcePlan M.empty [box] [] [] scopes [] own)
  plan <- case maybePlan of T.Just p -> pure p; _ -> error "box plan unavailable"
  prepared <- expect "box prepared" (SI.prepareGroup plan M.empty ["value"])
  raw <- expect "box raw" (I.compileLoweredGroup "RawGroup" [] [box] own)
  let key = keyFor (Q.encodeDatatypeContext [box])
      path = directory </> "box-record.mlfq"
      readBox state ds input = Q.readSourceCachedWithContext state (literal directory) key "RawGroup" [] ds ["value"] input
  Q.writeSourceCached T.Nothing (literal directory) (literal path) key raw >>= expect "box write"
  input <- readText path
  memo <- readBox previous [box] input >>= memoGood "different valid context refreshes" False prepared raw
  readBox memo [box] input >>= memoGood "different valid context reuses" True prepared raw >> pure ()
  forM_ [("kind",T.DataDeclK "Box" [("a",T.KArrow T.Star T.Star)] [T.ConstructorDecl "Box" [T.Parameter "a"]]),
         ("constructor",T.DataDecl "Box" ["a"] [T.ConstructorDecl "ChangedBox" [T.Parameter "a"]]),
         ("field",T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a",T.Parameter "a"]])] $ \(label,changed) ->
    readBox memo [changed] input >>= memoBad ("memo rejects datatype " ++ label ++ " change") False
  putStrLn "PASS datatype switch and structural guards"

memoCycle directory root invoke = do
  fresh root
  fresh directory
  let call phase = do
        (artifact,report) <- invoke phase
        save (root </> (phase ++ ".artifact")) artifact
        save (root </> (phase ++ ".queries")) report
        scratch <- doesPathExist (directory </> "query-key.new")
        need "memo public call cleans scratch" (not scratch)
        pure artifact
  baseline <- call "cold"
  warm <- call "warm"
  need "memo warm final complete equality" (warm == baseline)
  files <- sort <$> listDirectory directory
  selected <- case filter (\n -> reverse (take 5 (reverse n)) == ".mlfq") files of
    [a,_] -> pure a
    _ -> error "memo public program must have exactly two records"
  let file = directory </> selected
  original <- readText file
  (ref,compact,payload) <- recordParts original
  let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
  contextBlob <- readText contextPath
  need "memo public empty datatype fixture" (contextBlob == Q.sourceContextContents (Q.encodeDatatypeContext []))
  key <- expect "memo public full key" (Q.restoreSourceCacheKey (Q.encodeDatatypeContext []) compact)
  raw <- expect "memo public raw" (U.decodeContextualObject [] [] payload)
  let legacy = Q.encodeCached key raw
  withMemoLock directory $ \_ -> save file legacy
  stamp <- getModificationTime file
  mixed <- call "mixed"
  legacyAfter <- readText file
  stampAfter <- getModificationTime file
  need "legacy hit bytes/mtime unchanged during mixed call" (legacyAfter == legacy && stampAfter == stamp)
  need "memo mixed complete final equality" (mixed == baseline)
  -- Explicit test setup, not a claim that the legacy entry is never rewritten.
  -- Restore ALL C3 before invalidation so a wrongly global memo cannot hide
  -- behind a preceding legacy reset in the next invocation.
  withMemoLock directory $ \_ -> save file original
  restored <- call "restored-warm"
  need "restored C3 final equality" (restored == baseline)
  withMemoLock directory $ \_ -> save contextPath "corrupt-context-for-next-invocation"
  repaired <- call "corrupt-repair"
  actual <- readText contextPath
  need "corrupt context repaired on next invocation" (actual == contextBlob && repaired == baseline)
  withMemoLock directory $ \_ -> removeFile contextPath
  missing <- call "missing-repair"
  after <- readText contextPath
  need "missing context repaired on next invocation" (after == contextBlob && missing == baseline)
  save (root </> "context.original") contextBlob
  putStrLn "PASS six public invocations preserve complete final artifacts and repair context"

memoQuery directory root = do
  plan <- makePlan 41
  memoCycle directory root $ \_ -> do
    (objects,report,_) <- Q.compileParsedSourceGroups "memo-query" (literal directory) [] M.empty plan >>= expect "memo Query public driver"
    pure (U.pack (map U.encodeObject objects),Q.reportJSON "memo-query" "memo" report)

memoSession directory root = do
  -- The source/spec bytes remain identical across all six public invocations.
  let sourcePath = root </> "MemoSession.hs"
      specPath = root </> "memo.spec"
      prefix = root </> "memo"
      source = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule MemoSession where { import MLF.Primitive; first :: Int; first = 41; second :: Int; second = 99 }\n"
      spec = U.pack ["MLF-CRATE-1","memo-session","","true",U.pack [U.pack ["MemoSession",literal sourcePath]],U.pack [],literal directory,literal (root </> "builtin")]
  memoCycle directory root $ \phase -> do
    if phase == "cold" then writeFile sourcePath source >> save specPath spec else pure ()
    Session.compileSpecFile (literal specPath) (literal prefix) >>= expect "memo Session public driver"
    iface <- readText (prefix ++ ".mlfci")
    objects <- readText (prefix ++ ".mlfco")
    report <- readText (prefix ++ ".queries")
    pure (U.pack [iface,objects],report)

memoPreparedControl directory = do
  fresh directory
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
  (objects,cold,contracts) <- Q.compileSourceGroups "raw-final" (literal directory) [] M.empty plan >>= expect "raw/final cold"
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

  prepared <- expect "counterexample actual prepared authority"
    (SI.prepareGroup plan (M.filterWithKey (\name _ -> name /= "sameDeps") contracts) ["sameDeps"])
  withMemoLock directory $ \_ -> do
    memo <- Q.readSourceCachedWithContext T.Nothing (literal directory) key groupId parameters ds ["sameDeps"] input
      >>= memoGood "counterexample verified raw" False prepared raw
    let poisoned = newRecord ref compact (U.encodeContextualObject finalObject)
    (next,reused,result) <- Q.readSourceCachedWithContext memo (literal directory) key groupId parameters ds ["sameDeps"] poisoned
    need "final payload reaches verified reuse branch" (reused && not (memoAbsent next))
    decoded <- expect "generic memo reader admits final counterexample" result
    need "counterexample final decoded exactly" (sameObject decoded finalObject && not (sameObject decoded raw))
    reject "prepared authority rejects memo-decoded final payload" (SI.validatePreparedRaw prepared decoded)
  -- The reader cannot clear a later PreparedRaw failure it never receives.
  -- Both public workers clear it; unchanged original raw-final controls cover
  -- their real reinference, rather than claiming this helper owns that check.
