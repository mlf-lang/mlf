module Backends
  ( Backends, Event (..), Entry (..), Input (..), Observation (..)
  , withBackends, inCase, auditBackends, execute, capture, output, outputBytes
  ) where

import Control.Concurrent (threadDelay)
import Control.Exception (NonTermination, SomeException, bracket, displayException, mask, mask_, onException, try)
import Control.Monad (forM, unless, when)
import qualified Data.ByteString as BS
import Data.IORef
import Data.List (isInfixOf, stripPrefix)
import qualified Data.Map.Strict as Map
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import Numeric (readHex)
import System.Directory
  (createDirectory, findExecutable, getTemporaryDirectory, removeFile, removeDirectoryRecursive)
import System.Environment (getEnvironment, lookupEnv)
import System.Exit (ExitCode (..))
import System.FilePath ((</>))
import System.IO (IOMode (..), hClose, openTempFile, withBinaryFile)
import System.Process (CreateProcess (..), StdStream (..), proc, readCreateProcessWithExitCode,
  withCreateProcess, waitForProcess)
import System.Posix.Process (ProcessStatus (..), exitImmediately, forkProcess, getProcessStatus)
import System.Posix.Signals (sigKILL, signalProcess)
import System.Timeout (timeout)
import Text.Read (readMaybe)
import MLF.LLVM (emitLLVM, emitLLVMIO)
import qualified MLF.Runtime as R
import qualified MLF.X.Syntax as X

data Kind = Interpreter | LLVM deriving (Eq, Ord, Show, Enum, Bounded)
data Entry = IOEntry | ProgramEntry deriving (Eq, Show)
data Event = ReadLine | Write String | WriteBytes BS.ByteString deriving (Eq, Show, Read)
data Input = Input { inputText :: String, failWrites :: Bool } deriving Show
data Observation = Observation
  { outcome :: Either R.RuntimeError (), events :: [Event], remaining :: String }
  deriving (Eq, Show)
data Backends = Backends
  { directory :: FilePath, clang :: FilePath, flags :: [String]
  , binaries :: IORef (Map.Map String FilePath), serial :: IORef Int
  , currentCase :: IORef String, visits :: IORef (Map.Map (String,Int) [Kind])
  }

require :: Bool -> String -> IO ()
require condition message = unless condition (fail message)

bounded :: IO a -> IO a
bounded operation = timeout 60000000 operation >>= maybe (fail "backend operation timed out") pure

command :: FilePath -> [String] -> IO String
command file arguments = do
  (status,text,errors) <- bounded (readCreateProcessWithExitCode (proc file arguments) "")
  require (status == ExitSuccess) (unwords (file:arguments) ++ "\n" ++ text ++ errors)
  pure text

withBackends :: (Backends -> IO a) -> IO a
withBackends action = do
  compiler <- tool "clang"
  pkg <- tool "pkg-config"
  includes <- words <$> command pkg ["--cflags","gmp"]
  gmp <- words <$> command pkg ["--libs","gmp"]
  extra <- maybe [] words <$> lookupEnv "MLF_LLVM_TEST_CFLAGS"
  optimization <- maybe "-O2" id <$> lookupEnv "MLF_LLVM_TEST_OPT"
  require (optimization `elem` ["-O0","-O1","-O2","-O3"]) "invalid MLF_LLVM_TEST_OPT"
  bracket scratch removeDirectoryRecursive $ \dir -> do
    let common = [optimization,"-std=c11","-Wall","-Wextra","-Werror"] ++ extra
        interpose = ["-Dgetline=mlf_test_getline","-Dfwrite=mlf_test_fwrite",
          "-Dfputc=mlf_test_fputc","-Dfflush=mlf_test_fflush"]
    _ <- command compiler (common ++ includes ++ interpose ++ ["-DMLF_GC_THRESHOLD=32",
      "-c","runtime/mlf_runtime.c","-o",dir </> "runtime.o"])
    _ <- command compiler (common ++ ["-c","test/native_trace.c","-o",dir </> "trace.o"])
    context <- Backends dir compiler ([optimization] ++ extra ++ gmp ++ ["-lm"])
      <$> newIORef Map.empty <*> newIORef 0 <*> newIORef "<unlabelled>" <*> newIORef Map.empty
    action context
  where
    tool name = findExecutable name >>= maybe (fail ("Backend tests require " ++ name ++ " on PATH")) pure
    scratch = do
      parent <- getTemporaryDirectory
      (name,handle) <- openTempFile parent "mlf-backends"
      hClose handle
      removeFile name
      createDirectory name
      pure name

inCase :: Backends -> String -> IO a -> IO a
inCase context label action = writeIORef (currentCase context) label >> action

