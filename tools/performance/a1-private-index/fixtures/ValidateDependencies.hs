module Main where
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Types as T
import qualified MLF.Primitive as P
import MLF.Host.IO (runEntry)
import Control.Monad (forM_, unless)
import System.Environment (getArgs)
import System.Exit (exitFailure)
import System.IO (hPutStrLn, stderr)

reject :: String -> P.String -> IO a
reject tag message = hPutStrLn stderr (tag ++ P.textToChars message) >> exitFailure

check :: Int -> [String] -> IO ()
check expected paths = do
  loaded <- A.loadInterfaces (map P.textFromChars paths)
  case loaded of
    T.Left message -> reject "INTERFACE_REJECTED: " message
    T.Right interfaces -> do
      unless (length interfaces == expected) (hPutStrLn stderr "UNEXPECTED_CLOSURE_COUNT" >> exitFailure)
      forM_ interfaces $ \(metadata, iface) -> do
        object <- A.readObject (A.objectPath metadata) iface
        case object of
          T.Left message -> reject "OBJECT_REJECTED: " message
          T.Right _ -> return ()
      putStrLn ("{\"complete\":true,\"checked_objects\":" ++ show expected ++ ",\"reused_objects\":0}")

main :: IO ()
main = runEntry $ do
  args <- getArgs
  case args of
    ["--single-foundation-control", path] -> check 2 [path]
    paths | length paths == 6 -> check 7 paths
    _ -> hPutStrLn stderr "EXPECTED_SIX_DEPENDENCY_PATHS" >> exitFailure
