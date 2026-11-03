{-# LANGUAGE OverloadedStrings #-}
-- Real production API controls. This program never changes compiler globals.
module Main where
import Prelude
import Control.Monad (unless, forM_)
import Control.Exception (bracket)
import Data.List (sort, isInfixOf, nub)
import System.IO (hFlush, stdout)
import qualified Data.ByteString as BS
import System.Directory (createDirectory, doesPathExist, listDirectory, renameFile, removeFile, getModificationTime)
import System.Environment (getArgs)
import qualified Bootstrap.Data as D
import qualified Bootstrap.Types as T
import qualified Bootstrap.Bitstream as Wire
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.Std as Std
import qualified Bootstrap.Map as M
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.SourceInference as SI
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.CrateSession as Session
import qualified Bootstrap.Crate as Crate
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Separate as U
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Pretty as Pretty
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
keyFor context = U.pack ["MLF-SOURCE-CRATE-QUERY-7", "crate:α😀", "compiler",
                        "member:opaque:😀", "bindings", context,
                        "source-group", "observed-contracts", "scope-table:α😀"]
splitKey key = case Q.sourceCacheParts key of
  T.Just pair -> pure pair
  T.Nothing -> error "source v7 not recognized"
-- No textual view is ever fed to the new production reader. RecordInput keeps
-- the actual typed binary graph separate from explicitly old compatibility text.
data RecordInput = LegacyInput P.String | BinaryInput [Wire.Value]
data Payload = Payload Wire.Value Wire.Value
valueEqual a b = case (a,b) of
  (Wire.VInt x,Wire.VInt y) -> x == y
  (Wire.VBits x,Wire.VBits y) -> x == y
  (Wire.VText x,Wire.VText y) -> x == y
  (Wire.VNode x xs,Wire.VNode y ys) -> x == y && length xs == length ys && and (zipWith valueEqual xs ys)
  _ -> False
instance Eq RecordInput where
  LegacyInput a == LegacyInput b = a == b
  BinaryInput a == BinaryInput b = length a == length b && and (zipWith valueEqual a b)
  _ == _ = False
instance Eq Payload where
  Payload a b == Payload c d = valueEqual a c && valueEqual b d
readRecord path = do
  bytes <- Storage.readRaw (literal path) >>= expect "actual query bytes"
  input <- Storage.decode 2 bytes >>= expect "actual query wire decoder"
  case input of
    Storage.LegacyText text -> pure (LegacyInput text)
    Storage.BinaryInput _ -> do
      roots <- Wire.decode Wire.defaultLimits 2 bytes >>= expect "bounded fixture typed inspection"
      pure (BinaryInput roots)
saveRecord path record = case record of
  LegacyInput text -> save path text
  BinaryInput roots -> Storage.write 2 (literal path) roots >>= expect "write actual binary test record"
legacyRecord ref compact payload = U.pack ["MLF-QUERY-CACHE-3",ref,compact,payload]
legacyRecordParts text = do
  xs <- fields text
  case xs of
    ["MLF-QUERY-CACHE-3",ref,compact,payload] -> pure (ref,compact,payload)
    _ -> error "expected explicitly legacy CACHE3"
newRecord ref compact (Payload header body) =
  let parts = case U.unpack compact of
        T.Right xs -> Structure.toList Structure.toText xs
        T.Left _ -> Wire.VNode 2147483647 []
  in BinaryInput [Wire.VNode 301 [Wire.VText ref,parts,header,body]]
badPayload = Payload (Wire.VNode 2147483647 []) (Wire.VNode 2147483647 [])
badPayloadDiagnostic = "malformed binary artifact UnitInterface tag"
recordParts record = case record of
  BinaryInput [Wire.VNode 301 [Wire.VText ref,parts,header,body]] -> do
    compact <- expect "typed compact key" (Structure.fromList Structure.fromText parts)
    pure (ref,U.pack compact,Payload header body)
  _ -> error "default source writer did not produce structured binary shared record"
payloadFor raw = Payload
  (Structure.toUnitInterface (U.withInterfaceData (U.objectInterface raw) []
    (U.fingerprint (Pretty.prettyTerm (U.objectBody raw)))))
  (Structure.toXTerm (U.objectBody raw))
-- Shared metadata carries the body-only semantic checksum, just like MLFF2.
-- The full object hash is rebuilt under the independently expected context;
-- alpha-equivalent datatype spelling may differ without weakening body checks.
decodePayload ds (Payload header body) = do
  iface <- Structure.fromUnitInterface header
  Std.ensure (null (U.unitData iface)) "contextual fragment contains an inline datatype header"
  term <- Structure.fromXTerm body
  Std.ensure (U.fingerprint (Pretty.prettyTerm term) == U.unitObjectFingerprint iface)
    "contextual fragment body checksum mismatch"
  let complete = T.XWithData ds term
  Storage.checkUnit (U.UnitObject
    (U.withInterfaceData iface ds (U.fingerprint (Pretty.prettyTerm complete))) complete)
readContext path = do
  bytes <- Storage.readRaw (literal path) >>= expect "actual context bytes"
  roots <- Wire.decode Wire.defaultLimits 1 bytes >>= expect "actual binary context decoder"
  case roots of
    [root] -> expect "typed datatype context" (Structure.fromDataContext root)
    _ -> error "default context is not binary"
contextLogical path = Q.sourceContextContents . Q.encodeSourceDatatypes <$> readContext path
readRecordWindow previous directory key name bindings ds wanted record = case record of
  LegacyInput text -> Q.readSourceCachedWithWindow previous directory key name bindings ds wanted text
  BinaryInput roots -> do
    bytes <- Storage.encode 2 roots >>= expect "encode real binary mutation"
    graph <- Wire.decodeGraph Wire.defaultLimits 2 bytes >>= expect "decode real binary mutation graph"
    Q.readBinarySourceGraph previous directory key name bindings ds wanted graph
readRecordMemo previous directory key name bindings ds wanted record = do
  let entries = case previous of T.Nothing -> []; T.Just entry -> [entry]
  (next,reused,result) <- readRecordWindow entries directory key name bindings ds wanted record
  pure ((case next of [] -> T.Nothing; x:_ -> T.Just x),reused,result)
readRecordChecked directory key name bindings ds wanted record = do
  (_,_,result) <- readRecordWindow [] directory key name bindings ds wanted record
  pure result
readNew directory key input = readRecordChecked (literal directory) key "RawGroup" [] [] names input
readFormal prefix = do
  iface <- A.readInterface (literal (prefix ++ ".mlfci")) >>= expect "actual binary/legacy formal interface"
  object <- A.readObject (literal (prefix ++ ".mlfco")) iface >>= expect "actual binary/legacy formal object"
  pure (A.encodeInterface iface,A.encodeObject object)

helper directory = do
  fresh directory
  bracket (P.acquireFileLock (literal (directory </> ".lock"))) P.releaseFileLock (\_ -> helperLocked directory)
helperLocked directory = do
  object <- expect "raw inference" (I.compileLoweredGroup "RawGroup" [] [] (members 41))
  let context = Q.encodeSourceDatatypes []
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
  input <- readRecord path
  (ref,compact,payload) <- recordParts input
  (expectedCompact,expectedContext) <- splitKey key
  need "source parts retain all eight non-context fields" (compact == expectedCompact && context == expectedContext)
  restored <- expect "restore source key" (Q.restoreSourceCacheKey context compact)
  need "full Unicode/scalar key roundtrip" (restored == key)
  let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
  originalContextBytes <- BS.readFile contextPath
  blob <- contextLogical contextPath
  need "canonical context blob" (blob == Q.sourceContextContents context)
  digest <- P.fileDigest (literal contextPath)
  need "context SHA filename" (digest == ref && Q.validSourceContextDigest ref)
  checked <- readNew directory key input >>= expect "source CACHE3 reader"
  need "source checked object preserved" (sameObject checked object)
  -- Keep compiler, key pathname, context and well-typed payload fixed. Only
  -- change the saved identity, including after a successful context read.
  let builtins = D.builtinDeclarations
      tag = "MLF-SOURCE-CRATE-QUERY-7"
      changed = T.DataDecl "MLFLegacyUnit" [] [T.ConstructorDecl "MLFLegacyUnit" [T.Applied "Int" []]]
      candidates = [drop 1 builtins, reverse builtins, changed:drop 1 builtins,
                    T.DataDeclK "MLFLegacyUnit" [] [T.ConstructorDecl "MLFLegacyUnit" []]:drop 1 builtins]
      identities = map Q.sourceFormatFor candidates
  -- Independent MLFBIN tree_document(244, builtin_datatypes()) golden.
  -- This pins even raw binder names if both the live and frozen lists change.
  witness <- Storage.encode 1 [Structure.toDataContext Q.v7BuiltinDictionary] >>= expect "exact v7 dictionary"
  witnessDigest <- P.byteArrayDigest witness
  need "immutable v7 wire dictionary" (witnessDigest == "8769bc0f30eed0ef497f2b414239f9c8facc1dde749de6dcd7251da1a495224f")
  need "v7 dictionary binds every actual declaration" (length builtins == 68 && Q.sourceQueryFormat == tag)
  need "changed builtin order, constructor fields and declaration variants have distinct literal identities"
    (all (/=tag) identities && length (nub identities) == length candidates)
  compactFields <- fields compact
  fullFields <- fields key
  (window,_,_) <- readRecordWindow [] (literal directory) key "RawGroup" [] [] names input
  need "real verified context for substituted-record controls" (not (null window))
  forM_ (("pre-v7", "MLF-SOURCE-CRATE-QUERY-6") : zip (map show [1::Int ..]) identities) $ \(label,fmt) -> do
    let forge xs = U.pack (fmt:drop 1 xs)
        record = newRecord ref (forge compactFields) payload
    need (label ++ " claimed builtin identity rejected even with matching supplied key")
      (case Q.sourceCacheParts (forge fullFields) of T.Nothing -> True; _ -> False)
    (_,_,result) <- readRecordWindow window (literal directory) key "RawGroup" [] [] names record
    reject (label ++ " saved identity at current key with verified context") result
  let differentCompiler = U.pack (take 2 compactFields ++ ["other compiler"] ++ drop 3 compactFields)
  (_,_,foreignCompiler) <- readRecordWindow window (literal directory) key "RawGroup" [] [] names (newRecord ref differentCompiler payload)
  reject "foreign compiler at current address" foreignCompiler
  stamp <- getModificationTime contextPath
  let pooledPath = directory </> "pooled.mlfq"
  Q.writeSourceCached (T.Just (Q.prepareSourceEncodings [])) (literal directory) (literal pooledPath) key object >>= expect "pooled source write"
  pooled <- readRecord pooledPath
  stampAfter <- getModificationTime contextPath
  need "pool changes neither bytes nor existing context mtime" (pooled == input && stamp == stampAfter)
  -- Real binary typed mutations isolate admission, with original expected key.
  let decode k n bindings ds ns record = readRecordChecked (literal directory) k n bindings ds ns record
  decode key "WrongOwner" [] [] names input >>= reject "changed group ownership"
  decode key "RawGroup" [] [] ["other"] input >>= reject "changed declaration ownership"
  decode key "RawGroup" [("external",T.XCon "Int" [])] [] names input >>= reject "changed dependency parameters"
  decode key "RawGroup" [] [T.DataDecl "Other" [] [T.ConstructorDecl "Other" []]] names input >>= reject "different expected datatype layout"
  forM_ [0,1,2,3,4,6,7,8] $ \index -> do
    original <- fields key
    let changed = U.pack [if i == index then x P.++ "!" else x | (i,x) <- zip [0..] original]
    decode changed "RawGroup" [] [] names input >>= reject ("key field " ++ show index ++ " changed")
  -- Each carrier is encoded with a valid wire checksum and hashed to its own
  -- actual filename, so these failures exercise typed/context admission.
  let wrongContext label roots = do
        let stage = directory </> "test-context.new"
        Storage.write 1 (literal stage) roots >>= expect "encode malformed context fixture"
        badRef <- P.fileDigest (literal stage)
        let badPath = B.unpack (Q.sourceContextPath (literal directory) badRef)
        need "negative carrier cannot overwrite valid context" (badRef /= ref)
        renameFile stage badPath
        readNew directory key (newRecord badRef compact payload) >>= reject label
        removeFile badPath
  wrongContext "context carrier changed" [Structure.toDataContext [T.DataDecl "Other" [] [T.ConstructorDecl "Other" []]]]
  wrongContext "context carrier wrong version" [Wire.VNode 2147483647 []]
  wrongContext "context carrier extra field" [Structure.toDataContext [], Wire.VInt 1]
  decode key "RawGroup" [] [] names (newRecord ref compact badPayload) >>= reject "payload truncated"
  let trailing = case input of BinaryInput [Wire.VNode tag children] -> BinaryInput [Wire.VNode tag (children ++ [Wire.VInt 1])]; _ -> error "shared roots"
  decode key "RawGroup" [] [] names trailing >>= reject "record trailing field"
  -- Framing canonicality is wire-owned; actual malformed bytes must not decode.
  originalRecordBytes <- BS.readFile path
  BS.writeFile (directory </> "noncanonical.new") (originalRecordBytes <> BS.singleton 0)
  Storage.read 2 (literal (directory </> "noncanonical.new")) >>= reject "noncanonical record framing"
  removeFile (directory </> "noncanonical.new")
  decode key "RawGroup" [] [] names (newRecord ref "" payload) >>= reject "compact key truncated"
  let zeroRef = literal (replicate 64 '0')
      zeroPath = B.unpack (Q.sourceContextPath (literal directory) zeroRef)
  need "actual digest negative path fresh" =<< (not <$> doesPathExist zeroPath)
  BS.writeFile zeroPath originalContextBytes
  readNew directory key (newRecord zeroRef compact payload) >>= reject "actual context digest differs"
  removeFile zeroPath
  forM_ ["../escape", "", literal (replicate 63 'a'), literal (replicate 64 'A'), literal (replicate 64 'g')] $ \bad -> do
    need "invalid digest rejected before path use" (not (Q.validSourceContextDigest bad))
    readNew directory key (newRecord bad compact payload) >>= reject "untrusted context reference"
  renameFile contextPath (contextPath ++ ".saved")
  readNew directory key input >>= reject "missing context"
  renameFile (contextPath ++ ".saved") contextPath
  save contextPath "truncated"
  readNew directory key input >>= reject "corrupt context digest/content"
  BS.writeFile contextPath originalContextBytes
  readNew directory key input >>= expect "context restored" >> pure ()
  -- Distinct key changes only an unrelated field; one exact context remains.
  keyFields <- fields key
  let secondKey = U.pack [if i == 1 then "another-crate" else value | (i,value) <- zip [0..] keyFields]
  Q.writeSourceCached T.Nothing (literal directory) (literal (directory </> "second.mlfq")) secondKey object >>= expect "shared context second record"
  files <- sort <$> listDirectory directory
  need "one shared context file and no stage temporary" (length (filter (\x -> take 8 x == "context-") files) == 1 && not ("source-context.new" `elem` files))
  -- A mismatched v7 context must retain the established self-contained format.
  Q.writeSourceCached T.Nothing (literal directory) (literal (directory </> "fallback.mlfq")) (keyFor "wrong") object >>= expect "safe fallback write"
  fallback <- readRecord (directory </> "fallback.mlfq")
  need "ineligible source object uses checked binary inline format" (case fallback of BinaryInput [Wire.VNode 300 [Wire.VText saved,_]] -> saved == keyFor "wrong"; _ -> False)
  fallbackObject <- readRecordChecked (literal directory) (keyFor "wrong") "RawGroup" [] [] names fallback >>= expect "inline fallback semantic read"
  need "inline fallback preserves complete raw" (sameObject fallbackObject object)
  Q.writeSourceCached T.Nothing (literal directory) (literal (directory </> "legacy2.mlfq")) legacyKey object >>= expect "non-source inline write fallback"
  legacy2 <- readRecord (directory </> "legacy2.mlfq")
  need "non-source default is binary inline" (case legacy2 of BinaryInput [Wire.VNode 300 [Wire.VText saved,_]] -> saved == legacyKey; _ -> False)
  inlineObject <- readRecordChecked (literal directory) legacyKey "RawGroup" [] [] names legacy2 >>= expect "non-source inline read"
  need "non-source inline raw equals independently read old CACHE2" (sameObject inlineObject b)
  let boxA = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
      boxB = T.DataDecl "Box" ["b"] [T.ConstructorDecl "Box" [T.Parameter "b"]]
      changedBox = T.DataDecl "Box" ["b"] [T.ConstructorDecl "Box" [T.Parameter "b", T.Parameter "b"]]
      boxMembers = [("value",T.Nothing,T.SApp (T.SConstructor "Box") (T.SIntLit 7))]
      boxKey = keyFor (Q.encodeSourceDatatypes [boxA])
      boxPath = directory </> "box.mlfq"
  boxObject <- expect "nonempty datatype raw inference" (I.compileLoweredGroup "RawGroup" [] [boxA] boxMembers)
  need "alpha test setup uses identical complete canonical contexts" (Q.encodeSourceDatatypes [boxA] == Q.encodeSourceDatatypes [boxB])
  let boxLegacyKey = Q.queryKey "legacy-box" "compiler" boxMembers [] [boxA]
  _ <- Q.readSourceCached (literal directory) boxKey "RawGroup" [] [boxB] names (Q.encodeCached boxKey boxObject) >>= expect "legacy CACHE1 alpha compatibility"
  _ <- Q.readSourceCached (literal directory) boxLegacyKey "RawGroup" [] [boxB] names (Q.encodeCached boxLegacyKey boxObject) >>= expect "legacy CACHE2 alpha compatibility"
  Q.writeSourceCached (T.Just (Q.prepareSourceEncodings [boxA])) (literal directory) (literal boxPath) boxKey boxObject >>= expect "nonempty shared context write"
  boxInput <- readRecord boxPath
  (boxRef,_,_) <- recordParts boxInput
  need "different complete datatype context has different identity" (boxRef /= ref)
  alpha <- readRecordChecked (literal directory) boxKey "RawGroup" [] [boxB] names boxInput >>= expect "alpha-equivalent datatype context remains admissible"
  need "alpha-equivalent metadata preserves canonical layout" (Q.encodeSourceDatatypes (U.unitData (U.objectInterface alpha)) == Q.encodeSourceDatatypes [boxA])
  readRecordChecked (literal directory) boxKey "RawGroup" [] [changedBox] names boxInput >>= reject "same datatype name different layout"
  let legacyContextPath = directory </> "legacy-context.new"
  save legacyContextPath (Q.sourceContextContents context)
  legacyRef <- P.fileDigest (literal legacyContextPath)
  let legacyContextDestination = B.unpack (Q.sourceContextPath (literal directory) legacyRef)
      legacy3 = legacyRecord legacyRef compact (U.encodeContextualObject object)
  need "old context namespace distinct from binary" (legacyRef /= ref)
  renameFile legacyContextPath legacyContextDestination
  old3 <- Q.readSourceCached (literal directory) key "RawGroup" [] [] names legacy3 >>= expect "true legacy CACHE3 reader"
  need "true legacy CACHE3 preserves complete raw" (sameObject old3 object)
  removeFile legacyContextDestination
  putStrLn "PASS helper CACHE1/CACHE2/CACHE3, complete-key and corrupt-input controls"

legacyOne directory = do
  files <- sort . filter (\name -> reverse (take 5 (reverse name)) == ".mlfq") <$> listDirectory directory
  file <- case files of x:_ -> pure (directory </> x); _ -> error "missing query record"
  input <- readRecord file
  (ref,compact,payload) <- recordParts input
  blob <- contextLogical (B.unpack (Q.sourceContextPath (literal directory) ref)) >>= fields
  context <- case blob of ["MLF-SOURCE-QUERY-CONTEXT-1",c] -> pure c; _ -> error "context shape"
  key <- expect "legacy conversion full key" (Q.restoreSourceCacheKey context compact)
  raw <- expect "legacy conversion raw object" (decodePayload [] payload)
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
      input <- readRecord (directory </> (B.unpack digest ++ ".mlfq"))
      (key,raw) <- case input of
        BinaryInput _ -> do
          (ref,compact,payload) <- recordParts input
          actualContext <- contextLogical (B.unpack (Q.sourceContextPath (literal directory) ref))
          actualDigest <- P.fileDigest (Q.sourceContextPath (literal directory) ref)
          need "accounting empty datatype context" (actualContext == Q.sourceContextContents (Q.encodeSourceDatatypes []))
          need "accounting context digest" (actualDigest == ref)
          key <- expect "accounting full key" (Q.restoreSourceCacheKey (Q.encodeSourceDatatypes []) compact)
          raw <- expect "accounting contextual raw" (decodePayload [] payload)
          pure (key,raw)
        LegacyInput text -> do
          fs <- fields text
          case fs of
            ["MLF-QUERY-CACHE-1",key,iface,payload] -> do
              i <- expect "accounting legacy interface" (U.decodeInterface iface)
              raw <- expect "accounting legacy raw" (U.decodeObject i payload)
              pure (key,raw)
            _ -> error "accounting unsupported legacy representation"
      (_,context) <- splitKey key
      need "accounting full key empty context" (context == Q.encodeSourceDatatypes [])
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
  input <- readRecord file
  (ref,compact,payload) <- recordParts input
  contextBlob <- contextLogical (B.unpack (Q.sourceContextPath (literal directory) ref)) >>= fields
  context <- case contextBlob of ["MLF-SOURCE-QUERY-CONTEXT-1",c] -> pure c; _ -> error "context shape"
  key <- expect "raw/final full key" (Q.restoreSourceCacheKey context compact)
  let ds = U.unitData (U.objectInterface finalObject)
  raw <- expect "raw contextual object" (decodePayload ds payload)
  let parameters = [(X.nameHint n,t) | (n,t) <- fst (U.splitParameters (strip (U.objectTerm raw)))]
  _ <- expect "generic validator alone accepts final counterexample" (Q.decodeCached key groupId parameters ds ["sameDeps"] (Q.encodeCached key finalObject))
  need "raw object differs from compact final" (U.encodeObject raw /= U.encodeObject finalObject)
  -- Preserve the real reference and full-key projection: only the object
  -- payload is poisoned. This must not become a trivial envelope mismatch.
  let poisoned3 = newRecord ref compact (payloadFor finalObject)
  accepted3 <- readRecordChecked (literal directory) key groupId parameters ds ["sameDeps"] poisoned3 >>= expect "binary generic validator accepts finalized counterexample"
  need "CACHE3 final payload actually decoded" (sameObject accepted3 finalObject)
  saveRecord file poisoned3
  (repaired3,report3,_) <- Q.compileSourceGroups "raw-final" (literal directory) [] M.empty plan >>= expect "CACHE3 raw/final rejection and reinference"
  need "CACHE3 final-as-raw only reinfers poisoned group" (Q.inferredCount report3 == 1 && Q.reusedCount report3 == fromIntegral (length objects - 1))
  need "CACHE3 final artifact exact after repair" (map U.encodeObject repaired3 == map U.encodeObject objects)
  -- The repaired record must restore the raw payload, not simply preserve the
  -- poisoned cache while returning independently correct final artifacts.
  repairedInput3 <- readRecord file
  (repairedRef,repairedCompact,repairedPayload) <- recordParts repairedInput3
  need "CACHE3 repair keeps reference/key and restores raw payload"
    (repairedRef == ref && repairedCompact == compact && repairedPayload == payload)
  -- Keep the original legacy representation counterexample as a separate pass.
  save file (Q.encodeCached key finalObject)
  (repaired,report,_) <- Q.compileSourceGroups "raw-final" (literal directory) [] M.empty plan >>= expect "legacy raw/final rejection and reinference"
  need "legacy final-as-raw only reinfers poisoned group" (Q.inferredCount report == 1 && Q.reusedCount report == fromIntegral (length objects - 1))
  need "legacy final artifact exact after repair" (map U.encodeObject repaired == map U.encodeObject objects)
  -- Only the visible instance scope changes. Keep the caller's source and
  -- the Int instance fixed. Observe the actual source driver's per-SCC hit.
  broader <- expect "broader source scope" (SI.prepareSourcePlan M.empty [] [cls]
    [("tagInt",instanceInt),("tagBool",instanceBool)] (M.fromList P.compareString [("sameDeps",IS.fromList [0,1])])
    [IS.fromList [0,1],IS.fromList [0,1]] own)
  expanded <- case broader of T.Just p -> pure p; _ -> error "broader scope unavailable"
  (_,Q.QueryReport _ _ expandedRows,_) <- Q.compileSourceGroups "raw-final" (literal directory) [] M.empty expanded >>= expect "scope change"
  need "visible candidate scope invalidates the actual root"
    (case [(hit,k) | Q.GroupResult _ ns hit _ k <- expandedRows, ns == ["sameDeps"]] of
       [(False,k)] -> k /= digest; _ -> False)
  sourceInputChanges (directory ++ "-inputs")
  putStrLn "PASS final payload cannot masquerade as raw source cache"

-- One isolated source crate. Change exactly one imported type, then one
-- user layout, without changing any expression or the other two groups.
sourceInputChanges directory = do
  let own = [("boxed",T.Nothing,T.SConstructor "MakeBox"),
             ("dependent",T.Nothing,T.SVar "external"),("plain",T.Nothing,T.SIntLit 3)]
      scopes = M.fromList P.compareString [(n,IS.empty) | (n,_,_) <- own]
      checkRun external constructors missed previous = do
        let layout = T.DataDecl "Box" [] constructors
            imported = U.UnitInterface "External" [] [] [] [] [] [("external",T.XCon external [])] "parameters"
        planned <- expect "source input plan" (SI.prepareSourcePlan
          (M.fromList P.compareString [("external",T.SCon external [])]) [layout] [] [] scopes [] own)
        plan <- case planned of T.Just x -> pure x; _ -> error "source input plan unavailable"
        (_,Q.QueryReport inferred reused rows,_) <- Q.compileParsedSourceGroups "inputs" (literal directory)
          [imported] (M.fromList P.compareString [("external",False)]) plan >>= expect "compile changed source inputs"
        let result = [(n,k) | Q.GroupResult _ [n] _ _ k <- rows]
        need "exact cache hit/miss set" (length result == 3 && inferred == fromIntegral (length missed)
          && reused == 3-inferred && sort [B.unpack n | Q.GroupResult _ [n] False _ _ <- rows] == sort (map B.unpack missed))
        forM_ result $ \(n,k) -> case lookup n previous of
          Nothing -> pure ()
          Just old -> need "only changed semantic inputs replace their full keys" ((n `elem` missed) == (k /= old))
        pure result
      box = [T.ConstructorDecl "MakeBox" []]
  first <- checkRun "Int" box ["boxed","dependent","plain"] []
  warm <- checkRun "Int" box [] first
  imported <- checkRun "Bool" box ["dependent"] warm
  layout <- checkRun "Bool" (box ++ [T.ConstructorDecl "OtherBox" []]) ["boxed"] imported
  _ <- checkRun "Bool" (box ++ [T.ConstructorDecl "OtherBox" []]) [] layout
  pure ()


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
leftSession directory root builtinMetadata = do
  let sourcePath = root </> "ScratchFailure.hs"
      specPath = root </> "failure.spec"
      prefix = root </> "failure"
      source = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule ScratchFailure where { import MLF.Primitive; aGood :: Int; aGood = 1; zBad = aGood (2 :: Int) }\n"
      spec = U.pack ["MLF-CRATE-1","scratch-failure","","true",
             U.pack [U.pack ["ScratchFailure",literal sourcePath]],U.pack [literal builtinMetadata],literal directory,literal (root </> "builtin")]
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
    ["left-session",directory,root,builtinMetadata,"await-probe"] -> awaitProbe (leftSession directory root builtinMetadata)
    ["empty-success",directory] -> emptySuccess directory
    ["empty-directory-failure",directory,"await-probe"] -> awaitProbe (emptyDirectoryFailure directory)
    ["cleanup-dual-failure",directory,"await-probe"] -> awaitProbe (cleanupDualFailure directory)
    ["concurrent",directory,resultFile] -> concurrent directory resultFile
    ["context-directory-setup",directory] -> contextDirectorySetup directory
    ["context-directory-reject",directory] -> contextDirectoryReject directory
    ["context-stage-cleanup-failure",directory] -> contextStageCleanupFailure directory
    ["decoder-differential",directory] -> decoderDifferential directory
    ["window-helper",directory] -> windowHelper directory
    ["session-window-raw-final",directory,root] -> sessionWindowRawFinal directory root
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
  input <- readRecord (directory </> (B.unpack digest ++ ".mlfq"))
  (ref,compact,payload) <- recordParts input
  blob <- contextLogical (B.unpack (Q.sourceContextPath (literal directory) ref))
  need "helper real empty context" (blob == Q.sourceContextContents (Q.encodeSourceDatatypes []))
  key <- expect "helper complete key" (Q.restoreSourceCacheKey (Q.encodeSourceDatatypes []) compact)
  raw <- expect "helper actual raw" (decodePayload [] payload)
  prepared <- expect "helper actual prepared" (SI.prepareGroup plan M.empty memberNames)
  _ <- expect "helper original prepared validation" (SI.validatePreparedRaw prepared raw)
  pure (groupId,memberNames,key,input,raw,prepared)
memoRead previous directory (groupId,memberNames,key,input,_,_) =
  readRecordMemo previous (literal directory) key groupId [] [] memberNames input
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
          readRecordMemo prev (literal dir) k owner bindings ds wanted record
        readSame k owner bindings ds wanted record = readChanged memo directory k owner bindings ds wanted record
    readSame key gid [] [] ns (newRecord ref compact badPayload) >>= memoBad "memo rejects bad payload" True
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
      (next,reused,result) <- readChanged memo directory legacyKey gid [] [] ns (LegacyInput legacy)
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
  let key = keyFor (Q.encodeSourceDatatypes [box])
      path = directory </> "box-record.mlfq"
      readBox state ds input = readRecordMemo state (literal directory) key "RawGroup" [] ds ["value"] input
  Q.writeSourceCached T.Nothing (literal directory) (literal path) key raw >>= expect "box write"
  input <- readRecord path
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
  original <- readRecord file
  (ref,compact,payload) <- recordParts original
  let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
  contextBlob <- BS.readFile contextPath
  logicalContext <- contextLogical contextPath
  need "memo public empty datatype fixture" (logicalContext == Q.sourceContextContents (Q.encodeSourceDatatypes []))
  key <- expect "memo public full key" (Q.restoreSourceCacheKey (Q.encodeSourceDatatypes []) compact)
  raw <- expect "memo public raw" (decodePayload [] payload)
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
  withMemoLock directory $ \_ -> saveRecord file original
  restored <- call "restored-warm"
  need "restored C3 final equality" (restored == baseline)
  withMemoLock directory $ \_ -> save contextPath "corrupt-context-for-next-invocation"
  repaired <- call "corrupt-repair"
  actual <- BS.readFile contextPath
  need "corrupt context repaired on next invocation" (actual == contextBlob && repaired == baseline)
  withMemoLock directory $ \_ -> removeFile contextPath
  missing <- call "missing-repair"
  after <- BS.readFile contextPath
  need "missing context repaired on next invocation" (after == contextBlob && missing == baseline)
  BS.writeFile (root </> "context.original") contextBlob
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
    (iface,objects) <- readFormal prefix
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
  input <- readRecord file
  (ref,compact,payload) <- recordParts input
  contextBlob <- contextLogical (B.unpack (Q.sourceContextPath (literal directory) ref)) >>= fields
  context <- case contextBlob of ["MLF-SOURCE-QUERY-CONTEXT-1",c] -> pure c; _ -> error "context shape"
  key <- expect "raw/final full key" (Q.restoreSourceCacheKey context compact)
  let ds = U.unitData (U.objectInterface finalObject)
  raw <- expect "raw contextual object" (decodePayload ds payload)
  let parameters = [(X.nameHint n,t) | (n,t) <- fst (U.splitParameters (strip (U.objectTerm raw)))]

  prepared <- expect "counterexample actual prepared authority"
    (SI.prepareGroup plan (M.filterWithKey (\name _ -> name /= "sameDeps") contracts) ["sameDeps"])
  withMemoLock directory $ \_ -> do
    memo <- readRecordMemo T.Nothing (literal directory) key groupId parameters ds ["sameDeps"] input
      >>= memoGood "counterexample verified raw" False prepared raw
    let poisoned = newRecord ref compact (payloadFor finalObject)
    (next,reused,result) <- readRecordMemo memo (literal directory) key groupId parameters ds ["sameDeps"] poisoned
    need "final payload reaches verified reuse branch" (reused && not (memoAbsent next))
    decoded <- expect "generic memo reader admits final counterexample" result
    need "counterexample final decoded exactly" (sameObject decoded finalObject && not (sameObject decoded raw))
    reject "prepared authority rejects memo-decoded final payload" (SI.validatePreparedRaw prepared decoded)
  -- The reader cannot clear a later PreparedRaw failure it never receives.
  -- Both public workers clear it; unchanged original raw-final controls cover
  -- their real reinference, rather than claiming this helper owns that check.


-- Publication collision controls are additive to the original 34 commands.
-- Each API call is under the actual production cache-directory lock. The
-- Python driver installs the directory collision between completed commands.
contextPublicationError :: P.String
contextPublicationError = "cannot publish source query context: destination is a directory"

contextDirectorySetup directory = do
  fresh directory
  withMemoLock directory $ \_ -> do
    object <- expect "directory setup raw inference" (I.compileLoweredGroup "RawGroup" [] [] (members 41))
    let context = Q.encodeSourceDatatypes []
        key = keyFor context
        path = directory </> "existing.mlfq"
    Q.writeSourceCached T.Nothing (literal directory) (literal path) key object >>= expect "directory setup source write"
    input <- readRecord path
    (ref,_,_) <- recordParts input
    let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
    blob <- contextLogical contextPath
    actual <- P.fileDigest (literal contextPath)
    need "directory setup uses real context digest and contents"
      (Q.validSourceContextDigest ref && actual == ref && blob == Q.sourceContextContents context)
    checked <- readNew directory key input >>= expect "directory setup source read"
    need "directory setup preserves checked raw object" (sameObject checked object)
    putStrLn ("PASS context directory setup " ++ B.unpack ref)

contextDirectoryReject directory = withMemoLock directory $ \_ -> do
  -- A different valid payload makes the existing-record preservation oracle
  -- meaningful even if an incorrect writer silently replaces that record.
  object <- expect "directory rejection raw inference" (I.compileLoweredGroup "RawGroup" [] [] (members 42))
  let key = keyFor (Q.encodeSourceDatatypes [])
  forM_ ["new.mlfq", "existing.mlfq"] $ \leaf -> do
    result <- Q.writeSourceCached T.Nothing (literal directory) (literal (directory </> leaf)) key object
    case result of
      T.Left message -> need ("exact directory publication error for " ++ leaf) (message == contextPublicationError)
      T.Right _ -> error ("directory publication incorrectly returned Right for " ++ leaf)
    putStrLn ("PASS context directory rejects " ++ leaf)

contextStageCleanupFailure directory = withMemoLock directory $ \_ -> do
  -- This is a direct failure-composition control. A stage directory is not
  -- claimed to arise naturally after publishSourceContext's successful write.
  result <- Q.rejectSourceContextPublication (literal directory) contextPublicationError
  case result of
    T.Left message -> need "publication and directory cleanup errors both retained"
      (message == contextPublicationError P.++ "; cannot remove source query context staging: path is a directory")
    T.Right _ -> error "publication cleanup helper incorrectly returned Right"
  putStrLn "PASS context staging directory preserves publication and cleanup errors"


-- Retained legacy decoder differential. Binary seeds are independently checked
-- before constructing old carriers in memory. Seed IO reads only this invocation's fixed helper-cache,
-- under its real lock; all differential API calls themselves are stateless.
-- The frozen P decoder below is NOT a call to K's WithKeyParts helper.
-- Namespace qualification and the function name are the only token changes;
-- its exact original signature/body also lives in P-decoder-reference.txt.
frozenPDecodeSourceCachedWithEncoding :: P.String -> P.String -> P.String -> P.String ->
  [] ((,) P.String T.XType) -> [] T.DataDecl -> [] P.String -> P.String -> P.String ->
  T.Either P.String U.UnitObject;
frozenPDecodeSourceCachedWithEncoding verifiedEncoding actualDigest key name bindings datatypes names contextInput input = do {
  fields <- U.unpack input;
  case fields of {
    (:) format ((:) digest ((:) compact ((:) payload []))) -> do {
      Std.ensure (P.eqString format "MLF-QUERY-CACHE-3" && P.eqString input (U.pack fields)
        && Q.validSourceContextDigest digest && P.eqString actualDigest digest)
        "invalid source query context reference";
      case Q.sourceCacheParts key of {
        T.Nothing -> T.Left "unsupported source query key";
        T.Just ((,) _ expectedContext) -> do {
          Std.ensure (P.eqString expectedContext verifiedEncoding)
            "cached source query datatype context mismatch";
          Std.ensure (P.eqString contextInput (Q.sourceContextContents expectedContext))
            "cached source query context mismatch";
          savedKey <- Q.restoreSourceCacheKey expectedContext compact;
          Std.ensure (P.eqString key savedKey) "cached query key mismatch";
          object <- U.decodeContextualObject datatypes datatypes payload;
          Q.validateCached name bindings datatypes names object
        }
      }
    };
    _ -> T.Left "unsupported source query cache format"
  }
};

data DecoderInput = DecoderInput
  { decoderDigest :: P.String
  , decoderKey :: P.String
  , decoderName :: P.String
  , decoderBindings :: [(P.String,T.XType)]
  , decoderDatatypes :: [T.DataDecl]
  , decoderNames :: [P.String]
  , decoderContext :: P.String
  , decoderRecord :: P.String
  }
data DecoderExpectation = DecoderRight U.UnitObject | DecoderLeft P.String

-- Both results must independently have the expected Either constructor.
-- Right also matches independently inferred raw interface AND object bytes;
-- Left matches a fixed diagnostic as well as the frozen P decoder verbatim.
checkDecoderDifferential (label, expected, item) = do
  let ds = decoderDatatypes item
      old = frozenPDecodeSourceCachedWithEncoding (Q.encodeSourceDatatypes ds)
              (decoderDigest item) (decoderKey item) (decoderName item)
              (decoderBindings item) ds (decoderNames item)
              (decoderContext item) (decoderRecord item)
      new = Q.decodeSourceCached (decoderDigest item) (decoderKey item)
              (decoderName item) (decoderBindings item) ds (decoderNames item)
              (decoderContext item) (decoderRecord item)
  kind <- case (expected, old, new) of
    (DecoderRight raw, T.Right before, T.Right after) -> do
      need (label ++ " complete interface and object bytes")
        (sameObject before after && sameObject before raw && sameObject after raw)
      pure "Right"
    (DecoderLeft diagnostic, T.Left before, T.Left after) -> do
      need (label ++ " exact old/new/expected error")
        (before == after && before == diagnostic && after == diagnostic)
      pure "Left"
    _ -> error (label ++ " expected Either constructor differs")
  putStrLn ("PASS decoder differential " ++ label ++ " " ++ kind)

-- Python pins these actual binary writer files. The fixture verifies them
-- under lock, then hashes the independently encoded OLD text carrier in memory
-- for the unchanged pure legacy differential. No fake binary-text reference.
decoderSeed directory leaf ds key raw = do
  input <- readRecord (directory </> leaf)
  (reference,compact,payload) <- recordParts input
  need "decoder seed reference is safe" (Q.validSourceContextDigest reference)
  let path = Q.sourceContextPath (literal directory) reference
      context = Q.encodeSourceDatatypes ds
  blob <- contextLogical (B.unpack path)
  actual <- P.fileDigest path
  (expectedCompact,expectedContext) <- splitKey key
  need "decoder seed actual digest, canonical record/context and complete key"
    (actual == reference && blob == Q.sourceContextContents context &&
     input == newRecord reference compact payload &&
     compact == expectedCompact && expectedContext == context)
  decoded <- readRecordChecked (literal directory) key "RawGroup" [] ds names input >>= expect "seed actual binary API"
  need "decoder seed writer stored independently inferred full raw payload"
    (sameObject decoded raw && payload == payloadFor raw)
  -- Independently hashed OLD text carrier. Never borrow the binary carrier SHA
  -- for a text-format differential; no text record is published by this seed.
  oldBytes <- P.byteArrayFromString blob
  oldDigest <- P.byteArrayDigest oldBytes
  let oldInput = legacyRecord oldDigest compact (U.encodeContextualObject raw)
  pure (DecoderInput oldDigest key "RawGroup" [] ds names blob oldInput)

replaceDecoderField index replacement values =
  [if i == index then replacement else value | (i,value) <- zip [0 :: Int ..] values]
dropDecoderScalar value = literal (dropLast (B.unpack value))
  where
    dropLast [] = []
    dropLast [_] = []
    dropLast (firstScalar:secondScalar:rest) = firstScalar : dropLast (secondScalar:rest)

decoderDifferential directory = withMemoLock directory $ \_ -> do
  raw41 <- expect "decoder independent raw41 inference" (I.compileLoweredGroup "RawGroup" [] [] (members 41))
  raw42 <- expect "decoder independent raw42 inference" (I.compileLoweredGroup "RawGroup" [] [] (members 42))
  need "decoder raw41 and raw42 have genuinely different complete object bytes"
    (U.encodeObject raw41 /= U.encodeObject raw42 && not (sameObject raw41 raw42))
  let context = Q.encodeSourceDatatypes []
      key = keyFor context
  keyFields <- fields key
  need "decoder complete expected source key population" (length keyFields == 9)
  let secondKey = U.pack (replaceDecoderField 1 "another-crate" keyFields)
      box = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
      changedBox = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a",T.Parameter "a"]]
      boxMembers = [("value",T.Nothing,T.SApp (T.SConstructor "Box") (T.SIntLit 7))]
  boxRaw <- expect "decoder independent box inference" (I.compileLoweredGroup "RawGroup" [] [box] boxMembers)
  first <- decoderSeed directory "record.mlfq" [] key raw41
  second <- decoderSeed directory "second.mlfq" [] secondKey raw41
  boxSeed <- decoderSeed directory "box.mlfq" [box] (keyFor (Q.encodeSourceDatatypes [box])) boxRaw
  (reference,compact,payload) <- legacyRecordParts (decoderRecord first)
  (secondReference,secondCompact,_) <- legacyRecordParts (decoderRecord second)
  compactFields <- fields compact
  need "decoder two writer records share actual context but not complete key"
    (reference == secondReference && decoderContext first == decoderContext second &&
     key /= secondKey && compact /= secondCompact && length compactFields == 8)
  let right label item raw = (label,DecoderRight raw,item)
      left label diagnostic item = (label,DecoderLeft diagnostic,item)
      withCompact value = first { decoderRecord = legacyRecord reference value payload }
      withPayload value = first { decoderRecord = legacyRecord reference compact value }
      raw42First = withPayload (U.encodeContextualObject raw42)
      raw42Second = second { decoderRecord = legacyRecord reference secondCompact (U.encodeContextualObject raw42) }
      otherDigest = case B.unpack reference of
        [] -> ""
        firstScalar:rest -> literal ((if firstScalar == '0' then '1' else '0') : rest)
      badKey = "0" P.++ key
      badContextKey = U.pack (replaceDecoderField 5 (context P.++ "!") keyFields)
      badCarrier = Q.sourceContextContents "wrong"
      badCompact = compact P.++ "x"
      badPayload = ""
      unsupportedKey = "unsupported source query key"
      keyMismatch = "cached query key mismatch"
      dataMismatch = "cached source query datatype context mismatch"
      contextMismatch = "cached source query context mismatch"
      invalidReference = "invalid source query context reference"
      unsupportedRecord = "unsupported source query cache format"
      malformed = "malformed module artifact framing"
      truncated = "truncated module artifact"
      unsupportedPayload = "unsupported or malformed contextual inference fragment (expected MLFF-2)"
      unicodeFields = replaceDecoderField 7 "α😀" compactFields
      unicodeCompact = U.pack unicodeFields
  unicodeKey <- expect "decoder scalar complete key" (Q.restoreSourceCacheKey context unicodeCompact)
  need "Unicode framing counts scalars, not UTF8 bytes or UTF16 code units"
    (U.pack ["α😀"] == "2:α😀" && P.stringLength "α😀" == 2 && BS.length (B.utf8 "α😀") == 6)
  let unicodeSeed = first { decoderKey = unicodeKey, decoderRecord = legacyRecord reference unicodeCompact payload }
      unicodeFraming prefix = unicodeSeed
        { decoderRecord = legacyRecord reference (U.pack (take 7 unicodeFields) P.++ prefix P.++ "α😀") payload }
      good =
        [right "writer-raw41" first raw41
        ,right "writer-second-raw41" second raw41
        ,right "writer-box-context" boxSeed boxRaw
        ,right "codec-raw42-original-key" raw42First raw42
        ,right "codec-raw42-other-key" raw42Second raw42
        ,right "unicode-scalar-framing" unicodeSeed raw41]
      changedFields =
        [left ("compact-field-" ++ label) (if i == 0 then unsupportedKey else keyMismatch)
          (withCompact (U.pack (replaceDecoderField i (value P.++ "!") compactFields)))
        | (i,(label,value)) <- zip [0 :: Int ..]
            (zip ["tag","crate","compiler","members","bindings","prepared","contracts","scopes"] compactFields)]
      compactCases =
        [left "compact-leading-zero-length" unsupportedKey (withCompact ("0" P.++ compact))
        ,left "compact-truncated" truncated (withCompact (dropDecoderScalar compact))
        ,left "compact-trailing-bytes" malformed (withCompact badCompact)
        ,left "compact-seven-fields" unsupportedKey (withCompact (U.pack (take 7 compactFields)))
        ,left "compact-nine-fields" unsupportedKey (withCompact (U.pack (compactFields ++ ["extra"])))
        ,left "compact-empty" unsupportedKey (withCompact "")
        ,left "compact-nondigit-length" malformed (withCompact ("x:" P.++ compact))
        ,left "unicode-utf8-length" truncated (unicodeFraming "6:")
        ,left "unicode-utf16-length" truncated (unicodeFraming "3:")
        ,left "unicode-short-scalar-length" malformed (unicodeFraming "1:")]
      keyCases =
        [left "full-key-leading-zero-length" unsupportedKey first { decoderKey = badKey }
        ,left "full-key-truncated" unsupportedKey first { decoderKey = dropDecoderScalar key }
        ,left "full-key-trailing-bytes" unsupportedKey first { decoderKey = key P.++ "x" }
        ,left "full-key-eight-fields" unsupportedKey first { decoderKey = U.pack (take 8 keyFields) }
        ,left "full-key-ten-fields" unsupportedKey first { decoderKey = U.pack (keyFields ++ ["extra"]) }
        ,left "full-key-wrong-tag" unsupportedKey first { decoderKey = U.pack (replaceDecoderField 0 "WRONG" keyFields) }
        ,left "single-expected-context-field" dataMismatch first { decoderKey = badContextKey }
        ,left "same-context-other-record-key" keyMismatch raw42Second { decoderKey = key }
        ,left "same-context-other-expected-key" keyMismatch first { decoderKey = secondKey }]
      contextCases =
        [left "actual-datatypes-mismatch" dataMismatch first { decoderDatatypes = [box] }
        ,left "box-layout-mismatch" dataMismatch boxSeed { decoderDatatypes = [changedBox] }
        ,left "context-carrier-mismatch" contextMismatch first { decoderContext = badCarrier }
        ,left "context-carrier-wrong-tag" contextMismatch first { decoderContext = U.pack ["WRONG",context] }
        ,left "context-carrier-leading-zero-length" contextMismatch first { decoderContext = "0" P.++ decoderContext first }
        ,left "context-carrier-truncated" contextMismatch first { decoderContext = dropDecoderScalar (decoderContext first) }
        ,left "context-carrier-extra-field" contextMismatch first { decoderContext = U.pack ["MLF-SOURCE-QUERY-CONTEXT-1",context,"extra"] }]
      recordCases =
        [left "record-wrong-format" invalidReference first { decoderRecord = U.pack ["WRONG",reference,compact,payload] }
        ,left "record-invalid-reference" invalidReference first { decoderRecord = legacyRecord (literal (replicate 64 'A')) compact payload }
        ,left "actual-digest-mismatch" invalidReference first { decoderDigest = otherDigest }
        ,left "record-leading-zero-length" invalidReference first { decoderRecord = "0" P.++ decoderRecord first }
        ,left "record-truncated" truncated first { decoderRecord = dropDecoderScalar (decoderRecord first) }
        ,left "record-trailing-bytes" malformed first { decoderRecord = decoderRecord first P.++ "x" }
        ,left "record-three-fields" unsupportedRecord first { decoderRecord = U.pack ["MLF-QUERY-CACHE-3",reference,compact] }
        ,left "record-five-fields" unsupportedRecord first { decoderRecord = U.pack ["MLF-QUERY-CACHE-3",reference,compact,payload,"extra"] }
        ,left "payload-empty" unsupportedPayload (withPayload badPayload)
        ,left "owner-mismatch" "cached group identity mismatch" first { decoderName = "WrongOwner" }
        ,left "binding-mismatch" "cached dependency parameter mismatch" first { decoderBindings = [("external",T.XCon "Int" [])] }
        ,left "declaration-mismatch" "cached declaration ownership mismatch" first { decoderNames = ["other"] }]
      precedenceCases =
        [left "priority-framing-before-key" malformed first { decoderRecord = "x", decoderKey = badKey }
        ,left "priority-truncation-before-key" truncated first { decoderRecord = dropDecoderScalar (decoderRecord first), decoderKey = badKey }
        ,left "priority-record-shape-before-key" unsupportedRecord first { decoderRecord = U.pack ["MLF-QUERY-CACHE-3"], decoderKey = badKey }
        ,left "priority-reference-before-key" invalidReference first { decoderDigest = otherDigest, decoderKey = badKey }
        ,left "priority-key-before-context" unsupportedKey first { decoderKey = badKey, decoderContext = badCarrier }
        ,left "priority-datatypes-before-compact" dataMismatch (withCompact badCompact) { decoderKey = badContextKey }
        ,left "priority-context-before-compact" contextMismatch (withCompact badCompact) { decoderContext = badCarrier }
        ,left "priority-compact-framing-before-payload" malformed first { decoderRecord = legacyRecord reference badCompact badPayload }
        ,left "priority-key-mismatch-before-payload" keyMismatch first { decoderRecord = legacyRecord reference secondCompact badPayload }
        ,left "priority-payload-before-owner" unsupportedPayload (withPayload badPayload) { decoderName = "WrongOwner" }
        ,left "priority-owner-before-declarations" "cached group identity mismatch" first { decoderName = "WrongOwner", decoderNames = ["other"] }]
      cases = good ++ changedFields ++ compactCases ++ keyCases ++ contextCases ++ recordCases ++ precedenceCases
  mapM_ checkDecoderDifferential cases
  putStrLn ("PASS decoder differential complete " ++ show (length cases) ++ " cases")


-- Window entries below originate only in successful real public reads. The
-- constructor is inspected for route/order, never used to fabricate a value.
data WindowFixture = WindowFixture
  { windowDirectory :: FilePath
  , windowLabel :: String
  , windowReference :: P.String
  , windowKey :: P.String
  , windowDatatypes :: [T.DataDecl]
  , windowObject :: U.UnitObject
  , windowInput :: RecordInput
  }
windowRoutes entries = [(directory,reference) | Q.SourceContextRead directory reference _ _ _ <- entries]
windowExpected fixtures = [(literal (windowDirectory f),windowReference f) | f <- fixtures]
windowRead previous f = readRecordWindow previous (literal (windowDirectory f))
  (windowKey f) "RawGroup" [] (windowDatatypes f) names (windowInput f)
windowGood label reused fixtures raw (next,actual,result) = do
  need (label ++ " actual context branch and complete bounded MRU routes")
    (actual == reused && length next <= 8 && windowRoutes next == windowExpected fixtures)
  object <- expect label result
  need (label ++ " complete independently inferred raw object") (sameObject object raw)
  pure next
windowBad label reused diagnostic (next,actual,result) = do
  need (label ++ " clears entire window and reports actual branch") (null next && actual == reused)
  case result of
    T.Left message -> need (label ++ " exact Left") (message == diagnostic)
    T.Right _ -> error (label ++ " unexpectedly accepted")
windowPass label = putStrLn ("PASS window " ++ label)
windowHandshake marker acknowledgement = do
  putStrLn marker
  hFlush stdout
  answer <- getLine
  need "exact window parent acknowledgement" (answer == acknowledgement)
windowPath f = B.unpack (Q.sourceContextPath (literal (windowDirectory f)) (windowReference f))
windowBackup f = windowPath f ++ ".window-test-backup"
windowHide [] action = action
windowHide (f:rest) action = do
  exists <- doesPathExist (windowBackup f)
  need "fresh window context backup" (not exists)
  bracket (renameFile (windowPath f) (windowBackup f))
    (\_ -> renameFile (windowBackup f) (windowPath f))
    (\_ -> windowHide rest action)
windowCreate directory label ds value = do
  raw <- expect "window independent raw inference" (I.compileLoweredGroup "RawGroup" [] ds (members value))
  let key = keyFor (Q.encodeSourceDatatypes ds)
      path = directory </> ("entry-" ++ label ++ ".mlfq")
  Q.writeSourceCached T.Nothing (literal directory) (literal path) key raw >>= expect "window real writer"
  input <- readRecord path
  (reference,compact,payload) <- recordParts input
  (wantedCompact,context) <- splitKey key
  let contextPath = Q.sourceContextPath (literal directory) reference
  actual <- P.fileDigest contextPath
  blob <- contextLogical (B.unpack contextPath)
  need "window real canonical writer carrier/reference/raw"
    (Q.validSourceContextDigest reference && reference == actual && compact == wantedCompact &&
     blob == Q.sourceContextContents context && payload == payloadFor raw &&
     input == newRecord reference compact payload)
  pure (WindowFixture directory label reference key ds raw input)
windowSingle f = do
  result <- windowRead [] f >>= windowGood "singleton real verified entry" False [f] (windowObject f)
  case result of [entry] -> pure entry; _ -> error "window singleton population"
windowFill previous expected [] = pure previous
windowFill previous expected (f:rest) = do
  let wanted = take 8 (f:expected)
  next <- windowRead previous f >>= windowGood "distinct disk load retains previous entries" False wanted (windowObject f)
  windowFill next wanted rest

windowHelper directory = do
  fresh directory
  let otherDirectory = directory </> "different-cache"
  fresh otherDirectory
  withMemoLock directory $ \_ -> withMemoLock otherDirectory $ \_ -> do
    let box = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
        alphaBox = T.DataDecl "Box" ["b"] [T.ConstructorDecl "Box" [T.Parameter "b"]]
        choices = [(label,if label == "a" then [box] else
                      [T.DataDecl (literal ("Window" ++ label)) [] [T.ConstructorDecl (literal ("Window" ++ label)) []]],
                     fromIntegral value) | (label,value) <- zip ["a","b","c","d","e","f","g","h","i"] [41 :: Int ..]]
    fixtures <- mapM (\(label,ds,value) -> windowCreate directory label ds value) choices
    (a,b,c,d,e,f,g,h,i) <- case fixtures of
      [aa,bb,cc,dd,ee,ff,gg,hh,ii] -> pure (aa,bb,cc,dd,ee,ff,gg,hh,ii)
      _ -> error "exact nine window contexts"
    let references = map windowReference fixtures
    need "nine actually different complete contexts"
      (and [x /= y | (n,x) <- zip [0 :: Int ..] references, (m,y) <- zip [0 :: Int ..] references, n < m])
    other <- windowCreate otherDirectory "a" [box] 41
    need "same reference is independently published in another directory"
      (windowReference other == windowReference a && windowDirectory other /= windowDirectory a && sameObject (windowObject other) (windowObject a))
    singles <- mapM windowSingle fixtures
    otherState <- windowRead [] other >>= windowGood "other directory verified independently" False [other] (windowObject other)
    ab <- windowFill [] [] [a,b]
    eight <- windowFill [] [] (take 8 fixtures)
    promoted <- windowRead eight a >>= windowGood "promote oldest route to MRU" True [a,h,g,f,e,d,c,b] (windowObject a)
    ninth <- windowRead promoted i >>= windowGood "ninth disk load keeps promoted A and evicts B" False [i,a,h,g,f,e,d,c] (windowObject i)
    alphaRaw <- expect "independent alpha-renamed raw" (I.compileLoweredGroup "RawGroup" [] [alphaBox] (members 41))
    (_,compact,payload) <- recordParts (windowInput a)
    let alpha = a { windowDatatypes = [alphaBox], windowObject = alphaRaw }
        changedEncoded = a { windowKey = keyFor (Q.encodeSourceDatatypes (windowDatatypes b)) }
        structural =
          [("kind",T.DataDeclK "Box" [("a",T.KArrow T.Star T.Star)] [T.ConstructorDecl "Box" [T.Parameter "a"]])
          ,("constructor",T.DataDecl "Box" ["a"] [T.ConstructorDecl "ChangedBox" [T.Parameter "a"]])
          ,("field",T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a",T.Parameter "a"]])]
        missing = "source query context cache miss"
        dataMismatch = "cached source query datatype context mismatch"
        contextFiles = fixtures ++ [other]
    need "alpha spelling differs structurally but canonical context and raw payload agree"
      (Q.encodeSourceDatatypes [box] == Q.encodeSourceDatatypes [alphaBox] && U.encodeContextualObject alphaRaw == U.encodeContextualObject (windowObject a))
    windowHandshake ("WINDOW-BEFORE " ++ unwords (map B.unpack references)) "WINDOW-BEFORE-ACK"
    windowHide contextFiles $ do
      windowHandshake "WINDOW-HIDDEN" "WINDOW-HIDDEN-ACK"
      aba <- windowRead ab a >>= windowGood "alternation A without context file" True [a,b] (windowObject a)
      _ <- windowRead aba b >>= windowGood "alternation B without context file" True [b,a] (windowObject b)
      windowPass "alternating contexts reuse without files"
      _ <- windowRead ninth a >>= windowGood "promoted A survives ninth insertion" True [a,i,h,g,f,e,d,c] (windowObject a)
      windowPass "MRU promotion survives ninth insertion"
      windowRead ninth b >>= windowBad "ninth entry really evicted B" False missing
      windowPass "ninth insertion evicts least recent route"
      _ <- windowRead singles h >>= windowGood "only first eight genuine entries survive oversized input" True [h,a,b,c,d,e,f,g] (windowObject h)
      windowPass "oversized input prefix hit returns only eight"
      windowRead singles i >>= windowBad "genuine ninth input entry is outside lookup window" False missing
      windowPass "oversized input ninth entry is ignored"
      oneA <- case singles of entry:_ -> pure [entry]; [] -> error "verified singleton missing"
      windowRead oneA b >>= windowBad "different real reference cannot borrow A" False missing
      windowPass "different reference is isolated"
      windowRead eight other >>= windowBad "same reference in another directory cannot borrow entry" False missing
      windowPass "different directory is isolated"
      _ <- windowRead otherState other >>= windowGood "independently verified other-directory route" True [other] (windowObject other)
      windowPass "independently verified other directory reuses"
      windowRead eight changedEncoded >>= windowBad "same route expected encoding changed" False missing
      windowPass "encoded guard refuses hidden context reuse"
      forM_ structural $ \(label,changed) -> do
        windowRead eight a { windowDatatypes = [changed] } >>= windowBad ("same route datatype " ++ label) False missing
        windowPass (label ++ " guard refuses hidden context reuse")
      windowRead eight alpha >>= windowBad "alpha spelling must satisfy complete structural guard" False missing
      windowPass "alpha structural guard refuses hidden context reuse"
      let legacy1 = a { windowInput = LegacyInput (Q.encodeCached (windowKey a) (windowObject a)) }
          legacyKey = Q.queryKey "window-legacy" "compiler" (members 41) [] [box]
          legacy2 = a { windowKey = legacyKey, windowInput = LegacyInput (Q.encodeCached legacyKey (windowObject a)) }
      firstLegacy <- fields (Q.encodeCached (windowKey a) (windowObject a)); secondLegacy <- fields (Q.encodeCached legacyKey (windowObject a))
      need "two actual legacy codec versions" (case (firstLegacy,secondLegacy) of
        ("MLF-QUERY-CACHE-1":_,"MLF-QUERY-CACHE-2":_) -> True; _ -> False)
      _ <- windowRead eight legacy1 >>= windowGood "legacy CACHE1 clears entire window" False [] (windowObject a)
      _ <- windowRead eight legacy2 >>= windowGood "legacy CACHE2 clears entire window" False [] (windowObject a)
      windowPass "legacy CACHE1 and CACHE2 clear all entries with exact raw"
      windowRead eight a { windowInput = BinaryInput [] } >>= windowBad "malformed record clears entire window" False "malformed binary query roots"
      windowPass "malformed record clears all entries"
      windowRead eight a { windowInput = newRecord "../escape" compact payload } >>= windowBad "unsafe reference clears entire window" False "invalid source query context reference"
      windowPass "unsafe reference clears all entries"
      windowRead eight a { windowKey = "0" P.++ windowKey a } >>= windowBad "malformed full key clears entire window" False "unsupported source query key"
      windowPass "malformed full key clears all entries"
      keyFields <- fields (windowKey a)
      windowRead eight a { windowKey = U.pack (replaceDecoderField 8 "different-full-scope" keyFields) }
        >>= windowBad "full scope change clears despite route reuse" True "cached query key mismatch"
      windowPass "complete key mismatch clears after reuse"
      windowRead eight a { windowInput = newRecord (windowReference a) (compact P.++ "x") payload }
        >>= windowBad "malformed compact key rejected before context lookup" False "malformed binary query key fields"
      windowPass "malformed compact key clears before lookup"
      windowRead eight a { windowInput = newRecord (windowReference a) compact badPayload }
        >>= windowBad "bad raw payload clears despite route reuse" True badPayloadDiagnostic
      windowPass "raw payload rejection clears after reuse"
    windowHandshake "WINDOW-RESTORED" "WINDOW-RESTORED-ACK"
    _ <- windowRead ab c >>= windowGood "new route disk validation retains unrelated verified entries" False [c,b,a] (windowObject c)
    windowPass "successful disk miss retains other entries"
    _ <- windowRead ab other >>= windowGood "different directory disk validation retains original route" False [other,b,a] (windowObject other)
    windowPass "different directory disk miss retains original route"
    windowRead eight changedEncoded >>= windowBad "changed encoding has exact disk rejection and clears all" False dataMismatch
    windowPass "encoded guard disk rejection clears all entries"
    forM_ structural $ \(label,changed) -> do
      windowRead eight a { windowDatatypes = [changed] } >>= windowBad ("datatype " ++ label ++ " disk rejection") False dataMismatch
      windowPass (label ++ " guard disk rejection clears all entries")
    _ <- windowRead eight alpha >>= windowGood "same-route alpha mismatch clears old window before successful disk validation" False [alpha] alphaRaw
    windowPass "same route structural miss succeeds with only fresh entry"
  windowHandshake "WINDOW-RELEASED" "WINDOW-RELEASED-ACK"
  putStrLn "PASS window helper complete"


-- File-owned Session PreparedRaw negative control: only compileSpecFile is
-- called on Session. Its parsed plan and actual Query warm contracts provide
-- the authority, never a hand-constructed PreparedGroup or final-as-raw seed.
sessionWindowRawFinal directory root = do
  fresh root
  fresh directory
  let identity = "session-window-raw"
      moduleName = "WindowPreparedProbe"
      sourcePath = root </> "WindowPreparedProbe.hs"
      hiddenPath = root </> "WindowHidden.hs"
      specPath = root </> "probe.spec"
      prefix = root </> "probe"
      retained = directory </> "retained-raw"
      header = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n"
      source = header ++ "module WindowPreparedProbe where { import MLF.Primitive; class Tag a where { tag :: a -> Int }; instance Tag Int where { tag x = x }; sameDeps = let { known = (tag 2 :: Int) } in addInt (tag 1) known }\n"
      hidden = header ++ "module WindowHidden where { import MLF.Primitive; import WindowPreparedProbe; instance Tag Bool where { tag x = 42 } }\n"
      specText = U.pack ["MLF-CRATE-1",identity,"","true",U.pack [U.pack [moduleName,literal sourcePath],U.pack ["WindowHidden",literal hiddenPath]],U.pack [],literal directory,literal (root </> "builtin")]
      call phase = do
        Session.compileSpecFile (literal specPath) (literal prefix) >>= expect ("actual Session " ++ phase)
        (iface,object) <- readFormal prefix
        report <- readText (prefix ++ ".queries")
        BS.readFile (prefix ++ ".mlfci") >>= BS.writeFile (root </> (phase ++ ".interface"))
        BS.readFile (prefix ++ ".mlfco") >>= BS.writeFile (root </> (phase ++ ".object"))
        save (root </> (phase ++ ".queries")) report
        scratch <- doesPathExist (directory </> "query-key.new")
        need "Session public call cleans query scratch" (not scratch)
        pure (iface,object)
  writeFile sourcePath source
  writeFile hiddenPath hidden
  save specPath specText
  cold@(coldInterface,coldObject) <- call "cold"
  -- Preserve every actual original raw record immediately after cold, before
  -- even warm/support calls. These copies are INSIDE the fully counted cache.
  coldFiles <- withMemoLock directory $ \_ -> do
    files <- sort . filter (\name -> reverse (take 5 (reverse name)) == ".mlfq") <$> listDirectory directory
    need "small nonempty cold Session record population" (not (null files) && length files <= 16)
    fresh retained
    forM_ files $ \file -> BS.readFile (directory </> file) >>= BS.writeFile (retained </> file)
    pure files
  save (root </> "cold-records.inventory") (U.pack (map literal coldFiles))
  windowHandshake "SESSION-RAW-COLD" "SESSION-RAW-COLD-ACK"
  iface <- expect "actual Session interface decoder" (A.decodeInterface coldInterface)
  object <- expect "actual Session full object decoder" (A.decodeObject iface coldObject)
  let fragments = A.objectFragments object
      targetName = A.definitionName identity (Modules.Entity moduleName "sameDeps" Modules.Value)
  finalObject <- case [fragment | fragment <- fragments, targetName `elem` map fst (U.unitBindings (U.objectInterface fragment))] of
    [fragment] -> pure fragment
    _ -> error "one actual Session sameDeps fragment"
  spec <- expect "actual Session spec decoder" (Crate.decodeSpec specText)
  sources <- Crate.loadSourcesInPackage (Crate.specIdentity spec) (Crate.specSources spec) >>= expect "actual source parser for authority"
  (updated,interfaces) <- Crate.withPrelude spec sources [] >>= expect "actual checked dependency interfaces"
  preparedCrate <- expect "actual parsed crate preparation" (Crate.prepareCrate updated interfaces sources)
  plan0 <- case Crate.preparedSourcePlan preparedCrate of
    T.Just plan -> pure plan
    T.Nothing -> error "Session PreparedRaw fixture unexpectedly has no source plan"
  let imported = [U.UnitInterface (A.crateId dependency) [] [] [] [] [] (A.crateBindings dependency) "metadata" | (_,dependency) <- interfaces]
      protected = foldl (\acc (name,flag) -> M.insert P.compareString name (flag || M.findWithDefault P.compareString False name acc) acc)
                    M.empty (concatMap (A.crateProtection . snd) interfaces)
  plan <- expect "actual source protection initialization" (SI.initializeProtection plan0 protected)
  targetNames <- case [ns | ns <- SI.planGroups plan, targetName `elem` ns] of
    [ns] -> pure ns
    _ -> error "actual plan must own sameDeps exactly once"
  need "sameDeps is the original singleton negative-control group" (targetNames == [targetName])
  need "complete fixed four-group source plan accounts for all cold records"
    (length coldFiles == 4 && length (SI.planGroups plan) == 4)
  save (root </> "source-plan.inventory") (U.pack [U.pack [Q.groupName identity ns,U.pack ns] | ns <- SI.planGroups plan])
  (queryObjects,support,contracts) <- Q.compileParsedSourceGroups identity (literal directory) imported protected plan0
    >>= expect "public Query warm support obtains actual source contracts"
  need "Query support must be all hits in the real Session cache"
    (Q.inferredCount support == 0 && Q.reusedCount support == fromIntegral (length fragments) && length queryObjects == length fragments)
  need "Query and Session complete actual fragment bytes agree"
    (and [case [q | q <- queryObjects,U.unitName (U.objectInterface q) == U.unitName (U.objectInterface f)] of
            [q] -> sameObject q f; _ -> False | f <- fragments])
  save (root </> "query-support.queries") (Q.reportJSON identity "support" support)
  prepared <- expect "actual PreparedRaw authority"
    (SI.prepareGroup plan (M.filterWithKey (\name _ -> not (name `elem` targetNames)) contracts) targetNames)
  warm <- call "warm"
  need "actual Session warm final bytes exact" (warm == cold)
  let ds = U.unitData (U.objectInterface finalObject)
      gid = U.unitName (U.objectInterface finalObject)
      wantedContext = Q.encodeSourceDatatypes ds
  (leaf,original,reference,compact,payload,key,raw) <- withMemoLock directory $ \_ -> do
    files <- sort . filter (\name -> reverse (take 5 (reverse name)) == ".mlfq") <$> listDirectory directory
    need "same exact Session record population before poisoning" (files == coldFiles)
    forM_ files $ \file -> do
      before <- BS.readFile (retained </> file)
      actual <- BS.readFile (directory </> file)
      need "every original raw record remains exact through warm/support" (actual == before)
    matches <- mapM (\file -> do
      input <- readRecord (directory </> file)
      (ref,ck,body) <- recordParts input
      need "actual Session record uses bounded context reference" (Q.validSourceContextDigest ref)
      let contextPath = Q.sourceContextPath (literal directory) ref
      carrier <- contextLogical (B.unpack contextPath)
      actual <- P.fileDigest contextPath
      need "actual Session context file digest" (actual == ref)
      if carrier /= Q.sourceContextContents wantedContext then pure T.Nothing else
        case decodePayload ds body of
          T.Right rawObject | U.unitName (U.objectInterface rawObject) == gid -> do
            fullKey <- expect "actual Session full key" (Q.restoreSourceCacheKey wantedContext ck)
            pure (T.Just (file,input,ref,ck,body,fullKey,rawObject))
          _ -> pure T.Nothing) files
    case [value | T.Just value <- matches] of
      [value] -> pure value
      _ -> error "one actual Session raw record for sameDeps"
  let parameters = [(X.nameHint name,ty) | (name,ty) <- fst (U.splitParameters (strip (U.objectTerm raw)))]
      wholesale3 = newRecord reference compact (payloadFor finalObject)
      wholesale1 = Q.encodeCached key finalObject
      exactLeft label diagnostic result = case result of
        T.Left message -> need (label ++ " exact diagnostic") (message == diagnostic) >> pure message
        T.Right _ -> error (label ++ " unexpectedly accepted")
      envelopeError = "cached dependency parameter mismatch"
      authorityError = "raw source evidence prefix identity mismatch"
  _ <- expect "original Session raw passes actual PreparedRaw" (SI.validatePreparedRaw prepared raw)
  need "actual Session raw and finalized bytes differ" (U.encodeObject raw /= U.encodeObject finalObject)
  -- Preserve the genuinely different final fragment. Unlike the earlier Query
  -- counterexample, this real Session final adds an instance-dictionary external
  -- parameter and is rejected by generic envelope validation, before PreparedRaw.
  saveRecord (root </> "target.original.mlfq") original
  saveRecord (root </> "target.wholesale-cache3.mlfq") wholesale3
  save (root </> "target.wholesale-cache1.mlfq") wholesale1
  save (root </> "target.wholesale-payload.legacy") (U.encodeContextualObject finalObject)
  let payloadText = U.encodeContextualObject raw
  save (root </> "target.inventory") (U.pack [literal leaf,gid,U.pack targetNames,reference,compact,payloadText,U.encodeInterface (U.objectInterface raw),U.encodeObject raw,U.encodeInterface (U.objectInterface finalObject),U.encodeObject finalObject])
  whole3Result <- readRecordChecked (literal directory) key gid parameters ds targetNames wholesale3
  whole3Error <- exactLeft "actual Session whole-final CACHE3 envelope" envelopeError whole3Result
  whole1Error <- exactLeft "actual Session whole-final legacy envelope" envelopeError
    (Q.decodeCached key gid parameters ds targetNames wholesale1)
  save (root </> "wholesale-rejection.inventory") (U.pack [whole3Error,whole1Error])
  -- This distinct negative control changes only the source-issued evidence-slot
  -- spelling in an ACTUAL raw root. Binder identity, all references/types, the
  -- complete dependency envelope and declaration ownership stay unchanged.
  -- XName is not an opaque capability; no PreparedGroup/authority is fabricated.
  slot <- case snd (U.splitParameters (strip (U.objectTerm raw))) of
    T.XLet owner (T.XAbs binder _ _) (T.XConstructor "()" []) -> do
      need "actual evidence slot belongs to actual singleton root" (X.nameHint owner == targetName)
      pure binder
    _ -> error "actual raw source root needs a first evidence abstraction"
  let oldHint = X.nameHint slot
      changedHint = oldHint P.++ "WindowPoison"
      changedSlot = T.XName (X.nameId slot) changedHint
      rename n = if X.equalName n slot then changedSlot else n
      undo n = if X.equalName n slot then slot else n
      changedTerm = U.mapTerm rename id (U.objectTerm raw)
      restored = U.UnitObject (U.objectInterface raw) (U.mapTerm undo id changedTerm)
      proposed = U.UnitObject (U.objectInterface raw) changedTerm
  need "slot alpha mutation reverses to complete actual raw bytes" (sameObject restored raw && changedHint /= oldHint)
  poison <- expect "alpha-only raw is independently well-typed with unchanged generic envelope"
    (Q.validateCached gid parameters ds targetNames proposed)
  oldHeader <- fields (U.encodeInterface (U.objectInterface raw))
  newHeader <- fields (U.encodeInterface (U.objectInterface poison))
  need "alpha-only raw preserves complete interface except real checksum"
    (length oldHeader == 8 && length newHeader == 8 && take 7 oldHeader == take 7 newHeader)
  let poisoned3 = newRecord reference compact (payloadFor poison)
      poisoned1 = Q.encodeCached key poison
  need "alpha evidence poison is distinct from both raw and wholesale final"
    (U.encodeObject poison /= U.encodeObject raw && U.encodeObject poison /= U.encodeObject finalObject)
  saveRecord (root </> "target.poisoned-cache3.mlfq") poisoned3
  save (root </> "target.poisoned-cache1.mlfq") poisoned1
  save (root </> "target.poisoned-payload.legacy") (U.encodeContextualObject poison)
  save (root </> "alpha-slot.inventory") (U.pack [oldHint,changedHint,P.showInt (X.nameId slot),Pretty.name slot,Pretty.name changedSlot,U.encodeInterface (U.objectInterface poison),U.encodeObject poison])
  generic <- readRecordChecked (literal directory) key gid parameters ds targetNames poisoned3 >>= expect "actual alpha raw passes generic binary validation"
  need "generic CACHE3 admits complete alpha raw object" (sameObject generic poison)
  generic1 <- expect "actual alpha raw passes generic legacy validation"
    (Q.decodeCached key gid parameters ds targetNames poisoned1)
  need "generic legacy admits complete alpha raw object" (sameObject generic1 poison)
  prepared3Error <- exactLeft "actual PreparedRaw rejects alpha CACHE3 slot identity" authorityError
    (SI.validatePreparedRaw prepared generic)
  prepared1Error <- exactLeft "actual PreparedRaw rejects alpha legacy slot identity" authorityError
    (SI.validatePreparedRaw prepared generic1)
  save (root </> "prepared-rejection.txt") prepared3Error
  save (root </> "prepared-rejection-legacy.txt") prepared1Error
  withMemoLock directory $ \_ -> saveRecord (directory </> leaf) poisoned3
  repaired3 <- call "cache3-repair"
  need "actual Session CACHE3 poison repair preserves full final bytes" (repaired3 == cold)
  restored3 <- readRecord (directory </> leaf)
  need "actual Session CACHE3 repair restores the complete original raw record" (restored3 == original)
  withMemoLock directory $ \_ -> save (directory </> leaf) poisoned1
  repaired1 <- call "cache1-repair"
  need "actual Session legacy poison repair preserves full final bytes" (repaired1 == cold)
  restored1 <- readRecord (directory </> leaf)
  need "actual Session legacy repair restores complete original source CACHE3 raw record" (restored1 == original)
  forM_ coldFiles $ \file -> do
    before <- BS.readFile (retained </> file)
    actual <- BS.readFile (directory </> file)
    need "every original raw record survives both Session poison repairs" (actual == before)
  windowHandshake ("SESSION-RAW-RELEASED " ++ leaf) "SESSION-RAW-RELEASED-ACK"
  putStrLn "PASS actual Session whole-final generic Left and alpha raw generic Right PreparedRaw Left; both repairs preserve final and raw bytes"