-- Each invocation is a matrix row, even when one fixture invokes several
-- programs or input scripts. Missing/duplicate executions cannot count as a
-- passing row. There is no per-test backend selection or skip path.
auditBackends :: Backends -> IO ()
auditBackends context = do
  rows <- readIORef (visits context)
  require (not (Map.null rows)) "no backend matrix rows executed"
  let expected = reverse [minBound .. maxBound]
  mapM_ (\(row,kinds) -> require (kinds == expected) ("incomplete backend row: " ++ show (row,kinds))) (Map.toList rows)
  putStrLn ("Backend matrix: " ++ show (Map.size rows) ++ " rows x 2 backends; no missing executions")

execute :: Backends -> Entry -> Input -> X.Term -> IO Observation
execute context entry input term = do
  label <- readIORef (currentCase context)
  index <- atomicModifyIORef' (serial context) (\n -> (n+1,n))
  let row = (label,index)
  writeRow row []
  results <- forM [minBound .. maxBound] $ \kind -> do
    attempted <- try (case kind of
      Interpreter -> isolated context index (interpreted entry input term)
      LLVM -> native context index entry input term) :: IO (Either SomeException Observation)
    case attempted of
      Right _ -> writeRowKind row kind
      Left _ -> pure ()
    pure (kind,attempted)
  let failures = [show kind ++ ": " ++ displayException err | (kind,Left err) <- results]
  require (null failures) (label ++ ": backend execution failed\n" ++ unlines failures)
  case [observed | (_,Right observed) <- results] of
    [a,b] -> do
      require (a == b) (label ++ ": backend mismatch\nInterpreter: " ++ show a ++ "\nLLVM: " ++ show b)
      pure a
    _ -> fail "backend matrix must contain both implementations"
  where
    writeRow row kinds = modifyIORef' (visits context) (Map.insert row kinds)
    writeRowKind row kind = modifyIORef' (visits context) (Map.adjust (kind:) row)

capture :: Backends -> X.Term -> [String] -> IO (Either R.RuntimeError (),[Event])
capture context term inputs = do
  observed <- execute context IOEntry (Input (unlines inputs) False) term
  require (null (remaining observed)) ("unused backend input: " ++ show (remaining observed))
  pure (outcome observed,events observed)

output :: Observation -> String
output = Text.unpack . Text.decodeUtf8 . outputBytes

outputBytes :: Observation -> BS.ByteString
outputBytes = BS.concat . map (\event -> case event of
  Write text -> Text.encodeUtf8 (Text.pack text); WriteBytes bytes -> bytes; ReadLine -> BS.empty) . events

