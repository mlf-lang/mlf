-- | Generic POSIX services shared by the reference interpreter. The native
-- runtime implements the same protocol without invoking a shell.
module MLF.SystemIO where

import Control.Exception (IOException, bracket, catch, onException)
import Control.Monad (unless)
import Data.Char (isHexDigit)
import Data.List (sort)
import Data.Maybe (fromMaybe)
import qualified System.Directory as D
import qualified System.Environment as E
import System.Exit (ExitCode(..))
import System.IO (IOMode(..), SeekMode(..), hClose, openBinaryFile)
import qualified System.Posix.IO as P
import System.Posix.Signals (sigKILL, signalProcessGroup)
import System.Posix.Types (Fd(..))
import qualified System.Process as P
import System.Timeout (timeout)
import System.IO.Error (isDoesNotExistError)
import Text.Read (readMaybe)

getEnv :: String -> IO String
getEnv name = do
  unless (not (null name) && '=' `notElem` name) (fail "invalid environment name")
  fromMaybe "" <$> E.lookupEnv name
setEnv :: String -> String -> IO ()
setEnv name value = do
  unless ('\0' `notElem` value) (fail "invalid environment value")
  E.setEnv name value
unsetEnv :: String -> IO ()
unsetEnv = E.unsetEnv
listDirectory :: FilePath -> IO String
listDirectory path = concatMap (++ "\0") . sort <$> D.listDirectory path
directoryExists :: FilePath -> IO Bool
directoryExists = D.doesDirectoryExist
acquireFileLock :: FilePath -> IO Integer
acquireFileLock path = do
  fd@(Fd n) <- P.openFd path P.ReadWrite P.defaultFileFlags {P.creat=Just 0o600,P.cloexec=True}
  P.waitToSetLock fd (P.WriteLock,AbsoluteSeek,0,0) `onException` P.closeFd fd
  pure (toInteger n)
releaseFileLock :: Integer -> IO ()
releaseFileLock n = do
  unless (n>=0 && n<=2147483647) (fail "invalid file lock")
  P.closeFd (Fd (fromInteger n))

splitFields :: String -> [String]
splitFields "" = []
splitFields text = case break (=='\0') text of
  (a,_:rest) -> a:splitFields rest
  _ -> []

runProcess :: FilePath -> String -> IO Integer
runProcess directory spec = case splitFields spec of
  seconds:input:output:errors:command:args
    | Just n <- readMaybe seconds :: Maybe Int
    , n>0, n<=2147483647, not (null command), not (null spec), last spec=='\0' ->
      (redirect input ReadMode $ \i -> redirect output WriteMode $ \o ->
        (if not (null output) && output==errors then (\k -> k o) else redirect errors WriteMode) $ \e -> do
          let process = (P.proc command args) {P.cwd=if null directory then Nothing else Just directory,
                P.std_in=i,P.std_out=o,P.std_err=e,P.create_group=True,P.close_fds=True}
          (P.withCreateProcess process $ \_ _ _ handle -> do
            result <- timeout (n*1000000) (P.waitForProcess handle)
            case result of
              Just ExitSuccess -> pure 0
              Just (ExitFailure code) -> pure (toInteger (if code<0 then 128-code else code))
              Nothing -> do
                pid <- P.getPid handle
                maybe (pure ()) (signalProcessGroup sigKILL) pid
                _ <- P.waitForProcess handle
                pure 124) `catch` spawnFailure) `catch` redirectFailure
  _ -> fail "invalid process specification"
  where
    spawnFailure :: IOException -> IO Integer
    spawnFailure err = pure (if isDoesNotExistError err then 127 else 126)
    redirectFailure :: IOException -> IO Integer
    redirectFailure _ = pure 126
    redirect "" _ next = next P.Inherit
    redirect path mode next = bracket (openBinaryFile path mode) hClose (next . P.UseHandle)

-- Independent reference oracle for the native SHA-256 implementation.
fileDigest :: FilePath -> IO String
fileDigest path = do
  file <- D.canonicalizePath path
  sha <- D.findExecutable "sha256sum"
  text <- case sha of
    Just tool -> P.readProcess tool [file] ""
    Nothing -> P.readProcess "shasum" ["-a","256",file] ""
  let digest=take 64 text
  unless (length digest==64 && all isHexDigit digest) (fail "invalid SHA-256 output")
  pure digest
