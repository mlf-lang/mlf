{-# LANGUAGE OverloadedStrings #-}
-- Independent controlled workload; not a real-project corpus or legacy compiler.
module Main where
import Prelude
import Control.Monad (unless)
import Control.Exception (bracket)
import Data.List (sort)
import System.CPUTime (getCPUTime)
import System.Directory (createDirectory, doesPathExist)
import System.Environment (getArgs)
import qualified Data.ByteString as BS
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.SourceInference as SI
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.Separate as U
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.Runtime as R
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P

need label ok = unless ok (error label)
expect label result = case result of
  T.Left message -> error (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value
literal = B.literal
readText path = literal <$> readFile path
save path = writeFile path . B.unpack
fields = expect "canonical field framing" . U.unpack
infixr 5 </>
(</>) :: FilePath -> FilePath -> FilePath
parent </> leaf = parent ++ "/" ++ leaf
crateIdentity = "query-context-64"
indices = [0..63] :: [Int]
memberName i = literal ("v" ++ replicate (3 - length (show i)) '0' ++ show i)
expectedNames = map memberName indices
expectedValue changed i = fromIntegral (if changed && i == 0 then 2000 else 1000 + i) :: P.Int
makePlan64 changed = do
  let members = [(memberName i,T.Nothing,T.SIntLit (expectedValue changed i)) | i <- indices]
      scopes = M.fromList P.compareString [(name,IS.empty) | name <- expectedNames]
  result <- expect "64 independent source plan" (SI.prepareSourcePlan M.empty [] [] [] scopes [] members)
  case result of
    T.Just plan -> pure plan
    T.Nothing -> error "64 workload unexpectedly fell back"

-- These spine helpers are the maintained SourceSCC method, without partial
-- head/list bindings and without its unnecessary external-dependency linker.
replaceTail (T.XLet name rhs rest) term = T.XLet name rhs (replaceTail rest term)
replaceTail (T.XLetRec bindings rest) term = T.XLetRec bindings (replaceTail rest term)
replaceTail (T.XConstructor "()" []) term = term
replaceTail _ _ = error "not a fragment binding spine"
findBinding wanted (T.XLet name rhs rest)
  | X.nameHint name == wanted = (name,rhs)
  | otherwise = findBinding wanted rest
findBinding wanted (T.XLetRec bindings rest) =
  case [(name,rhs) | (name,_,rhs) <- bindings, X.nameHint name == wanted] of
    [binding] -> binding
    [] -> findBinding wanted rest
    _ -> error "duplicate requested root"
findBinding _ _ = error "requested root absent"
checkIndependentValue changed object = do
  let iface = U.objectInterface object
      (ds,body) = case U.objectTerm object of
        T.XWithData declarations term -> (declarations,term)
        term -> ([],term)
      (parameters,core) = U.splitParameters body
  need "independent group has no external parameters" (null parameters)
  name <- case U.unitBindings iface of
    [(n,_)] -> pure n
    _ -> error "expected one independent binding"
  index <- case [i | i <- indices, memberName i == name] of
    [i] -> pure i
    _ -> error "unexpected or ambiguous independent member"
  need "exact independent unit owner" (U.unitName iface == Q.groupName crateIdentity [name])
  let (binder,_) = findBinding name core
      linked = T.XWithData ds (replaceTail core (T.XVarTerm binder))
  checked <- expect "independent final target check" (Checked.check linked)
  let term = Checked.term checked
  (environment,_) <- expect "independent runtime prepare" (R.prepare False term)
  value <- expect "independent runtime" (R.evaluate environment (R.REnv M.empty) (X.erase term))
  case value of
    R.RInteger actual -> do
      need "independent integer semantics" (actual == expectedValue changed index)
      pure (name,actual)
    _ -> error "expected an integer result"
reportIndex report = do
  let Q.QueryReport _ _ groups = report
  rows <- mapM one groups
  need "exact 64 report members" (sort (map (B.unpack . (\(_,name,_) -> name)) rows) == sort (map B.unpack expectedNames))
  pure rows
  where
    one (Q.GroupResult identity names _ _ digest) = case names of
      [name] -> do
        need "report exact generated owner" (identity == Q.groupName crateIdentity [name])
        need "report SHA name" (Q.validSourceContextDigest digest)
        pure (identity,name,digest)
      _ -> error "expected 64 singleton source groups"
encodeIndex rows = U.pack ["MLF-CONTEXT-64-INDEX-1", U.pack [U.pack [identity,name,digest] | (identity,name,digest) <- rows]]

query64 directory prefix changed = do
  plan <- makePlan64 changed
  before <- getCPUTime
  (objects,report,_) <- Q.compileParsedSourceGroups crateIdentity (literal directory) [] M.empty plan >>= expect "actual 64 source driver"
  after <- getCPUTime
  -- This narrow CPU sample is around the IO action/Either result only. Lazy
  -- returned terms may be demanded later; it is NOT whole-compile wall time.
  writeFile (prefix ++ ".q-cpu-picoseconds") (show (after - before) ++ "\n")
  need "exact 64 final objects" (length objects == 64)
  values <- mapM (checkIndependentValue changed) objects
  need "exact unique evaluated members" (sort (map (B.unpack . fst) values) == sort (map B.unpack expectedNames))
  rows <- reportIndex report
  save (prefix ++ ".objects") (U.pack (map U.encodeObject objects))
  save (prefix ++ ".values") (U.pack [U.pack [name,P.showInt actual] | (name,actual) <- values])
  save (prefix ++ ".index") (encodeIndex rows)
  -- No legacyAccounting, cache re-encoding or snapshot occurs in this mode.
  putStr (B.unpack (Q.reportJSON crateIdentity "controlled-64-independent-ints" report))

sameObject left right = U.encodeInterface (U.objectInterface left) == U.encodeInterface (U.objectInterface right)
                    && U.encodeObject left == U.encodeObject right
parseIndex input = do
  outer <- fields input
  encodedRows <- case outer of
    ["MLF-CONTEXT-64-INDEX-1",rows] -> pure rows
    _ -> error "unexpected frozen index format"
  need "canonical index framing" (U.pack outer == input)
  rows <- fields encodedRows >>= mapM one
  need "materializer exactly 64 unique names" (sort (map (B.unpack . (\(_,name,_) -> name)) rows) == sort (map B.unpack expectedNames))
  need "canonical full index" (encodeIndex rows == input)
  pure rows
  where
    one text = do
      row <- fields text
      case row of
        [identity,name,digest] -> do
          need "index canonical row" (U.pack row == text)
          need "index expected unit owner" (identity == Q.groupName crateIdentity [name])
          need "index safe SHA filename" (Q.validSourceContextDigest digest)
          pure (identity,name,digest)
        _ -> error "unexpected index row"

materialize64 source destination indexPath prefix = do
  exists <- doesPathExist destination
  need "fresh independent legacy cache" (not exists)
  createDirectory destination
  index <- readText indexPath >>= parseIndex
  -- Fixed A->B direction; do not reopen/close either .lock while owning it.
  rows <- bracket (P.acquireFileLock (literal (source </> ".lock"))) P.releaseFileLock $ \_ ->
    bracket (P.acquireFileLock (literal (destination </> ".lock"))) P.releaseFileLock $ \_ ->
      mapM convert index
  save (prefix ++ ".conversion") (U.pack ["MLF-CONTEXT-64-CONVERSION-1",U.pack rows])
  putStrLn "PASS materialized 64 self-contained legacy records"
  where
    convert (identity,name,digest) = do
      let filename = B.unpack digest ++ ".mlfq"
      input <- readText (source </> filename)
      outer <- fields input
      (reference,compact,payload) <- case outer of
        ["MLF-QUERY-CACHE-3",ref,key,body] -> pure (ref,key,body)
        _ -> error "materializer requires actual compact cold records"
      need "canonical compact record" (U.pack outer == input)
      need "safe context reference" (Q.validSourceContextDigest reference)
      let contextPath = Q.sourceContextPath (literal source) reference
      context <- P.readFile contextPath
      actualDigest <- P.fileDigest contextPath
      need "actual context SHA and fixed empty datatype context"
        (actualDigest == reference && context == Q.sourceContextContents (Q.encodeDatatypeContext []))
      key <- expect "restore all nine source-key fields" (Q.restoreSourceCacheKey (Q.encodeDatatypeContext []) compact)
      raw <- expect "actual contextual raw decode" (U.decodeContextualObject [] [] payload)
      checked <- expect "actual source cache admission" (Q.decodeSourceCached actualDigest key identity [] [] [name] context input)
      need "source decoder exact raw object" (sameObject raw checked && null (U.unitData (U.objectInterface raw)))
      let legacy = Q.encodeCached key raw
      legacyFields <- fields legacy
      need "old representation is self-contained CACHE1" (case legacyFields of
        ["MLF-QUERY-CACHE-1",savedKey,_,_] -> savedKey == key
        _ -> False)
      Q.writeCache (literal (destination </> filename)) legacy >>= expect "publish actual legacy record"
      saved <- readText (destination </> filename)
      need "exact persisted legacy bytes" (saved == legacy)
      restored <- expect "persisted old decoder" (Q.decodeCached key identity [] [] [name] saved)
      need "persisted old raw semantics identical" (sameObject raw restored)
      -- The outer Python reader independently SHA256s the EXISTING full key
      -- field in persisted CACHE1 and restores each compact key in memory.
      -- No key temporary, full-key report duplication or new scratch lifecycle.
      pure (U.pack [identity,name,digest,literal (show (BS.length (B.utf8 input))),literal (show (BS.length (B.utf8 saved)))])

main = do
  args <- getArgs
  case args of
    ["query64",directory,prefix,"original"] -> query64 directory prefix False
    ["query64",directory,prefix,"changed"] -> query64 directory prefix True
    ["materialize64",source,destination,indexPath,prefix] -> materialize64 source destination indexPath prefix
    _ -> error "expected query64 CACHE PREFIX original|changed or materialize64 A B INDEX PREFIX"
