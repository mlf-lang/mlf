{-# LANGUAGE OverloadedStrings #-}
-- Frozen schema-conformance fixture. Generated from the published contract,
-- not from target to/from implementations or observed successful outputs.
module Main where
import Prelude
import Control.Monad (unless, forM_, zipWithM_)
import Control.Exception (try, evaluate, bracket)
import System.Mem.StableName (makeStableName, eqStableName)
import System.Environment (getArgs, getExecutablePath)
import System.Directory (doesPathExist, createDirectory, renameFile)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Module as M
import qualified Bootstrap.Separate as U
import qualified Bootstrap.ArtifactStructure as A
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.InferenceUnit as InferenceUnit
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.CrateSession as Session
import qualified Bootstrap.CrateArtifact as CrateArtifact
import qualified Package.Distribution as Distribution
import qualified Package.Release as Release
import qualified Package.Json as Json
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

need label value = unless value (error label)
expect label value = case value of T.Left e -> error (label ++ ": " ++ B.unpack e); T.Right v -> pure v
reject label value = case value of T.Left _ -> pure (); T.Right _ -> error ("accepted " ++ label)
same (W.VInt a) (W.VInt b) = a == b
same (W.VBits a) (W.VBits b) = a == b
same (W.VText a) (W.VText b) = a == b
same (W.VNode a xs) (W.VNode b ys) = a == b && length xs == length ys && and (zipWith same xs ys)
same _ _ = False
sameValues xs ys = length xs == length ys && and (zipWith same xs ys)
sampleString n = B.literal ("field-" ++ show n ++ "-α😀\NUL")
expectString n = W.VText (sampleString n)
sampleInt n = fromIntegral (negate (3*n+7)) :: P.Int
expectInt n = W.VInt (sampleInt n)
sampleDouble n = P.doubleFromBits (fromIntegral n)
expectDouble n = W.VBits (fromIntegral n)
sampleBool n = odd n
expectBool n = W.VNode (if odd n then 7 else 6) []
sampleList f n = [f (3*n+1), f (3*n+2), f (3*n+1)]
expectList f n = W.VNode 1 (sampleList f n)
sampleMaybe f n = if even n then T.Nothing else T.Just (f n)
expectMaybe f n = if even n then W.VNode 4 [] else W.VNode 5 [f n]
samplePrimitive _ = T.PByteArrayDigest
expectPrimitive _ = W.VNode 32 [W.VInt 131]
sampleInterfaceInstance n = T.SInstanceDecl [(sampleString n,T.Star)] [] (sampleString (n+1)) [T.STVar (sampleString (n+2))] [(sampleString (n+3),T.SIntLit (sampleInt n))]
expectInterfaceInstance n = W.VNode 173 [W.VNode 1 [W.VNode 2 [expectString n,W.VNode 10 []]],W.VNode 1 [],expectString (n+1),W.VNode 1 [W.VNode 100 [expectString (n+2)]],W.VNode 1 [expectString (n+3)]]
sampleRawUnitObject n = U.UnitObject (sampleUnitInterface n) (sampleXTerm (n+1))
expectRawUnitObject n = W.VNode 241 [expectUnitInterface n,expectXTerm (n+1)]

checkCase label encode decode value expected = do
  need (label ++ " exact published tag/ordered fields") (same (encode value) expected)
  restored <- expect (label ++ " decode explicit expected shape") (decode expected)
  need (label ++ " typed roundtrip") (same (encode restored) expected)
  reject (label ++ " wrong leaf kind") (decode (W.VBits 0))
  reject (label ++ " unknown tag") (decode (W.VNode 2147483647 []))
  case expected of
    W.VNode tag children -> do
      reject (label ++ " extra field") (decode (W.VNode tag (children ++ [W.VInt 0])))
      case children of
        [] -> pure ()
        _:rest -> do
          reject (label ++ " missing field") (decode (W.VNode tag rest))
          reject (label ++ " malformed recursive field") (decode (W.VNode tag (W.VNode 2147483647 []:rest)))
    _ -> pure ()
  pure expected

byteList a = do
  n <- P.lengthByteArray a
  mapM (P.readByteArray a) [0..n-1]
fromBytes xs = do
  array <- P.newByteArray (fromIntegral (length xs)) 0
  forM_ (zip [0..] xs) (\(i,x) -> P.writeByteArray array i x)
  pure array
saveBytes path bytes = do
  diagnostic <- P.writeByteFileOrError (B.literal path) bytes
  need ("raw binary write " ++ path ++ ": " ++ B.unpack diagnostic) (diagnostic == "")
wireCheck path roots = do
  bytes <- W.encode W.defaultLimits 7 roots >>= expect "wire encode all constructors"
  decoded <- W.decode W.defaultLimits 7 bytes >>= expect "wire decode all constructors"
  need "whole typed corpus preserves every root and order" (sameValues decoded roots)
  bytes2 <- W.encode W.defaultLimits 7 decoded >>= expect "deterministic reencode"
  a <- byteList bytes; b <- byteList bytes2
  need "deterministic byte-for-byte encoding" (a == b)
  saveBytes path bytes

sampleKind n = (T.Star )
expectKind n = W.VNode 10 []
sampleFlag n = (T.Flexible )
expectFlag n = W.VNode 12 []
sampleField n = (T.Parameter (sampleString ((n) * 7 + 1)))
expectField n = W.VNode 20 [expectString ((n) * 7 + 1)]
sampleConstructorDecl n = (T.ConstructorDecl (sampleString ((n) * 7 + 1)) (sampleList (\z -> sampleField (z)) ((n) * 7 + 2)))
expectConstructorDecl n = W.VNode 25 [expectString ((n) * 7 + 1), expectList (\z -> expectField (z)) ((n) * 7 + 2)]
sampleDataDecl n = (T.DataDecl (sampleString ((n) * 7 + 1)) (sampleList (\z -> sampleString (z)) ((n) * 7 + 2)) (sampleList (\z -> sampleConstructorDecl (z)) ((n) * 7 + 3)))
expectDataDecl n = W.VNode 26 [expectString ((n) * 7 + 1), expectList (\z -> expectString (z)) ((n) * 7 + 2), expectList (\z -> expectConstructorDecl (z)) ((n) * 7 + 3)]
sampleXTyVar n = (T.XTyVar (sampleInt ((n) * 7 + 1)))
expectXTyVar n = W.VNode 30 [expectInt ((n) * 7 + 1)]
sampleXName n = (T.XName (sampleInt ((n) * 7 + 1)) (sampleString ((n) * 7 + 2)))
expectXName n = W.VNode 31 [expectInt ((n) * 7 + 1), expectString ((n) * 7 + 2)]
sampleXType n = (T.XVar (sampleXTyVar ((n) * 7 + 1)))
expectXType n = W.VNode 40 [expectXTyVar ((n) * 7 + 1)]
sampleXComputation n = (T.XRefl )
expectXComputation n = W.VNode 50 []
sampleXTerm n = (T.XVarTerm (sampleXName ((n) * 7 + 1)))
expectXTerm n = W.VNode 70 [expectXName ((n) * 7 + 1)]
sampleXPattern n = (T.XConstructorPattern (sampleString ((n) * 7 + 1)) (sampleList (\z -> sampleMaybe (\z -> sampleXName (z)) (z)) ((n) * 7 + 2)))
expectXPattern n = W.VNode 90 [expectString ((n) * 7 + 1), expectList (\z -> expectMaybe (\z -> expectXName (z)) (z)) ((n) * 7 + 2)]
sampleXAlternative n = (T.XAlternative (sampleXPattern ((n) * 7 + 1)) (sampleXTerm ((n) * 7 + 2)))
expectXAlternative n = W.VNode 92 [expectXPattern ((n) * 7 + 1), expectXTerm ((n) * 7 + 2)]
sampleSType n = (T.STVar (sampleString ((n) * 7 + 1)))
expectSType n = W.VNode 100 [expectString ((n) * 7 + 1)]
sampleSAnnotation n = (T.SAnnotation (sampleList (\z -> sampleString (z)) ((n) * 7 + 1)) (sampleSType ((n) * 7 + 2)))
expectSAnnotation n = W.VNode 110 [expectList (\z -> expectString (z)) ((n) * 7 + 1), expectSType ((n) * 7 + 2)]
sampleRecursiveMode n = (T.InferRecursive )
expectRecursiveMode n = W.VNode 111 []
sampleSourceSpan n = (T.SourceSpan (sampleString ((n) * 7 + 1)) (sampleString ((n) * 7 + 2)) (sampleString ((n) * 7 + 3)) (sampleInt ((n) * 7 + 4)) (sampleInt ((n) * 7 + 5)) (sampleInt ((n) * 7 + 6)) (sampleInt ((n) * 7 + 7)))
expectSourceSpan n = W.VNode 113 [expectString ((n) * 7 + 1), expectString ((n) * 7 + 2), expectString ((n) * 7 + 3), expectInt ((n) * 7 + 4), expectInt ((n) * 7 + 5), expectInt ((n) * 7 + 6), expectInt ((n) * 7 + 7)]
sampleSourceString n = (T.ScalarString (sampleString ((n) * 7 + 1)))
expectSourceString n = W.VNode 114 [expectString ((n) * 7 + 1)]
sampleEvidenceRole n = (T.GivenEvidence )
expectEvidenceRole n = W.VNode 116 []
sampleSExpr n = (T.SVar (sampleString ((n) * 7 + 1)))
expectSExpr n = W.VNode 120 [expectString ((n) * 7 + 1)]
sampleSPattern n = (T.SConstructorPattern (sampleString ((n) * 7 + 1)) (sampleList (\z -> sampleMaybe (\z -> sampleString (z)) (z)) ((n) * 7 + 2)))
expectSPattern n = W.VNode 150 [expectString ((n) * 7 + 1), expectList (\z -> expectMaybe (\z -> expectString (z)) (z)) ((n) * 7 + 2)]
sampleSAlternative n = (T.SAlternative (sampleSPattern ((n) * 7 + 1)) (sampleSExpr ((n) * 7 + 2)))
expectSAlternative n = W.VNode 160 [expectSPattern ((n) * 7 + 1), expectSExpr ((n) * 7 + 2)]
sampleSStatement n = (T.SDoBind (sampleSPattern ((n) * 7 + 1)) (sampleSExpr ((n) * 7 + 2)))
expectSStatement n = W.VNode 161 [expectSPattern ((n) * 7 + 1), expectSExpr ((n) * 7 + 2)]
sampleSPredicate n = (T.SPredicate (sampleString ((n) * 7 + 1)) (sampleList (\z -> sampleSType (z)) ((n) * 7 + 2)))
expectSPredicate n = W.VNode 170 [expectString ((n) * 7 + 1), expectList (\z -> expectSType (z)) ((n) * 7 + 2)]
sampleSClassDecl n = (T.SClassDecl (sampleString ((n) * 7 + 1)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleKind ((z) * 5 + 2))) ((n) * 7 + 2)) (sampleList (\z -> sampleSPredicate (z)) ((n) * 7 + 3)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleSType ((z) * 5 + 2))) ((n) * 7 + 4)))
expectSClassDecl n = W.VNode 171 [expectString ((n) * 7 + 1), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectKind ((z) * 5 + 2)]) ((n) * 7 + 2), expectList (\z -> expectSPredicate (z)) ((n) * 7 + 3), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectSType ((z) * 5 + 2)]) ((n) * 7 + 4)]
sampleSInstanceDecl n = (T.SInstanceDecl (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleKind ((z) * 5 + 2))) ((n) * 7 + 1)) (sampleList (\z -> sampleSPredicate (z)) ((n) * 7 + 2)) (sampleString ((n) * 7 + 3)) (sampleList (\z -> sampleSType (z)) ((n) * 7 + 4)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleSExpr ((z) * 5 + 2))) ((n) * 7 + 5)))
expectSInstanceDecl n = W.VNode 172 [expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectKind ((z) * 5 + 2)]) ((n) * 7 + 1), expectList (\z -> expectSPredicate (z)) ((n) * 7 + 2), expectString ((n) * 7 + 3), expectList (\z -> expectSType (z)) ((n) * 7 + 4), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectSExpr ((z) * 5 + 2)]) ((n) * 7 + 5)]
sampleRole n = (M.Value )
expectRole n = W.VNode 180 []
sampleEntity n = (M.Entity (sampleString ((n) * 7 + 1)) (sampleString ((n) * 7 + 2)) (sampleRole ((n) * 7 + 3)))
expectEntity n = W.VNode 189 [expectString ((n) * 7 + 1), expectString ((n) * 7 + 2), expectRole ((n) * 7 + 3)]
sampleSourceSyntax n = (T.LegacyEmlfV1 )
expectSourceSyntax n = W.VNode 200 []
sampleSelection n = (T.Everything )
expectSelection n = W.VNode 203 []
sampleExport n = (T.ExportValue (sampleString ((n) * 7 + 1)))
expectExport n = W.VNode 206 [expectString ((n) * 7 + 1)]
sampleMembers n = (T.Abstract )
expectMembers n = W.VNode 209 []
sampleImport n = (T.Import (sampleString ((n) * 7 + 1)) (sampleBool ((n) * 7 + 2)) (sampleMaybe (\z -> sampleString (z)) ((n) * 7 + 3)) (sampleSelection ((n) * 7 + 4)))
expectImport n = W.VNode 212 [expectString ((n) * 7 + 1), expectBool ((n) * 7 + 2), expectMaybe (\z -> expectString (z)) ((n) * 7 + 3), expectSelection ((n) * 7 + 4)]
sampleSourceModule n = (T.SourceModule (sampleString ((n) * 7 + 1)) (sampleMaybe (\z -> sampleString (z)) ((n) * 7 + 2)) (sampleMaybe (\z -> sampleList (\z -> sampleExport (z)) (z)) ((n) * 7 + 3)) (sampleList (\z -> sampleImport (z)) ((n) * 7 + 4)) (sampleList (\z -> sampleDataDecl (z)) ((n) * 7 + 5)) (sampleList (\z -> sampleSClassDecl (z)) ((n) * 7 + 6)) (sampleList (\z -> sampleSInstanceDecl (z)) ((n) * 7 + 7)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleMaybe (\z -> sampleSAnnotation (z)) ((z) * 5 + 2), sampleSExpr ((z) * 5 + 3))) ((n) * 7 + 8)) (sampleMaybe (\z -> sampleSExpr (z)) ((n) * 7 + 9)) (sampleSourceSyntax ((n) * 7 + 10)))
expectSourceModule n = W.VNode 213 [expectString ((n) * 7 + 1), expectMaybe (\z -> expectString (z)) ((n) * 7 + 2), expectMaybe (\z -> expectList (\z -> expectExport (z)) (z)) ((n) * 7 + 3), expectList (\z -> expectImport (z)) ((n) * 7 + 4), expectList (\z -> expectDataDecl (z)) ((n) * 7 + 5), expectList (\z -> expectSClassDecl (z)) ((n) * 7 + 6), expectList (\z -> expectSInstanceDecl (z)) ((n) * 7 + 7), expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectMaybe (\z -> expectSAnnotation (z)) ((z) * 5 + 2), expectSExpr ((z) * 5 + 3)]) ((n) * 7 + 8), expectMaybe (\z -> expectSExpr (z)) ((n) * 7 + 9), expectSourceSyntax ((n) * 7 + 10)]
sampleSProgram n = (T.SProgram (sampleList (\z -> sampleDataDecl (z)) ((n) * 7 + 1)) (sampleSExpr ((n) * 7 + 2)))
expectSProgram n = W.VNode 214 [expectList (\z -> expectDataDecl (z)) ((n) * 7 + 1), expectSExpr ((n) * 7 + 2)]
sampleUnitInterface n = (U.UnitInterface (sampleString ((n) * 7 + 1)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleString ((z) * 5 + 2))) ((n) * 7 + 2)) (sampleList (\z -> sampleEntity (z)) ((n) * 7 + 3)) (sampleList (\z -> sampleDataDecl (z)) ((n) * 7 + 4)) (sampleList (\z -> sampleSClassDecl (z)) ((n) * 7 + 5)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleInterfaceInstance ((z) * 5 + 2))) ((n) * 7 + 6)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleXType ((z) * 5 + 2))) ((n) * 7 + 7)) (sampleString ((n) * 7 + 8)))
expectUnitInterface n = W.VNode 240 [expectString ((n) * 7 + 1), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectString ((z) * 5 + 2)]) ((n) * 7 + 2), expectList (\z -> expectEntity (z)) ((n) * 7 + 3), expectList (\z -> expectDataDecl (z)) ((n) * 7 + 4), expectList (\z -> expectSClassDecl (z)) ((n) * 7 + 5), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectInterfaceInstance ((z) * 5 + 2)]) ((n) * 7 + 6), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectXType ((z) * 5 + 2)]) ((n) * 7 + 7), expectString ((n) * 7 + 8)]
sampleCrateInterfaceFields n = (A.CrateInterfaceFields (sampleString ((n) * 7 + 1)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleString ((z) * 5 + 2), sampleString ((z) * 5 + 3))) ((n) * 7 + 2)) (sampleList (\z -> sampleString (z)) ((n) * 7 + 3)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleList (\z -> sampleEntity (z)) ((z) * 5 + 2))) ((n) * 7 + 4)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleList (\z -> sampleString (z)) ((z) * 5 + 2))) ((n) * 7 + 5)) (sampleList (\z -> sampleDataDecl (z)) ((n) * 7 + 6)) (sampleList (\z -> sampleSClassDecl (z)) ((n) * 7 + 7)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleInterfaceInstance ((z) * 5 + 2))) ((n) * 7 + 8)) (sampleList (\z -> sampleDataDecl (z)) ((n) * 7 + 9)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleXType ((z) * 5 + 2))) ((n) * 7 + 10)) (sampleString ((n) * 7 + 11)) (sampleString ((n) * 7 + 12)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleBool ((z) * 5 + 2))) ((n) * 7 + 13)))
expectCrateInterfaceFields n = W.VNode 242 [expectString ((n) * 7 + 1), expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectString ((z) * 5 + 2), expectString ((z) * 5 + 3)]) ((n) * 7 + 2), expectList (\z -> expectString (z)) ((n) * 7 + 3), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectList (\z -> expectEntity (z)) ((z) * 5 + 2)]) ((n) * 7 + 4), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectList (\z -> expectString (z)) ((z) * 5 + 2)]) ((n) * 7 + 5), expectList (\z -> expectDataDecl (z)) ((n) * 7 + 6), expectList (\z -> expectSClassDecl (z)) ((n) * 7 + 7), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectInterfaceInstance ((z) * 5 + 2)]) ((n) * 7 + 8), expectList (\z -> expectDataDecl (z)) ((n) * 7 + 9), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectXType ((z) * 5 + 2)]) ((n) * 7 + 10), expectString ((n) * 7 + 11), expectString ((n) * 7 + 12), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectBool ((z) * 5 + 2)]) ((n) * 7 + 13)]
sampleCrateObjectFields n = (A.CrateObjectFields (sampleBool ((n) * 7 + 1)) (sampleCrateInterfaceFields ((n) * 7 + 2)) (sampleList (\z -> sampleRawUnitObject (z)) ((n) * 7 + 3)))
expectCrateObjectFields n = W.VNode 243 [expectBool ((n) * 7 + 1), expectCrateInterfaceFields ((n) * 7 + 2), expectList (\z -> expectRawUnitObject (z)) ((n) * 7 + 3)]

