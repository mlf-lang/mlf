{-# LANGUAGE OverloadedStrings #-}
module OptimizationMetadata (run) where

import Control.Exception (bracket)
import Control.Monad (forM_, unless)
import System.Directory (doesFileExist, getTemporaryDirectory, removeFile)
import System.IO (hClose, openBinaryTempFile)
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.Map as M
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as P

need :: String -> Bool -> IO ()
need label condition = unless condition (fail label)

observe result = case result of
  T.Left message -> Left (H.unpack message)
  T.Right iface -> Right (H.unpack (Artifact.encodeInterface iface))

run :: IO ()
run = bracket temporary cleanup $ \path -> do
  let file = H.literal path
      original = "metadata\NULsnapshot"
      write text = do
        bytes <- P.byteArrayFromString text
        message <- P.writeByteFileOrError file bytes
        need "metadata fixture write failed" (H.unpack message == "")
        pure bytes
  published <- write original
  -- The sentinel makes reuse observable. This cache is an internal immutable
  -- admission result; modified bytes must go through the ordinary decoder.
  let retained = M.singleton file
        (Artifact.PublishedMetadata published (T.Left "retained exact snapshot"))
      readRetained = Artifact.readInterfaceRetaining T.Nothing retained file
  same <- readRetained
  need "equal snapshots no longer reuse their admission result"
    (observe same == Left (path ++ ": retained exact snapshot"))
  forM_ ["MetadatA\NULsnapshot", "metadata\NULsnapshoT", "metadata\NULsnapShot",
         "metadata\NULsnapshot-longer", "", "metadata\NULsnapshot"] $ \current -> do
    _ <- write current
    actual <- readRetained
    if current == original then
      need "restored exact bytes were not recognized"
        (observe actual == Left (path ++ ": retained exact snapshot"))
    else do
      expected <- Artifact.readInterface file
      need "changed file reused a stale metadata admission" (observe expected == observe actual)
      need "invalid changed fixture unexpectedly used sentinel"
        (observe actual /= Left (path ++ ": retained exact snapshot"))
  removeFile path
  expected <- Artifact.readInterface file
  actual <- readRetained
  need "retained metadata skipped a fresh failing file read" (observe expected == observe actual)
  where
    temporary = do
      directory <- getTemporaryDirectory
      (path, handle) <- openBinaryTempFile directory "mlf-pr55-metadata"
      hClose handle
      pure path
    cleanup path = do
      exists <- doesFileExist path
      if exists then removeFile path else pure ()
