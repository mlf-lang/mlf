{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
-- Test-only views. The public readers, linker and checker remain unchanged.
module Main where
import Prelude
import Control.Monad (unless)
import System.Environment (getArgs)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.X.Checked as Checked

right :: String -> T.Either B.String a -> IO a
right label answer = case answer of
  T.Left message -> errorWithoutStackTrace (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value

readObject :: String -> IO Artifact.CrateObject
readObject prefix = do
  iface <- Artifact.readInterface (B.literal (prefix ++ ".mlfci")) >>= right "read interface"
  Artifact.readObject (B.literal (prefix ++ ".mlfco")) iface >>= right "read object"

saveLinked :: FilePath -> String -> Checked.CheckedTerm -> IO ()
saveLinked directory name checked =
  Storage.write 6 (B.literal (directory ++ "/" ++ (name ++ ".xterm-v6.bin")))
    [Structure.toXTerm (Checked.term checked)] >>= right "save complete linked XTerm"

main :: IO ()
main = do
  arguments <- getArgs
  case arguments of
    [closedPrefix, openPrefix, destination] -> do
      closed <- readObject closedPrefix
      opened <- readObject openPrefix
      unless (not (Artifact.openMarked closed) && Artifact.openMarked opened)
        (errorWithoutStackTrace "expected closed reference and open candidate")
      -- This compatibility view is retained as evidence, not a byte-equality
      -- oracle or permission to discard metadata differences.
      Artifact.writeObjectEither (B.literal (destination ++ "/" ++ "legacy"))
        (Artifact.legacyObject opened) >>= right "write explicit legacy view"
      oldLinked <- Artifact.linkCheckedFile (B.literal (closedPrefix ++ ".mlfci")) >>= right "link closed reference"
      newLinked <- Artifact.linkCheckedFile (B.literal (openPrefix ++ ".mlfci")) >>= right "link open candidate"
      saveLinked destination "crate" oldLinked
      saveLinked destination "session" newLinked
      case opened of
        Artifact.OpenCrateObject iface package -> do
          imported <- Artifact.loadInterfaces
            (map Artifact.dependencyPath (Artifact.crateDependencies iface)) >>= right "load complete dependency interfaces"
          -- Retain the returned checked fragments. Discarding them would fail
          -- to test the exact used-reference inventory in the rebuilt bytes.
          audited <- mapM (\(name, fragment) -> do
            checked <- right "audit complete open fragment" (Open.audit fragment)
            pure (name, checked)) (Open.packageFragments package)
          rebuilt <- Artifact.makeOpenObject iface (map snd imported) audited >>= right "rebuild audited object"
          Artifact.writeObjectEither (B.literal (destination ++ "/" ++ "audited-open"))
            rebuilt >>= right "write audited object"
          mapM_ (\(index, (path, _)) -> do
            bytes <- Storage.readRaw path >>= right "read actual dependency bytes"
            Storage.writeRawAtomic
              (B.literal (destination ++ "/" ++ ("dependency-" ++ show index ++ ".mlfci")))
              bytes >>= right "save actual dependency bytes") (zip ([0..] :: [Int]) imported)
          putStrLn ("PASS C4 public views " ++ show (length audited) ++ " " ++ show (length imported))
        _ -> errorWithoutStackTrace "unreachable non-open candidate"
    _ -> errorWithoutStackTrace "usage: closed-prefix open-prefix fresh-view-directory"