constructorTests = sequence [
  checkCase "Star" A.toKind A.fromKind (T.Star ) (W.VNode 10 []),
  checkCase "KArrow" A.toKind A.fromKind (T.KArrow (sampleKind ((2) * 7 + 1)) (sampleKind ((2) * 7 + 2))) (W.VNode 11 [expectKind ((2) * 7 + 1), expectKind ((2) * 7 + 2)]),
  checkCase "Flexible" A.toFlag A.fromFlag (T.Flexible ) (W.VNode 12 []),
  checkCase "Rigid" A.toFlag A.fromFlag (T.Rigid ) (W.VNode 13 []),
  checkCase "Parameter" A.toField A.fromField (T.Parameter (sampleString ((5) * 7 + 1))) (W.VNode 20 [expectString ((5) * 7 + 1)]),
  checkCase "Function" A.toField A.fromField (T.Function (sampleField ((6) * 7 + 1)) (sampleField ((6) * 7 + 2))) (W.VNode 21 [expectField ((6) * 7 + 1), expectField ((6) * 7 + 2)]),
  checkCase "Applied" A.toField A.fromField (T.Applied (sampleString ((7) * 7 + 1)) (sampleList (\z -> sampleField (z)) ((7) * 7 + 2))) (W.VNode 22 [expectString ((7) * 7 + 1), expectList (\z -> expectField (z)) ((7) * 7 + 2)]),
  checkCase "Application" A.toField A.fromField (T.Application (sampleField ((8) * 7 + 1)) (sampleField ((8) * 7 + 2))) (W.VNode 23 [expectField ((8) * 7 + 1), expectField ((8) * 7 + 2)]),
  checkCase "Quantified" A.toField A.fromField (T.Quantified (sampleString ((9) * 7 + 1)) (sampleKind ((9) * 7 + 2)) (sampleField ((9) * 7 + 3))) (W.VNode 24 [expectString ((9) * 7 + 1), expectKind ((9) * 7 + 2), expectField ((9) * 7 + 3)]),
  checkCase "ConstructorDecl" A.toConstructorDecl A.fromConstructorDecl (T.ConstructorDecl (sampleString ((10) * 7 + 1)) (sampleList (\z -> sampleField (z)) ((10) * 7 + 2))) (W.VNode 25 [expectString ((10) * 7 + 1), expectList (\z -> expectField (z)) ((10) * 7 + 2)]),
  checkCase "DataDecl" A.toDataDecl A.fromDataDecl (T.DataDecl (sampleString ((11) * 7 + 1)) (sampleList (\z -> sampleString (z)) ((11) * 7 + 2)) (sampleList (\z -> sampleConstructorDecl (z)) ((11) * 7 + 3))) (W.VNode 26 [expectString ((11) * 7 + 1), expectList (\z -> expectString (z)) ((11) * 7 + 2), expectList (\z -> expectConstructorDecl (z)) ((11) * 7 + 3)]),
  checkCase "DataDeclK" A.toDataDecl A.fromDataDecl (T.DataDeclK (sampleString ((12) * 7 + 1)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleKind ((z) * 5 + 2))) ((12) * 7 + 2)) (sampleList (\z -> sampleConstructorDecl (z)) ((12) * 7 + 3))) (W.VNode 27 [expectString ((12) * 7 + 1), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectKind ((z) * 5 + 2)]) ((12) * 7 + 2), expectList (\z -> expectConstructorDecl (z)) ((12) * 7 + 3)]),
  checkCase "XTyVar" A.toXTyVar A.fromXTyVar (T.XTyVar (sampleInt ((13) * 7 + 1))) (W.VNode 30 [expectInt ((13) * 7 + 1)]),
  checkCase "XName" A.toXName A.fromXName (T.XName (sampleInt ((14) * 7 + 1)) (sampleString ((14) * 7 + 2))) (W.VNode 31 [expectInt ((14) * 7 + 1), expectString ((14) * 7 + 2)]),
  checkCase "XVar" A.toXType A.fromXType (T.XVar (sampleXTyVar ((15) * 7 + 1))) (W.VNode 40 [expectXTyVar ((15) * 7 + 1)]),
  checkCase "XBot" A.toXType A.fromXType (T.XBot ) (W.VNode 41 []),
  checkCase "XBotKind" A.toXType A.fromXType (T.XBotKind (sampleKind ((17) * 7 + 1))) (W.VNode 42 [expectKind ((17) * 7 + 1)]),
  checkCase "XArrow" A.toXType A.fromXType (T.XArrow (sampleXType ((18) * 7 + 1)) (sampleXType ((18) * 7 + 2))) (W.VNode 43 [expectXType ((18) * 7 + 1), expectXType ((18) * 7 + 2)]),
  checkCase "XCon" A.toXType A.fromXType (T.XCon (sampleString ((19) * 7 + 1)) (sampleList (\z -> sampleXType (z)) ((19) * 7 + 2))) (W.VNode 44 [expectString ((19) * 7 + 1), expectList (\z -> expectXType (z)) ((19) * 7 + 2)]),
  checkCase "XApply" A.toXType A.fromXType (T.XApply (sampleXType ((20) * 7 + 1)) (sampleXType ((20) * 7 + 2))) (W.VNode 45 [expectXType ((20) * 7 + 1), expectXType ((20) * 7 + 2)]),
  checkCase "XForall" A.toXType A.fromXType (T.XForall (sampleXTyVar ((21) * 7 + 1)) (sampleXType ((21) * 7 + 2)) (sampleXType ((21) * 7 + 3))) (W.VNode 46 [expectXTyVar ((21) * 7 + 1), expectXType ((21) * 7 + 2), expectXType ((21) * 7 + 3)]),
  checkCase "XRefl" A.toXComputation A.fromXComputation (T.XRefl ) (W.VNode 50 []),
  checkCase "XBottom" A.toXComputation A.fromXComputation (T.XBottom (sampleXType ((23) * 7 + 1))) (W.VNode 51 [expectXType ((23) * 7 + 1)]),
  checkCase "XHyp" A.toXComputation A.fromXComputation (T.XHyp (sampleXTyVar ((24) * 7 + 1))) (W.VNode 52 [expectXTyVar ((24) * 7 + 1)]),
  checkCase "XInner" A.toXComputation A.fromXComputation (T.XInner (sampleXComputation ((25) * 7 + 1))) (W.VNode 53 [expectXComputation ((25) * 7 + 1)]),
  checkCase "XOuter" A.toXComputation A.fromXComputation (T.XOuter (sampleXTyVar ((26) * 7 + 1)) (sampleXComputation ((26) * 7 + 2))) (W.VNode 54 [expectXTyVar ((26) * 7 + 1), expectXComputation ((26) * 7 + 2)]),
  checkCase "XElim" A.toXComputation A.fromXComputation (T.XElim ) (W.VNode 55 []),
  checkCase "XIntro" A.toXComputation A.fromXComputation (T.XIntro (sampleXTyVar ((28) * 7 + 1))) (W.VNode 56 [expectXTyVar ((28) * 7 + 1)]),
  checkCase "XIntroKind" A.toXComputation A.fromXComputation (T.XIntroKind (sampleXTyVar ((29) * 7 + 1)) (sampleKind ((29) * 7 + 2))) (W.VNode 57 [expectXTyVar ((29) * 7 + 1), expectKind ((29) * 7 + 2)]),
  checkCase "XThen" A.toXComputation A.fromXComputation (T.XThen (sampleXComputation ((30) * 7 + 1)) (sampleXComputation ((30) * 7 + 2))) (W.VNode 58 [expectXComputation ((30) * 7 + 1), expectXComputation ((30) * 7 + 2)]),
  checkCase "XVarTerm" A.toXTerm A.fromXTerm (T.XVarTerm (sampleXName ((31) * 7 + 1))) (W.VNode 70 [expectXName ((31) * 7 + 1)]),
  checkCase "XAbs" A.toXTerm A.fromXTerm (T.XAbs (sampleXName ((32) * 7 + 1)) (sampleXType ((32) * 7 + 2)) (sampleXTerm ((32) * 7 + 3))) (W.VNode 71 [expectXName ((32) * 7 + 1), expectXType ((32) * 7 + 2), expectXTerm ((32) * 7 + 3)]),
  checkCase "XApp" A.toXTerm A.fromXTerm (T.XApp (sampleXTerm ((33) * 7 + 1)) (sampleXTerm ((33) * 7 + 2))) (W.VNode 72 [expectXTerm ((33) * 7 + 1), expectXTerm ((33) * 7 + 2)]),
  checkCase "XTypeAbs" A.toXTerm A.fromXTerm (T.XTypeAbs (sampleXTyVar ((34) * 7 + 1)) (sampleXType ((34) * 7 + 2)) (sampleXTerm ((34) * 7 + 3))) (W.VNode 73 [expectXTyVar ((34) * 7 + 1), expectXType ((34) * 7 + 2), expectXTerm ((34) * 7 + 3)]),
  checkCase "XTypeApp" A.toXTerm A.fromXTerm (T.XTypeApp (sampleXTerm ((35) * 7 + 1)) (sampleXComputation ((35) * 7 + 2))) (W.VNode 74 [expectXTerm ((35) * 7 + 1), expectXComputation ((35) * 7 + 2)]),
  checkCase "XLet" A.toXTerm A.fromXTerm (T.XLet (sampleXName ((36) * 7 + 1)) (sampleXTerm ((36) * 7 + 2)) (sampleXTerm ((36) * 7 + 3))) (W.VNode 75 [expectXName ((36) * 7 + 1), expectXTerm ((36) * 7 + 2), expectXTerm ((36) * 7 + 3)]),
  checkCase "XLetRec" A.toXTerm A.fromXTerm (T.XLetRec (sampleList (\z -> (sampleXName ((z) * 5 + 1), sampleXType ((z) * 5 + 2), sampleXTerm ((z) * 5 + 3))) ((37) * 7 + 1)) (sampleXTerm ((37) * 7 + 2))) (W.VNode 76 [expectList (\z -> W.VNode 3 [expectXName ((z) * 5 + 1), expectXType ((z) * 5 + 2), expectXTerm ((z) * 5 + 3)]) ((37) * 7 + 1), expectXTerm ((37) * 7 + 2)]),
  checkCase "XIntTerm" A.toXTerm A.fromXTerm (T.XIntTerm (sampleInt ((38) * 7 + 1))) (W.VNode 77 [expectInt ((38) * 7 + 1)]),
  checkCase "XDoubleTerm" A.toXTerm A.fromXTerm (T.XDoubleTerm (sampleDouble ((39) * 7 + 1))) (W.VNode 78 [expectDouble ((39) * 7 + 1)]),
  checkCase "XBoolTerm" A.toXTerm A.fromXTerm (T.XBoolTerm (sampleBool ((40) * 7 + 1))) (W.VNode 79 [expectBool ((40) * 7 + 1)]),
  checkCase "XStringTerm" A.toXTerm A.fromXTerm (T.XStringTerm (sampleString ((41) * 7 + 1))) (W.VNode 80 [expectString ((41) * 7 + 1)]),
  checkCase "XPrimitive" A.toXTerm A.fromXTerm (T.XPrimitive (samplePrimitive ((42) * 7 + 1)) (sampleList (\z -> sampleXType (z)) ((42) * 7 + 2))) (W.VNode 81 [expectPrimitive ((42) * 7 + 1), expectList (\z -> expectXType (z)) ((42) * 7 + 2)]),
  checkCase "XConstructor" A.toXTerm A.fromXTerm (T.XConstructor (sampleString ((43) * 7 + 1)) (sampleList (\z -> sampleXType (z)) ((43) * 7 + 2))) (W.VNode 82 [expectString ((43) * 7 + 1), expectList (\z -> expectXType (z)) ((43) * 7 + 2)]),
  checkCase "XCase" A.toXTerm A.fromXTerm (T.XCase (sampleXTerm ((44) * 7 + 1)) (sampleXType ((44) * 7 + 2)) (sampleList (\z -> sampleXAlternative (z)) ((44) * 7 + 3))) (W.VNode 83 [expectXTerm ((44) * 7 + 1), expectXType ((44) * 7 + 2), expectList (\z -> expectXAlternative (z)) ((44) * 7 + 3)]),
  checkCase "XWithData" A.toXTerm A.fromXTerm (T.XWithData (sampleList (\z -> sampleDataDecl (z)) ((45) * 7 + 1)) (sampleXTerm ((45) * 7 + 2))) (W.VNode 84 [expectList (\z -> expectDataDecl (z)) ((45) * 7 + 1), expectXTerm ((45) * 7 + 2)]),
  checkCase "XConstructorPattern" A.toXPattern A.fromXPattern (T.XConstructorPattern (sampleString ((46) * 7 + 1)) (sampleList (\z -> sampleMaybe (\z -> sampleXName (z)) (z)) ((46) * 7 + 2))) (W.VNode 90 [expectString ((46) * 7 + 1), expectList (\z -> expectMaybe (\z -> expectXName (z)) (z)) ((46) * 7 + 2)]),
  checkCase "XDefaultPattern" A.toXPattern A.fromXPattern (T.XDefaultPattern (sampleMaybe (\z -> sampleXName (z)) ((47) * 7 + 1))) (W.VNode 91 [expectMaybe (\z -> expectXName (z)) ((47) * 7 + 1)]),
  checkCase "XAlternative" A.toXAlternative A.fromXAlternative (T.XAlternative (sampleXPattern ((48) * 7 + 1)) (sampleXTerm ((48) * 7 + 2))) (W.VNode 92 [expectXPattern ((48) * 7 + 1), expectXTerm ((48) * 7 + 2)]),
  checkCase "STVar" A.toSType A.fromSType (T.STVar (sampleString ((49) * 7 + 1))) (W.VNode 100 [expectString ((49) * 7 + 1)]),
  checkCase "SBottom" A.toSType A.fromSType (T.SBottom ) (W.VNode 101 []),
  checkCase "SBottomKind" A.toSType A.fromSType (T.SBottomKind (sampleKind ((51) * 7 + 1))) (W.VNode 102 [expectKind ((51) * 7 + 1)]),
  checkCase "SArrow" A.toSType A.fromSType (T.SArrow (sampleSType ((52) * 7 + 1)) (sampleSType ((52) * 7 + 2))) (W.VNode 103 [expectSType ((52) * 7 + 1), expectSType ((52) * 7 + 2)]),
  checkCase "SCon" A.toSType A.fromSType (T.SCon (sampleString ((53) * 7 + 1)) (sampleList (\z -> sampleSType (z)) ((53) * 7 + 2))) (W.VNode 104 [expectString ((53) * 7 + 1), expectList (\z -> expectSType (z)) ((53) * 7 + 2)]),
  checkCase "STypeApp" A.toSType A.fromSType (T.STypeApp (sampleSType ((54) * 7 + 1)) (sampleSType ((54) * 7 + 2))) (W.VNode 105 [expectSType ((54) * 7 + 1), expectSType ((54) * 7 + 2)]),
  checkCase "SForall" A.toSType A.fromSType (T.SForall (sampleFlag ((55) * 7 + 1)) (sampleString ((55) * 7 + 2)) (sampleSType ((55) * 7 + 3)) (sampleSType ((55) * 7 + 4))) (W.VNode 106 [expectFlag ((55) * 7 + 1), expectString ((55) * 7 + 2), expectSType ((55) * 7 + 3), expectSType ((55) * 7 + 4)]),
  checkCase "SQualified" A.toSType A.fromSType (T.SQualified (sampleList (\z -> sampleSPredicate (z)) ((56) * 7 + 1)) (sampleSType ((56) * 7 + 2))) (W.VNode 107 [expectList (\z -> expectSPredicate (z)) ((56) * 7 + 1), expectSType ((56) * 7 + 2)]),
  checkCase "SAnnotation" A.toSAnnotation A.fromSAnnotation (T.SAnnotation (sampleList (\z -> sampleString (z)) ((57) * 7 + 1)) (sampleSType ((57) * 7 + 2))) (W.VNode 110 [expectList (\z -> expectString (z)) ((57) * 7 + 1), expectSType ((57) * 7 + 2)]),
  checkCase "InferRecursive" A.toRecursiveMode A.fromRecursiveMode (T.InferRecursive ) (W.VNode 111 []),
  checkCase "CheckRecursive" A.toRecursiveMode A.fromRecursiveMode (T.CheckRecursive (sampleSAnnotation ((59) * 7 + 1))) (W.VNode 112 [expectSAnnotation ((59) * 7 + 1)]),
  checkCase "SourceSpan" A.toSourceSpan A.fromSourceSpan (T.SourceSpan (sampleString ((60) * 7 + 1)) (sampleString ((60) * 7 + 2)) (sampleString ((60) * 7 + 3)) (sampleInt ((60) * 7 + 4)) (sampleInt ((60) * 7 + 5)) (sampleInt ((60) * 7 + 6)) (sampleInt ((60) * 7 + 7))) (W.VNode 113 [expectString ((60) * 7 + 1), expectString ((60) * 7 + 2), expectString ((60) * 7 + 3), expectInt ((60) * 7 + 4), expectInt ((60) * 7 + 5), expectInt ((60) * 7 + 6), expectInt ((60) * 7 + 7)]),
  checkCase "ScalarString" A.toSourceString A.fromSourceString (T.ScalarString (sampleString ((61) * 7 + 1))) (W.VNode 114 [expectString ((61) * 7 + 1)]),
  checkCase "CharString" A.toSourceString A.fromSourceString (T.CharString (sampleList (\z -> sampleInt (z)) ((62) * 7 + 1))) (W.VNode 115 [expectList (\z -> expectInt (z)) ((62) * 7 + 1)]),
  checkCase "GivenEvidence" A.toEvidenceRole A.fromEvidenceRole (T.GivenEvidence ) (W.VNode 116 []),
  checkCase "SuperclassEvidence" A.toEvidenceRole A.fromEvidenceRole (T.SuperclassEvidence ) (W.VNode 117 []),
  checkCase "InstanceEvidence" A.toEvidenceRole A.fromEvidenceRole (T.InstanceEvidence ) (W.VNode 118 []),
  checkCase "SVar" A.toSExpr A.fromSExpr (T.SVar (sampleString ((66) * 7 + 1))) (W.VNode 120 [expectString ((66) * 7 + 1)]),
  checkCase "SConstructor" A.toSExpr A.fromSExpr (T.SConstructor (sampleString ((67) * 7 + 1))) (W.VNode 121 [expectString ((67) * 7 + 1)]),
  checkCase "SLam" A.toSExpr A.fromSExpr (T.SLam (sampleString ((68) * 7 + 1)) (sampleMaybe (\z -> sampleSAnnotation (z)) ((68) * 7 + 2)) (sampleSExpr ((68) * 7 + 3))) (W.VNode 122 [expectString ((68) * 7 + 1), expectMaybe (\z -> expectSAnnotation (z)) ((68) * 7 + 2), expectSExpr ((68) * 7 + 3)]),
  checkCase "SApp" A.toSExpr A.fromSExpr (T.SApp (sampleSExpr ((69) * 7 + 1)) (sampleSExpr ((69) * 7 + 2))) (W.VNode 123 [expectSExpr ((69) * 7 + 1), expectSExpr ((69) * 7 + 2)]),
  checkCase "SLet" A.toSExpr A.fromSExpr (T.SLet (sampleString ((70) * 7 + 1)) (sampleSExpr ((70) * 7 + 2)) (sampleSExpr ((70) * 7 + 3))) (W.VNode 124 [expectString ((70) * 7 + 1), expectSExpr ((70) * 7 + 2), expectSExpr ((70) * 7 + 3)]),
  checkCase "SAnn" A.toSExpr A.fromSExpr (T.SAnn (sampleSExpr ((71) * 7 + 1)) (sampleSAnnotation ((71) * 7 + 2))) (W.VNode 125 [expectSExpr ((71) * 7 + 1), expectSAnnotation ((71) * 7 + 2)]),
  checkCase "SSignature" A.toSExpr A.fromSExpr (T.SSignature (sampleSExpr ((72) * 7 + 1)) (sampleSAnnotation ((72) * 7 + 2))) (W.VNode 126 [expectSExpr ((72) * 7 + 1), expectSAnnotation ((72) * 7 + 2)]),
  checkCase "SIntLit" A.toSExpr A.fromSExpr (T.SIntLit (sampleInt ((73) * 7 + 1))) (W.VNode 127 [expectInt ((73) * 7 + 1)]),
  checkCase "SDoubleLit" A.toSExpr A.fromSExpr (T.SDoubleLit (sampleDouble ((74) * 7 + 1))) (W.VNode 128 [expectDouble ((74) * 7 + 1)]),
  checkCase "SBoolLit" A.toSExpr A.fromSExpr (T.SBoolLit (sampleBool ((75) * 7 + 1))) (W.VNode 129 [expectBool ((75) * 7 + 1)]),
  checkCase "SStringLit" A.toSExpr A.fromSExpr (T.SStringLit (sampleString ((76) * 7 + 1))) (W.VNode 130 [expectString ((76) * 7 + 1)]),
  checkCase "SPrimitive" A.toSExpr A.fromSExpr (T.SPrimitive (samplePrimitive ((77) * 7 + 1))) (W.VNode 131 [expectPrimitive ((77) * 7 + 1)]),
  checkCase "SCase" A.toSExpr A.fromSExpr (T.SCase (sampleSExpr ((78) * 7 + 1)) (sampleList (\z -> sampleSAlternative (z)) ((78) * 7 + 2))) (W.VNode 132 [expectSExpr ((78) * 7 + 1), expectList (\z -> expectSAlternative (z)) ((78) * 7 + 2)]),
  checkCase "SDo" A.toSExpr A.fromSExpr (T.SDo (sampleList (\z -> sampleSStatement (z)) ((79) * 7 + 1)) (sampleSExpr ((79) * 7 + 2))) (W.VNode 133 [expectList (\z -> expectSStatement (z)) ((79) * 7 + 1), expectSExpr ((79) * 7 + 2)]),
  checkCase "SEquations" A.toSExpr A.fromSExpr (T.SEquations (sampleList (\z -> (sampleList (\z -> sampleSPattern (z)) ((z) * 5 + 1), sampleSExpr ((z) * 5 + 2))) ((80) * 7 + 1))) (W.VNode 134 [expectList (\z -> W.VNode 2 [expectList (\z -> expectSPattern (z)) ((z) * 5 + 1), expectSExpr ((z) * 5 + 2)]) ((80) * 7 + 1)]),
  checkCase "SLetRec" A.toSExpr A.fromSExpr (T.SLetRec (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleRecursiveMode ((z) * 5 + 2), sampleSExpr ((z) * 5 + 3))) ((81) * 7 + 1)) (sampleSExpr ((81) * 7 + 2))) (W.VNode 135 [expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectRecursiveMode ((z) * 5 + 2), expectSExpr ((z) * 5 + 3)]) ((81) * 7 + 1), expectSExpr ((81) * 7 + 2)]),
  checkCase "SWanted" A.toSExpr A.fromSExpr (T.SWanted (sampleString ((82) * 7 + 1)) (sampleList (\z -> (sampleEvidenceRole ((z) * 5 + 1), sampleString ((z) * 5 + 2))) ((82) * 7 + 2))) (W.VNode 136 [expectString ((82) * 7 + 1), expectList (\z -> W.VNode 2 [expectEvidenceRole ((z) * 5 + 1), expectString ((z) * 5 + 2)]) ((82) * 7 + 2)]),
  checkCase "SChecked" A.toSExpr A.fromSExpr (T.SChecked (sampleSType ((83) * 7 + 1)) (sampleSExpr ((83) * 7 + 2))) (W.VNode 137 [expectSType ((83) * 7 + 1), expectSExpr ((83) * 7 + 2)]),
  checkCase "SSourceDefinition" A.toSExpr A.fromSExpr (T.SSourceDefinition (sampleSExpr ((84) * 7 + 1))) (W.VNode 138 [expectSExpr ((84) * 7 + 1)]),
  checkCase "SCallSite" A.toSExpr A.fromSExpr (T.SCallSite (sampleString ((85) * 7 + 1)) (sampleSourceSpan ((85) * 7 + 2)) (sampleSExpr ((85) * 7 + 3))) (W.VNode 139 [expectString ((85) * 7 + 1), expectSourceSpan ((85) * 7 + 2), expectSExpr ((85) * 7 + 3)]),
  checkCase "SSharedBind" A.toSExpr A.fromSExpr (T.SSharedBind (sampleSPattern ((86) * 7 + 1)) (sampleSExpr ((86) * 7 + 2)) (sampleSExpr ((86) * 7 + 3)) (sampleSExpr ((86) * 7 + 4)) (sampleSExpr ((86) * 7 + 5))) (W.VNode 140 [expectSPattern ((86) * 7 + 1), expectSExpr ((86) * 7 + 2), expectSExpr ((86) * 7 + 3), expectSExpr ((86) * 7 + 4), expectSExpr ((86) * 7 + 5)]),
  checkCase "SConstructorPattern" A.toSPattern A.fromSPattern (T.SConstructorPattern (sampleString ((87) * 7 + 1)) (sampleList (\z -> sampleMaybe (\z -> sampleString (z)) (z)) ((87) * 7 + 2))) (W.VNode 150 [expectString ((87) * 7 + 1), expectList (\z -> expectMaybe (\z -> expectString (z)) (z)) ((87) * 7 + 2)]),
  checkCase "SDefaultPattern" A.toSPattern A.fromSPattern (T.SDefaultPattern (sampleMaybe (\z -> sampleString (z)) ((88) * 7 + 1))) (W.VNode 151 [expectMaybe (\z -> expectString (z)) ((88) * 7 + 1)]),
  checkCase "SNestedPattern" A.toSPattern A.fromSPattern (T.SNestedPattern (sampleString ((89) * 7 + 1)) (sampleList (\z -> sampleSPattern (z)) ((89) * 7 + 2))) (W.VNode 152 [expectString ((89) * 7 + 1), expectList (\z -> expectSPattern (z)) ((89) * 7 + 2)]),
  checkCase "SAnnotatedPattern" A.toSPattern A.fromSPattern (T.SAnnotatedPattern (sampleString ((90) * 7 + 1)) (sampleSAnnotation ((90) * 7 + 2))) (W.VNode 153 [expectString ((90) * 7 + 1), expectSAnnotation ((90) * 7 + 2)]),
  checkCase "SIntPattern" A.toSPattern A.fromSPattern (T.SIntPattern (sampleInt ((91) * 7 + 1))) (W.VNode 154 [expectInt ((91) * 7 + 1)]),
  checkCase "SStringPattern" A.toSPattern A.fromSPattern (T.SStringPattern (sampleString ((92) * 7 + 1))) (W.VNode 155 [expectString ((92) * 7 + 1)]),
  checkCase "SOverloadedStringPattern" A.toSPattern A.fromSPattern (T.SOverloadedStringPattern (sampleSourceString ((93) * 7 + 1)) (sampleString ((93) * 7 + 2)) (sampleString ((93) * 7 + 3))) (W.VNode 156 [expectSourceString ((93) * 7 + 1), expectString ((93) * 7 + 2), expectString ((93) * 7 + 3)]),
  checkCase "SBoolPattern" A.toSPattern A.fromSPattern (T.SBoolPattern (sampleBool ((94) * 7 + 1))) (W.VNode 157 [expectBool ((94) * 7 + 1)]),
  checkCase "SAsPattern" A.toSPattern A.fromSPattern (T.SAsPattern (sampleString ((95) * 7 + 1)) (sampleSPattern ((95) * 7 + 2))) (W.VNode 158 [expectString ((95) * 7 + 1), expectSPattern ((95) * 7 + 2)]),
  checkCase "SLazyPattern" A.toSPattern A.fromSPattern (T.SLazyPattern (sampleSPattern ((96) * 7 + 1))) (W.VNode 159 [expectSPattern ((96) * 7 + 1)]),
  checkCase "SAlternative" A.toSAlternative A.fromSAlternative (T.SAlternative (sampleSPattern ((97) * 7 + 1)) (sampleSExpr ((97) * 7 + 2))) (W.VNode 160 [expectSPattern ((97) * 7 + 1), expectSExpr ((97) * 7 + 2)]),
  checkCase "SDoBind" A.toSStatement A.fromSStatement (T.SDoBind (sampleSPattern ((98) * 7 + 1)) (sampleSExpr ((98) * 7 + 2))) (W.VNode 161 [expectSPattern ((98) * 7 + 1), expectSExpr ((98) * 7 + 2)]),
  checkCase "SDoThen" A.toSStatement A.fromSStatement (T.SDoThen (sampleSExpr ((99) * 7 + 1))) (W.VNode 162 [expectSExpr ((99) * 7 + 1)]),
  checkCase "SDoLet" A.toSStatement A.fromSStatement (T.SDoLet (sampleString ((100) * 7 + 1)) (sampleMaybe (\z -> sampleSAnnotation (z)) ((100) * 7 + 2)) (sampleSExpr ((100) * 7 + 3))) (W.VNode 163 [expectString ((100) * 7 + 1), expectMaybe (\z -> expectSAnnotation (z)) ((100) * 7 + 2), expectSExpr ((100) * 7 + 3)]),
  checkCase "SDoLetRec" A.toSStatement A.fromSStatement (T.SDoLetRec (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleRecursiveMode ((z) * 5 + 2), sampleSExpr ((z) * 5 + 3))) ((101) * 7 + 1))) (W.VNode 164 [expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectRecursiveMode ((z) * 5 + 2), expectSExpr ((z) * 5 + 3)]) ((101) * 7 + 1)]),
  checkCase "SPredicate" A.toSPredicate A.fromSPredicate (T.SPredicate (sampleString ((102) * 7 + 1)) (sampleList (\z -> sampleSType (z)) ((102) * 7 + 2))) (W.VNode 170 [expectString ((102) * 7 + 1), expectList (\z -> expectSType (z)) ((102) * 7 + 2)]),
  checkCase "SClassDecl" A.toSClassDecl A.fromSClassDecl (T.SClassDecl (sampleString ((103) * 7 + 1)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleKind ((z) * 5 + 2))) ((103) * 7 + 2)) (sampleList (\z -> sampleSPredicate (z)) ((103) * 7 + 3)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleSType ((z) * 5 + 2))) ((103) * 7 + 4))) (W.VNode 171 [expectString ((103) * 7 + 1), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectKind ((z) * 5 + 2)]) ((103) * 7 + 2), expectList (\z -> expectSPredicate (z)) ((103) * 7 + 3), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectSType ((z) * 5 + 2)]) ((103) * 7 + 4)]),
  checkCase "SInstanceDecl" A.toSInstanceDecl A.fromSInstanceDecl (T.SInstanceDecl (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleKind ((z) * 5 + 2))) ((104) * 7 + 1)) (sampleList (\z -> sampleSPredicate (z)) ((104) * 7 + 2)) (sampleString ((104) * 7 + 3)) (sampleList (\z -> sampleSType (z)) ((104) * 7 + 4)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleSExpr ((z) * 5 + 2))) ((104) * 7 + 5))) (W.VNode 172 [expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectKind ((z) * 5 + 2)]) ((104) * 7 + 1), expectList (\z -> expectSPredicate (z)) ((104) * 7 + 2), expectString ((104) * 7 + 3), expectList (\z -> expectSType (z)) ((104) * 7 + 4), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectSExpr ((z) * 5 + 2)]) ((104) * 7 + 5)]),
  checkCase "Modules.Value" A.toRole A.fromRole (M.Value ) (W.VNode 180 []),
  checkCase "Modules.Datatype" A.toRole A.fromRole (M.Datatype ) (W.VNode 181 []),
  checkCase "Modules.Class" A.toRole A.fromRole (M.Class ) (W.VNode 182 []),
  checkCase "Modules.Constructor" A.toRole A.fromRole (M.Constructor (sampleString ((108) * 7 + 1))) (W.VNode 183 [expectString ((108) * 7 + 1)]),
  checkCase "Modules.Method" A.toRole A.fromRole (M.Method (sampleString ((109) * 7 + 1))) (W.VNode 184 [expectString ((109) * 7 + 1)]),
  checkCase "Modules.BuiltinType" A.toRole A.fromRole (M.BuiltinType ) (W.VNode 185 []),
  checkCase "Modules.Primitive" A.toRole A.fromRole (M.Primitive (samplePrimitive ((111) * 7 + 1))) (W.VNode 186 [expectPrimitive ((111) * 7 + 1)]),
  checkCase "Modules.Boolean" A.toRole A.fromRole (M.Boolean (sampleBool ((112) * 7 + 1))) (W.VNode 187 [expectBool ((112) * 7 + 1)]),
  checkCase "Modules.ManagedConstraint" A.toRole A.fromRole (M.ManagedConstraint ) (W.VNode 188 []),
  checkCase "Modules.Entity" A.toEntity A.fromEntity (M.Entity (sampleString ((114) * 7 + 1)) (sampleString ((114) * 7 + 2)) (sampleRole ((114) * 7 + 3))) (W.VNode 189 [expectString ((114) * 7 + 1), expectString ((114) * 7 + 2), expectRole ((114) * 7 + 3)]),
  checkCase "LegacyEmlfV1" A.toSourceSyntax A.fromSourceSyntax (T.LegacyEmlfV1 ) (W.VNode 200 []),
  checkCase "SharedHaskellV1" A.toSourceSyntax A.fromSourceSyntax (T.SharedHaskellV1 ) (W.VNode 201 []),
  checkCase "MetadataSyntax" A.toSourceSyntax A.fromSourceSyntax (T.MetadataSyntax ) (W.VNode 202 []),
  checkCase "Everything" A.toSelection A.fromSelection (T.Everything ) (W.VNode 203 []),
  checkCase "Only" A.toSelection A.fromSelection (T.Only (sampleList (\z -> sampleExport (z)) ((119) * 7 + 1))) (W.VNode 204 [expectList (\z -> expectExport (z)) ((119) * 7 + 1)]),
  checkCase "Hiding" A.toSelection A.fromSelection (T.Hiding (sampleList (\z -> sampleExport (z)) ((120) * 7 + 1))) (W.VNode 205 [expectList (\z -> expectExport (z)) ((120) * 7 + 1)]),
  checkCase "ExportValue" A.toExport A.fromExport (T.ExportValue (sampleString ((121) * 7 + 1))) (W.VNode 206 [expectString ((121) * 7 + 1)]),
  checkCase "ExportType" A.toExport A.fromExport (T.ExportType (sampleString ((122) * 7 + 1)) (sampleMembers ((122) * 7 + 2))) (W.VNode 207 [expectString ((122) * 7 + 1), expectMembers ((122) * 7 + 2)]),
  checkCase "ExportModule" A.toExport A.fromExport (T.ExportModule (sampleString ((123) * 7 + 1))) (W.VNode 208 [expectString ((123) * 7 + 1)]),
  checkCase "Abstract" A.toMembers A.fromMembers (T.Abstract ) (W.VNode 209 []),
  checkCase "AllMembers" A.toMembers A.fromMembers (T.AllMembers ) (W.VNode 210 []),
  checkCase "Members" A.toMembers A.fromMembers (T.Members (sampleList (\z -> sampleString (z)) ((126) * 7 + 1))) (W.VNode 211 [expectList (\z -> expectString (z)) ((126) * 7 + 1)]),
  checkCase "Import" A.toImport A.fromImport (T.Import (sampleString ((127) * 7 + 1)) (sampleBool ((127) * 7 + 2)) (sampleMaybe (\z -> sampleString (z)) ((127) * 7 + 3)) (sampleSelection ((127) * 7 + 4))) (W.VNode 212 [expectString ((127) * 7 + 1), expectBool ((127) * 7 + 2), expectMaybe (\z -> expectString (z)) ((127) * 7 + 3), expectSelection ((127) * 7 + 4)]),
  checkCase "SourceModule" A.toSourceModule A.fromSourceModule (T.SourceModule (sampleString ((128) * 7 + 1)) (sampleMaybe (\z -> sampleString (z)) ((128) * 7 + 2)) (sampleMaybe (\z -> sampleList (\z -> sampleExport (z)) (z)) ((128) * 7 + 3)) (sampleList (\z -> sampleImport (z)) ((128) * 7 + 4)) (sampleList (\z -> sampleDataDecl (z)) ((128) * 7 + 5)) (sampleList (\z -> sampleSClassDecl (z)) ((128) * 7 + 6)) (sampleList (\z -> sampleSInstanceDecl (z)) ((128) * 7 + 7)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleMaybe (\z -> sampleSAnnotation (z)) ((z) * 5 + 2), sampleSExpr ((z) * 5 + 3))) ((128) * 7 + 8)) (sampleMaybe (\z -> sampleSExpr (z)) ((128) * 7 + 9)) (sampleSourceSyntax ((128) * 7 + 10))) (W.VNode 213 [expectString ((128) * 7 + 1), expectMaybe (\z -> expectString (z)) ((128) * 7 + 2), expectMaybe (\z -> expectList (\z -> expectExport (z)) (z)) ((128) * 7 + 3), expectList (\z -> expectImport (z)) ((128) * 7 + 4), expectList (\z -> expectDataDecl (z)) ((128) * 7 + 5), expectList (\z -> expectSClassDecl (z)) ((128) * 7 + 6), expectList (\z -> expectSInstanceDecl (z)) ((128) * 7 + 7), expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectMaybe (\z -> expectSAnnotation (z)) ((z) * 5 + 2), expectSExpr ((z) * 5 + 3)]) ((128) * 7 + 8), expectMaybe (\z -> expectSExpr (z)) ((128) * 7 + 9), expectSourceSyntax ((128) * 7 + 10)]),
  checkCase "SProgram" A.toSProgram A.fromSProgram (T.SProgram (sampleList (\z -> sampleDataDecl (z)) ((129) * 7 + 1)) (sampleSExpr ((129) * 7 + 2))) (W.VNode 214 [expectList (\z -> expectDataDecl (z)) ((129) * 7 + 1), expectSExpr ((129) * 7 + 2)]),
  checkCase "SClassProgram" A.toSProgram A.fromSProgram (T.SClassProgram (sampleList (\z -> sampleDataDecl (z)) ((130) * 7 + 1)) (sampleList (\z -> sampleSClassDecl (z)) ((130) * 7 + 2)) (sampleList (\z -> sampleSInstanceDecl (z)) ((130) * 7 + 3)) (sampleSExpr ((130) * 7 + 4))) (W.VNode 215 [expectList (\z -> expectDataDecl (z)) ((130) * 7 + 1), expectList (\z -> expectSClassDecl (z)) ((130) * 7 + 2), expectList (\z -> expectSInstanceDecl (z)) ((130) * 7 + 3), expectSExpr ((130) * 7 + 4)]),
  checkCase "Separate.UnitInterface" A.toUnitInterface A.fromUnitInterface (U.UnitInterface (sampleString ((131) * 7 + 1)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleString ((z) * 5 + 2))) ((131) * 7 + 2)) (sampleList (\z -> sampleEntity (z)) ((131) * 7 + 3)) (sampleList (\z -> sampleDataDecl (z)) ((131) * 7 + 4)) (sampleList (\z -> sampleSClassDecl (z)) ((131) * 7 + 5)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleInterfaceInstance ((z) * 5 + 2))) ((131) * 7 + 6)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleXType ((z) * 5 + 2))) ((131) * 7 + 7)) (sampleString ((131) * 7 + 8))) (W.VNode 240 [expectString ((131) * 7 + 1), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectString ((z) * 5 + 2)]) ((131) * 7 + 2), expectList (\z -> expectEntity (z)) ((131) * 7 + 3), expectList (\z -> expectDataDecl (z)) ((131) * 7 + 4), expectList (\z -> expectSClassDecl (z)) ((131) * 7 + 5), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectInterfaceInstance ((z) * 5 + 2)]) ((131) * 7 + 6), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectXType ((z) * 5 + 2)]) ((131) * 7 + 7), expectString ((131) * 7 + 8)]),
  checkCase "CrateInterfaceFields" A.toCrateInterfaceFields A.fromCrateInterfaceFields (A.CrateInterfaceFields (sampleString ((132) * 7 + 1)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleString ((z) * 5 + 2), sampleString ((z) * 5 + 3))) ((132) * 7 + 2)) (sampleList (\z -> sampleString (z)) ((132) * 7 + 3)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleList (\z -> sampleEntity (z)) ((z) * 5 + 2))) ((132) * 7 + 4)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleList (\z -> sampleString (z)) ((z) * 5 + 2))) ((132) * 7 + 5)) (sampleList (\z -> sampleDataDecl (z)) ((132) * 7 + 6)) (sampleList (\z -> sampleSClassDecl (z)) ((132) * 7 + 7)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleInterfaceInstance ((z) * 5 + 2))) ((132) * 7 + 8)) (sampleList (\z -> sampleDataDecl (z)) ((132) * 7 + 9)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleXType ((z) * 5 + 2))) ((132) * 7 + 10)) (sampleString ((132) * 7 + 11)) (sampleString ((132) * 7 + 12)) (sampleList (\z -> (sampleString ((z) * 5 + 1), sampleBool ((z) * 5 + 2))) ((132) * 7 + 13))) (W.VNode 242 [expectString ((132) * 7 + 1), expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectString ((z) * 5 + 2), expectString ((z) * 5 + 3)]) ((132) * 7 + 2), expectList (\z -> expectString (z)) ((132) * 7 + 3), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectList (\z -> expectEntity (z)) ((z) * 5 + 2)]) ((132) * 7 + 4), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectList (\z -> expectString (z)) ((z) * 5 + 2)]) ((132) * 7 + 5), expectList (\z -> expectDataDecl (z)) ((132) * 7 + 6), expectList (\z -> expectSClassDecl (z)) ((132) * 7 + 7), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectInterfaceInstance ((z) * 5 + 2)]) ((132) * 7 + 8), expectList (\z -> expectDataDecl (z)) ((132) * 7 + 9), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectXType ((z) * 5 + 2)]) ((132) * 7 + 10), expectString ((132) * 7 + 11), expectString ((132) * 7 + 12), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectBool ((z) * 5 + 2)]) ((132) * 7 + 13)]),
  checkCase "CrateObjectFields" A.toCrateObjectFields A.fromCrateObjectFields (A.CrateObjectFields (sampleBool ((133) * 7 + 1)) (sampleCrateInterfaceFields ((133) * 7 + 2)) (sampleList (\z -> sampleRawUnitObject (z)) ((133) * 7 + 3))) (W.VNode 243 [expectBool ((133) * 7 + 1), expectCrateInterfaceFields ((133) * 7 + 2), expectList (\z -> expectRawUnitObject (z)) ((133) * 7 + 3)]),
  checkCase "PIOReturn" A.toPrimitive A.fromPrimitive T.PIOReturn (W.VNode 32 [W.VInt 0]),
  checkCase "PIOBind" A.toPrimitive A.fromPrimitive T.PIOBind (W.VNode 32 [W.VInt 1]),
  checkCase "PPutStr" A.toPrimitive A.fromPrimitive T.PPutStr (W.VNode 32 [W.VInt 2]),
  checkCase "PPutStrLn" A.toPrimitive A.fromPrimitive T.PPutStrLn (W.VNode 32 [W.VInt 3]),
  checkCase "PGetLine" A.toPrimitive A.fromPrimitive T.PGetLine (W.VNode 32 [W.VInt 4]),
  checkCase "PPrintInt" A.toPrimitive A.fromPrimitive T.PPrintInt (W.VNode 32 [W.VInt 5]),
  checkCase "PConcatString" A.toPrimitive A.fromPrimitive T.PConcatString (W.VNode 32 [W.VInt 6]),
  checkCase "PShowInt" A.toPrimitive A.fromPrimitive T.PShowInt (W.VNode 32 [W.VInt 7]),
  checkCase "PAddInt" A.toPrimitive A.fromPrimitive T.PAddInt (W.VNode 32 [W.VInt 8]),
  checkCase "PSubInt" A.toPrimitive A.fromPrimitive T.PSubInt (W.VNode 32 [W.VInt 9]),
  checkCase "PEqInt" A.toPrimitive A.fromPrimitive T.PEqInt (W.VNode 32 [W.VInt 10]),
  checkCase "PLtInt" A.toPrimitive A.fromPrimitive T.PLtInt (W.VNode 32 [W.VInt 11]),
  checkCase "PEqString" A.toPrimitive A.fromPrimitive T.PEqString (W.VNode 32 [W.VInt 12]),
  checkCase "PIfThenElse" A.toPrimitive A.fromPrimitive T.PIfThenElse (W.VNode 32 [W.VInt 13]),
  checkCase "PMulInt" A.toPrimitive A.fromPrimitive T.PMulInt (W.VNode 32 [W.VInt 14]),
  checkCase "PQuotInt" A.toPrimitive A.fromPrimitive T.PQuotInt (W.VNode 32 [W.VInt 15]),
  checkCase "PRemInt" A.toPrimitive A.fromPrimitive T.PRemInt (W.VNode 32 [W.VInt 16]),
  checkCase "PReadInt" A.toPrimitive A.fromPrimitive T.PReadInt (W.VNode 32 [W.VInt 17]),
  checkCase "PAddDouble" A.toPrimitive A.fromPrimitive T.PAddDouble (W.VNode 32 [W.VInt 18]),
  checkCase "PSubDouble" A.toPrimitive A.fromPrimitive T.PSubDouble (W.VNode 32 [W.VInt 19]),
  checkCase "PMulDouble" A.toPrimitive A.fromPrimitive T.PMulDouble (W.VNode 32 [W.VInt 20]),
  checkCase "PDivDouble" A.toPrimitive A.fromPrimitive T.PDivDouble (W.VNode 32 [W.VInt 21]),
  checkCase "PSqrtDouble" A.toPrimitive A.fromPrimitive T.PSqrtDouble (W.VNode 32 [W.VInt 22]),
  checkCase "PEqDouble" A.toPrimitive A.fromPrimitive T.PEqDouble (W.VNode 32 [W.VInt 23]),
  checkCase "PLtDouble" A.toPrimitive A.fromPrimitive T.PLtDouble (W.VNode 32 [W.VInt 24]),
  checkCase "PIntToDouble" A.toPrimitive A.fromPrimitive T.PIntToDouble (W.VNode 32 [W.VInt 25]),
  checkCase "PFormatDouble" A.toPrimitive A.fromPrimitive T.PFormatDouble (W.VNode 32 [W.VInt 26]),
  checkCase "PNewIntArray" A.toPrimitive A.fromPrimitive T.PNewIntArray (W.VNode 32 [W.VInt 27]),
  checkCase "PReadIntArray" A.toPrimitive A.fromPrimitive T.PReadIntArray (W.VNode 32 [W.VInt 28]),
  checkCase "PWriteIntArray" A.toPrimitive A.fromPrimitive T.PWriteIntArray (W.VNode 32 [W.VInt 29]),
  checkCase "PLengthIntArray" A.toPrimitive A.fromPrimitive T.PLengthIntArray (W.VNode 32 [W.VInt 30]),
  checkCase "PNewDoubleArray" A.toPrimitive A.fromPrimitive T.PNewDoubleArray (W.VNode 32 [W.VInt 31]),
  checkCase "PReadDoubleArray" A.toPrimitive A.fromPrimitive T.PReadDoubleArray (W.VNode 32 [W.VInt 32]),
  checkCase "PWriteDoubleArray" A.toPrimitive A.fromPrimitive T.PWriteDoubleArray (W.VNode 32 [W.VInt 33]),
  checkCase "PLengthDoubleArray" A.toPrimitive A.fromPrimitive T.PLengthDoubleArray (W.VNode 32 [W.VInt 34]),
  checkCase "PNewByteArray" A.toPrimitive A.fromPrimitive T.PNewByteArray (W.VNode 32 [W.VInt 35]),
  checkCase "PReadByteArray" A.toPrimitive A.fromPrimitive T.PReadByteArray (W.VNode 32 [W.VInt 36]),
  checkCase "PWriteByteArray" A.toPrimitive A.fromPrimitive T.PWriteByteArray (W.VNode 32 [W.VInt 37]),
  checkCase "PLengthByteArray" A.toPrimitive A.fromPrimitive T.PLengthByteArray (W.VNode 32 [W.VInt 38]),
  checkCase "PByteArrayFromString" A.toPrimitive A.fromPrimitive T.PByteArrayFromString (W.VNode 32 [W.VInt 39]),
  checkCase "PPutBytes" A.toPrimitive A.fromPrimitive T.PPutBytes (W.VNode 32 [W.VInt 40]),
  checkCase "PGetByteLine" A.toPrimitive A.fromPrimitive T.PGetByteLine (W.VNode 32 [W.VInt 41]),
  checkCase "PNewIntTable" A.toPrimitive A.fromPrimitive T.PNewIntTable (W.VNode 32 [W.VInt 42]),
  checkCase "PReadIntTable" A.toPrimitive A.fromPrimitive T.PReadIntTable (W.VNode 32 [W.VInt 43]),
  checkCase "PWriteIntTable" A.toPrimitive A.fromPrimitive T.PWriteIntTable (W.VNode 32 [W.VInt 44]),
  checkCase "PAndInt" A.toPrimitive A.fromPrimitive T.PAndInt (W.VNode 32 [W.VInt 45]),
  checkCase "PStringLength" A.toPrimitive A.fromPrimitive T.PStringLength (W.VNode 32 [W.VInt 46]),
  checkCase "PStringCodeAt" A.toPrimitive A.fromPrimitive T.PStringCodeAt (W.VNode 32 [W.VInt 47]),
  checkCase "PStringSlice" A.toPrimitive A.fromPrimitive T.PStringSlice (W.VNode 32 [W.VInt 48]),
  checkCase "PStringFromCode" A.toPrimitive A.fromPrimitive T.PStringFromCode (W.VNode 32 [W.VInt 49]),
  checkCase "PCompareString" A.toPrimitive A.fromPrimitive T.PCompareString (W.VNode 32 [W.VInt 50]),
  checkCase "PReadDouble" A.toPrimitive A.fromPrimitive T.PReadDouble (W.VNode 32 [W.VInt 51]),
  checkCase "PDoubleToBits" A.toPrimitive A.fromPrimitive T.PDoubleToBits (W.VNode 32 [W.VInt 52]),
  checkCase "PDoubleFromBits" A.toPrimitive A.fromPrimitive T.PDoubleFromBits (W.VNode 32 [W.VInt 53]),
  checkCase "PSeq" A.toPrimitive A.fromPrimitive T.PSeq (W.VNode 32 [W.VInt 54]),
  checkCase "PPanic" A.toPrimitive A.fromPrimitive T.PPanic (W.VNode 32 [W.VInt 55]),
  checkCase "PReadFile" A.toPrimitive A.fromPrimitive T.PReadFile (W.VNode 32 [W.VInt 56]),
  checkCase "PWriteFile" A.toPrimitive A.fromPrimitive T.PWriteFile (W.VNode 32 [W.VInt 57]),
  checkCase "PFileExists" A.toPrimitive A.fromPrimitive T.PFileExists (W.VNode 32 [W.VInt 58]),
  checkCase "PCanonicalPath" A.toPrimitive A.fromPrimitive T.PCanonicalPath (W.VNode 32 [W.VInt 59]),
  checkCase "PGetArgCount" A.toPrimitive A.fromPrimitive T.PGetArgCount (W.VNode 32 [W.VInt 60]),
  checkCase "PGetArg" A.toPrimitive A.fromPrimitive T.PGetArg (W.VNode 32 [W.VInt 61]),
  checkCase "PPutErr" A.toPrimitive A.fromPrimitive T.PPutErr (W.VNode 32 [W.VInt 62]),
  checkCase "PExitWith" A.toPrimitive A.fromPrimitive T.PExitWith (W.VNode 32 [W.VInt 63]),
  checkCase "PGetExecutablePath" A.toPrimitive A.fromPrimitive T.PGetExecutablePath (W.VNode 32 [W.VInt 64]),
  checkCase "PGetContents" A.toPrimitive A.fromPrimitive T.PGetContents (W.VNode 32 [W.VInt 65]),
  checkCase "PSTReturn" A.toPrimitive A.fromPrimitive T.PSTReturn (W.VNode 32 [W.VInt 66]),
  checkCase "PSTBind" A.toPrimitive A.fromPrimitive T.PSTBind (W.VNode 32 [W.VInt 67]),
  checkCase "PRunST" A.toPrimitive A.fromPrimitive T.PRunST (W.VNode 32 [W.VInt 68]),
  checkCase "PNewSTArray" A.toPrimitive A.fromPrimitive T.PNewSTArray (W.VNode 32 [W.VInt 69]),
  checkCase "PReadSTArray" A.toPrimitive A.fromPrimitive T.PReadSTArray (W.VNode 32 [W.VInt 70]),
  checkCase "PWriteSTArray" A.toPrimitive A.fromPrimitive T.PWriteSTArray (W.VNode 32 [W.VInt 71]),
  checkCase "PLengthSTArray" A.toPrimitive A.fromPrimitive T.PLengthSTArray (W.VNode 32 [W.VInt 72]),
  checkCase "PGetEnv" A.toPrimitive A.fromPrimitive T.PGetEnv (W.VNode 32 [W.VInt 73]),
  checkCase "PSetEnv" A.toPrimitive A.fromPrimitive T.PSetEnv (W.VNode 32 [W.VInt 74]),
  checkCase "PUnsetEnv" A.toPrimitive A.fromPrimitive T.PUnsetEnv (W.VNode 32 [W.VInt 75]),
  checkCase "PRunProcess" A.toPrimitive A.fromPrimitive T.PRunProcess (W.VNode 32 [W.VInt 76]),
  checkCase "PListDirectory" A.toPrimitive A.fromPrimitive T.PListDirectory (W.VNode 32 [W.VInt 77]),
  checkCase "PDirectoryExists" A.toPrimitive A.fromPrimitive T.PDirectoryExists (W.VNode 32 [W.VInt 78]),
  checkCase "PFileDigest" A.toPrimitive A.fromPrimitive T.PFileDigest (W.VNode 32 [W.VInt 79]),
  checkCase "PAcquireFileLock" A.toPrimitive A.fromPrimitive T.PAcquireFileLock (W.VNode 32 [W.VInt 80]),
  checkCase "PReleaseFileLock" A.toPrimitive A.fromPrimitive T.PReleaseFileLock (W.VNode 32 [W.VInt 81]),
  checkCase "PProcessSupervisor" A.toPrimitive A.fromPrimitive T.PProcessSupervisor (W.VNode 32 [W.VInt 82]),
  checkCase "PAsyncScopeNew" A.toPrimitive A.fromPrimitive T.PAsyncScopeNew (W.VNode 32 [W.VInt 83]),
  checkCase "PAsyncScopeClose" A.toPrimitive A.fromPrimitive T.PAsyncScopeClose (W.VNode 32 [W.VInt 84]),
  checkCase "PAsyncNewCompletion" A.toPrimitive A.fromPrimitive T.PAsyncNewCompletion (W.VNode 32 [W.VInt 85]),
  checkCase "PAsyncResolveCompletion" A.toPrimitive A.fromPrimitive T.PAsyncResolveCompletion (W.VNode 32 [W.VInt 86]),
  checkCase "PAsyncReadCompletion" A.toPrimitive A.fromPrimitive T.PAsyncReadCompletion (W.VNode 32 [W.VInt 87]),
  checkCase "PAsyncSubscribeCompletion" A.toPrimitive A.fromPrimitive T.PAsyncSubscribeCompletion (W.VNode 32 [W.VInt 88]),
  checkCase "PAsyncSubscriptionStatus" A.toPrimitive A.fromPrimitive T.PAsyncSubscriptionStatus (W.VNode 32 [W.VInt 89]),
  checkCase "PAsyncCancelSubscription" A.toPrimitive A.fromPrimitive T.PAsyncCancelSubscription (W.VNode 32 [W.VInt 90]),
  checkCase "PAsyncStep" A.toPrimitive A.fromPrimitive T.PAsyncStep (W.VNode 32 [W.VInt 91]),
  checkCase "PAsyncEnqueue" A.toPrimitive A.fromPrimitive T.PAsyncEnqueue (W.VNode 32 [W.VInt 92]),
  checkCase "PAsyncDelay" A.toPrimitive A.fromPrimitive T.PAsyncDelay (W.VNode 32 [W.VInt 93]),
  checkCase "PAsyncWait" A.toPrimitive A.fromPrimitive T.PAsyncWait (W.VNode 32 [W.VInt 94]),
  checkCase "PTextToChars" A.toPrimitive A.fromPrimitive T.PTextToChars (W.VNode 32 [W.VInt 95]),
  checkCase "PTextFromChars" A.toPrimitive A.fromPrimitive T.PTextFromChars (W.VNode 32 [W.VInt 96]),
  checkCase "PCharCode" A.toPrimitive A.fromPrimitive T.PCharCode (W.VNode 32 [W.VInt 97]),
  checkCase "PCharFromCode" A.toPrimitive A.fromPrimitive T.PCharFromCode (W.VNode 32 [W.VInt 98]),
  checkCase "PUserError" A.toPrimitive A.fromPrimitive T.PUserError (W.VNode 32 [W.VInt 99]),
  checkCase "PIOError" A.toPrimitive A.fromPrimitive T.PIOError (W.VNode 32 [W.VInt 100]),
  checkCase "PCatchIOError" A.toPrimitive A.fromPrimitive T.PCatchIOError (W.VNode 32 [W.VInt 101]),
  checkCase "PIOErrorString" A.toPrimitive A.fromPrimitive T.PIOErrorString (W.VNode 32 [W.VInt 102]),
  checkCase "PEmptyCallStack" A.toPrimitive A.fromPrimitive T.PEmptyCallStack (W.VNode 32 [W.VInt 103]),
  checkCase "PPushCallStack" A.toPrimitive A.fromPrimitive T.PPushCallStack (W.VNode 32 [W.VInt 104]),
  checkCase "PPrettyCallStack" A.toPrimitive A.fromPrimitive T.PPrettyCallStack (W.VNode 32 [W.VInt 105]),
  checkCase "PIOErrorWithStack" A.toPrimitive A.fromPrimitive T.PIOErrorWithStack (W.VNode 32 [W.VInt 106]),
  checkCase "PConcatStringList" A.toPrimitive A.fromPrimitive T.PConcatStringList (W.VNode 32 [W.VInt 107]),
  checkCase "POrInt" A.toPrimitive A.fromPrimitive T.POrInt (W.VNode 32 [W.VInt 108]),
  checkCase "PXorInt" A.toPrimitive A.fromPrimitive T.PXorInt (W.VNode 32 [W.VInt 109]),
  checkCase "PShiftLInt" A.toPrimitive A.fromPrimitive T.PShiftLInt (W.VNode 32 [W.VInt 110]),
  checkCase "PShiftRInt" A.toPrimitive A.fromPrimitive T.PShiftRInt (W.VNode 32 [W.VInt 111]),
  checkCase "PUnsignedShiftRInt" A.toPrimitive A.fromPrimitive T.PUnsignedShiftRInt (W.VNode 32 [W.VInt 112]),
  checkCase "PCountLeadingZerosInt" A.toPrimitive A.fromPrimitive T.PCountLeadingZerosInt (W.VNode 32 [W.VInt 113]),
  checkCase "PCountTrailingZerosInt" A.toPrimitive A.fromPrimitive T.PCountTrailingZerosInt (W.VNode 32 [W.VInt 114]),
  checkCase "PPopCountInt" A.toPrimitive A.fromPrimitive T.PPopCountInt (W.VNode 32 [W.VInt 115]),
  checkCase "PIntToInteger" A.toPrimitive A.fromPrimitive T.PIntToInteger (W.VNode 32 [W.VInt 116]),
  checkCase "PIntegerToInt" A.toPrimitive A.fromPrimitive T.PIntegerToInt (W.VNode 32 [W.VInt 117]),
  checkCase "PAddInteger" A.toPrimitive A.fromPrimitive T.PAddInteger (W.VNode 32 [W.VInt 118]),
  checkCase "PSubInteger" A.toPrimitive A.fromPrimitive T.PSubInteger (W.VNode 32 [W.VInt 119]),
  checkCase "PMulInteger" A.toPrimitive A.fromPrimitive T.PMulInteger (W.VNode 32 [W.VInt 120]),
  checkCase "PQuotInteger" A.toPrimitive A.fromPrimitive T.PQuotInteger (W.VNode 32 [W.VInt 121]),
  checkCase "PRemInteger" A.toPrimitive A.fromPrimitive T.PRemInteger (W.VNode 32 [W.VInt 122]),
  checkCase "PEqInteger" A.toPrimitive A.fromPrimitive T.PEqInteger (W.VNode 32 [W.VInt 123]),
  checkCase "PLtInteger" A.toPrimitive A.fromPrimitive T.PLtInteger (W.VNode 32 [W.VInt 124]),
  checkCase "PShowInteger" A.toPrimitive A.fromPrimitive T.PShowInteger (W.VNode 32 [W.VInt 125]),
  checkCase "PReadInteger" A.toPrimitive A.fromPrimitive T.PReadInteger (W.VNode 32 [W.VInt 126]),
  checkCase "PIntegerToDouble" A.toPrimitive A.fromPrimitive T.PIntegerToDouble (W.VNode 32 [W.VInt 127]),
  checkCase "PUnsignedLtInt" A.toPrimitive A.fromPrimitive T.PUnsignedLtInt (W.VNode 32 [W.VInt 128]),
  checkCase "PReadByteFileOrError" A.toPrimitive A.fromPrimitive T.PReadByteFileOrError (W.VNode 32 [W.VInt 129]),
  checkCase "PWriteByteFileOrError" A.toPrimitive A.fromPrimitive T.PWriteByteFileOrError (W.VNode 32 [W.VInt 130]),
  checkCase "PByteArrayDigest" A.toPrimitive A.fromPrimitive T.PByteArrayDigest (W.VNode 32 [W.VInt 131])
  ]

