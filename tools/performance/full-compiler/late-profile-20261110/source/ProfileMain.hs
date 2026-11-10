-- PRIVATE REVIEW DRAFT. Not compiled or tested; not an ordinary compiler entry.
-- Preserve the complete Entry.main route. Only this wrapper adds a timeout and
-- a diagnostic outcome receipt. RTS profiling still needs a normal shutdown.
module Main where

import Control.Concurrent (threadDelay)
import Control.Exception (SomeException, displayException, evaluate, fromException, try)
import Control.Monad (forever)
import Data.IORef (modifyIORef', newIORef, readIORef)
import GHC.Clock (getMonotonicTimeNSec)
import MLF.Host.IO (runEntry, v_processSupervisor)
import qualified MLF.Host.Base as Host
import qualified MLF.Entry.Emlf as Entry
import System.Directory (doesFileExist, renameFile)
import System.Environment (getEnv, lookupEnv)
import System.Exit (ExitCode(..), exitWith)
import System.IO (hFlush, hPutStrLn, stderr)
import System.Timeout (timeout)
import Text.Read (readMaybe)

main :: IO ()
main = do
  mode <- lookupEnv "MLF_COST_CENTRE_MODE"
  action <- case mode of
    Nothing -> pure Entry.main
    Just "target" -> pure Entry.main
    Just "allocate" -> pure allocateUntilCancelled
    Just "active-child" -> pure activeChildUntilCancelled
    Just "exit-124" -> pure (exitWith (ExitFailure 124))
    _ -> ioError (userError "unknown private diagnostic control mode")
  runProfiled (runEntry action)

-- Real CLI and every deterministic control share this exact function and the
-- same runEntry/finally shutdown boundary in this one private Main object.
runProfiled :: IO () -> IO ()
runProfiled action = do
  destination <- getEnv "MLF_COST_CENTRE_OUTCOME"
  requested <- lookupEnv "MLF_COST_CENTRE_TIMEOUT_MS"
  milliseconds <- case requested of
    Nothing -> pure 90000
    Just value -> case readMaybe value of
      Just n | n > 0 && n <= (90000 :: Int) -> pure n
      _ -> ioError (userError "diagnostic timeout must be 1..90000 ms")
  stat <- readFile "/proc/self/stat"
  let pid = takeWhile (/= ' ') stat
      values = words (drop 1 (dropWhile (/= ')') stat))
      identity = "{\"pid\":" ++ pid ++ ",\"start_ticks\":\"" ++ values !! 19 ++
                 "\",\"process_group\":" ++ values !! 2 ++ "}\n"
  writeFile (destination ++ ".process.json.tmp") identity
  renameFile (destination ++ ".process.json.tmp") (destination ++ ".process.json")
  started <- getMonotonicTimeNSec
  outcome <- try (timeout (milliseconds * 1000) action)
    :: IO (Either SomeException (Maybe ()))
  finished <- getMonotonicTimeNSec
  let (label, actionComplete, status) = case outcome of
        Right (Just ()) -> ("compiler-returned", "true", ExitSuccess)
        Right Nothing -> ("internal-timeout", "false", ExitFailure 124)
        Left exception -> case fromException exception of
          Just ExitSuccess -> ("compiler-exit-success", "true", ExitSuccess)
          Just code -> ("compiler-exit-failure", "false", code)
          Nothing -> ("compiler-exception", "false", ExitFailure 1)
      exitNumber = case status of ExitSuccess -> 0; ExitFailure n -> n
      body = "{\"diagnostic_only\":true,\"ordinary_endpoint\":false," ++
        "\"outcome\":\"" ++ label ++ "\",\"compiler_action_complete\":" ++ actionComplete ++
        ",\"exit_code\":" ++ show exitNumber ++
        ",\"elapsed_nanoseconds\":" ++ show (finished - started) ++ "}\n"
  -- Fresh output paths are an external precondition. This marker precedes RTS
  -- shutdown; it does NOT prove that the .prof report was successfully written.
  writeFile (destination ++ ".tmp") body
  renameFile (destination ++ ".tmp") destination
  case outcome of
    Left exception -> hPutStrLn stderr (displayException exception)
    Right Nothing -> hPutStrLn stderr "DIAGNOSTIC ONLY: internal timeout; compilation incomplete"
    Right (Just ()) -> pure ()
  hFlush stderr
  exitWith status

allocateUntilCancelled :: IO ()
allocateUntilCancelled = do
  counter <- newIORef (0 :: Integer)
  forever $ do
    modifyIORef' counter (+ 1)
    value <- readIORef counter
    _ <- evaluate (length (show value))
    pure ()

fields :: String -> [String]
fields [] = []
fields text = case break (== '\0') text of
  (value, []) -> [value]
  (value, _ : rest) -> value : fields rest

request :: [String] -> IO [String]
request values = do
  reply <- v_processSupervisor (Host.literal (concatMap (++ "\0") ("MLF-PROCESS-1" : values)))
  case fields (Host.unpack reply) of
    "0" : result -> pure result
    other -> ioError (userError ("supervisor control failed: " ++ show other))

activeChildUntilCancelled :: IO ()
activeChildUntilCancelled = do
  python <- getEnv "MLF_COST_CENTRE_PYTHON"
  script <- getEnv "MLF_COST_CENTRE_CHILD"
  identity <- getEnv "MLF_COST_CENTRE_CHILD_IDENTITY"
  result <- request ["create", "1", "1", "2"]
  scope <- case result of
    [value] -> pure value
    _ -> ioError (userError "unexpected supervisor scope reply")
  _ <- request (["submit", scope, python, "", "", "", "", "0", "30000", "30000", "3"] ++
                [python, script, identity, "0"])
  let awaitChild = do
        ready <- doesFileExist identity
        if ready then pure () else do
          -- Poll is nonblocking and may legitimately report no completed event.
          _ <- v_processSupervisor (Host.literal ("MLF-PROCESS-1\0poll\0" ++ scope ++ "\0"))
          threadDelay 5000
          awaitChild
  awaitChild
  allocateUntilCancelled
