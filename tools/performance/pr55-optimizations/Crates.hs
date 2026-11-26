{-# LANGUAGE OverloadedStrings #-}
-- Compile this unchanged driver against each checkout's production modules.
module Main where

import Control.Exception (evaluate)
import Data.List (foldl')
import System.CPUTime (getCPUTime)
import System.Environment (getArgs)
import Text.Printf (printf)
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.ImportedRoot as Imports
import qualified Bootstrap.InferenceUnit as Inference
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Pretty as Pretty
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as P

-- The positional checksum observes every scalar, including supplementary
-- Unicode and NUL. The Python runner derives the expected framed bytes itself.
digest :: H.String -> (Int, Integer)
digest = foldl' step (0, 0) . H.unpack
  where
    step (count, checksum) char =
      let next = count + 1
          value = (checksum + fromIntegral next * fromIntegral (fromEnum char)) `mod` 1000000007
      in next `seq` value `seq` (next, value)

query :: String -> Int -> H.String
query family size = Q.encodeType (foldr next (T.STVar "λ😀\NUL") [1..size])
  where
    next i body = case family of
      "source-arrow" -> T.SArrow (T.STVar "a") body
      "source-forall" -> T.SForall T.Rigid (H.literal ("v" ++ show i))
        (T.SBottomKind (T.KArrow T.Star T.Star)) body
      "source-qualified" -> T.SQualified [T.SPredicate "Cλ" [T.STVar "a"]] body
      _ -> error "unknown query family"

importResult :: Int -> H.String
importResult size = case run of
  T.Left message -> error (H.unpack message)
  T.Right (_, parameters, term) -> case parameters of
    [(_, ty)] -> P.concatString (Pretty.prettyType ty) (Pretty.prettyTerm term)
    _ -> error "incorrect import inventory"
  where
    vars = [T.XTyVar (fromIntegral (97 + i*11)) | i <- [0..size-1]]
    names = [H.literal ("a" ++ show i) | i <- [0..2*size-1]]
    declarations = [T.DataDecl "Dictionary" names [T.ConstructorDecl "DictionaryValue" []]]
    slot = V.fromInt 37
    scheme = foldr (\v body -> T.XForall v T.XBot body)
      (T.XCon "Dictionary" (map T.XVar (vars ++ vars))) vars
    parameters = [(slot, "instance", scheme)]
    concrete = T.SCon "Dictionary" (replicate (2*size) (T.SCon "Int" []))
    rhs = T.SAnn (T.SWantedRefs "Dictionary" [(T.InstanceEvidence, T.DeclRef slot "instance")])
      (T.SAnnotation [] concrete)
    run = do
      env <- Open.environment declarations
      (_, lowered) <- Inference.prepareIndexedGroup parameters declarations
        [(V.fromInt 101, ("entry", T.Nothing, rhs))]
      selected <- Imports.fileImports parameters lowered
      Imports.finishFileImportsIn (T.Just env) selected lowered

timed :: String -> Int -> IO (Int, Integer) -> IO ()
timed family size action = do
  start <- getCPUTime
  result@(count, checksum) <- action
  _ <- evaluate (count `seq` checksum `seq` result)
  end <- getCPUTime
  printf "{\"family\":%s,\"size\":%d,\"count\":%d,\"checksum\":%d,\"cpu_seconds\":%.9f}\n"
    (show family) size count checksum (fromIntegral (end-start) / 1e12 :: Double)

main :: IO ()
main = do
  args <- getArgs
  (family, size) <- case args of
    [family, n] | [(size, "")] <- reads n, size > 0 -> pure (family, size)
    _ -> fail "usage: crates-probe FAMILY POSITIVE_SIZE"
  if family == "metadata-bytes" then do
    left <- P.newByteArray (fromIntegral size) 173
    right <- P.newByteArray (fromIntegral size) 173
    timed family size $ do
      equal <- Storage.sameBytes left right
      pure (size, if equal then 1 else 0)
  else timed family size $ pure $ digest $
    if family == "evidence-import" then importResult size else query family size