graphChecks = [
  \g root -> checkGraph "Star" A.toKind A.fromGraphKind g root (W.VNode 10 []),
  \g root -> checkGraph "KArrow" A.toKind A.fromGraphKind g root (W.VNode 11 [expectKind ((2) * 7 + 1), expectKind ((2) * 7 + 2)]),
  \g root -> checkGraph "Flexible" A.toFlag A.fromGraphFlag g root (W.VNode 12 []),
  \g root -> checkGraph "Rigid" A.toFlag A.fromGraphFlag g root (W.VNode 13 []),
  \g root -> checkGraph "Parameter" A.toField A.fromGraphField g root (W.VNode 20 [expectString ((5) * 7 + 1)]),
  \g root -> checkGraph "Function" A.toField A.fromGraphField g root (W.VNode 21 [expectField ((6) * 7 + 1), expectField ((6) * 7 + 2)]),
  \g root -> checkGraph "Applied" A.toField A.fromGraphField g root (W.VNode 22 [expectString ((7) * 7 + 1), expectList (\z -> expectField (z)) ((7) * 7 + 2)]),
  \g root -> checkGraph "Application" A.toField A.fromGraphField g root (W.VNode 23 [expectField ((8) * 7 + 1), expectField ((8) * 7 + 2)]),
  \g root -> checkGraph "Quantified" A.toField A.fromGraphField g root (W.VNode 24 [expectString ((9) * 7 + 1), expectKind ((9) * 7 + 2), expectField ((9) * 7 + 3)]),
  \g root -> checkGraph "ConstructorDecl" A.toConstructorDecl A.fromGraphConstructorDecl g root (W.VNode 25 [expectString ((10) * 7 + 1), expectList (\z -> expectField (z)) ((10) * 7 + 2)]),
  \g root -> checkGraph "DataDecl" A.toDataDecl A.fromGraphDataDecl g root (W.VNode 26 [expectString ((11) * 7 + 1), expectList (\z -> expectString (z)) ((11) * 7 + 2), expectList (\z -> expectConstructorDecl (z)) ((11) * 7 + 3)]),
  \g root -> checkGraph "DataDeclK" A.toDataDecl A.fromGraphDataDecl g root (W.VNode 27 [expectString ((12) * 7 + 1), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectKind ((z) * 5 + 2)]) ((12) * 7 + 2), expectList (\z -> expectConstructorDecl (z)) ((12) * 7 + 3)]),
  \g root -> checkGraph "XTyVar" A.toXTyVar A.fromGraphXTyVar g root (W.VNode 30 [expectInt ((13) * 7 + 1)]),
  \g root -> checkGraph "XName" A.toXName A.fromGraphXName g root (W.VNode 31 [expectInt ((14) * 7 + 1), expectString ((14) * 7 + 2)]),
  \g root -> checkGraph "XVar" A.toXType A.fromGraphXType g root (W.VNode 40 [expectXTyVar ((15) * 7 + 1)]),
  \g root -> checkGraph "XBot" A.toXType A.fromGraphXType g root (W.VNode 41 []),
  \g root -> checkGraph "XBotKind" A.toXType A.fromGraphXType g root (W.VNode 42 [expectKind ((17) * 7 + 1)]),
  \g root -> checkGraph "XArrow" A.toXType A.fromGraphXType g root (W.VNode 43 [expectXType ((18) * 7 + 1), expectXType ((18) * 7 + 2)]),
  \g root -> checkGraph "XCon" A.toXType A.fromGraphXType g root (W.VNode 44 [expectString ((19) * 7 + 1), expectList (\z -> expectXType (z)) ((19) * 7 + 2)]),
  \g root -> checkGraph "XApply" A.toXType A.fromGraphXType g root (W.VNode 45 [expectXType ((20) * 7 + 1), expectXType ((20) * 7 + 2)]),
  \g root -> checkGraph "XForall" A.toXType A.fromGraphXType g root (W.VNode 46 [expectXTyVar ((21) * 7 + 1), expectXType ((21) * 7 + 2), expectXType ((21) * 7 + 3)]),
  \g root -> checkGraph "XRefl" A.toXComputation A.fromGraphXComputation g root (W.VNode 50 []),
  \g root -> checkGraph "XBottom" A.toXComputation A.fromGraphXComputation g root (W.VNode 51 [expectXType ((23) * 7 + 1)]),
  \g root -> checkGraph "XHyp" A.toXComputation A.fromGraphXComputation g root (W.VNode 52 [expectXTyVar ((24) * 7 + 1)]),
  \g root -> checkGraph "XInner" A.toXComputation A.fromGraphXComputation g root (W.VNode 53 [expectXComputation ((25) * 7 + 1)]),
  \g root -> checkGraph "XOuter" A.toXComputation A.fromGraphXComputation g root (W.VNode 54 [expectXTyVar ((26) * 7 + 1), expectXComputation ((26) * 7 + 2)]),
  \g root -> checkGraph "XElim" A.toXComputation A.fromGraphXComputation g root (W.VNode 55 []),
  \g root -> checkGraph "XIntro" A.toXComputation A.fromGraphXComputation g root (W.VNode 56 [expectXTyVar ((28) * 7 + 1)]),
  \g root -> checkGraph "XIntroKind" A.toXComputation A.fromGraphXComputation g root (W.VNode 57 [expectXTyVar ((29) * 7 + 1), expectKind ((29) * 7 + 2)]),
  \g root -> checkGraph "XThen" A.toXComputation A.fromGraphXComputation g root (W.VNode 58 [expectXComputation ((30) * 7 + 1), expectXComputation ((30) * 7 + 2)]),
  \g root -> checkGraph "XVarTerm" A.toXTerm A.fromGraphXTerm g root (W.VNode 70 [expectXName ((31) * 7 + 1)]),
  \g root -> checkGraph "XAbs" A.toXTerm A.fromGraphXTerm g root (W.VNode 71 [expectXName ((32) * 7 + 1), expectXType ((32) * 7 + 2), expectXTerm ((32) * 7 + 3)]),
  \g root -> checkGraph "XApp" A.toXTerm A.fromGraphXTerm g root (W.VNode 72 [expectXTerm ((33) * 7 + 1), expectXTerm ((33) * 7 + 2)]),
  \g root -> checkGraph "XTypeAbs" A.toXTerm A.fromGraphXTerm g root (W.VNode 73 [expectXTyVar ((34) * 7 + 1), expectXType ((34) * 7 + 2), expectXTerm ((34) * 7 + 3)]),
  \g root -> checkGraph "XTypeApp" A.toXTerm A.fromGraphXTerm g root (W.VNode 74 [expectXTerm ((35) * 7 + 1), expectXComputation ((35) * 7 + 2)]),
  \g root -> checkGraph "XLet" A.toXTerm A.fromGraphXTerm g root (W.VNode 75 [expectXName ((36) * 7 + 1), expectXTerm ((36) * 7 + 2), expectXTerm ((36) * 7 + 3)]),
  \g root -> checkGraph "XLetRec" A.toXTerm A.fromGraphXTerm g root (W.VNode 76 [expectList (\z -> W.VNode 3 [expectXName ((z) * 5 + 1), expectXType ((z) * 5 + 2), expectXTerm ((z) * 5 + 3)]) ((37) * 7 + 1), expectXTerm ((37) * 7 + 2)]),
  \g root -> checkGraph "XIntTerm" A.toXTerm A.fromGraphXTerm g root (W.VNode 77 [expectInt ((38) * 7 + 1)]),
  \g root -> checkGraph "XDoubleTerm" A.toXTerm A.fromGraphXTerm g root (W.VNode 78 [expectDouble ((39) * 7 + 1)]),
  \g root -> checkGraph "XBoolTerm" A.toXTerm A.fromGraphXTerm g root (W.VNode 79 [expectBool ((40) * 7 + 1)]),
  \g root -> checkGraph "XStringTerm" A.toXTerm A.fromGraphXTerm g root (W.VNode 80 [expectString ((41) * 7 + 1)]),
  \g root -> checkGraph "XPrimitive" A.toXTerm A.fromGraphXTerm g root (W.VNode 81 [expectPrimitive ((42) * 7 + 1), expectList (\z -> expectXType (z)) ((42) * 7 + 2)]),
  \g root -> checkGraph "XConstructor" A.toXTerm A.fromGraphXTerm g root (W.VNode 82 [expectString ((43) * 7 + 1), expectList (\z -> expectXType (z)) ((43) * 7 + 2)]),
  \g root -> checkGraph "XCase" A.toXTerm A.fromGraphXTerm g root (W.VNode 83 [expectXTerm ((44) * 7 + 1), expectXType ((44) * 7 + 2), expectList (\z -> expectXAlternative (z)) ((44) * 7 + 3)]),
  \g root -> checkGraph "XWithData" A.toXTerm A.fromGraphXTerm g root (W.VNode 84 [expectList (\z -> expectDataDecl (z)) ((45) * 7 + 1), expectXTerm ((45) * 7 + 2)]),
  \g root -> checkGraph "XConstructorPattern" A.toXPattern A.fromGraphXPattern g root (W.VNode 90 [expectString ((46) * 7 + 1), expectList (\z -> expectMaybe (\z -> expectXName (z)) (z)) ((46) * 7 + 2)]),
  \g root -> checkGraph "XDefaultPattern" A.toXPattern A.fromGraphXPattern g root (W.VNode 91 [expectMaybe (\z -> expectXName (z)) ((47) * 7 + 1)]),
  \g root -> checkGraph "XAlternative" A.toXAlternative A.fromGraphXAlternative g root (W.VNode 92 [expectXPattern ((48) * 7 + 1), expectXTerm ((48) * 7 + 2)]),
  \g root -> checkGraph "STVar" A.toSType A.fromGraphSType g root (W.VNode 100 [expectString ((49) * 7 + 1)]),
  \g root -> checkGraph "SBottom" A.toSType A.fromGraphSType g root (W.VNode 101 []),
  \g root -> checkGraph "SBottomKind" A.toSType A.fromGraphSType g root (W.VNode 102 [expectKind ((51) * 7 + 1)]),
  \g root -> checkGraph "SArrow" A.toSType A.fromGraphSType g root (W.VNode 103 [expectSType ((52) * 7 + 1), expectSType ((52) * 7 + 2)]),
  \g root -> checkGraph "SCon" A.toSType A.fromGraphSType g root (W.VNode 104 [expectString ((53) * 7 + 1), expectList (\z -> expectSType (z)) ((53) * 7 + 2)]),
  \g root -> checkGraph "STypeApp" A.toSType A.fromGraphSType g root (W.VNode 105 [expectSType ((54) * 7 + 1), expectSType ((54) * 7 + 2)]),
  \g root -> checkGraph "SForall" A.toSType A.fromGraphSType g root (W.VNode 106 [expectFlag ((55) * 7 + 1), expectString ((55) * 7 + 2), expectSType ((55) * 7 + 3), expectSType ((55) * 7 + 4)]),
  \g root -> checkGraph "SQualified" A.toSType A.fromGraphSType g root (W.VNode 107 [expectList (\z -> expectSPredicate (z)) ((56) * 7 + 1), expectSType ((56) * 7 + 2)]),
  \g root -> checkGraph "SAnnotation" A.toSAnnotation A.fromGraphSAnnotation g root (W.VNode 110 [expectList (\z -> expectString (z)) ((57) * 7 + 1), expectSType ((57) * 7 + 2)]),
  \g root -> checkGraph "InferRecursive" A.toRecursiveMode A.fromGraphRecursiveMode g root (W.VNode 111 []),
  \g root -> checkGraph "CheckRecursive" A.toRecursiveMode A.fromGraphRecursiveMode g root (W.VNode 112 [expectSAnnotation ((59) * 7 + 1)]),
  \g root -> checkGraph "SourceSpan" A.toSourceSpan A.fromGraphSourceSpan g root (W.VNode 113 [expectString ((60) * 7 + 1), expectString ((60) * 7 + 2), expectString ((60) * 7 + 3), expectInt ((60) * 7 + 4), expectInt ((60) * 7 + 5), expectInt ((60) * 7 + 6), expectInt ((60) * 7 + 7)]),
  \g root -> checkGraph "ScalarString" A.toSourceString A.fromGraphSourceString g root (W.VNode 114 [expectString ((61) * 7 + 1)]),
  \g root -> checkGraph "CharString" A.toSourceString A.fromGraphSourceString g root (W.VNode 115 [expectList (\z -> expectInt (z)) ((62) * 7 + 1)]),
  \g root -> checkGraph "GivenEvidence" A.toEvidenceRole A.fromGraphEvidenceRole g root (W.VNode 116 []),
  \g root -> checkGraph "SuperclassEvidence" A.toEvidenceRole A.fromGraphEvidenceRole g root (W.VNode 117 []),
  \g root -> checkGraph "InstanceEvidence" A.toEvidenceRole A.fromGraphEvidenceRole g root (W.VNode 118 []),
  \g root -> checkGraph "SVar" A.toSExpr A.fromGraphSExpr g root (W.VNode 120 [expectString ((66) * 7 + 1)]),
  \g root -> checkGraph "SConstructor" A.toSExpr A.fromGraphSExpr g root (W.VNode 121 [expectString ((67) * 7 + 1)]),
  \g root -> checkGraph "SLam" A.toSExpr A.fromGraphSExpr g root (W.VNode 122 [expectString ((68) * 7 + 1), expectMaybe (\z -> expectSAnnotation (z)) ((68) * 7 + 2), expectSExpr ((68) * 7 + 3)]),
  \g root -> checkGraph "SApp" A.toSExpr A.fromGraphSExpr g root (W.VNode 123 [expectSExpr ((69) * 7 + 1), expectSExpr ((69) * 7 + 2)]),
  \g root -> checkGraph "SLet" A.toSExpr A.fromGraphSExpr g root (W.VNode 124 [expectString ((70) * 7 + 1), expectSExpr ((70) * 7 + 2), expectSExpr ((70) * 7 + 3)]),
  \g root -> checkGraph "SAnn" A.toSExpr A.fromGraphSExpr g root (W.VNode 125 [expectSExpr ((71) * 7 + 1), expectSAnnotation ((71) * 7 + 2)]),
  \g root -> checkGraph "SSignature" A.toSExpr A.fromGraphSExpr g root (W.VNode 126 [expectSExpr ((72) * 7 + 1), expectSAnnotation ((72) * 7 + 2)]),
  \g root -> checkGraph "SIntLit" A.toSExpr A.fromGraphSExpr g root (W.VNode 127 [expectInt ((73) * 7 + 1)]),
  \g root -> checkGraph "SDoubleLit" A.toSExpr A.fromGraphSExpr g root (W.VNode 128 [expectDouble ((74) * 7 + 1)]),
  \g root -> checkGraph "SBoolLit" A.toSExpr A.fromGraphSExpr g root (W.VNode 129 [expectBool ((75) * 7 + 1)]),
  \g root -> checkGraph "SStringLit" A.toSExpr A.fromGraphSExpr g root (W.VNode 130 [expectString ((76) * 7 + 1)]),
  \g root -> checkGraph "SPrimitive" A.toSExpr A.fromGraphSExpr g root (W.VNode 131 [expectPrimitive ((77) * 7 + 1)]),
  \g root -> checkGraph "SCase" A.toSExpr A.fromGraphSExpr g root (W.VNode 132 [expectSExpr ((78) * 7 + 1), expectList (\z -> expectSAlternative (z)) ((78) * 7 + 2)]),
  \g root -> checkGraph "SDo" A.toSExpr A.fromGraphSExpr g root (W.VNode 133 [expectList (\z -> expectSStatement (z)) ((79) * 7 + 1), expectSExpr ((79) * 7 + 2)]),
  \g root -> checkGraph "SEquations" A.toSExpr A.fromGraphSExpr g root (W.VNode 134 [expectList (\z -> W.VNode 2 [expectList (\z -> expectSPattern (z)) ((z) * 5 + 1), expectSExpr ((z) * 5 + 2)]) ((80) * 7 + 1)]),
  \g root -> checkGraph "SLetRec" A.toSExpr A.fromGraphSExpr g root (W.VNode 135 [expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectRecursiveMode ((z) * 5 + 2), expectSExpr ((z) * 5 + 3)]) ((81) * 7 + 1), expectSExpr ((81) * 7 + 2)]),
  \g root -> checkGraph "SWanted" A.toSExpr A.fromGraphSExpr g root (W.VNode 136 [expectString ((82) * 7 + 1), expectList (\z -> W.VNode 2 [expectEvidenceRole ((z) * 5 + 1), expectString ((z) * 5 + 2)]) ((82) * 7 + 2)]),
  \g root -> checkGraph "SChecked" A.toSExpr A.fromGraphSExpr g root (W.VNode 137 [expectSType ((83) * 7 + 1), expectSExpr ((83) * 7 + 2)]),
  \g root -> checkGraph "SSourceDefinition" A.toSExpr A.fromGraphSExpr g root (W.VNode 138 [expectSExpr ((84) * 7 + 1)]),
  \g root -> checkGraph "SCallSite" A.toSExpr A.fromGraphSExpr g root (W.VNode 139 [expectString ((85) * 7 + 1), expectSourceSpan ((85) * 7 + 2), expectSExpr ((85) * 7 + 3)]),
  \g root -> checkGraph "SSharedBind" A.toSExpr A.fromGraphSExpr g root (W.VNode 140 [expectSPattern ((86) * 7 + 1), expectSExpr ((86) * 7 + 2), expectSExpr ((86) * 7 + 3), expectSExpr ((86) * 7 + 4), expectSExpr ((86) * 7 + 5)]),
  \g root -> checkGraph "SConstructorPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 150 [expectString ((87) * 7 + 1), expectList (\z -> expectMaybe (\z -> expectString (z)) (z)) ((87) * 7 + 2)]),
  \g root -> checkGraph "SDefaultPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 151 [expectMaybe (\z -> expectString (z)) ((88) * 7 + 1)]),
  \g root -> checkGraph "SNestedPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 152 [expectString ((89) * 7 + 1), expectList (\z -> expectSPattern (z)) ((89) * 7 + 2)]),
  \g root -> checkGraph "SAnnotatedPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 153 [expectString ((90) * 7 + 1), expectSAnnotation ((90) * 7 + 2)]),
  \g root -> checkGraph "SIntPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 154 [expectInt ((91) * 7 + 1)]),
  \g root -> checkGraph "SStringPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 155 [expectString ((92) * 7 + 1)]),
  \g root -> checkGraph "SOverloadedStringPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 156 [expectSourceString ((93) * 7 + 1), expectString ((93) * 7 + 2), expectString ((93) * 7 + 3)]),
  \g root -> checkGraph "SBoolPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 157 [expectBool ((94) * 7 + 1)]),
  \g root -> checkGraph "SAsPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 158 [expectString ((95) * 7 + 1), expectSPattern ((95) * 7 + 2)]),
  \g root -> checkGraph "SLazyPattern" A.toSPattern A.fromGraphSPattern g root (W.VNode 159 [expectSPattern ((96) * 7 + 1)]),
  \g root -> checkGraph "SAlternative" A.toSAlternative A.fromGraphSAlternative g root (W.VNode 160 [expectSPattern ((97) * 7 + 1), expectSExpr ((97) * 7 + 2)]),
  \g root -> checkGraph "SDoBind" A.toSStatement A.fromGraphSStatement g root (W.VNode 161 [expectSPattern ((98) * 7 + 1), expectSExpr ((98) * 7 + 2)]),
  \g root -> checkGraph "SDoThen" A.toSStatement A.fromGraphSStatement g root (W.VNode 162 [expectSExpr ((99) * 7 + 1)]),
  \g root -> checkGraph "SDoLet" A.toSStatement A.fromGraphSStatement g root (W.VNode 163 [expectString ((100) * 7 + 1), expectMaybe (\z -> expectSAnnotation (z)) ((100) * 7 + 2), expectSExpr ((100) * 7 + 3)]),
  \g root -> checkGraph "SDoLetRec" A.toSStatement A.fromGraphSStatement g root (W.VNode 164 [expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectRecursiveMode ((z) * 5 + 2), expectSExpr ((z) * 5 + 3)]) ((101) * 7 + 1)]),
  \g root -> checkGraph "SPredicate" A.toSPredicate A.fromGraphSPredicate g root (W.VNode 170 [expectString ((102) * 7 + 1), expectList (\z -> expectSType (z)) ((102) * 7 + 2)]),
  \g root -> checkGraph "SClassDecl" A.toSClassDecl A.fromGraphSClassDecl g root (W.VNode 171 [expectString ((103) * 7 + 1), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectKind ((z) * 5 + 2)]) ((103) * 7 + 2), expectList (\z -> expectSPredicate (z)) ((103) * 7 + 3), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectSType ((z) * 5 + 2)]) ((103) * 7 + 4)]),
  \g root -> checkGraph "SInstanceDecl" A.toSInstanceDecl A.fromGraphSInstanceDecl g root (W.VNode 172 [expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectKind ((z) * 5 + 2)]) ((104) * 7 + 1), expectList (\z -> expectSPredicate (z)) ((104) * 7 + 2), expectString ((104) * 7 + 3), expectList (\z -> expectSType (z)) ((104) * 7 + 4), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectSExpr ((z) * 5 + 2)]) ((104) * 7 + 5)]),
  \g root -> checkGraph "Modules.Value" A.toRole A.fromGraphRole g root (W.VNode 180 []),
  \g root -> checkGraph "Modules.Datatype" A.toRole A.fromGraphRole g root (W.VNode 181 []),
  \g root -> checkGraph "Modules.Class" A.toRole A.fromGraphRole g root (W.VNode 182 []),
  \g root -> checkGraph "Modules.Constructor" A.toRole A.fromGraphRole g root (W.VNode 183 [expectString ((108) * 7 + 1)]),
  \g root -> checkGraph "Modules.Method" A.toRole A.fromGraphRole g root (W.VNode 184 [expectString ((109) * 7 + 1)]),
  \g root -> checkGraph "Modules.BuiltinType" A.toRole A.fromGraphRole g root (W.VNode 185 []),
  \g root -> checkGraph "Modules.Primitive" A.toRole A.fromGraphRole g root (W.VNode 186 [expectPrimitive ((111) * 7 + 1)]),
  \g root -> checkGraph "Modules.Boolean" A.toRole A.fromGraphRole g root (W.VNode 187 [expectBool ((112) * 7 + 1)]),
  \g root -> checkGraph "Modules.ManagedConstraint" A.toRole A.fromGraphRole g root (W.VNode 188 []),
  \g root -> checkGraph "Modules.Entity" A.toEntity A.fromGraphEntity g root (W.VNode 189 [expectString ((114) * 7 + 1), expectString ((114) * 7 + 2), expectRole ((114) * 7 + 3)]),
  \g root -> checkGraph "LegacyEmlfV1" A.toSourceSyntax A.fromGraphSourceSyntax g root (W.VNode 200 []),
  \g root -> checkGraph "SharedHaskellV1" A.toSourceSyntax A.fromGraphSourceSyntax g root (W.VNode 201 []),
  \g root -> checkGraph "MetadataSyntax" A.toSourceSyntax A.fromGraphSourceSyntax g root (W.VNode 202 []),
  \g root -> checkGraph "Everything" A.toSelection A.fromGraphSelection g root (W.VNode 203 []),
  \g root -> checkGraph "Only" A.toSelection A.fromGraphSelection g root (W.VNode 204 [expectList (\z -> expectExport (z)) ((119) * 7 + 1)]),
  \g root -> checkGraph "Hiding" A.toSelection A.fromGraphSelection g root (W.VNode 205 [expectList (\z -> expectExport (z)) ((120) * 7 + 1)]),
  \g root -> checkGraph "ExportValue" A.toExport A.fromGraphExport g root (W.VNode 206 [expectString ((121) * 7 + 1)]),
  \g root -> checkGraph "ExportType" A.toExport A.fromGraphExport g root (W.VNode 207 [expectString ((122) * 7 + 1), expectMembers ((122) * 7 + 2)]),
  \g root -> checkGraph "ExportModule" A.toExport A.fromGraphExport g root (W.VNode 208 [expectString ((123) * 7 + 1)]),
  \g root -> checkGraph "Abstract" A.toMembers A.fromGraphMembers g root (W.VNode 209 []),
  \g root -> checkGraph "AllMembers" A.toMembers A.fromGraphMembers g root (W.VNode 210 []),
  \g root -> checkGraph "Members" A.toMembers A.fromGraphMembers g root (W.VNode 211 [expectList (\z -> expectString (z)) ((126) * 7 + 1)]),
  \g root -> checkGraph "Import" A.toImport A.fromGraphImport g root (W.VNode 212 [expectString ((127) * 7 + 1), expectBool ((127) * 7 + 2), expectMaybe (\z -> expectString (z)) ((127) * 7 + 3), expectSelection ((127) * 7 + 4)]),
  \g root -> checkGraph "SourceModule" A.toSourceModule A.fromGraphSourceModule g root (W.VNode 213 [expectString ((128) * 7 + 1), expectMaybe (\z -> expectString (z)) ((128) * 7 + 2), expectMaybe (\z -> expectList (\z -> expectExport (z)) (z)) ((128) * 7 + 3), expectList (\z -> expectImport (z)) ((128) * 7 + 4), expectList (\z -> expectDataDecl (z)) ((128) * 7 + 5), expectList (\z -> expectSClassDecl (z)) ((128) * 7 + 6), expectList (\z -> expectSInstanceDecl (z)) ((128) * 7 + 7), expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectMaybe (\z -> expectSAnnotation (z)) ((z) * 5 + 2), expectSExpr ((z) * 5 + 3)]) ((128) * 7 + 8), expectMaybe (\z -> expectSExpr (z)) ((128) * 7 + 9), expectSourceSyntax ((128) * 7 + 10)]),
  \g root -> checkGraph "SProgram" A.toSProgram A.fromGraphSProgram g root (W.VNode 214 [expectList (\z -> expectDataDecl (z)) ((129) * 7 + 1), expectSExpr ((129) * 7 + 2)]),
  \g root -> checkGraph "SClassProgram" A.toSProgram A.fromGraphSProgram g root (W.VNode 215 [expectList (\z -> expectDataDecl (z)) ((130) * 7 + 1), expectList (\z -> expectSClassDecl (z)) ((130) * 7 + 2), expectList (\z -> expectSInstanceDecl (z)) ((130) * 7 + 3), expectSExpr ((130) * 7 + 4)]),
  \g root -> checkGraph "Separate.UnitInterface" A.toUnitInterface A.fromGraphUnitInterface g root (W.VNode 240 [expectString ((131) * 7 + 1), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectString ((z) * 5 + 2)]) ((131) * 7 + 2), expectList (\z -> expectEntity (z)) ((131) * 7 + 3), expectList (\z -> expectDataDecl (z)) ((131) * 7 + 4), expectList (\z -> expectSClassDecl (z)) ((131) * 7 + 5), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectInterfaceInstance ((z) * 5 + 2)]) ((131) * 7 + 6), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectXType ((z) * 5 + 2)]) ((131) * 7 + 7), expectString ((131) * 7 + 8)]),
  \g root -> checkGraph "CrateInterfaceFields" A.toCrateInterfaceFields A.fromGraphCrateInterfaceFields g root (W.VNode 242 [expectString ((132) * 7 + 1), expectList (\z -> W.VNode 3 [expectString ((z) * 5 + 1), expectString ((z) * 5 + 2), expectString ((z) * 5 + 3)]) ((132) * 7 + 2), expectList (\z -> expectString (z)) ((132) * 7 + 3), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectList (\z -> expectEntity (z)) ((z) * 5 + 2)]) ((132) * 7 + 4), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectList (\z -> expectString (z)) ((z) * 5 + 2)]) ((132) * 7 + 5), expectList (\z -> expectDataDecl (z)) ((132) * 7 + 6), expectList (\z -> expectSClassDecl (z)) ((132) * 7 + 7), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectInterfaceInstance ((z) * 5 + 2)]) ((132) * 7 + 8), expectList (\z -> expectDataDecl (z)) ((132) * 7 + 9), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectXType ((z) * 5 + 2)]) ((132) * 7 + 10), expectString ((132) * 7 + 11), expectString ((132) * 7 + 12), expectList (\z -> W.VNode 2 [expectString ((z) * 5 + 1), expectBool ((z) * 5 + 2)]) ((132) * 7 + 13)]),
  \g root -> checkGraph "CrateObjectFields" A.toCrateObjectFields A.fromGraphCrateObjectFields g root (W.VNode 243 [expectBool ((133) * 7 + 1), expectCrateInterfaceFields ((133) * 7 + 2), expectList (\z -> expectRawUnitObject (z)) ((133) * 7 + 3)]),
  \g root -> checkGraph "PIOReturn" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 0]),
  \g root -> checkGraph "PIOBind" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 1]),
  \g root -> checkGraph "PPutStr" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 2]),
  \g root -> checkGraph "PPutStrLn" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 3]),
  \g root -> checkGraph "PGetLine" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 4]),
  \g root -> checkGraph "PPrintInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 5]),
  \g root -> checkGraph "PConcatString" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 6]),
  \g root -> checkGraph "PShowInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 7]),
  \g root -> checkGraph "PAddInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 8]),
  \g root -> checkGraph "PSubInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 9]),
  \g root -> checkGraph "PEqInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 10]),
  \g root -> checkGraph "PLtInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 11]),
  \g root -> checkGraph "PEqString" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 12]),
  \g root -> checkGraph "PIfThenElse" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 13]),
  \g root -> checkGraph "PMulInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 14]),
  \g root -> checkGraph "PQuotInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 15]),
  \g root -> checkGraph "PRemInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 16]),
  \g root -> checkGraph "PReadInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 17]),
  \g root -> checkGraph "PAddDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 18]),
  \g root -> checkGraph "PSubDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 19]),
  \g root -> checkGraph "PMulDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 20]),
  \g root -> checkGraph "PDivDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 21]),
  \g root -> checkGraph "PSqrtDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 22]),
  \g root -> checkGraph "PEqDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 23]),
  \g root -> checkGraph "PLtDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 24]),
  \g root -> checkGraph "PIntToDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 25]),
  \g root -> checkGraph "PFormatDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 26]),
  \g root -> checkGraph "PNewIntArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 27]),
  \g root -> checkGraph "PReadIntArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 28]),
  \g root -> checkGraph "PWriteIntArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 29]),
  \g root -> checkGraph "PLengthIntArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 30]),
  \g root -> checkGraph "PNewDoubleArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 31]),
  \g root -> checkGraph "PReadDoubleArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 32]),
  \g root -> checkGraph "PWriteDoubleArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 33]),
  \g root -> checkGraph "PLengthDoubleArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 34]),
  \g root -> checkGraph "PNewByteArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 35]),
  \g root -> checkGraph "PReadByteArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 36]),
  \g root -> checkGraph "PWriteByteArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 37]),
  \g root -> checkGraph "PLengthByteArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 38]),
  \g root -> checkGraph "PByteArrayFromString" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 39]),
  \g root -> checkGraph "PPutBytes" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 40]),
  \g root -> checkGraph "PGetByteLine" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 41]),
  \g root -> checkGraph "PNewIntTable" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 42]),
  \g root -> checkGraph "PReadIntTable" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 43]),
  \g root -> checkGraph "PWriteIntTable" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 44]),
  \g root -> checkGraph "PAndInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 45]),
  \g root -> checkGraph "PStringLength" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 46]),
  \g root -> checkGraph "PStringCodeAt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 47]),
  \g root -> checkGraph "PStringSlice" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 48]),
  \g root -> checkGraph "PStringFromCode" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 49]),
  \g root -> checkGraph "PCompareString" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 50]),
  \g root -> checkGraph "PReadDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 51]),
  \g root -> checkGraph "PDoubleToBits" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 52]),
  \g root -> checkGraph "PDoubleFromBits" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 53]),
  \g root -> checkGraph "PSeq" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 54]),
  \g root -> checkGraph "PPanic" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 55]),
  \g root -> checkGraph "PReadFile" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 56]),
  \g root -> checkGraph "PWriteFile" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 57]),
  \g root -> checkGraph "PFileExists" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 58]),
  \g root -> checkGraph "PCanonicalPath" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 59]),
  \g root -> checkGraph "PGetArgCount" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 60]),
  \g root -> checkGraph "PGetArg" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 61]),
  \g root -> checkGraph "PPutErr" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 62]),
  \g root -> checkGraph "PExitWith" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 63]),
  \g root -> checkGraph "PGetExecutablePath" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 64]),
  \g root -> checkGraph "PGetContents" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 65]),
  \g root -> checkGraph "PSTReturn" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 66]),
  \g root -> checkGraph "PSTBind" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 67]),
  \g root -> checkGraph "PRunST" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 68]),
  \g root -> checkGraph "PNewSTArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 69]),
  \g root -> checkGraph "PReadSTArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 70]),
  \g root -> checkGraph "PWriteSTArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 71]),
  \g root -> checkGraph "PLengthSTArray" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 72]),
  \g root -> checkGraph "PGetEnv" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 73]),
  \g root -> checkGraph "PSetEnv" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 74]),
  \g root -> checkGraph "PUnsetEnv" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 75]),
  \g root -> checkGraph "PRunProcess" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 76]),
  \g root -> checkGraph "PListDirectory" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 77]),
  \g root -> checkGraph "PDirectoryExists" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 78]),
  \g root -> checkGraph "PFileDigest" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 79]),
  \g root -> checkGraph "PAcquireFileLock" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 80]),
  \g root -> checkGraph "PReleaseFileLock" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 81]),
  \g root -> checkGraph "PProcessSupervisor" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 82]),
  \g root -> checkGraph "PAsyncScopeNew" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 83]),
  \g root -> checkGraph "PAsyncScopeClose" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 84]),
  \g root -> checkGraph "PAsyncNewCompletion" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 85]),
  \g root -> checkGraph "PAsyncResolveCompletion" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 86]),
  \g root -> checkGraph "PAsyncReadCompletion" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 87]),
  \g root -> checkGraph "PAsyncSubscribeCompletion" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 88]),
  \g root -> checkGraph "PAsyncSubscriptionStatus" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 89]),
  \g root -> checkGraph "PAsyncCancelSubscription" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 90]),
  \g root -> checkGraph "PAsyncStep" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 91]),
  \g root -> checkGraph "PAsyncEnqueue" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 92]),
  \g root -> checkGraph "PAsyncDelay" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 93]),
  \g root -> checkGraph "PAsyncWait" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 94]),
  \g root -> checkGraph "PTextToChars" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 95]),
  \g root -> checkGraph "PTextFromChars" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 96]),
  \g root -> checkGraph "PCharCode" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 97]),
  \g root -> checkGraph "PCharFromCode" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 98]),
  \g root -> checkGraph "PUserError" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 99]),
  \g root -> checkGraph "PIOError" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 100]),
  \g root -> checkGraph "PCatchIOError" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 101]),
  \g root -> checkGraph "PIOErrorString" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 102]),
  \g root -> checkGraph "PEmptyCallStack" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 103]),
  \g root -> checkGraph "PPushCallStack" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 104]),
  \g root -> checkGraph "PPrettyCallStack" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 105]),
  \g root -> checkGraph "PIOErrorWithStack" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 106]),
  \g root -> checkGraph "PConcatStringList" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 107]),
  \g root -> checkGraph "POrInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 108]),
  \g root -> checkGraph "PXorInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 109]),
  \g root -> checkGraph "PShiftLInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 110]),
  \g root -> checkGraph "PShiftRInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 111]),
  \g root -> checkGraph "PUnsignedShiftRInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 112]),
  \g root -> checkGraph "PCountLeadingZerosInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 113]),
  \g root -> checkGraph "PCountTrailingZerosInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 114]),
  \g root -> checkGraph "PPopCountInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 115]),
  \g root -> checkGraph "PIntToInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 116]),
  \g root -> checkGraph "PIntegerToInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 117]),
  \g root -> checkGraph "PAddInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 118]),
  \g root -> checkGraph "PSubInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 119]),
  \g root -> checkGraph "PMulInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 120]),
  \g root -> checkGraph "PQuotInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 121]),
  \g root -> checkGraph "PRemInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 122]),
  \g root -> checkGraph "PEqInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 123]),
  \g root -> checkGraph "PLtInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 124]),
  \g root -> checkGraph "PShowInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 125]),
  \g root -> checkGraph "PReadInteger" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 126]),
  \g root -> checkGraph "PIntegerToDouble" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 127]),
  \g root -> checkGraph "PUnsignedLtInt" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 128]),
  \g root -> checkGraph "PReadByteFileOrError" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 129]),
  \g root -> checkGraph "PWriteByteFileOrError" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 130]),
  \g root -> checkGraph "PByteArrayDigest" A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt 131])
  ]

