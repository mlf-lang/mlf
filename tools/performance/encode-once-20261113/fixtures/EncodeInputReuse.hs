{-# LANGUAGE OverloadedStrings #-}
module Main where

-- The same source tests the frozen baseline and the candidate. No new helper
-- is called directly: both changed production entry points are exercised.
import Prelude
import Control.Exception (SomeException, displayException, evaluate, try)
import Control.Monad (forM, forM_, unless)
import Data.List (isInfixOf, sort)
import qualified Data.ByteString as BS
import System.Directory (createDirectory, doesDirectoryExist, doesPathExist, listDirectory)
import System.Environment (getArgs, lookupEnv)
import System.FilePath ((</>))
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.SourceInference as S
import qualified Bootstrap.CrateGraph as C
import qualified Bootstrap.QueryGraph as Q
import qualified Bootstrap.OpenFragment as O
import qualified Bootstrap.Bitstream as W
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

need label okay = unless okay (errorWithoutStackTrace label)
right label result = case result of
  T.Left message -> errorWithoutStackTrace (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value
pass label = putStrLn ("PASS\t" ++ label)

-- Frozen two-record protocol from f9 CrateGraph.hs:49-68. It deliberately
-- calls Q.record twice and does not share the candidate's new helper.
oldBindings scope values session = case values of
  [] -> pure (T.Right session)
  (i,contract):rest -> do
    observed <- Q.record (Q.inputKey (C.bindingKey scope i)) [] False (C.contractValue contract) session
    case observed of
      T.Left e -> pure (T.Left e)
      T.Right (leaf,next) -> do
        recorded <- Q.record (C.bindingKey scope i) [Q.edge leaf] True (C.contractValue contract) next
        case recorded of
          T.Left e -> pure (T.Left e)
          T.Right (_,final) -> oldBindings scope rest final
oldDatatypes values session = case values of
  [] -> pure (T.Right session)
  declaration:rest -> do
    let wanted = C.datatypeKey (datatypeName declaration)
        value = O.declarationValue declaration
    observed <- Q.record (Q.inputKey wanted) [] False value session
    case observed of
      T.Left e -> pure (T.Left e)
      T.Right (leaf,next) -> do
        recorded <- Q.record wanted [Q.edge leaf] True value next
        case recorded of
          T.Left e -> pure (T.Left e)
          T.Right (_,final) -> oldDatatypes rest final
datatypeName (T.DataDecl name _ _) = name
datatypeName (T.DataDeclK name _ _) = name

names = ["alpha", "beta", "gamma", "delta"]
symbols = D.symbols [(n,False) | n <- names]
scope = S.declarationScope symbols (V.indices (D.symbolNodes symbols)) [] []
slot name = case S.requireDecl scope name of
  T.Right i -> i
  T.Left _ -> errorWithoutStackTrace "fixture scope construction"
plain = S.SourceContract (T.XCon "Int" []) [] False
bound = S.SourceContract
  (T.XForall (T.XTyVar 91) T.XBot
    (T.XArrow (T.XVar (T.XTyVar 91)) (T.XVar (T.XTyVar 91))))
  ["Eq Int", "Class\x03b1\x1f600"] True
higher = S.SourceContract
  (T.XForall (T.XTyVar 17) (T.XBotKind (T.KArrow T.Star T.Star))
    (T.XApply (T.XVar (T.XTyVar 17)) (T.XCon "Int" []))) [] False
changed = S.SourceContract (T.XCon "Bool" []) ["Ord Bool", "Eq Bool"] True
bindings = [(slot "alpha",plain),(slot "beta",bound),(slot "gamma",higher),(slot "delta",plain)]
datatypes =
  [ T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
  , T.DataDeclK "Higher" [("f",T.KArrow T.Star T.Star)]
      [T.ConstructorDecl "Higher" [T.Application (T.Parameter "f") (T.Applied "Int" [])]]
  , T.DataDecl "Unicode\x03a9" [] [T.ConstructorDecl "Unicode\x03a9" []]
  ]
changedData = T.DataDecl "Box" [] [T.ConstructorDecl "Box" [T.Applied "Bool" []]]
empty = Q.Session "unused-no-files" "encode-reuse-fixture-v1" "" M.empty M.empty M.empty

nodeSnapshot node =
  (B.unpack (Q.nodeKey node), B.unpack (Q.nodeHash node),
   [(B.unpack k,B.unpack h) | (k,h) <- Q.nodeReads node],
   case Q.nodePayload node of T.Nothing -> Nothing; T.Just h -> Just (B.unpack h))
nodesSnapshot = map nodeSnapshot . M.elems
byteSnapshot bytes = do
  count <- P.lengthByteArray bytes
  forM [0..count-1] $ \i -> do
    byte <- P.readByteArray bytes i
    pure (fromIntegral byte :: Int)
sessionSnapshot (Q.Session _ configuration generation old current pending) = do
  payloads <- forM (M.toList pending) $ \(digest,bytes) -> do
    raw <- byteSnapshot bytes
    pure (B.unpack digest,raw)
  pure (B.unpack configuration,B.unpack generation,nodesSnapshot old,nodesSnapshot current,payloads)
forceString [] = ()
forceString (x:xs) = x `seq` forceString xs
renderSession session = do
  snapshot <- sessionSnapshot session
  let rendered = show snapshot
  evaluate (forceString rendered)
  pure rendered
sameSessions label expected actual = do
  a <- renderSession expected
  b <- renderSession actual
  need (label ++ ": exact session/ordered-read/payload-byte mismatch") (a == b)

runBatch bindingAction datatypeAction bs ds initial = do
  first <- bindingAction scope bs initial
  case first of
    T.Left e -> pure (T.Left e)
    T.Right next -> datatypeAction ds next
oldBatch = runBatch oldBindings oldDatatypes
newBatch = runBatch C.recordInitialBindings C.recordDatatypes
compareBatch label bs ds initial = do
  a <- oldBatch bs ds initial >>= right (label ++ " frozen protocol")
  b <- newBatch bs ds initial >>= right (label ++ " production")
  sameSessions label a b
  pass label
  pure b
restart (Q.Session path config _ _ current _) =
  Q.Session path config "prior-generation" current M.empty M.empty
withOld (Q.Session path config generation _ current pending) old =
  Q.Session path config generation old current pending

-- Failure comparison observes the complete successful session, not merely
-- Either WHNF. These are host partial-value controls, not source programs.
capture action = do
  result <- try (do
    answer <- action
    case answer of
      T.Left message -> do
        let text = "Left:" ++ B.unpack message
        evaluate (forceString text)
        pure text
      T.Right session -> renderSession session) :: IO (Either SomeException String)
  pure (case result of Left e -> "Exception:" ++ displayException e; Right text -> text)
sameFailure label marker old new = do
  a <- capture old
  b <- capture new
  need (label ++ ": failure or ordering changed") (a == b && marker `isInfixOf` a)
  pass label

pureTests = do
  _ <- compareBatch "empty" [] [] empty
  _ <- compareBatch "singleton-binding" (take 1 bindings) [] empty
  _ <- compareBatch "contracts-kinds-classes-protection-and-shared-values" bindings [] empty
  _ <- compareBatch "datatypes-unicode-and-higher-kinds" [] datatypes empty
  cold <- compareBatch "mixed-ordered-batch" bindings datatypes empty
  _ <- compareBatch "same-key-ordered-replacement"
    [(slot "alpha",plain),(slot "alpha",changed)] [head datatypes,changedData] empty
  _ <- compareBatch "old-matching-nodes" bindings datatypes (restart cold)
  _ <- compareBatch "old-authority-changed"
    [(slot "alpha",changed)] [changedData] (restart cold)
  _ <- compareBatch "already-active-entries" [(slot "alpha",changed)] [changedData] cold
  let wanted = C.bindingKey scope (slot "alpha")
      originalNode = case M.lookup P.compareString wanted (Q.currentNodes cold) of
        T.Just n -> n
        T.Nothing -> errorWithoutStackTrace "fixture missing original node"
      malformedOld = Q.QueryNode wanted (Q.nodeHash originalNode)
        [("unexpected-read",B.literal (replicate 64 '1'))] T.Nothing
      unrelated = Q.QueryNode "unrelated-old" (B.literal (replicate 64 '2')) [] T.Nothing
      oldMap = M.fromList P.compareString [(wanted,malformedOld),("unrelated-old",unrelated)]
  _ <- compareBatch "old-row-fields-not-hash-only" (take 1 bindings) [] (withOld empty oldMap)

  let dependent = Q.key "Binding" "dependent"
      leaf = case M.lookup P.compareString wanted (Q.currentNodes cold) of
        T.Just n -> n
        T.Nothing -> errorWithoutStackTrace "fixture missing recorded node"
  (_,withDependent) <- Q.record dependent [Q.edge leaf,Q.edge leaf] False (W.VInt 1) cold
    >>= right "dependent record"
  forM_ [("dependency-unchanged",take 1 bindings,True),
         ("dependency-changed",[(slot "alpha",changed)],False),
         ("dependency-deleted",[],False)] $ \(label,bs,expected) -> do
    a <- oldBatch bs [] (restart withDependent) >>= right label
    b <- newBatch bs [] (restart withDependent) >>= right label
    let (oldResult,oldSession) = Q.validate dependent a
        (newResult,newSession) = Q.validate dependent b
        present value = case value of T.Nothing -> False; T.Just _ -> True
    need (label ++ ": invalidation result")
      (present oldResult == expected && present newResult == expected)
    sameSessions label oldSession newSession
    pass label

  let badType = S.SourceContract (errorWithoutStackTrace "fixture:first-type")
        (errorWithoutStackTrace "fixture:later-classes") False
      badValues = (slot "alpha",badType) : errorWithoutStackTrace "fixture:later-list"
      badDecls = errorWithoutStackTrace "fixture:first-declaration" :
        errorWithoutStackTrace "fixture:later-declarations"
  sameFailure "partial-contract-first-before-later-fields" "fixture:first-type"
    (oldBindings scope badValues empty) (C.recordInitialBindings scope badValues empty)
  sameFailure "partial-declaration-first-before-tail" "fixture:first-declaration"
    (oldDatatypes badDecls empty) (C.recordDatatypes badDecls empty)
  sameFailure "value-before-session" "fixture:first-type"
    (oldBindings scope badValues (errorWithoutStackTrace "fixture:session"))
    (C.recordInitialBindings scope badValues (errorWithoutStackTrace "fixture:session"))
  sameFailure "successful-value-then-session" "fixture:session"
    (oldBindings scope (take 1 bindings) (errorWithoutStackTrace "fixture:session"))
    (C.recordInitialBindings scope (take 1 bindings) (errorWithoutStackTrace "fixture:session"))
  sameFailure "empty-does-not-force-scope" "fixture:session"
    (oldBindings (errorWithoutStackTrace "fixture:scope") [] (errorWithoutStackTrace "fixture:session"))
    (C.recordInitialBindings (errorWithoutStackTrace "fixture:scope") [] (errorWithoutStackTrace "fixture:session"))
  putStrLn "SUMMARY\tpure\t18"

-- Real publisher/reopen controls, never invoked by the source author. A fresh
-- explicit root is mandatory; no existing directory is removed or reused.
filesUnder root = visit ""
  where
    visit relative = do
      namesHere <- sort <$> listDirectory (root </> relative)
      fmap concat $ forM namesHere $ \name -> do
        let child = relative </> name
        directory <- doesDirectoryExist (root </> child)
        if directory then visit child else do
          bytes <- BS.readFile (root </> child)
          pure [(child,bytes)]
samePublished label root = do
  a <- filesUnder (root </> "frozen")
  b <- filesUnder (root </> "production")
  need (label ++ ": exact file set or bytes changed") (a == b)
publicationTests root = do
  exists <- doesPathExist root
  need "publication requires a new root" (not exists)
  failpoint <- lookupEnv "MLF_QUERY_FAILPOINT"
  need "publication requires no inherited query failpoint" (failpoint == Nothing)
  createDirectory root
  forM_ [("cold",bindings,datatypes,True),
         ("warm",bindings,datatypes,False),
         ("changed",[(slot "alpha",changed)], [changedData],True),
         ("deleted",[],[],True)] $ \(label,bs,ds,expectedChanged) -> do
    beforeOld <- Q.begin (B.literal (root </> "frozen")) "encode-reuse-fixture-v1" >>= right label
    beforeNew <- Q.begin (B.literal (root </> "production")) "encode-reuse-fixture-v1" >>= right label
    sameSessions (label ++ " reopened") beforeOld beforeNew
    old <- oldBatch bs ds beforeOld >>= right label
    new <- newBatch bs ds beforeNew >>= right label
    sameSessions label old new
    oldChanged <- Q.publish old >>= right label
    newChanged <- Q.publish new >>= right label
    need (label ++ ": publication switch result")
      (oldChanged == expectedChanged && newChanged == expectedChanged)
    samePublished label root
    pass ("publication-" ++ label)
  putStrLn "SUMMARY\tpublication\t4"

main = do
  args <- getArgs
  case args of
    ["pure"] -> pureTests
    ["publication",root] -> publicationTests root
    _ -> errorWithoutStackTrace "usage: encode-input-reuse pure | publication FRESH_ROOT"
