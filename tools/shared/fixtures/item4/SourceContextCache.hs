{-# LANGUAGE OverloadedStrings #-}
-- Real production API controls. This program never changes compiler globals.
module Main where
import Prelude
import SourceKeyWitness (sourceKeys, fullKey, fingerprint)
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
exactLeft label diagnostic result = case result of
  T.Left message -> need (label ++ " exact diagnostic") (message == diagnostic) >> pure message
  T.Right _ -> error (label ++ " unexpectedly accepted")
fields = expect "framing" . U.unpack
literal = B.literal
save p = writeFile p . B.unpack
fresh p = do exists <- doesPathExist p; need ("fresh directory " ++ p) (not exists); createDirectory p
sameObject a b = U.encodeInterface (U.objectInterface a) == U.encodeInterface (U.objectInterface b)
              && U.encodeObject a == U.encodeObject b
names = ["value"]
members n = [("value", T.Nothing, T.SIntLit n)]
keyFor context = U.pack ["MLF-SOURCE-CRATE-QUERY-7", "crate:α😀", "compiler",
                        "member:opaque:😀", "bindings", context,
                        "source-group", "observed-contracts", "scope-table:α😀"]
-- Independently frame retired text records only for rejection checks.
retiredInline key object = U.pack ["MLF-QUERY-CACHE-1",key,
  U.encodeInterface (U.objectInterface object),U.encodeObject object]
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
badPayload = Payload (Wire.VNode 2147483647 []) (Wire.VNode 2147483647 [])
badPayloadDiagnostic = "malformed binary artifact UnitInterface tag"
legacyRecord ref compact payload = U.pack ["MLF-QUERY-CACHE-3",ref,compact,payload]
-- Legacy poisons need full inputs. Reconstruct those from the test program,
-- never from the record under test. Keep the current envelope for new poisons.
localRecordParts keys record = recordPartsWith (fullKey keys) record
recordParts key = recordPartsWith (\digest -> do
  actual <- fingerprint key
  need "writer used expected input digest" (actual == digest)
  pure key)
recordPartsWith keyForDigest record = case record of
  BinaryInput [Wire.VText address,Wire.VNode 303 [Wire.VText ref,Wire.VText digest,Wire.VText ich,header,body]] ->
    decoded address digest ich ref header body
  BinaryInput [Wire.VText address,Wire.VNode 306 [Wire.VText digest,Wire.VText ich,Wire.VText ref,header,body]] ->
    decoded address digest ich ref header body
  _ -> error "expected a fingerprinted source record"
 where
  decoded address digest ich ref header body = do
    need "address matches stored input and hashes are valid"
      (address == digest && Q.validSourceContextDigest digest && Q.validSourceContextDigest ich)
    input <- keyForDigest digest
    pure (ref,input,Payload header body)
localRecord ref input (Payload header body) = do
  digest <- fingerprint input
  ich <- Q.localResultHash digest [Wire.VText ref,header,body] >>= expect "poison ICH"
  let address = Wire.VText digest
  pure (BinaryInput [address,Wire.VNode 303 [Wire.VText ref,address,Wire.VText ich,header,body]])
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
contextLogical path = Q.encodeSourceDatatypes <$> readContext path
readRecordWindow previous directory key name bindings ds wanted record = case record of
  LegacyInput text -> do
    let path = B.unpack directory </> "obsolete-source-record.tmp"
    bracket (save path text) (\_ -> removeFile path) $ \_ ->
      Q.readSourceCacheFileWithWindow previous directory key name bindings ds wanted (literal path)
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
helper directory = do
  fresh directory
  bracket (P.acquireFileLock (literal (directory </> ".lock"))) P.releaseFileLock (\_ -> helperLocked directory)
helperLocked directory = do
  object <- expect "raw inference" (I.compileLoweredGroup "RawGroup" [] [] (members 41))
  let context = Q.encodeSourceDatatypes []
      key = keyFor context
      path = directory </> "record.mlfq"
      old1 = retiredInline key object
      old2 = U.pack ["MLF-QUERY-CACHE-2",key,U.encodeContextualObject object]
  forM_ [old1,old2] $ \retired -> do
    result <- readNew directory key (LegacyInput retired)
    _ <- exactLeft "obsolete source cache rejected" "unsupported source query cache format" result
    pure ()
  need "noncanonical source key is not eligible" (case Q.sourceQueryContext ("0" P.++ key) of T.Nothing -> True; _ -> False)
  before <- listDirectory directory
  need "legacy readers did not migrate/write" (sort before == [".lock"])
  Q.writeSourceCached T.Nothing (literal directory) (literal path) key object >>= expect "source write"
  input <- readRecord path
  (ref,storedKey,payload) <- recordParts key input
  need "source input hash binds the complete Unicode key" (storedKey == key)
  let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
  originalContextBytes <- BS.readFile contextPath
  blob <- contextLogical contextPath
  need "canonical context blob" (blob == context)
  digest <- P.fileDigest (literal contextPath)
  need "context SHA filename" (digest == ref && Q.validSourceContextDigest ref)
  checked <- readNew directory key input >>= expect "addressed binary source reader"
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
  fullFields <- fields key
  (window,_,_) <- readRecordWindow [] (literal directory) key "RawGroup" [] [] names input
  need "real verified context for substituted-record controls" (not (null window))
  forM_ (("pre-v7", "MLF-SOURCE-CRATE-QUERY-6") : zip (map show [1::Int ..]) identities) $ \(label,fmt) -> do
    let forge xs = U.pack (fmt:drop 1 xs)
    record <- localRecord ref (forge fullFields) payload
    need (label ++ " claimed builtin identity rejected even with matching supplied key")
      (case Q.sourceQueryContext (forge fullFields) of T.Nothing -> True; _ -> False)
    (_,_,result) <- readRecordWindow window (literal directory) key "RawGroup" [] [] names record
    reject (label ++ " saved identity at current key with verified context") result
  let differentCompiler = U.pack (take 2 fullFields ++ ["other compiler"] ++ drop 3 fullFields)
  foreignRecord <- localRecord ref differentCompiler payload
  (_,_,foreignCompiler) <- readRecordWindow window (literal directory) key "RawGroup" [] [] names foreignRecord
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
        localRecord badRef key payload >>= readNew directory key >>= reject label
        removeFile badPath
  wrongContext "context carrier changed" [Structure.toDataContext [T.DataDecl "Other" [] [T.ConstructorDecl "Other" []]]]
  wrongContext "context carrier wrong version" [Wire.VNode 2147483647 []]
  wrongContext "context carrier extra field" [Structure.toDataContext [], Wire.VInt 1]
  localRecord ref key badPayload >>= decode key "RawGroup" [] [] names >>= reject "payload truncated"
  let trailing = case input of BinaryInput [address,Wire.VNode tag children] -> BinaryInput [address,Wire.VNode tag (children ++ [Wire.VInt 1])]; _ -> error "shared roots"
  decode key "RawGroup" [] [] names trailing >>= reject "record trailing field"
  -- Framing canonicality is wire-owned; actual malformed bytes must not decode.
  originalRecordBytes <- BS.readFile path
  BS.writeFile (directory </> "noncanonical.new") (originalRecordBytes <> BS.singleton 0)
  Storage.read 2 (literal (directory </> "noncanonical.new")) >>= reject "noncanonical record framing"
  removeFile (directory </> "noncanonical.new")
  let zeroRef = literal (replicate 64 '0')
      zeroPath = B.unpack (Q.sourceContextPath (literal directory) zeroRef)
  need "actual digest negative path fresh" =<< (not <$> doesPathExist zeroPath)
  BS.writeFile zeroPath originalContextBytes
  localRecord zeroRef key payload >>= readNew directory key >>= reject "actual context digest differs"
  removeFile zeroPath
  forM_ ["../escape", "", literal (replicate 63 'a'), literal (replicate 64 'A'), literal (replicate 64 'g')] $ \bad -> do
    need "invalid digest rejected before path use" (not (Q.validSourceContextDigest bad))
    localRecord bad key payload >>= readNew directory key >>= reject "untrusted context reference"
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
  need "ineligible source object uses checked binary inline format" (case fallback of BinaryInput [_,Wire.VNode tag _] -> tag == 302 || tag == 305; _ -> False)
  fallbackObject <- readRecordChecked (literal directory) (keyFor "wrong") "RawGroup" [] [] names fallback >>= expect "inline fallback semantic read"
  need "inline fallback preserves complete raw" (sameObject fallbackObject object)
  let boxA = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
      boxB = T.DataDecl "Box" ["b"] [T.ConstructorDecl "Box" [T.Parameter "b"]]
      changedBox = T.DataDecl "Box" ["b"] [T.ConstructorDecl "Box" [T.Parameter "b", T.Parameter "b"]]
      boxMembers = [("value",T.Nothing,T.SApp (T.SConstructor "Box") (T.SIntLit 7))]
      boxKey = keyFor (Q.encodeSourceDatatypes [boxA])
      boxPath = directory </> "box.mlfq"
  boxObject <- expect "nonempty datatype raw inference" (I.compileLoweredGroup "RawGroup" [] [boxA] boxMembers)
  need "alpha test setup uses identical complete canonical contexts" (Q.encodeSourceDatatypes [boxA] == Q.encodeSourceDatatypes [boxB])
  Q.writeSourceCached (T.Just (Q.prepareSourceEncodings [boxA])) (literal directory) (literal boxPath) boxKey boxObject >>= expect "nonempty shared context write"
  boxInput <- readRecord boxPath
  (boxRef,_,_) <- recordParts boxKey boxInput
  need "different complete datatype context has different identity" (boxRef /= ref)
  alpha <- readRecordChecked (literal directory) boxKey "RawGroup" [] [boxB] names boxInput >>= expect "alpha-equivalent datatype context remains admissible"
  need "alpha-equivalent metadata preserves canonical layout" (Q.encodeSourceDatatypes (U.unitData (U.objectInterface alpha)) == Q.encodeSourceDatatypes [boxA])
  readRecordChecked (literal directory) boxKey "RawGroup" [] [changedBox] names boxInput >>= reject "same datatype name different layout"
  let legacyContextPath = directory </> "legacy-context.new"
  save legacyContextPath (U.pack ["MLF-SOURCE-QUERY-CONTEXT-1",context])
  legacyRef <- P.fileDigest (literal legacyContextPath)
  let legacyContextDestination = B.unpack (Q.sourceContextPath (literal directory) legacyRef)
      legacy3 = legacyRecord legacyRef (U.pack (take 5 fullFields ++ drop 6 fullFields)) (U.encodeContextualObject object)
  need "old context namespace distinct from binary" (legacyRef /= ref)
  renameFile legacyContextPath legacyContextDestination
  old3 <- readNew directory key (LegacyInput legacy3)
  _ <- exactLeft "obsolete CACHE3 refused despite matching context" "unsupported source query cache format" old3
  removeFile legacyContextDestination
  putStrLn "PASS helper rejects obsolete text and checks current keys and corrupt inputs"

legacyOne directory = do
  files <- sort . filter (\name -> reverse (take 5 (reverse name)) == ".mlfq") <$> listDirectory directory
  file <- case files of x:_ -> pure (directory </> x); _ -> error "missing query record"
  input <- readRecord file
  plan <- makePlan 41
  keys <- sourceKeys "query-context-control" plan [] M.empty M.empty
  (_,key,payload) <- localRecordParts keys input
  raw <- expect "legacy conversion raw object" (decodePayload [] payload)
  save file (retiredInline key raw)
  putStrLn "PASS fixture replaced one record with valid old CACHE1"

makePlan value = do
  let own = [("first",T.Nothing,T.SIntLit value),("second",T.Nothing,T.SIntLit 99)]
      scopes = M.fromList P.compareString [(n,IS.empty) | (n,_,_) <- own]
  p <- expect "source plan" (SI.prepareSourcePlan M.empty [] [] [] scopes [] own)
  case p of T.Just plan -> pure plan; _ -> error "unexpected whole-source fallback"

query directory resultFile value = do
  plan <- makePlan value
  (objects,report,_) <- Q.compileParsedSourceGroups "query-context-control" (literal directory) [] M.empty plan >>= expect "Query actual source driver"
  save resultFile (U.pack (map U.encodeObject objects))
  putStrLn (B.unpack (Q.reportJSON "query-context-control" "test" report))

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
  keys <- sourceKeys "raw-final" plan [] M.empty contracts
  (ref,key,payload) <- localRecordParts keys input
  let ds = U.unitData (U.objectInterface finalObject)
  raw <- expect "raw contextual object" (decodePayload ds payload)
  let parameters = [(X.nameHint n,t) | (n,t) <- fst (U.splitParameters (strip (U.objectTerm raw)))]
  need "raw object differs from compact final" (U.encodeObject raw /= U.encodeObject finalObject)
  -- Preserve the real reference and full-key projection: only the object
  -- payload is poisoned. This must not become a trivial envelope mismatch.
  poisoned3 <- localRecord ref key (payloadFor finalObject)
  accepted3 <- readRecordChecked (literal directory) key groupId parameters ds ["sameDeps"] poisoned3 >>= expect "binary generic validator accepts finalized counterexample"
  need "binary final payload actually decoded" (sameObject accepted3 finalObject)
  saveRecord file poisoned3
  (repaired3,report3,_) <- Q.compileSourceGroups "raw-final" (literal directory) [] M.empty plan >>= expect "binary raw/final rejection and reinference"
  need "binary final-as-raw only reinfers poisoned group" (Q.inferredCount report3 == 1 && Q.reusedCount report3 == fromIntegral (length objects - 1))
  need "binary final artifact exact after repair" (map U.encodeObject repaired3 == map U.encodeObject objects)
  -- The repaired record must restore the raw payload, not simply preserve the
  -- poisoned cache while returning independently correct final artifacts.
  repairedInput3 <- readRecord file
  (repairedRef,repairedKey,repairedPayload) <- localRecordParts keys repairedInput3
  need "binary repair keeps reference/key and restores raw payload"
    (repairedRef == ref && repairedKey == key && repairedPayload == payload)
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
    ["helper",directory] -> helper directory
    ["query",directory,resultFile,value] -> query directory resultFile (read value)
    ["raw-final",directory] -> rawFinal directory
    ["legacy-one",directory] -> legacyOne directory
    ["left-legacy",directory,"await-probe"] -> awaitProbe (leftLegacy directory)
    ["left-source",directory,"await-probe"] -> awaitProbe (leftSource directory)
    ["empty-success",directory] -> emptySuccess directory
    ["empty-directory-failure",directory,"await-probe"] -> awaitProbe (emptyDirectoryFailure directory)
    ["cleanup-dual-failure",directory,"await-probe"] -> awaitProbe (cleanupDualFailure directory)
    ["concurrent",directory,resultFile] -> concurrent directory resultFile
    ["context-directory-setup",directory] -> contextDirectorySetup directory
    ["context-directory-reject",directory] -> contextDirectoryReject directory
    ["context-stage-cleanup-failure",directory] -> contextStageCleanupFailure directory
    ["window-helper",directory] -> windowHelper directory
    _ -> error "unknown source-context control or invalid arguments"

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
memoEntry keys directory plan (Q.GroupResult groupId memberNames _ _ digest) = do
  input <- readRecord (directory </> (B.unpack digest ++ ".mlfq"))
  (ref,key,payload) <- localRecordParts keys input
  blob <- contextLogical (B.unpack (Q.sourceContextPath (literal directory) ref))
  need "helper real empty context" (blob == Q.encodeSourceDatatypes [])
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
  (_,cold,contracts) <- Q.compileParsedSourceGroups "memo-helper" (literal directory) [] M.empty plan >>= expect "memo helper cold"
  need "memo helper two cold groups" (Q.inferredCount cold == 2 && Q.reusedCount cold == 0)
  let Q.QueryReport _ _ groups = cold
  (first,second) <- case groups of [a,b] -> pure (a,b); _ -> error "two independent memo groups required"
  keys <- sourceKeys "memo-helper" plan [] M.empty contracts
  withMemoLock directory $ \_ -> do
    firstEntry@(_,_,_,_,rawA,preparedA) <- memoEntry keys directory plan first
    secondEntry@(gid,ns,key,input,rawB,preparedB) <- memoEntry keys directory plan second
    memo <- memoRead T.Nothing directory firstEntry >>= memoGood "first verified context" False preparedA rawA
    memoRead memo directory secondEntry >>= memoGood "same context verified reuse" True preparedB rawB >> pure ()
    (ref,_,payload) <- localRecordParts keys input
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
    localRecord ref key badPayload >>= readSame key gid [] [] ns >>= memoBad "memo rejects bad payload" True
    fs <- fields key
    let change i = U.pack [if j == i then value P.++ "!" else value | (j,value) <- zip [0..] fs]
    readSame (change 8) gid [] [] ns input >>= memoBad "memo rejects full scope key change" False
    readSame key "WrongOwner" [] [] ns input >>= memoBad "memo rejects owner change" True
    readSame key gid [("external",T.XCon "Int" [])] [] ns input >>= memoBad "memo rejects parameter change" True
    readSame key gid [] [] ["wrongName"] input >>= memoBad "memo rejects declaration change" True
    readSame (change 5) gid [] [] ns input >>= memoBad "memo rejects context field change" False
    let otherRef = literal (replicate 64 '0')
    need "distinct absent valid digest" (otherRef /= ref)
    absent <- doesPathExist (B.unpack (Q.sourceContextPath (literal directory) otherRef))
    need "no zero digest context" (not absent)
    localRecord otherRef key payload >>= readSame key gid [] [] ns >>= memoBad "memo rejects different digest" False
    localRecord "../escape" key payload >>= readSame key gid [] [] ns >>= memoBad "memo rejects unsafe reference" False
    let otherDirectory = directory </> "different-cache"
    fresh otherDirectory
    withMemoLock otherDirectory $ \_ ->
      readChanged memo otherDirectory key gid [] [] ns input >>= memoBad "memo does not cross cache directory" False
    (cleared,reused,old) <- readSame key gid [] [] ns (LegacyInput (retiredInline key rawB))
    need "old source text clears context memo" (memoAbsent cleared && not reused)
    _ <- exactLeft "retired source text" "unsupported source query cache format" old
    putStrLn "PASS obsolete source record clears memo"
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

memoCycle directory root keyWitnesses invoke = do
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
  keys <- keyWitnesses
  (ref,key,payload) <- localRecordParts keys original
  let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
  contextBlob <- BS.readFile contextPath
  logicalContext <- contextLogical contextPath
  need "memo public empty datatype fixture" (logicalContext == Q.encodeSourceDatatypes [])
  raw <- expect "memo public raw" (decodePayload [] payload)
  let legacy = retiredInline key raw
  withMemoLock directory $ \_ -> save file legacy
  mixed <- call "mixed"
  current <- readRecord file
  need "obsolete record rebuilt as the current binary" (current == original)
  need "repair preserves complete output" (mixed == baseline)
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
  memoCycle directory root (sourceKeys "memo-query" plan [] M.empty M.empty) $ \_ -> do
    (objects,report,_) <- Q.compileParsedSourceGroups "memo-query" (literal directory) [] M.empty plan >>= expect "memo Query public driver"
    pure (U.pack (map U.encodeObject objects),Q.reportJSON "memo-query" "memo" report)

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
  keys <- sourceKeys "raw-final" plan [] M.empty contracts
  (ref,key,payload) <- localRecordParts keys input
  let ds = U.unitData (U.objectInterface finalObject)
  raw <- expect "raw contextual object" (decodePayload ds payload)
  let parameters = [(X.nameHint n,t) | (n,t) <- fst (U.splitParameters (strip (U.objectTerm raw)))]

  prepared <- expect "counterexample actual prepared authority"
    (SI.prepareGroup plan (M.filterWithKey (\name _ -> name /= "sameDeps") contracts) ["sameDeps"])
  withMemoLock directory $ \_ -> do
    memo <- readRecordMemo T.Nothing (literal directory) key groupId parameters ds ["sameDeps"] input
      >>= memoGood "counterexample verified raw" False prepared raw
    poisoned <- localRecord ref key (payloadFor finalObject)
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
    (ref,_,_) <- recordParts key input
    let contextPath = B.unpack (Q.sourceContextPath (literal directory) ref)
    blob <- contextLogical contextPath
    actual <- P.fileDigest (literal contextPath)
    need "directory setup uses real context digest and contents"
      (Q.validSourceContextDigest ref && actual == ref && blob == context)
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
  -- intended to simulate a successful publication.
  result <- Q.rejectSourceContextPublication (literal directory) contextPublicationError
  case result of
    T.Left message -> need "publication and directory cleanup errors both retained"
      (message == contextPublicationError P.++ "; cannot remove source query context staging: path is a directory")
    T.Right _ -> error "publication cleanup helper incorrectly returned Right"
  putStrLn "PASS context staging directory preserves publication and cleanup errors"


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
windowRoutes entries = [(directory,reference) | Q.SourceContextRead directory reference _ _ <- entries]
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
  (reference,storedKey,payload) <- recordParts key input
  let context = Q.encodeSourceDatatypes ds
  let contextPath = Q.sourceContextPath (literal directory) reference
  actual <- P.fileDigest contextPath
  blob <- contextLogical (B.unpack contextPath)
  need "window real canonical writer carrier/reference/raw"
    (Q.validSourceContextDigest reference && reference == actual && storedKey == key &&
     blob == context && payload == payloadFor raw)
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
    (_,_,payload) <- recordParts (windowKey a) (windowInput a)
    let changedKey = keyFor (Q.encodeSourceDatatypes (windowDatatypes b))
    changedRecord <- localRecord (windowReference a) changedKey payload
    let alpha = a { windowDatatypes = [alphaBox], windowObject = alphaRaw }
        changedEncoded = a { windowKey = changedKey, windowInput = changedRecord }
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
      windowRead eight a { windowInput = LegacyInput (retiredInline (windowKey a) (windowObject a)) }
        >>= windowBad "obsolete source record clears entire window" False "unsupported source query cache format"
      windowPass "obsolete source record clears all entries"
      windowRead eight a { windowInput = BinaryInput [] } >>= windowBad "malformed record clears entire window" False "malformed binary query roots"
      windowPass "malformed record clears all entries"
      unsafe <- localRecord "../escape" (windowKey a) payload
      windowRead eight a { windowInput = unsafe } >>= windowBad "unsafe reference clears entire window" False "invalid source query context reference"
      windowPass "unsafe reference clears all entries"
      windowRead eight a { windowKey = "0" P.++ windowKey a } >>= windowBad "malformed full key clears entire window" False "unsupported source query key"
      windowPass "malformed full key clears all entries"
      keyFields <- fields (windowKey a)
      windowRead eight a { windowKey = U.pack (take 8 keyFields ++ ["different-full-scope"]) }
        >>= windowBad "full scope change clears before route reuse" False "cached query key mismatch"
      windowPass "complete key mismatch clears before reuse"
      rejectedPayload <- localRecord (windowReference a) (windowKey a) badPayload
      windowRead eight a { windowInput = rejectedPayload }
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