checkGraph label encode decode graph root expected = do
  restored <- expect (label ++ " graph decode") (decode graph root)
  need (label ++ " graph typed semantics") (same (encode restored) expected)
  let malformed = [W.VBits 0,W.VNode 2147483647 []] ++ case expected of
        W.VNode tag children -> [W.VNode tag (children ++ [W.VInt 0])] ++ case children of
          [] -> []
          _:rest -> [W.VNode tag rest,W.VNode tag (W.VNode 2147483647 []:rest)]
        _ -> []
  badBytes <- W.encode W.defaultLimits 7 malformed >>= expect "malformed typed shapes are valid wire"
  badGraph <- W.decodeGraph W.defaultLimits 7 badBytes >>= expect "malformed typed graph wire"
  forM_ (W.graphRoots badGraph) (\index -> reject (label ++ " Graph shape rejection") (decode badGraph index))

graphConstructorTests bytes = do
  graph <- W.decodeGraph W.defaultLimits 7 bytes >>= expect "whole constructor graph"
  need "all constructor graph roots" (length (W.graphRoots graph) == length graphChecks)
  zipWithM_ (\check root -> check graph root) graphChecks (W.graphRoots graph)
  reject "negative graph index" (W.lookupGraphNode graph (-1))
  reject "out-of-range graph index" (W.lookupGraphNode graph 2147483647)

