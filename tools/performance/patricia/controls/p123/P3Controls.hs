{-# LANGUAGE OverloadedStrings #-}
module P3Controls where
import Prelude
import Control.Exception (SomeException, bracket, evaluate, try, displayException)
import Control.Monad (forM_, unless)
import Data.IORef
import Data.Char (ord)
import Data.List (foldl')
import System.Directory (getTemporaryDirectory, removeFile)
import System.IO (openBinaryTempFile, hClose)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Data as D
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.Separate as S
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.Bitstream as Wire
import qualified Bootstrap.CrateQuery as Q
import qualified FingerprintReference as Reference
import qualified Bootstrap.SourceInference as Source
import qualified Bootstrap.InferenceUnit as I
import qualified FrozenPrefix as Old
import qualified FrozenInferenceUnit as OldI

text :: P.String -> IO String
text value = do
  let cs = P.textToChars value
  _ <- evaluate (foldl' (\n c -> n + ord c) (0::Int) cs)
  pure cs

check :: IORef Int -> String -> P.String -> P.String -> IO ()
check count label old new = do
  a <- text old; b <- text new
  unless (a==b) (error ("mismatch: " ++ label ++ "\n" ++ take 500 a ++ "\n" ++ take 500 b))
  modifyIORef' count (+1)

outcome :: P.String -> IO (Either String String)
outcome value = do
  result <- try (text value)
  pure $ case result of
    Left e -> Left (takeWhile (/='\n') (displayException (e::SomeException)))
    Right a -> Right a

checkOutcome count label old new = do
  a <- outcome old; b <- outcome new
  unless (a==b) (error ("outcome mismatch: " ++ label ++ show (a,b)))
  modifyIORef' count (+1)

renderObject result = case result of
  T.Left err -> P.concatString "Left:" err
  T.Right obj -> S.encodeObject obj

box = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
changed = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Function (T.Parameter "a") (T.Parameter "a")]]
kinded = T.DataDeclK "Box" [("a",T.Star)] [T.ConstructorDecl "Box" [T.Parameter "a"]]
complex = T.DataDeclK "Higher" [("f",T.KArrow T.Star T.Star)]
  [T.ConstructorDecl "Higher" [T.Quantified "a" T.Star (T.Application (T.Parameter "f") (T.Parameter "a"))]]
unicode = T.DataDecl "汉🚀" [] [T.ConstructorDecl "É\0\n" []]
declarations = [box,changed,kinded,complex,unicode,T.DataDecl "Empty" [] []]
contexts = [[],[box],[changed],[kinded],[complex],[unicode],declarations,reverse declarations,[box,box]]
bodies = [T.XIntTerm 1,T.XIntTerm (-123456789012345678901234567890),T.XStringTerm "汉\0é🚀\n\x10ffff",T.XWithData [changed] (T.XBoolTerm True)]
classes = [T.SClassDecl "C" [("a",T.Star)] [] [("m",T.STVar "a")]]
-- Interface pretty-printing must continue to ignore method implementations.
instances = [("dict",T.SInstanceDecl [] [] "C" [T.SCon "Int" []] [("m",error "unused instance body")])]
iface ds withClasses = S.UnitInterface "Unit" [("Dependency","123-456")] [] ds
  (if withClasses then classes else []) (if withClasses then instances else []) [("value",T.XCon "Int" [])] "object-digest"

right result = case result of
  T.Left message -> fail (P.textToChars message)
  T.Right value -> pure value

-- Inspect the lowered writer's raw metadata and term before semantic admission.
readWrittenObject path key object = do
  _ <- Q.writeLoweredCache path key object >>= right
  bytes <- Storage.readRaw path >>= right
  graph <- Wire.decodeGraph Wire.defaultLimits 2 bytes >>= right
  case Wire.graphRoots graph of
    [root] -> do
      node <- right (Wire.lookupGraphNode graph root)
      case node of
        Wire.GNode 300 [saved, payload] -> do
          stored <- right (Wire.lookupGraphNode graph saved)
          case stored of
            Wire.GText actual | actual == key -> right (Structure.fromGraphRawUnitObject graph payload)
            _ -> fail "lowered record key mismatch"
        _ -> fail "expected a lowered query record"
    _ -> fail "expected one lowered query root"

checkBinaryObjects count = do
  directory <- getTemporaryDirectory
  let temporary = do
        (path, handle) <- openBinaryTempFile directory "p3-query.mlfq"
        hClose handle
        pure path
  bracket temporary removeFile $ \path ->
    forM_ contexts $ \ds -> forM_ [False,True] $ \withClasses -> do
      let header=iface ds withClasses
          key=Q.queryKey "crate" "compiler" [] [] ds
      forM_ [ds,[changed,unicode]] $ \bodyContext -> do
        let object=S.UnitObject header (T.XWithData bodyContext (T.XIntTerm 23))
        decoded <- readWrittenObject (P.textFromChars path) key object
        check count "raw binary metadata" (Old.encodeInterface header) (S.encodeInterface (S.objectInterface decoded))
        check count "raw binary object" (Old.encodeObject object) (S.encodeObject decoded)

-- The empty preparation has no lowered/original members, scopes, or contracts.
emptyKey context = S.pack ["MLF-SOURCE-CRATE-QUERY-7", "crate", "compiler", "", "", context,
  S.pack ["prepared-source-group", "", "", "", S.pack ["unchanged-source-or-support"], ""], "", ""]

main = do
  count <- newIORef 0
  let prepared=Source.PreparedGroup [] [] [] M.empty [] T.Nothing []
  forM_ [[],[box],[changed],declarations,reverse declarations] $ \inventory -> do
    let pool=S.prepareDatatypeEncodings inventory
        queryPool=Q.prepareSourceEncodings inventory
    forM_ contexts $ \ds -> do
      let expected=Q.encodeSourceDatatypes ds
          pooled=Q.encodeSourceDatatypesWithPool queryPool ds
      check count "canonical source datatype context" expected pooled
      check count "complete source key" (emptyKey expected)
        (Q.sourceQueryKeyWithContext "crate" "compiler" prepared M.empty pooled)
      forM_ bodies $ \body -> do
        let term=T.XWithData ds body
            digest=Reference.fingerprint (P.textToChars (Pretty.prettyTerm term))
        check count "pooled payload digest" (P.textFromChars digest) (S.fingerprintTermWithDatatypes pool term)
  checkBinaryObjects count
  let unused=T.DataDecl "Unused" [] (error "unused declaration constructors")
      lazyPool=S.prepareDatatypeEncodings [unused,box]
      plain=T.XIntTerm 4
      bodyless=T.XWithData [] plain
  check count "unused encoding entry" (S.fingerprint (Pretty.prettyTerm (T.XWithData [box] plain)))
    (S.fingerprintTermWithDatatypes lazyPool (T.XWithData [box] plain))
  check count "unused query encoding entry" (Q.encodeSourceDatatypes [box])
    (Q.encodeSourceDatatypesWithPool (Q.prepareSourceEncodings [unused,box]) [box])
  check count "noncontext term does not demand pool" (S.fingerprint (Pretty.prettyTerm plain))
    (S.fingerprintTermWithDatatypes (error "unused pool") plain)
  check count "empty context does not demand pool" (S.fingerprint (Pretty.prettyTerm bodyless))
    (S.fingerprintTermWithDatatypes (error "unused pool") bodyless)
  let iNoHash=S.UnitInterface "Unit" [] [] [box] [] [] [] (error "unused object hash")
  check count "interface hash ignores object hash" (Old.interfaceFingerprint iNoHash)
    (S.interfaceFingerprint iNoHash)
  forM_ [T.DataDecl "Box" [] (error "actual constructors"),T.DataDecl "New" [] (error "actual constructors")] $ \bad -> do
    let term=T.XWithData [bad] plain
    checkOutcome count "actual malformed declaration" (S.fingerprint (Pretty.prettyTerm term))
      (S.fingerprintTermWithDatatypes lazyPool term)
  -- Empty group must reject before looking at any pool or other arguments.
  check count "empty group error order"
    (renderObject (OldI.compileLoweredGroup (error "name") (error "imports") (error "data") []))
    (renderObject (I.compileLoweredGroupWithDatatypes (error "pool") (error "name") (error "imports") (error "data") []))
  forM_ [[],[box]] $ \ds -> do
    let members=[("value",T.Nothing,T.SIntLit 2)]
    check count "full inference result"
      (renderObject (OldI.compileLoweredGroup "Group" [] ds members))
      (renderObject (I.compileLoweredGroupWithDatatypes (S.prepareDatatypeEncodings [changed,box]) "Group" [] ds members))
    let bad=[("value",T.Nothing,T.SVar "missing")]
    check count "full inference error"
      (renderObject (OldI.compileLoweredGroup "Group" [] ds bad))
      (renderObject (I.compileLoweredGroupWithDatatypes (S.prepareDatatypeEncodings [changed,box]) "Group" [] ds bad))
  forM_ ([(-1,-1),(-123456789012345678901234567890,3),(0,1),(9,-23),(2147483650,2147483640)] ++ [(minBound,maxBound),(maxBound,minBound),(maxBound,maxBound),(0,maxBound),(maxBound,0),(2^62,1),(1,2^62)]) $ \seed -> do
    let entry=S.datatypeEncoding box
        actual=S.appendDatatypeEncoding seed entry
        expected=Reference.state seed (P.textToChars (D.prettyDeclaration box) ++ "\n")
    unless (actual==expected) (error "signed datatype state mismatch")
    modifyIORef' count (+1)
  emptyGroups <- Q.runSourceGroups (error "crate") (error "compiler") (error "directory")
    (error "inventory") (error "plan") [] (error "contracts") [] 0 0 []
  case emptyGroups of
    T.Left _ -> error "empty source group loop unexpectedly failed"
    T.Right _ -> modifyIORef' count (+1)
  emptyOptimized <- Q.runSourceGroupsWithEncodings (T.Just (error "unused encodings"))
    (error "crate") (error "compiler") (error "directory") (error "inventory")
    (error "plan") [] (error "contracts") [] 0 0 []
  case emptyOptimized of
    T.Left _ -> error "empty optimized group loop unexpectedly failed"
    T.Right _ -> modifyIORef' count (+1)
  n <- readIORef count
  putStrLn ("{\"complete\":true,\"differential_controls\":"++show n++"}")
