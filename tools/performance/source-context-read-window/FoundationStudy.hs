{-# LANGUAGE OverloadedStrings #-}
-- Study wrapper. Ordinary argv dispatches the unmodified maintained entry.
-- Materialization is wire admission only. Real source/PreparedRaw admission is
-- established by subsequent --compile-crate runs requiring 504/0 cache hits.
module Main where

import Prelude
import Control.Exception (bracket)
import Control.Monad (unless)
import Data.List (nub, sort)
import qualified Data.ByteString as BS
import System.Directory (createDirectory, doesPathExist)
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Crate as C
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.Separate as U
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Map as M
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Checked as Checked
import qualified MLF.Entry.Emlf as Entry
import qualified MLF.Host.Base as B
import MLF.Host.IO (runEntry)
import qualified MLF.Primitive as P

type Row = (B.String, [B.String], B.String)

crateId :: B.String
crateId = "mlf-foundation/0.3.0/library"

need :: String -> Bool -> IO ()
need label condition = unless condition (errorWithoutStackTrace label)

expect :: String -> T.Either B.String a -> IO a
expect label result = case result of
  T.Left message -> errorWithoutStackTrace (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value

readText :: FilePath -> IO B.String
readText = P.readFile . B.literal

save :: FilePath -> B.String -> IO ()
save path = P.writeFile (B.literal path)

fields :: B.String -> IO [B.String]
fields text = do
  values <- expect "canonical framing" (U.unpack text)
  need "framing must roundtrip exactly" (U.pack values == text)
  pure values

utf8Bytes :: B.String -> Int
utf8Bytes = BS.length . B.utf8

encodeIndex :: [Row] -> B.String
encodeIndex rows = U.pack ["MLF-FOUNDATION-STUDY-INDEX-1",
  U.pack [U.pack [identity, U.pack members, digest] |
          (identity, members, digest) <- rows]]

readIndex :: FilePath -> IO [Row]
readIndex path = do
  text <- readText path
  outer <- fields text
  body <- case outer of
    ["MLF-FOUNDATION-STUDY-INDEX-1", packed] -> pure packed
    _ -> errorWithoutStackTrace "unexpected foundation index format"
  entries <- fields body
  rows <- mapM one entries
  let identities = [B.unpack identity | (identity, _, _) <- rows]
      names = concat [map B.unpack members | (_, members, _) <- rows]
      digests = [B.unpack digest | (_, _, digest) <- rows]
  need "exact real SCC population" (length rows == 504)
  need "unique group owners/members/keys"
    (length (nub identities) == 504 && length (nub digests) == 504 &&
     length (nub names) == length names)
  need "fixed SCC size histogram"
    (length [() | (_, ns, _) <- rows, length ns == 1] == 501 &&
     length [() | (_, ns, _) <- rows, length ns == 4] == 2 &&
     length [() | (_, ns, _) <- rows, length ns == 2] == 1)
  need "whole index canonical" (encodeIndex rows == text)
  pure rows
  where
    one encoded = do
      row <- fields encoded
      case row of
        [identity, packedMembers, digest] -> do
          members <- fields packedMembers
          need "nonempty sorted SCC member inventory"
            (not (null members) && map B.unpack members == sort (map B.unpack members))
          need "real expected group owner" (identity == Q.groupName crateId members)
          need "safe query SHA filename" (Q.validSourceContextDigest digest)
          pure (identity, members, digest)
        _ -> errorWithoutStackTrace "unexpected index row"

loadFinal :: FilePath -> [Row] -> IO [U.UnitObject]
loadFinal prefix rows = do
  iface <- A.readInterface (B.literal (prefix ++ ".mlfci")) >>= expect "actual crate interface"
  _ <- expect "complete interface validation" (A.validateInterface iface)
  need "exact foundation crate identity" (A.crateId iface == crateId)
  object <- A.readObject (B.literal (prefix ++ ".mlfco")) iface >>= expect "actual crate object"
  let fragments = A.objectFragments object
  need "complete finalized fragment population" (length fragments == 504)
  mapM_ match (zip rows fragments)
  pure fragments
  where
    match ((identity, members, _), object) = do
      let iface = U.objectInterface object
      need "final artifact exact ordered group owner" (U.unitName iface == identity)
      need "final artifact exact declaration ownership"
        (sort (map (B.unpack . fst) (U.unitBindings iface)) == sort (map B.unpack members))

sameRaw :: U.UnitObject -> U.UnitObject -> Bool
sameRaw a b = U.encodeInterface (U.objectInterface a) == U.encodeInterface (U.objectInterface b)
           && U.encodeObject a == U.encodeObject b

rawParameters :: U.UnitObject -> [(B.String, T.XType)]
rawParameters object =
  let body = case U.objectTerm object of
        T.XWithData _ inner -> inner
        inner -> inner
  in [(X.nameHint name, ty) | (name, ty) <- fst (Q.peelParameters body)]

materialize :: FilePath -> FilePath -> FilePath -> FilePath -> FilePath -> IO ()
materialize source destination indexPath coldPrefix evidence = do
  rows <- readIndex indexPath
  finals <- loadFinal coldPrefix rows
  present <- doesPathExist destination
  need "fresh independent legacy cache" (not present)
  createDirectory destination
  -- One fixed A->B lock order. Do not reopen either .lock while owning it.
  converted <- bracket (P.acquireFileLock (B.literal (source ++ "/.lock"))) P.releaseFileLock $ \_ ->
    bracket (P.acquireFileLock (B.literal (destination ++ "/.lock"))) P.releaseFileLock $ \_ ->
      mapM convert (zip rows finals)
  save evidence (U.pack ["MLF-FOUNDATION-CONVERSION-1", U.pack converted])
  putStrLn "PASS materialized 504 self-contained legacy source records"
  where
    convert ((identity, members, digest), finalObject) = do
      let filename = B.unpack digest ++ ".mlfq"
          sourceFile = source ++ "/" ++ filename
          destinationFile = destination ++ "/" ++ filename
          -- Only declarations are borrowed. NEVER use finalObject's body as raw.
          ds = U.unitData (U.objectInterface finalObject)
          expectedContext = Q.encodeDatatypeContext ds
      input <- readText sourceFile
      outer <- fields input
      (key, raw, format) <- case outer of
        ["MLF-QUERY-CACHE-3", reference, compact, payload] -> do
          need "safe context address" (Q.validSourceContextDigest reference)
          let contextPath = Q.sourceContextPath (B.literal source) reference
          blob <- P.readFile contextPath
          actualDigest <- P.fileDigest contextPath
          need "actual context bytes/hash against candidate declarations"
            (actualDigest == reference && blob == Q.sourceContextContents expectedContext)
          key <- expect "restore complete nine-field source key" (Q.restoreSourceCacheKey expectedContext compact)
          raw <- expect "decode ORIGINAL raw payload with candidate declarations"
            (U.decodeContextualObject ds ds payload)
          need "original compact payload exact roundtrip" (U.encodeContextualObject raw == payload)
          admitted <- expect "formal compact wire admission (NOT source proof)"
            (Q.decodeSourceCached actualDigest key identity (rawParameters raw) ds members blob input)
          need "formal compact decoder preserves whole raw" (sameRaw raw admitted)
          pure (key, admitted, "MLF-QUERY-CACHE-3")
        ["MLF-QUERY-CACHE-1", key, metadata, payload] -> do
          iface <- expect "actual fallback metadata" (U.decodeInterface metadata)
          raw <- expect "actual fallback raw payload" (U.decodeObject iface payload)
          admitted <- expect "formal fallback wire admission (NOT source proof)"
            (Q.decodeCached key identity (rawParameters raw) ds members input)
          need "fallback exact raw roundtrip" (sameRaw raw admitted)
          pure (key, admitted, "MLF-QUERY-CACHE-1")
        _ -> errorWithoutStackTrace "unexpected actual source cache format"
      -- A is allowed to retain a legitimate source-format fallback, never QUERY4.
      case Q.sourceCacheParts key of
        T.Just (_, context) -> need "full source key context agrees" (context == expectedContext)
        T.Nothing -> errorWithoutStackTrace "expected complete SOURCE-QUERY-6 key"
      let legacy = Q.encodeCached key raw
      legacyFields <- fields legacy
      need "newly materialized self-contained CACHE1" (case legacyFields of
        ["MLF-QUERY-CACHE-1", savedKey, _, _] -> savedKey == key
        _ -> False)
      Q.writeCache (B.literal destinationFile) legacy >>= expect "publish actual old representation"
      persisted <- readText destinationFile
      need "persisted legacy bytes exact" (persisted == legacy)
      decoded <- expect "formal persisted legacy readback"
        (Q.decodeCached key identity (rawParameters raw) ds members persisted)
      need "complete raw interface/object equality" (sameRaw raw decoded)
      -- Python independently checks full-key UTF8 SHA == digest on both actual
      -- directories. No new query-key scratch or full-key evidence copy is made.
      pure (U.pack [identity, U.pack members, digest, format,
                    B.literal (show (utf8Bytes input)), B.literal (show (utf8Bytes persisted))])

replaceTail :: T.XTerm -> T.XTerm -> T.XTerm
replaceTail (T.XLet name rhs rest) term = T.XLet name rhs (replaceTail rest term)
replaceTail (T.XLetRec bindings rest) term = T.XLetRec bindings (replaceTail rest term)
replaceTail (T.XConstructor "()" []) term = term
replaceTail _ _ = errorWithoutStackTrace "not a fragment binding spine"

findUniqueBinding :: B.String -> T.XTerm -> T.XName
findUniqueBinding wanted term = case collect term of
  [name] -> name
  [] -> errorWithoutStackTrace "Version binding absent from linked closure"
  _ -> errorWithoutStackTrace "duplicate Version binding in linked closure"
  where
    collect (T.XLet name _ rest) =
      [name | X.nameHint name == wanted] ++ collect rest
    collect (T.XLetRec bindings rest) =
      [name | (name, _, _) <- bindings, X.nameHint name == wanted] ++ collect rest
    collect (T.XConstructor "()" []) = []
    collect _ = errorWithoutStackTrace "not a complete linked library binding spine"

versionAudit :: FilePath -> FilePath -> String -> FilePath -> IO ()
versionAudit prefix indexPath state evidence = do
  rows <- readIndex indexPath
  fragments <- loadFinal prefix rows
  expected <- case state of
    "original" -> pure "0.3.0"
    "changed" -> pure "0.3.1"
    _ -> errorWithoutStackTrace "unknown frozen source state"
  let name = A.definitionName crateId (Modules.Entity "Bootstrap.Version" "version" Modules.Value)
  need "Version has one singleton finalized fragment"
    (length [object | object <- fragments,
                      map fst (U.unitBindings (U.objectInterface object)) == [name]] == 1)
  -- Resolve EVERY actual parameter through the maintained artifact linker.
  -- A fragment's overloaded String expression imports fromString/IsString;
  -- dropping its leading lambdas would not produce an independent value.
  linked <- A.linkCheckedFile (B.literal (prefix ++ ".mlfci"))
            >>= expect "complete independent Version dependency linkage"
  let (ds, core) = case Checked.term linked of
        T.XWithData declarations term -> (declarations, term)
        term -> ([], term)
      binder = findUniqueBinding name core
      selected = T.XWithData ds (replaceTail core (T.XVarTerm binder))
  checked <- expect "independent Version target check" (Checked.check selected)
  let term = Checked.term checked
  (environment, _) <- expect "independent Version runtime preparation" (R.prepare False term)
  value <- expect "independent Version evaluation"
    (R.evaluate environment (R.REnv M.empty) (X.erase term))
  case value of
    R.RString actual -> do
      need ("Version oracle mismatch: expected " ++ B.unpack expected ++ "; actual " ++ B.unpack actual)
        (actual == expected)
      save evidence (U.pack ["MLF-FOUNDATION-VERSION-1", "504", actual])
    _ -> errorWithoutStackTrace "Version result was not RString"
  putStrLn "PASS 504 finalized fragments and independent Version RString"

prepareBuiltin :: FilePath -> IO ()
prepareBuiltin prefix = do
  metadata <- C.ensureBuiltin (B.literal prefix) >>= expect "fixed untimed builtin preparation"
  need "exact builtin metadata prefix" (metadata == B.literal (prefix ++ ".mlfci"))
  putStrLn "PASS fixed builtin prepared outside target timing"

main :: IO ()
main = do
  args <- getArgs
  case args of
    ["--study-materialize", source, destination, indexPath, coldPrefix, evidence] ->
      runEntry (materialize source destination indexPath coldPrefix evidence)
    ["--study-version", prefix, indexPath, state, evidence] ->
      runEntry (versionAudit prefix indexPath state evidence)
    ["--study-builtin", prefix] -> runEntry (prepareBuiltin prefix)
    _ -> runEntry Entry.main