-- Hand-authored semantic edges beyond the generated closed-shape inventory.
scalarRoots = map W.VInt [-9223372036854775808,-65536,-129,-128,-1,0,1,63,64,127,128,65535,9223372036854775807]
  ++ map W.VBits [0,-9223372036854775808,1,4503599627370495,4503599627370496,4607182418800017408,9218868437227405311,9218868437227405312,-4503599627370496,9221120237041090561,9218868437227405313,-2251799813685247]
  ++ map (W.VText . B.literal) ["","\NUL","ASCII","α😀","\x7f\x80\x7ff\x800\xd7ff\xe000\xffff\x10000\x10ffff","a\NULb"]
sharedLeaf = W.VNode 31 [W.VInt (-7),W.VText "same hint\NUL😀"]
sharedRoots = [W.VNode 70 [sharedLeaf],W.VNode 72 [sharedLeaf,sharedLeaf],W.VNode 72 [sharedLeaf,sharedLeaf],W.VText "same hint\NUL😀"]

semanticEdges directory = do
  forM_ [-9223372036854775808,-1,0,1,9223372036854775807] $ \x -> do
    restored <- expect "Int64 boundary" (A.fromInt (A.toInt x)); need "Int64 exact" (restored == x)
    let name = T.XName x "full hint\NULα😀"
    decoded <- expect "full name" (A.fromXName (A.toXName name))
    case decoded of T.XName identity hint -> need "name identity and hint exact" (identity == x && hint == "full hint\NULα😀")
  forM_ [0,-9223372036854775808,1,4503599627370495,4503599627370496,9218868437227405311,9218868437227405312,-4503599627370496,9221120237041090561,9218868437227405313,-2251799813685247] $ \bits -> do
    value <- expect "IEEE decode" (A.fromDouble (W.VBits bits))
    need "IEEE exact signed bits; not numeric equality" (P.doubleToBits value == bits && same (A.toDouble value) (W.VBits bits))
    term <- expect "IEEE term decode" (A.fromXTerm (W.VNode 78 [W.VBits bits]))
    case term of T.XDoubleTerm d -> need "IEEE term exact" (P.doubleToBits d == bits); _ -> error "IEEE wrong constructor"
  forM_ [-1,132,2147483647] $ \code -> do
    let value=W.VNode 32 [W.VInt code]
    reject "unknown primitive ABI code" (A.fromPrimitive value)
    bytes <- W.encode W.defaultLimits 7 [value] >>= expect "unknown primitive is valid wire"
    graph <- W.decodeGraph W.defaultLimits 7 bytes >>= expect "unknown primitive graph"
    case W.graphRoots graph of
      [root] -> reject "unknown primitive Graph ABI code" (A.fromGraphPrimitive graph root)
      _ -> error "unknown primitive root inventory"
  reject "primitive wrong scalar" (A.fromPrimitive (W.VNode 32 [W.VBits 0]))
  need "empty Maybe" (same (A.toMaybe A.toInt T.Nothing) (W.VNode 4 []))
  need "present Maybe" (same (A.toMaybe A.toInt (T.Just 42)) (W.VNode 5 [W.VInt 42]))
  need "list order and duplicates" (same (A.toList A.toInt [2,1,2]) (W.VNode 1 [W.VInt 2,W.VInt 1,W.VInt 2]))
  _ <- checkCase "raw UnitObject" A.toRawUnitObject A.fromRawUnitObject (sampleRawUnitObject 31) (expectRawUnitObject 31)
  raw <- expect "raw unit decoder" (A.fromRawUnitObject (expectRawUnitObject 31))
  case raw of U.UnitObject _ _ -> pure (); U.CheckedUnitObject _ _ -> error "deserialized checked evidence"
  iface <- expect "interface old semantic roundtrip" (A.fromUnitInterface (A.toUnitInterface (sampleUnitInterface 31)))
  need "old interface meaning retained" (U.encodeInterface iface == U.encodeInterface (sampleUnitInterface 31))
  let original = sampleInterfaceInstance 45
  metadata <- expect "interface metadata" (A.fromInterfaceInstance (A.toInterfaceInstance original))
  need "interface body stripping matches existing contract" (same (A.toSInstanceDecl metadata) (A.toSInstanceDecl (U.stripInstance original)))
  full <- expect "full source instance" (A.fromSInstanceDecl (A.toSInstanceDecl original))
  need "full source method bodies survive" (same (A.toSInstanceDecl full) (A.toSInstanceDecl original))
  reject "fullsource tag not interface metadata" (A.fromInterfaceInstance (A.toSInstanceDecl original))
  reject "interface metadata tag not fullsource" (A.fromSInstanceDecl (A.toInterfaceInstance original))
  forM_ [False,True] $ \legacy -> do
    let value = A.CrateObjectFields legacy (sampleCrateInterfaceFields 9) [sampleRawUnitObject 1,sampleRawUnitObject 2]
    restored <- expect "legacy/modern crate flag" (A.fromCrateObjectFields (A.toCrateObjectFields value))
    case restored of A.CrateObjectFields actual _ _ -> need "crate variant exact" (actual == legacy)
  let ds = [sampleDataDecl 1,sampleDataDecl 2,sampleDataDecl 1]
  context <- expect "data context" (A.fromDataContext (A.toDataContext ds))
  need "context order and duplicates" (same (A.toDataContext context) (W.VNode 244 [W.VNode 1 (map A.toDataDecl ds)]))
  contextBytes <- W.encode W.defaultLimits 1 [A.toDataContext ds] >>= expect "DataContext schema1 encode"
  contextGraph <- W.decodeGraph W.defaultLimits 1 contextBytes >>= expect "DataContext schema1 Graph"
  case W.graphRoots contextGraph of
    [root] -> do
      restored <- expect "Graph DataContext typed adapter" (A.fromGraphDataContext contextGraph root)
      need "Graph DataContext order and duplicates" (same (A.toDataContext restored) (A.toDataContext ds))
    _ -> error "DataContext one-root family contract"

  -- Invalid Unicode is never normalized to replacement characters.
  forM_ [0xd800,0xdfff] $ \point -> do
    result <- try (evaluate (B.literal [toEnum point])) :: IO (Either B.HostError P.String)
    case result of
      Left (B.HostError message) -> need "surrogate rejected at existing scalar constructor" (message == "invalid Unicode scalar")
      Right _ -> error "surrogate scalar constructed"
  wireCheck (directory ++ "/scalars.bin") scalarRoots
  scalarBytes <- readBounded (directory ++ "/scalars.bin")
  scalarGraph <- W.decodeGraph W.defaultLimits 7 scalarBytes >>= expect "scalar Graph fixture"
  need "all scalar Graph roots retained" (length (W.graphRoots scalarGraph) == length scalarRoots)
  zipWithM_ (\root value -> case value of
    W.VInt number -> do
      actual <- expect "Graph Int64 boundary" (A.fromGraphInt scalarGraph root)
      need "Graph exact Int64" (actual == number)
    W.VBits bits -> do
      actual <- expect "Graph IEEE boundary" (A.fromGraphDouble scalarGraph root)
      need "Graph exact IEEE bits" (P.doubleToBits actual == bits)
    W.VText text -> do
      actual <- expect "Graph Unicode boundary" (A.fromGraphText scalarGraph root)
      need "Graph exact scalar text" (actual == text)
    _ -> error "unexpected scalar fixture constructor") (W.graphRoots scalarGraph) scalarRoots
  wireCheck (directory ++ "/sharing.bin") sharedRoots

