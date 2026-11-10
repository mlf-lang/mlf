{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Exception (bracket, evaluate)
import System.Mem.StableName (makeStableName)
import Control.Monad (forM_, unless, foldM)
import qualified Data.ByteString as BS
import System.Directory (createDirectory, doesPathExist, getModificationTime, removeFile, removeDirectory)
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.Data as D
import qualified Bootstrap.InferenceUnit as Inference
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

need label ok = unless ok (error label)
expect label result = case result of
  T.Left message -> error (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value
reject label wanted result = case result of
  T.Left message -> need label (message == wanted)
  T.Right _ -> error ("accepted " ++ label)
contextParts (Q.BinarySourceContextEncoding _ digest bytes) = (digest, bytes)
fixtures =
  [ [], D.builtinDeclarations,
    [T.DataDecl "Tα😀" ["a"] [T.ConstructorDecl "T" [T.Parameter "a"]]],
    [T.DataDecl "Tα😀" ["b"] [T.ConstructorDecl "T" [T.Parameter "b"]]],
    [T.DataDecl "Tα😀" ["a"] [T.ConstructorDecl "Other" [T.Parameter "a"]]],
    [T.DataDecl "Tα😀" ["a"] [T.ConstructorDecl "T" [T.Function (T.Parameter "a") (T.Applied "Int" [])]]],
    [T.DataDeclK "Tα😀" [("f", T.KArrow T.Star T.Star)]
      [T.ConstructorDecl "T" [T.Application (T.Parameter "f") (T.Applied "Int" [])]]],
    [T.DataDeclK "Tα😀" [("f", T.Star)]
      [T.ConstructorDecl "T" [T.Quantified "q" T.Star (T.Parameter "q")]]],
    [T.DataDecl "Duplicate" [] [], T.DataDecl "Duplicate" [] [T.ConstructorDecl "D" []]] ]

controls directory = do
  createDirectory directory
  bracket (P.acquireFileLock (B.literal (directory ++ "/.lock"))) P.releaseFileLock
    (\_ -> controlsLocked directory)

controlsLocked directory = do
  -- All transitions include structurally changed same-name layouts, kinds,
  -- binders, declaration order and duplicate declarations. Expected bytes come
  -- directly from the unchanged structural serializer, not from the memo.
  forM_ (zip [(0::Int)..] fixtures) $ \(i, old) -> do
    previous <- Q.encodeBinarySourceContext T.Nothing old >>= expect "seed encoding"
    forM_ (zip [(0::Int)..] fixtures) $ \(j, ds) -> do
      actual <- Q.encodeBinarySourceContext (T.Just previous) ds >>= expect "memo encoding"
      oracle <- Storage.encode 1 [Structure.toDataContext ds] >>= expect "independent encoding"
      oracleHash <- P.byteArrayDigest oracle
      let (digest, bytes) = contextParts actual
      equal <- Storage.sameBytes oracle bytes
      need ("byte/digest transition " ++ show (i,j)) (equal && digest == oracleHash)
  originalEntry <- Q.encodeBinarySourceContext T.Nothing D.builtinDeclarations >>= expect "reuse seed"
  repeatEntry <- Q.encodeBinarySourceContext (T.Just originalEntry) D.builtinDeclarations >>= expect "reuse hit"
  oldName <- evaluate (snd (contextParts originalEntry)) >>= makeStableName
  newName <- evaluate (snd (contextParts repeatEntry)) >>= makeStableName
  need "repeated context retains the actual immutable bytearray" (oldName == newName)
  forM_ [(1048576, True), (1048577, False)] $ \(size, expected) -> do
    bytes <- P.newByteArray size 0
    retained <- Q.retainBinarySourceContext (Q.BinarySourceContextEncoding [] "unused" bytes)
    need "retention cap" ((case retained of T.Just _ -> True; T.Nothing -> False) == expected)
  entry <- Q.encodeBinarySourceContext T.Nothing D.builtinDeclarations >>= expect "filesystem encoding"
  let (digest, _) = contextParts entry
      target = B.unpack (Q.sourceContextPath (B.literal directory) digest)
      publish = Q.publishEncodedSourceContext (B.literal directory) entry
  _ <- publish >>= expect "first publication"
  original <- BS.readFile target
  timestamp <- getModificationTime target
  _ <- publish >>= expect "same publication"
  need "unchanged publication preserves timestamp" . (== timestamp) =<< getModificationTime target
  BS.writeFile target "corrupt"
  _ <- publish >>= expect "corrupt publication repaired"
  need "corrupt repair bytes" . (== original) =<< BS.readFile target
  removeFile target
  _ <- publish >>= expect "missing publication repaired"
  need "missing repair bytes" . (== original) =<< BS.readFile target
  removeFile target
  createDirectory target
  publish >>= reject "directory destination rejects" "cannot publish source query context: destination is a directory"
  removeDirectory target
  createDirectory (directory ++ "/source-context.new")
  failed <- publish
  case failed of T.Left _ -> pure (); T.Right _ -> error "directory staging accepted"
  exists <- doesPathExist target
  need "failed staging did not publish destination" (not exists)
  removeDirectory (directory ++ "/source-context.new")
  _ <- publish >>= expect "retry after staging failure"
  need "retry repairs exact bytes" . (== original) =<< BS.readFile target
  raw <- expect "record raw inference" (Inference.compileLoweredGroup "RawGroup" [] []
    [("value", T.Nothing, T.SIntLit 41)])
  let input = B.literal (replicate 64 'a')
      record1 = directory ++ "/first.mlfq"
      record2 = directory ++ "/memo.mlfq"
      context = Q.encodeSourceDatatypes []
      save previous path = Q.writeSourceRecordWithContext previous Q.DirectRecords T.Nothing
        (B.literal directory) (B.literal path) input context raw
  (memo, first) <- save T.Nothing record1
  _ <- expect "first complete writer" first
  need "first writer retains encoding" (case memo of T.Just _ -> True; T.Nothing -> False)
  (_, second) <- save memo record2
  _ <- expect "second complete writer" second
  before <- BS.readFile record1
  need "memo changes no record bytes" . (== before) =<< BS.readFile record2
  reference <- Q.publishBinarySourceContext (B.literal directory) [] >>= expect "record context reference"
  let recordContext = B.unpack (Q.sourceContextPath (B.literal directory) reference)
  removeFile recordContext
  createDirectory recordContext
  (cleared, failedWrite) <- save memo record2
  need "writer failure clears retained encoding" (case cleared of T.Nothing -> True; T.Just _ -> False)
  failedWrite `rejectAs` "cannot publish source query context: destination is a directory"
  need "failed writer preserves existing record" . (== before) =<< BS.readFile record2
  removeDirectory recordContext
  putStrLn "PASS 81 byte/digest transitions; retention identity/cap; publication repair/failure and complete writer controls"
  where rejectAs result wanted = reject "complete writer exact failure" wanted result

-- Synthetic repeated finite contexts. This isolates encoding work, not end to
-- end compilation. The original arm starts with no memo every time.
benchmark mode repetitions count = do
  let ds = [T.DataDecl (B.literal ("T" ++ show i)) ["a"]
             [T.ConstructorDecl (B.literal ("C" ++ show i))
               [T.Function (T.Parameter "a") (T.Applied "Int" [])]]
            | i <- [(1::Int)..count]]
  final <- foldM (\previous _ -> do
      entry <- Q.encodeBinarySourceContext (if mode == "memo" then previous else T.Nothing) ds
        >>= expect "benchmark encoding"
      let (digest,bytes) = contextParts entry
      lengthBytes <- P.lengthByteArray bytes
      need "complete bytearray and SHA256" (lengthBytes > 0 && P.stringLength digest == 64)
      pure (T.Just entry)) T.Nothing [1..repetitions]
  case final of
    T.Nothing -> error "zero repetitions"
    T.Just entry -> let (digest,_) = contextParts entry in putStrLn (B.unpack digest)

main = do
  args <- getArgs
  case args of
    ["controls", directory] -> controls directory
    [mode, repetitions, count] | mode `elem` ["fresh", "memo"] -> benchmark mode (read repetitions :: Int) (read count)
    _ -> error "usage: controls DIRECTORY | fresh/memo REPETITIONS DATATYPES"