bytesEvent :: BS.ByteString -> Event
bytesEvent bytes = either (const (WriteBytes bytes)) (Write . Text.unpack) (Text.decodeUtf8' bytes)

-- Keep the timeout in the parent: an in-process timer prevents GHC from
-- diagnosing a blocked recursive thunk as NonTermination. Forking also
-- preserves caller-constructed terms, including deliberately spoofed hints,
-- without routing one backend through a different parser/serialization path.
isolated :: Backends -> Int -> IO Observation -> IO Observation
isolated context index action = mask $ \restore -> do
  let file = directory context </> ("interpreter-" ++ show index)
      worker = do
        result <- try action :: IO (Either SomeException Observation)
        let reply = case result of
              Left err -> Left (displayException err)
              Right observed -> Right
                ( either (Left . show) Right (outcome observed)
                , events observed
                , remaining observed )
        writeFile file (show reply)
        exitImmediately ExitSuccess
  pid <- forkProcess (restore worker)
  reaped <- newIORef False
  let poll = mask_ $ do
        status <- getProcessStatus False False pid
        case status of
          Nothing -> pure Nothing
          Just final -> writeIORef reaped True >> pure (Just final)
      await = poll >>= maybe (threadDelay 10000 >> await) pure
      cleanup = do
        done <- readIORef reaped
        unless done $ do
          signalProcess sigKILL pid
          _ <- getProcessStatus True False pid
          pure ()
  status <- restore (bounded await) `onException` cleanup
  case status of
    Exited ExitSuccess -> pure ()
    _ -> fail ("interpreter process failed: " ++ show status)
  encoded <- readFile file
  case readMaybe encoded :: Maybe (Either String (Either String (),[Event],String)) of
    Just (Right (result,trace,unused)) -> pure (Observation
      (either (Left . R.RuntimeError) Right result) trace unused)
    Just (Left err) -> fail ("interpreter worker: " ++ err)
    Nothing -> fail "malformed interpreter observation"

interpreted :: Entry -> Input -> X.Term -> IO Observation
interpreted entry input term = do
  pending <- newIORef (inputText input)
  trace <- newIORef []
  let backend = R.IOBackend
        { R.readLine = do
            modifyIORef' trace (ReadLine:)
            rest <- readIORef pending
            case rest of
              [] -> ioError (userError "test input exhausted")
              _ -> do
                let (line,suffix) = break (== '\n') rest
                writeIORef pending (drop 1 suffix)
                pure line
        , R.writeText = \text -> do
            modifyIORef' trace (Write text:)
            when (failWrites input) (ioError (userError "write failed"))
        , R.writeBytes = \bytes -> do
            modifyIORef' trace (bytesEvent bytes:)
            when (failWrites input) (ioError (userError "write failed"))
        }
      run = case entry of IOEntry -> R.runTerm; ProgramEntry -> R.runProgram
  result <- try (run backend term) :: IO (Either NonTermination (Either R.RuntimeError ()))
  let normalized = case result of
        Left _ -> Left (R.RuntimeError "cyclic evaluation of a recursive binding")
        Right value -> either (Left . normalize) Right value
  Observation normalized <$> (reverse <$> readIORef trace) <*> readIORef pending

normalize :: R.RuntimeError -> R.RuntimeError
normalize error' = R.RuntimeError $ case stripPrefix "LLVM " message of
  Just rest -> rest
  Nothing
    | "test input exhausted" `isInfixOf` message || "getLine reached EOF" `isInfixOf` message -> "IO error: test input exhausted"
    | "write failed" `isInfixOf` message || "output failed" `isInfixOf` message -> "IO error: write failed"
    | "cyclic evaluation" `isInfixOf` message -> "cyclic evaluation of a recursive binding"
    | otherwise -> message
  where message = show error'

native :: Backends -> Int -> Entry -> Input -> X.Term -> IO Observation
native context index entry input term = case emitter term of
  Left message -> pure (Observation (Left (normalize (R.RuntimeError message))) [] (inputText input))
  Right ir -> do
    known <- readIORef (binaries context)
    executable <- case Map.lookup ir known of
      Just file -> pure file
      Nothing -> do
        let file = directory context </> ("program-" ++ show index)
            source = file ++ ".ll"
        writeFile source ir
        _ <- command (clang context) (flags context ++ ["-Wno-override-module",source,
          directory context </> "runtime.o",directory context </> "trace.o","-o",file])
        modifyIORef' (binaries context) (Map.insert ir file)
        pure file
    let traceFile = directory context </> ("trace-" ++ show index)
    inherited <- filter (\(key,_) -> key `notElem` ["MLF_TEST_TRACE","MLF_TEST_FAIL_WRITE"]) <$> getEnvironment
    let environment = ("MLF_TEST_TRACE",traceFile) :
          [("MLF_TEST_FAIL_WRITE","1") | failWrites input] ++ inherited
    let inputFile = traceFile ++ ".stdin"
        outputFile = traceFile ++ ".stdout"
        errorFile = traceFile ++ ".stderr"
    BS.writeFile inputFile (Text.encodeUtf8 (Text.pack (inputText input)))
    status <- withBinaryFile inputFile ReadMode $ \hin ->
      withBinaryFile outputFile WriteMode $ \hout ->
      withBinaryFile errorFile WriteMode $ \herr -> bounded $
        withCreateProcess (proc executable []) { env = Just environment,
          std_in = UseHandle hin, std_out = UseHandle hout, std_err = UseHandle herr } $
          \_ _ _ process -> waitForProcess process
    stdoutBytes <- BS.readFile outputFile
    errors <- readFile errorFile
    require (not ("Sanitizer" `isInfixOf` errors || "runtime error:" `isInfixOf` errors)) errors
    (trace,unused) <- readFile traceFile >>= parseTrace
    require (stdoutBytes == outputBytes (Observation (Right ()) trace unused)) "native stdout and write trace disagree"
    result <- case status of
      ExitSuccess -> require (null errors) errors >> pure (Right ())
      ExitFailure 1 -> case stripPrefix "Runtime: " errors of
        Just message -> pure (Left (normalize (R.RuntimeError (reverse (dropWhile (== '\n') (reverse message))))))
        Nothing -> fail ("native process failed unexpectedly: " ++ errors)
      _ -> fail ("native process crashed: " ++ show status ++ "\n" ++ errors)
    pure (Observation result trace unused)
  where emitter = case entry of IOEntry -> emitLLVMIO; ProgramEntry -> emitLLVM

parseTrace :: String -> IO ([Event],String)
parseTrace text = go [] (lines text)
  where
    go accumulated [line] | Just unused <- stripPrefix "U " line = do
      remainingText <- decode unused
      pure (reverse accumulated,remainingText)
    go accumulated ("R":rest) = go (ReadLine:accumulated) rest
    go accumulated (line:rest) | Just bytes <- stripPrefix "W " line = do
      value <- bytesEvent . BS.pack <$> hexBytes bytes
      go (value:accumulated) rest
    go _ _ = fail ("malformed native event trace: " ++ text)
    decode encoded = do
      bytes <- hexBytes encoded
      either (fail . show) (pure . Text.unpack) (Text.decodeUtf8' (BS.pack bytes))
    hexBytes [] = pure []
    hexBytes (a:b:rest) = case readHex [a,b] of
      [(byte,"")] -> (byte:) <$> hexBytes rest
      _ -> fail "invalid native trace hex"
    hexBytes _ = fail "truncated native trace byte"