readBounded path = do
  (diagnostic,bytes) <- P.readByteFileOrError (B.literal path) (256*1024*1024)
  need ("fixture input " ++ path ++ ": " ++ B.unpack diagnostic) (diagnostic == "")
  pure bytes
splitTabs line = case break (=='\t') line of (a,[]) -> [a]; (a,_:b) -> a:splitTabs b
wireCorpus manifest = do
  bytes <- P.newByteArray 5 0
  let value = B.literal "Aé"; W.Read parse = W.getUtf8 3
  end <- W.putText bytes 3 value 0
  need "unaligned UTF-8 write extent" (end == 27)
  result <- parse (W.Cursor bytes 3 end) >>= expect "unaligned UTF-8 read"
  case result of
    (text,W.Cursor _ next _) -> need "unaligned UTF-8 roundtrip" (text == value && next == end)
  -- A poisoned suffix makes backward scanning observable without large
  -- allocations. The first invalid scalar must fail before touching it.
  prefixBytes <- fromBytes [128,32,255]
  let W.Read readSymbols = W.getSymbols W.defaultLimits 1
  rejected <- readSymbols (W.Cursor prefixBytes 0 (4098 * 8))
  case rejected of
    T.Left msg -> need "invalid prefix short circuits symbol allocation" (msg == "invalid binary UTF-8 leading byte")
    T.Right _ -> error "invalid symbol prefix admitted"
  input <- readFile manifest
  forM_ (lines input) $ \line -> case splitTabs line of
    [name,path,expected,schema,b,s,one,total,n,e,d,w] -> do
      bytes <- readBounded path
      result <- W.decode (W.Limits (read b) (read s) (read one) (read total) (read n) (read e) (read d) (read w)) (read schema) bytes
      case (expected,result) of
        ("accept",T.Right values) -> do
          -- Positive corpus inputs are canonical: encoder must produce exactly
          -- these independently authored bytes under the same limits.
          again <- W.encode (W.Limits (read b) (read s) (read one) (read total) (read n) (read e) (read d) (read w)) (read schema) values >>= expect (name ++ " reencode")
          a <- byteList bytes; b2 <- byteList again; need (name ++ " canonical exact bytes") (a == b2)
        ("reject",T.Left _) -> pure ()
        _ -> error ("wire outcome disagrees with fixed oracle: " ++ name)
      graphResult <- W.decodeGraph (W.Limits (read b) (read s) (read one) (read total) (read n) (read e) (read d) (read w)) (read schema) bytes
      case (expected,graphResult,result) of
        ("accept",T.Right graph,T.Right values) -> do
          need (name ++ " graph root inventory") (length (W.graphRoots graph) == length values)
          zipWithM_ (sameGraphValue graph) (W.graphRoots graph) values
        ("reject",T.Left _,T.Left _) -> pure ()
        _ -> error ("graph decoder outcome disagrees with fixed oracle: " ++ name)
      let hints = [B.literal (replicate 1100 'A')]
      hinted <- W.decodeGraphWithText hints (W.Limits (read b) (read s) (read one) (read total) (read n) (read e) (read d) (read w)) (read schema) bytes
      case (result,hinted) of
        (T.Right values,T.Right graph) -> do
          need (name ++ " hinted graph roots") (length values == length (W.graphRoots graph))
          zipWithM_ (sameGraphValue graph) (W.graphRoots graph) values
        (T.Left ordinary,T.Left withHint) -> need (name ++ " hinted rejection") (ordinary == withHint)
        _ -> error ("hint changed wire admission: " ++ name)
      putStrLn ("PASS " ++ name)
    _ -> error "bad corpus manifest shape"

sameGraphValue graph index value = do
  node <- expect "graph child lookup" (W.lookupGraphNode graph index)
  case (node,value) of
    (W.GInt a,W.VInt b) -> need "graph int bits" (a == b)
    (W.GBits a,W.VBits b) -> need "graph raw bits" (a == b)
    (W.GText a,W.VText b) -> need "graph text scalar bytes" (a == b)
    (W.GNode a xs,W.VNode b ys) -> do
      need "graph node tag/arity" (a == b && length xs == length ys)
      zipWithM_ (sameGraphValue graph) xs ys
    _ -> error "graph node kind disagrees with Value decode"


rawIO directory = do
  exists <- doesPathExist directory; need "fresh raw fixture directory" (not exists); createDirectory directory
  empty <- fromBytes []
  bytes <- fromBytes [0..255]
  let p x = B.literal (directory ++ "/" ++ x)
      readOK label path limit expected = do
        (diagnostic,array) <- P.readByteFileOrError path limit
        actual <- byteList array
        need label (diagnostic == "" && actual == expected)
      readBad label path limit expected = do
        (diagnostic,array) <- P.readByteFileOrError path limit
        actual <- byteList array
        need label (diagnostic == expected && null actual)
  saveBytes (directory ++ "/empty.bin") empty
  saveBytes (directory ++ "/allbytes.bin") bytes
  readOK "empty with zero limit" (p "empty.bin") 0 []
  readOK "all raw byte values exact boundary" (p "allbytes.bin") 256 [0..255]
  readOK "raw exact larger limit" (p "allbytes.bin") 257 [0..255]
  readBad "nonempty zero cap" (p "allbytes.bin") 0 "byte file exceeds limit"
  readBad "discard partial read" (p "allbytes.bin") 255 "byte file exceeds limit"
  readBad "missing path diagnostic" (p "missing.bin") 256 "IO error: byte file read failed"
  readBad "negative limit" (p "allbytes.bin") (-1) "invalid byte file limit"
  readBad "overflow-prone limit" (p "allbytes.bin") 9223372036854775807 "invalid byte file limit"
  readBad "path NUL has priority" (p "allbytes.bin\NULsuffix") (-1) "file path contains NUL"
  diagnostic <- P.writeByteFileOrError (p "nul-created.bin\NULsuffix") bytes
  need "write NUL diagnostic" (diagnostic == "file path contains NUL")
  nulExists <- doesPathExist (directory ++ "/nul-created.bin"); need "NUL path not truncated/opened" (not nulExists)
  noParent <- P.writeByteFileOrError (p "missing-parent/file") bytes
  need "missing parent write ordinary failure" (noParent == "IO error: byte file write failed")
  directoryFailure <- P.writeByteFileOrError (B.literal directory) bytes
  need "directory write ordinary failure" (directoryFailure == "IO error: byte file write failed")
  digestEmpty <- P.byteArrayDigest empty
  digestAll <- P.byteArrayDigest bytes
  P.writeByteArray bytes 0 255
  changed <- P.byteArrayDigest bytes
  saveBytes (directory ++ "/changed.bin") bytes
  writeFile (directory ++ "/digests.tsv") ("empty.bin\t" ++ B.unpack digestEmpty ++ "\nallbytes.bin\t" ++ B.unpack digestAll ++ "\nchanged.bin\t" ++ B.unpack changed ++ "\n")
  forM_ [1,55,56,63,64,65,127,128,129,4095,4096,4097] $ \size -> do
    boundary <- fromBytes [i `mod` 256 | i <- [0..size-1]]
    let leaf="sha-" ++ show size ++ ".bin"
    saveBytes (directory ++ "/" ++ leaf) boundary
    fingerprint <- P.byteArrayDigest boundary
    appendFile (directory ++ "/digests.tsv") (leaf ++ "\t" ++ B.unpack fingerprint ++ "\n")
  need "digest changes with mutable byte snapshot" (digestAll /= changed)
  -- Snapshot digest must not depend on the current contents of the source path.
  saveBytes (directory ++ "/allbytes.bin") empty
  retained <- P.byteArrayDigest bytes
  need "byte digest is array snapshot not reopened path" (retained == changed)
  saveBytes (directory ++ "/allbytes.bin") =<< fromBytes [0..255]
  putStrLn "PASS raw-byte-io-and-digest"

partialWrite sink = do
  bytes <- P.newByteArray 8192 255
  diagnostic <- P.writeByteFileOrError (B.literal sink) bytes
  need "short write or close failure must not report success" (diagnostic == "IO error: byte file write failed")
  putStrLn "PASS raw-write-failure"

main = do
  args <- getArgs
  case args of
    ["constructors",directory] -> do
      exists <- doesPathExist directory; need "fresh constructor directory" (not exists); createDirectory directory
      roots <- constructorTests
      wireCheck (directory ++ "/constructors.bin") roots
      readBounded (directory ++ "/constructors.bin") >>= graphConstructorTests
      semanticEdges directory
      putStrLn ("PASS constructors " ++ show (length roots))
    ["source-admission",directory] -> sourceAdmissionTests directory
    ["admission"] -> admissionTests
    ["base64",directory] -> base64Tests directory
    ["lowered-query",directory,resultFile,value] -> loweredQuery directory resultFile (read value)
    ["lowered-legacy",path,version] -> loweredLegacy path version
    ["distribution-seed",directory] -> distributionSeed directory
    ["release-builtin-branches",directory] -> releaseBuiltinBranches directory
    ["release-forged-current",directory] -> releaseForgedCurrent directory
    ["release-materialize",directory,digest,cache,compiler] ->
      Release.materializePinned (B.literal directory) (B.literal digest) (B.literal cache) (B.literal compiler) True >>= putStrLn . B.unpack
    ["distribution-pack",directory,asset] -> Distribution.pack (B.literal directory) (B.literal asset) >>= putStrLn . B.unpack . Json.render
    ["distribution-unpack",asset,destination,expectedSHA] -> Distribution.unpack (B.literal asset) (B.literal destination) (B.literal expectedSHA) >>= putStrLn . B.unpack . Json.render
    ["distribution-asset",path,expectedSHA,expected] -> do
      actual <- Distribution.validAsset (B.literal path) (B.literal expectedSHA)
      need "actual release asset SHA pin" (actual == (expected == "valid"))
      putStrLn "PASS distribution-asset-pin"
    ["formal-check",prefix,expected] -> formalCheck prefix expected
    ["typed-bounds",directory] -> typedBounds directory
    ["wire-corpus",manifest] -> wireCorpus manifest
    ["raw-io",directory] -> rawIO directory
    ["partial-write",sink] -> partialWrite sink
    _ -> error "expected constructors DIR | wire-corpus MANIFEST | raw-io DIR | partial-write FAILURE-SINK"

-- Finite stress cases cover the *typed* graph boundary, not just wire parsing.
-- They intentionally do not imply the old semantic fingerprinting pass is O(DAG).
typedBounds directory = do
  exists <- doesPathExist directory; need "fresh typed bounds directory" (not exists); createDirectory directory
  let wide = W.VNode 1 [W.VText (B.literal ("field-" ++ show i)) | i <- [0..4095 :: Int]]
      chain 0 = W.VNode 10 []
      chain depth = W.VNode 11 [W.VNode 10 [],chain (depth-1)]
      bomb 0 = W.VNode 10 []
      bomb depth = let child=bomb (depth-1) in W.VNode 11 [child,child]
      graphFrom limits value = do
        bytes <- W.encode limits 7 [value] >>= expect "typed stress encode"
        graph <- W.decodeGraph limits 7 bytes >>= expect "typed stress graph decode"
        root <- case W.graphRoots graph of [r] -> pure r; _ -> error "typed stress roots"
        pure (bytes,graph,root)
  (wideBytes,wideGraph,wideRoot) <- graphFrom W.defaultLimits wide
  strings <- expect "wide typed list" (A.fromGraphTextList wideGraph wideRoot)
  need "wide list exact length/order" (map B.unpack strings == ["field-" ++ show i | i <- [0..4095 :: Int]])
  saveBytes (directory ++ "/wide.bin") wideBytes
  let deep=chain (2048 :: Int)
  (deepBytes,deepGraph,deepRoot) <- graphFrom W.defaultLimits deep
  kind <- expect "deep typed Kind" (A.fromGraphKind deepGraph deepRoot)
  let depth T.Star = 0 :: Int
      depth (T.KArrow T.Star rest) = 1 + depth rest
      depth _ = error "deep Kind shape changed"
  need "deep typed chain survives" (depth kind == 2048)
  direct <- expect "deep Value adapter explicit stack" (A.fromKind deep)
  need "deep Value adapter result" (depth direct == 2048)
  saveBytes (directory ++ "/deep.bin") deepBytes
  let limits=W.Limits 1048576 16 1024 4096 64 128 64 524287
      tooSmall=W.Limits 1048576 16 1024 4096 64 128 64 524286
      exponential=bomb (18 :: Int)
  (bombBytes,bombGraph,bombRoot) <- graphFrom limits exponential
  W.decodeGraph tooSmall 7 bombBytes >>= reject "typed graph exponential work preflight"
  W.decode tooSmall 7 bombBytes >>= reject "Value decode same exponential work preflight"
  shared <- expect "typed graph bounded KArrow DAG" (A.fromGraphKind bombGraph bombRoot)
  let sharing 0 T.Star = pure ()
      sharing remaining (T.KArrow a b) = do
        a' <- evaluate a; b' <- evaluate b
        left <- makeStableName a'; right <- makeStableName b'
        need "Graph decoder retains raw syntax child identity" (eqStableName left right)
        sharing (remaining-1) a'
      sharing _ _ = error "typed shared Kind shape changed"
  sharing (18 :: Int) shared
  saveBytes (directory ++ "/exponential.bin") bombBytes
  let rawValue=W.VNode 241 [expectUnitInterface 1, W.VNode 77 [W.VInt 1]]
  (_,rawGraph,rawRoot) <- graphFrom W.defaultLimits rawValue
  raw <- expect "typed graph raw unit" (A.fromGraphRawUnitObject rawGraph rawRoot)
  case raw of U.UnitObject _ _ -> pure (); U.CheckedUnitObject _ _ -> error "Graph reused/deserialized proof evidence"
  putStrLn "PASS typed-wide-deep-shared-raw"

base64Tests directory = do
  exists <- doesPathExist directory; need "fresh base64 directory" (not exists); createDirectory directory
  forM_ [("",""),("f","Zg=="),("fo","Zm8="),("foo","Zm9v"),("foob","Zm9vYg=="),("fooba","Zm9vYmE="),("foobar","Zm9vYmFy")] $ \(source,expected) -> do
    bytes <- P.byteArrayFromString (B.literal source)
    encoded <- Storage.encodeBase64 bytes >>= expect "RFC4648 base64 encode"
    need "fixed RFC4648 golden" (encoded == B.literal expected)
    decoded <- Storage.decodeBase64 (B.literal expected) >>= expect "RFC4648 base64 decode"
    original <- byteList bytes; actual <- byteList decoded; need "base64 byte roundtrip" (original == actual)
  forM_ ["Z","Zg","Zg=","Zg===","Zh==","Zm9=","Zg==AAAA","Z=g=","====","____","Zg==\n","αααα","AA A"] $ \bad ->
    Storage.decodeBase64 (B.literal bad) >>= reject "noncanonical release base64"
  bytes <- fromBytes [0..255]
  encoded <- Storage.encodeBase64 bytes >>= expect "all-byte base64"
  writeFile (directory ++ "/allbytes.base64") (B.unpack encoded)
  decoded <- Storage.decodeBase64 encoded >>= expect "all-byte decode"
  actual <- byteList decoded; need "all-byte base64 exact" (actual == [0..255])
  putStrLn "PASS canonical-base64"

loweredQuery directory resultFile value = do
  let members=[("first",T.Nothing,T.SIntLit value),("second",T.Nothing,T.SIntLit 99)]
  (objects,report) <- Q.compileGroups "binary-lowered" (B.literal directory) [] [] members >>= expect "actual lowered QUERY4 driver"
  writeFile resultFile (B.unpack (U.pack (map U.encodeObject objects)))
  putStrLn (B.unpack (Q.reportJSON "binary-lowered" "test" report))

loweredLegacy path version = do
  bytes <- readBounded path
  graph <- W.decodeGraph W.defaultLimits 2 bytes >>= expect "real inline binary query"
  root <- case W.graphRoots graph of [r] -> pure r; _ -> error "inline query roots"
  node <- expect "inline query root" (W.lookupGraphNode graph root)
  (key,object) <- case node of
    W.GNode 300 [keyNode,objectNode] -> do
      key <- expect "inline full exact key" (A.fromGraphText graph keyNode)
      object <- expect "inline complete raw unit" (A.fromGraphRawUnitObject graph objectNode)
      pure (key,object)
    _ -> error "lowered driver did not write binary inline root300"
  let text=if version == "1" then U.pack ["MLF-QUERY-CACHE-1",key,U.encodeInterface (U.objectInterface object),U.encodeObject object]
           else Q.encodeCached key object
  parts <- expect "legacy query framing" (U.unpack text)
  need "exact intended old lowered query format" (case parts of tag:_ -> tag == (if version == "1" then "MLF-QUERY-CACHE-1" else "MLF-QUERY-CACHE-2"); _ -> False)
  writeFile path (B.unpack text)
  putStrLn ("PASS lowered-install-CACHE" ++ version)

formalCheck prefix expected = do
  result <- CrateArtifact.readInterface (B.literal (prefix ++ ".mlfci"))
  combined <- case result of
    T.Left message -> pure (T.Left message)
    T.Right iface -> CrateArtifact.readObject (B.literal (prefix ++ ".mlfco")) iface
  case (expected,combined) of
    ("accept",T.Right _) -> putStrLn "PASS formal-accept"
    ("reject-interface-version",T.Left message) -> do
      need "recognized interface magic uses exact binary version refusal" (message == B.literal (prefix ++ ".mlfci: unsupported binary format version"))
      putStrLn "PASS formal-interface-version-reject"
    ("reject-object-version",T.Left message) -> do
      need "recognized object magic uses exact binary version refusal" (message == B.literal (prefix ++ ".mlfco: unsupported binary format version"))
      putStrLn "PASS formal-object-version-reject"
    _ -> error "actual formal artifact reader disagrees with fixed expectation"

distributionSeed directory = do
  exists <- doesPathExist directory; need "fresh distribution seed" (not exists); createDirectory directory
  let sourcePath=directory ++ "/BinaryPackage.hs"
      specPath=directory ++ "/seed.spec"
      prefix=directory ++ "/seed"
      source="-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule BinaryPackage where { import MLF.Primitive; value :: Int; value = 41 }\n"
      spec=U.pack ["MLF-CRATE-1","binary-package/1/library","","true",U.pack [U.pack ["BinaryPackage",B.literal sourcePath]],U.pack [],B.literal (directory ++ "/cache"),B.literal (directory ++ "/builtin")]
  writeFile sourcePath source
  writeFile specPath (B.unpack spec)
  Session.compileSpecFile (B.literal specPath) (B.literal prefix) >>= expect "real library Session producer"
  iface <- CrateArtifact.readInterface (B.literal (prefix ++ ".mlfci")) >>= expect "new complete binary interface reader"
  object <- CrateArtifact.readObject (B.literal (prefix ++ ".mlfco")) iface >>= expect "new complete binary object reader"
  builtinPath <- P.canonicalPath (B.literal (directory ++ "/builtin.mlfci"))
  builtinIface <- CrateArtifact.readInterface builtinPath >>= expect "actual Session builtin interface"
  builtinObject <- CrateArtifact.readObject (CrateArtifact.objectPath builtinPath) builtinIface >>= expect "actual Session builtin object"
  canonicalBuiltin <- expect "canonical builtin fixture" CrateArtifact.builtinPrelude
  need "Session dependency is exact canonical builtin pair"
    (CrateArtifact.encodeInterface builtinIface == CrateArtifact.encodeInterface (CrateArtifact.objectInterface canonicalBuiltin) &&
     CrateArtifact.encodeObject builtinObject == CrateArtifact.encodeObject canonicalBuiltin)
  need "release fixture exact builtin dependency and no entry"
    (CrateArtifact.crateDependencies iface == [("mlf:builtin-shared-haskell-v1:11",builtinPath,CrateArtifact.semanticFingerprint builtinIface)] &&
     CrateArtifact.crateEntry iface == "")
  need "builtin leaf has no dependencies or entry"
    (CrateArtifact.crateId builtinIface == "mlf:builtin-shared-haskell-v1:11" && null (CrateArtifact.crateDependencies builtinIface) && CrateArtifact.crateEntry builtinIface == "")
  need "release fixture exact identity/module" (CrateArtifact.crateId iface == "binary-package/1/library" && CrateArtifact.crateModules iface == ["BinaryPackage"])
  writeFile (directory ++ "/legacy.mlfci") (B.unpack (CrateArtifact.encodeInterface iface))
  writeFile (directory ++ "/legacy.mlfco") (B.unpack (CrateArtifact.encodeObject object))
  -- Keep the original Session pair for the formal/public-pair oracles. Real
  -- Release.publish separately writes the complete binary portable closure.
  executable <- getExecutablePath
  compiler <- P.fileDigest (B.literal executable)
  Release.publish (B.literal (prefix ++ ".mlfci")) compiler True "binary-package" "1" (B.literal (directory ++ "/release-binary"))
  -- Legacy bytes have different digest keys. Encode the canonical leaf first,
  -- then relocate the unchanged root through the production relocation helper.
  let legacyBuiltinPrefix = directory ++ "/release-legacy-builtin"
  writeFile (legacyBuiltinPrefix ++ ".mlfci") (B.unpack (CrateArtifact.encodeInterface builtinIface))
  writeFile (legacyBuiltinPrefix ++ ".mlfco") (B.unpack (CrateArtifact.encodeObject builtinObject))
  legacyMetadata <- P.fileDigest (B.literal (legacyBuiltinPrefix ++ ".mlfci"))
  legacyBody <- P.fileDigest (B.literal (legacyBuiltinPrefix ++ ".mlfco"))
  let legacyPath = Release.virtualPath (Release.pairKey legacyMetadata legacyBody)
  portableLegacy <- expect "legacy root relocation" (Release.relocateObject [("mlf:builtin-shared-haskell-v1:11",legacyPath)] object)
  need "legacy closure exact relocated dependency"
    (CrateArtifact.crateDependencies (CrateArtifact.objectInterface portableLegacy) ==
      [("mlf:builtin-shared-haskell-v1:11",legacyPath,CrateArtifact.semanticFingerprint builtinIface)])
  writeFile (directory ++ "/release-legacy-root.mlfci") (B.unpack (CrateArtifact.encodeInterface (CrateArtifact.objectInterface portableLegacy)))
  writeFile (directory ++ "/release-legacy-root.mlfco") (B.unpack (CrateArtifact.encodeObject portableLegacy))
  putStrLn "PASS actual-binary-library-and-legacy-formal"

-- Raw structural fidelity is intentionally broader than production parser
-- admission. These negatives invoke the actual production checker with a
-- correct outer term fingerprint; they cannot pass via an unrelated hash error.
admissionTests = do
  let bad label reason tasks = case Storage.admit tasks of
        T.Left message -> need label (message == "binary artifact syntax admission: " P.++ B.literal reason)
        T.Right _ -> error ("production syntax accepted " ++ label)
  bad "class empty parameters" "invalid class name or empty parameters" [Storage.AdmitClasses [T.SClassDecl "Eq" [] [] []]]
  bad "class illegal name" "invalid class name or empty parameters" [Storage.AdmitClasses [T.SClassDecl "bad name" [("a",T.Star)] [] []]]
  bad "instance empty head" "invalid instance class or empty head" [Storage.AdmitInstances [("opaque ID",T.SInstanceDecl [] [] "Eq" [] [])]]
  bad "instance illegal class name" "invalid instance class or empty head" [Storage.AdmitInstances [("opaque ID",T.SInstanceDecl [] [] "bad name" [T.SCon "Int" []] [])]]
  bad "field quantified binder" "invalid quantified field binder" [Storage.AdmitField True (T.Quantified "Upper" T.Star (T.Parameter "Upper"))]
  bad "field variable binder" "invalid field parameter" [Storage.AdmitField True (T.Parameter "Upper")]
  bad "negative term name ID" "invalid term identity or hint" [Storage.AdmitName (T.XName (-1) "x")]
  bad "illegal term hint" "invalid term identity or hint" [Storage.AdmitName (T.XName 0 "bad space")]
  bad "min type variable ID" "type identity outside legacy decimal domain" [Storage.AdmitVariable (T.XTyVar (-9223372036854775808))]
  bad "class method name" "invalid class method name" [Storage.AdmitMethods [("bad space",T.SCon "Int" [])]]
  bad "instance method name" "invalid instance method name" [Storage.AdmitMethodNames [("bad space",T.SIntLit 0)]]
  bad "predicate empty arguments" "invalid predicate class or empty arguments" [Storage.AdmitPredicates [T.SPredicate "Eq" []]]
  bad "surface binder" "invalid surface type binder" [Storage.AdmitSurface (T.SForall T.Flexible "Upper" T.SBottom (T.STVar "Upper"))]
  forM_ ["True.T","False.T","M.True.T","M.False.T"] $ \name -> do
    bad "reserved boolean cannot be a qualified prefix" "invalid surface type constructor" [Storage.AdmitSurface (T.SCon name [])]
    bad "reserved boolean cannot prefix metadata field type" "invalid field constructor" [Storage.AdmitField True (T.Applied name [])]
  bad "metadata colon surface type" "invalid surface type constructor" [Storage.AdmitSurface (T.SCon ":" [])]
  bad "metadata colon field type" "invalid field constructor" [Storage.AdmitField True (T.Applied ":" [])]
  forM_ ["M.True","M.False","True","False"] $ \name -> do
    _ <- expect "boolean spelling is allowed as the terminal metadata component" (Storage.admit [Storage.AdmitSurface (T.SCon name []),Storage.AdmitField True (T.Applied name [])])
    pure ()
  _ <- expect "xMLF field profile retains legal builtin colon" (Storage.admit [Storage.AdmitField False (T.Applied ":" [])])

  let box=T.DataDeclK "Box" [("a",T.Star)] [T.ConstructorDecl "Box" [T.Parameter "a"]]
      application=T.Application (T.Applied "Box" []) (T.Applied "Int" [])
  _ <- expect "all-Star DataDeclK is a legal representation" (Storage.admit [Storage.AdmitData True [box]])
  _ <- expect "Application is a legal field representation" (Storage.admit [Storage.AdmitField True application])
  _ <- expect "ordinary class/instance syntax" (Storage.admit [
    Storage.AdmitClasses [T.SClassDecl "Eq" [("a",T.Star)] [] [("eq",T.SArrow (T.STVar "a") (T.STVar "a"))]],
    Storage.AdmitInstances [("opaque ID",T.SInstanceDecl [] [] "Eq" [T.SCon "Int" []] [("eq",T.SIntLit 0)])],
    Storage.AdmitVariable (T.XTyVar (-9223372036854775807)),Storage.AdmitName (T.XName 9223372036854775807 "x"),
    Storage.AdmitPredicates [T.SPredicate "HasCallStack" []]])
  -- The raw codec must not normalize away the representational differences.
  restoredBox <- expect "raw all-Star DataDeclK" (A.fromDataDecl (A.toDataDecl box))
  need "raw DataDeclK tag retained" (case restoredBox of T.DataDeclK _ _ _ -> True; _ -> False)
  restoredField <- expect "raw Application" (A.fromField (A.toField application))
  need "raw Application tag retained" (case restoredField of T.Application _ _ -> True; _ -> False)
  let checkBadUnit term reason = do
        let iface=U.UnitInterface "AdmissionProbe" [] [] [] [] [] [] (U.fingerprint (Pretty.prettyTerm term))
            object=U.UnitObject iface term
        bytes <- W.encode W.defaultLimits 7 [A.toRawUnitObject object] >>= expect "invalid-admission raw syntax encodes"
        graph <- W.decodeGraph W.defaultLimits 7 bytes >>= expect "invalid-admission wire graph decodes"
        root <- case W.graphRoots graph of [r] -> pure r; _ -> error "admission raw root"
        raw <- expect "invalid-admission typed raw syntax decodes" (A.fromGraphRawUnitObject graph root)
        case Storage.checkUnit raw of
          T.Left message -> need "actual checkUnit correct admission boundary, not outer checksum" (message == "binary artifact syntax admission: " P.++ B.literal reason)
          T.Right _ -> error "production admitted malformed raw term syntax"
  checkBadUnit (T.XVarTerm (T.XName (-1) "x")) "invalid term identity or hint"
  checkBadUnit (T.XVarTerm (T.XName 0 "bad space")) "invalid term identity or hint"
  checkBadUnit (T.XTypeAbs (T.XTyVar (-9223372036854775808)) T.XBot (T.XIntTerm 0)) "type identity outside legacy decimal domain"
  let goodTerm=T.XIntTerm 41
      goodIface=U.UnitInterface "AdmissionProbe" [] [] [] [] [] [] (U.fingerprint (Pretty.prettyTerm goodTerm))
  accepted <- expect "production checker still admits valid raw syntax" (Storage.checkUnit (U.UnitObject goodIface goodTerm))
  case accepted of U.CheckedUnitObject _ _ -> pure (); U.UnitObject _ _ -> error "production failed to establish checked evidence"
  putStrLn "PASS production-admission-distinct-from-raw-codec"


-- R2 regression: keep the source key and actual schema301 empty
-- context/int-only raw body fixed. Only the caller's expected datatype list
-- changes. A body that does not mention Other must not bypass key/context
-- binding, including after a genuine invocation-local memo was established.
sourceAdmissionTests directory = do
  exists <- doesPathExist directory; need "fresh source-admission directory" (not exists); createDirectory directory
  bracket (P.acquireFileLock (B.literal (directory ++ "/.lock"))) P.releaseFileLock $ \_ -> do
    object <- expect "actual int-only empty-context raw inference" (InferenceUnit.compileLoweredGroup "RawGroup" [] [] [("value",T.Nothing,T.SIntLit 41)])
    let encoded=Q.encodeSourceDatatypes []
        key=U.pack ["MLF-SOURCE-CRATE-QUERY-7","binary-source-admission","compiler","member","bindings",encoded,"source-group","contracts","scope"]
        path=directory ++ "/record.mlfq"
        other=[T.DataDecl "Other" [] [T.ConstructorDecl "Other" []]]
        mismatch="cached source query datatype context mismatch"
        missing="source query context cache miss"
        invalid="invalid source query context reference"
        readCurrent previous declarations = Q.readSourceCacheFileWithWindow previous (B.literal directory) key "RawGroup" [] declarations ["value"] (B.literal path)
        rejected label expected (next,reused,result) = do
          need (label ++ " structural miss clears memo") (null next && not reused)
          case result of
            T.Left message -> need (label ++ " exact error precedence") (message == expected)
            T.Right _ -> error ("accepted " ++ label)
        accepted label expectedReuse (next,reused,result) = do
          raw <- expect label result
          need (label ++ " actual verified memo") (not (null next) && reused == expectedReuse)
          need (label ++ " exact complete object") (U.encodeObject raw == U.encodeObject object && U.encodeInterface (U.objectInterface raw) == U.encodeInterface (U.objectInterface object))
          pure next
    Q.writeSourceCached T.Nothing (B.literal directory) (B.literal path) key object >>= expect "actual schema301 publication"
    bytes <- readBounded path
    graph <- W.decodeGraph W.defaultLimits 2 bytes >>= expect "actual binary source record"
    reference <- case W.graphRoots graph of
      [root] -> do
        value <- expect "actual source root" (W.lookupGraphNode graph root)
        case value of
          W.GNode 301 [ref,_,_,_] -> expect "actual source context reference" (A.fromGraphText graph ref)
          _ -> error "source-admission fixture did not publish real schema301"
      _ -> error "source-admission root inventory"
    let contextPath=B.unpack (Q.sourceContextPath (B.literal directory) reference)
    contextBytes <- readBounded contextPath
    digest <- P.byteArrayDigest contextBytes
    need "source-admission content address is exact physical binary bytes" (digest == reference)
    contextGraph <- W.decodeGraph W.defaultLimits 1 contextBytes >>= expect "actual source context schema"
    declarations <- case W.graphRoots contextGraph of
      [root] -> expect "actual source typed context" (A.fromGraphDataContext contextGraph root)
      _ -> error "source context root inventory"
    need "source-admission actual context is empty" (null declarations)
    readCurrent [] other >>= rejected "cold unchanged key but wrong expectedDS" mismatch
    memo <- readCurrent [] [] >>= accepted "establish real empty-context memo" False
    _ <- readCurrent memo [] >>= accepted "same context genuine memo hit" True
    readCurrent memo other >>= rejected "warm unchanged key wrong expectedDS with carrier present" mismatch
    -- A cooperating private fixture owns the actual lock throughout these
    -- visibility tests. This is not a guarantee for lock-ignoring mutation.
    bracket (renameFile contextPath (contextPath ++ ".held")) (\_ -> renameFile (contextPath ++ ".held") contextPath) $ \_ -> do
      readCurrent [] other >>= rejected "cold missing carrier precedes expectedDS mismatch" missing
      readCurrent memo other >>= rejected "warm structural miss needs actual carrier" missing
      _ <- readCurrent memo [] >>= accepted "unchanged verified memo is independent of subsequent carrier IO" True
      pure ()
    broken <- fromBytes [0,1,2]
    bracket (saveBytes contextPath broken) (\_ -> saveBytes contextPath contextBytes) $ \_ -> do
      readCurrent [] other >>= rejected "corrupt carrier digest precedes expectedDS mismatch" invalid
      readCurrent memo other >>= rejected "warm structural miss validates carrier digest first" invalid
    readCurrent memo other >>= rejected "restored carrier still rejects wrong expectedDS" mismatch
    -- Exercise a real old CACHE3 record with its OWN old-text content SHA.
    -- No binary digest is relabeled as a legacy carrier identity.
    let oldCarrier=Q.sourceContextContents encoded
    oldBytes <- P.byteArrayFromString oldCarrier
    oldReference <- P.byteArrayDigest oldBytes
    need "legacy and binary physical identities are distinct" (oldReference /= reference)
    let oldPath=B.unpack (Q.sourceContextPath (B.literal directory) oldReference)
        oldRecordPath=directory ++ "/legacy.mlfq"
    compact <- case Q.sourceCacheParts key of T.Just (value,_) -> pure value; T.Nothing -> error "source key projection"
    let oldRecord=U.pack ["MLF-QUERY-CACHE-3",oldReference,compact,U.encodeContextualObject object]
    saveBytes oldPath oldBytes
    writeFile oldRecordPath (B.unpack oldRecord)
    let readOld = Q.readSourceCacheFileWithWindow [] (B.literal directory) key "RawGroup" [] [] ["value"] (B.literal oldRecordPath)
    _ <- readOld >>= accepted "actual legacy CACHE3 and its own carrier" False
    bracket (renameFile oldPath (oldPath ++ ".held")) (\_ -> renameFile (oldPath ++ ".held") oldPath) $ \_ ->
      readOld >>= rejected "legacy CACHE3 missing carrier exact compatibility diagnostic" missing
    _ <- readOld >>= accepted "legacy carrier restored" False
    putStrLn "PASS source-key-context-admission-and-priority"

-- Regression controls for all three canonical builtin authority branches.
releaseReadPair prefix = do
  iface <- CrateArtifact.readInterface (B.literal (prefix ++ ".mlfci")) >>= expect "release control checked interface"
  object <- CrateArtifact.readObject (B.literal (prefix ++ ".mlfco")) iface >>= expect "release control checked object"
  pure object

releaseBuiltinBranches directory = do
  binary <- releaseReadPair (directory ++ "/builtin")
  legacy <- releaseReadPair (directory ++ "/release-legacy-builtin")
  root <- releaseReadPair (directory ++ "/seed")
  let current = CrateArtifact.builtinCrateIdentity
      compiler = B.literal (replicate 64 'c')
      key = B.literal (replicate 128 'd')
      row identity = Json.Object [("identity",Json.str identity),("key",Json.str key)]
      builtin = CrateArtifact.objectInterface binary
      replaceIdentityModules identity modules iface = case iface of
        CrateArtifact.CrateInterface _ dependencies _ exports imports datatypes classes instances layouts bindings entry fingerprint protection ->
          CrateArtifact.CrateInterface identity dependencies modules exports imports datatypes classes instances layouts bindings entry fingerprint protection
      ownership label identity modules expected = case CrateArtifact.validateBuiltinOwnership (replaceIdentityModules identity modules builtin) of
        T.Left message -> need label (message == expected)
        T.Right _ -> error ("accepted ownership regression: " ++ label)
  need "fixed current builtin authority" (current == "mlf:builtin-shared-haskell-v1:11")
  need "builtin localPrefix uses canonical compiler cache"
    (Release.localPrefix "/cache" compiler (row current) == ("/cache/.queries/builtin-prelude/" P.++ compiler P.++ "/unit"))
  need "ordinary localPrefix keeps release key cache"
    (Release.localPrefix "/cache" compiler (row "binary-package/1/library") == ("/cache/.releases/" P.++ compiler P.++ "/" P.++ key P.++ "/unit"))
  Release.verifyPrelude binary
  Release.verifyPrelude legacy
  Release.verifyPrelude root
  ownership "obsolete prelude owner" "mlf:builtin-prelude:1" ["MLF.Primitive","Prelude"] "stale or forged builtin crate identity"
  ownership "stale shared ABI owner" "mlf:builtin-shared-haskell-v1:10" ["MLF.Primitive","Prelude"] "stale or forged builtin crate identity"
  ownership "ordinary forged owner" "other/library" ["MLF.Primitive","Prelude"] "stale or forged builtin crate identity"
  ownership "missing primitive ownership" current ["Prelude"] "builtin crate must own exactly Prelude and MLF.Primitive"
  ownership "extra builtin module" current ["Extra","MLF.Primitive","Prelude"] "builtin crate must own exactly Prelude and MLF.Primitive"
  putStrLn "PASS release-canonical-builtin-paths-ownership-binary-legacy"

releaseForgedCurrent directory = do
  canonical <- releaseReadPair (directory ++ "/builtin")
  fragments <- case CrateArtifact.objectFragments canonical of
    [] -> error "canonical builtin must have a typed fragment"
    first:rest -> do
      let changedInterface = case U.objectInterface first of
            U.UnitInterface name dependencies exports datatypes classes instances bindings fingerprint ->
              U.UnitInterface (name P.++ ".noncanonical-release-control") dependencies exports datatypes classes instances bindings fingerprint
          -- Terms, types and bindings remain exact. Change only the checked
          -- fragment inventory label, then recompute its real pooled checksum.
          changed = U.UnitObject changedInterface (U.objectTerm first)
      pure (changed:rest)
  let forged = CrateArtifact.makeObject (CrateArtifact.objectInterface canonical) fragments
      iface = CrateArtifact.objectInterface forged
  need "forged control retains exact current identity and ownership"
    (CrateArtifact.crateId iface == "mlf:builtin-shared-haskell-v1:11" &&
     CrateArtifact.crateModules iface == CrateArtifact.crateModules (CrateArtifact.objectInterface canonical))
  _ <- expect "forged control passes complete ordinary typed linking" (CrateArtifact.linkCheckedObjects [forged] (CrateArtifact.crateId iface))
  need "forged control is genuinely noncanonical" (CrateArtifact.encodeObject forged /= CrateArtifact.encodeObject canonical)
  putStrLn "PASS release-forged-current-fully-typed"
  Release.verifyPrelude forged
  error "accepted noncanonical current builtin"
