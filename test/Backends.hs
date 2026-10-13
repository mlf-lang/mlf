module Backends
  ( Backends, Event (..), Entry (..), Input (..), Observation (..)
  , withBackends, withExecutionTimeout, inCase, auditBackends, execute, executeWithArguments, capture, output, outputBytes, stderrOutput
  ) where

import Control.Concurrent (threadDelay)
import Control.Exception (NonTermination, SomeException, bracket, displayException, mask, mask_, onException, try)
import Control.Monad (forM, unless, when)
import qualified Data.ByteString as BS
import qualified Data.ByteString.Char8 as Bytes
import Data.Char (isAlpha, isAlphaNum)
import Data.IORef
import Data.List (isInfixOf, stripPrefix)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
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
import MLF.LLVM (emitLLVM, emitLLVMIO, emitLLVMForGC, emitLLVMIOForGC)
import qualified MLF.Runtime as R
import qualified MLF.X.Syntax as X
import MLF.X.Pretty (prettyTerm)

data Kind = Interpreter | LLVM deriving (Eq, Ord, Show, Enum, Bounded)
data Entry = IOEntry | ProgramEntry deriving (Eq, Show)
data Event = ReadLine | Write String | WriteBytes BS.ByteString | WriteError String deriving (Eq, Show, Read)
data Input = Input { inputText :: String, failWrites :: Bool }
           | RawInput { inputBytes :: BS.ByteString, failWrites :: Bool } deriving Show

encodedInput :: Input -> BS.ByteString
encodedInput (Input text _) = Text.encodeUtf8 (Text.pack text)
encodedInput (RawInput bytes _) = bytes

-- Keep existing text assertions readable; raw fixtures compare remaining bytes
-- through a reversible Latin-1 String instead of losing invalid UTF-8.
decodeInput :: Input -> BS.ByteString -> String
decodeInput (Input _ _) = Text.unpack . Text.decodeUtf8
decodeInput (RawInput _ _) = Bytes.unpack
data Observation = Observation
  { outcome :: Either R.RuntimeError (), events :: [Event], remaining :: String }
  deriving (Eq, Show)
data Backends = Backends
  { directory :: FilePath, clang :: FilePath, flags :: [String], linkFlags :: [String]
  , binaries :: IORef (Map.Map String FilePath), serial :: IORef Int
  , currentCase :: IORef String, visits :: IORef (Map.Map (String,Int) [Kind])
  , compactGC :: Bool
  , executionTimeoutMicros :: Int, candidateTimeoutMicros :: Int
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

candidateBudget :: IO Int
candidateBudget = do
  enabled <- any (/= Nothing) <$> mapM lookupEnv ["MLF_BOOTSTRAP_INTERPRETER","MLF_BOOTSTRAP_LLVM"]
  setting <- lookupEnv "MLF_BOOTSTRAP_TIMEOUT_SECONDS"
  seconds <- case setting of
    Nothing -> pure 60
    Just value -> do
      require enabled "MLF_BOOTSTRAP_TIMEOUT_SECONDS requires an external bootstrap interpreter or LLVM driver"
      case readMaybe value :: Maybe Integer of
        Just n | n > 0 && n <= toInteger (maxBound :: Int) `div` 1000000 -> pure (fromInteger n)
        _ -> fail "MLF_BOOTSTRAP_TIMEOUT_SECONDS must be a positive integer within the supported timer range"
  when enabled (putStrLn ("Bootstrap candidate execution/emission budget: " ++ show seconds ++ " seconds"))
  pure (seconds * 1000000)

withBackends :: (Backends -> IO a) -> IO a
withBackends action = do
  candidateTimeout <- candidateBudget
  compiler <- tool "clang"
  pkg <- tool "pkg-config"
  includes <- words <$> command pkg ["--cflags","gmp"]
  gmp <- words <$> command pkg ["--libs","gmp"]
  supplied <- maybe [] words <$> lookupEnv "MLF_LLVM_TEST_CFLAGS"
  abi <- maybe "standard" id <$> lookupEnv "MLF_LLVM_TEST_ABI"
  require (abi `elem` ["standard","compact-gc"]) "invalid MLF_LLVM_TEST_ABI"
  let compact = abi == "compact-gc"
      extra = supplied ++ if compact then ["-DMLF_USE_BDWGC","-DMLF_COMPACT_BDWGC"] else []
  extraLibraries <- maybe [] words <$> lookupEnv "MLF_LLVM_TEST_LIBS"
  optimization <- maybe "-O2" id <$> lookupEnv "MLF_LLVM_TEST_OPT"
  require (optimization `elem` ["-O0","-O1","-O2","-O3"]) "invalid MLF_LLVM_TEST_OPT"
  bracket scratch removeDirectoryRecursive $ \dir -> do
    let common = [optimization,"-std=c11","-Wall","-Wextra","-Werror"] ++ extra
        interpose = ["-Dgetline=mlf_test_getline","-Dfwrite=mlf_test_fwrite",
          "-Dfputc=mlf_test_fputc","-Dfflush=mlf_test_fflush"]
    _ <- command compiler (common ++ includes ++ interpose ++ ["-DMLF_GC_THRESHOLD=32",
      "-c","runtime/mlf_runtime.c","-o",dir </> "runtime.o"])
    _ <- command compiler (common ++ ["-c","test/native_trace.c","-o",dir </> "trace.o"])
    context <- Backends dir compiler ([optimization] ++ extra ++ gmp ++ ["-lm"]) extraLibraries
      <$> newIORef Map.empty <*> newIORef 0 <*> newIORef "<unlabelled>" <*> newIORef Map.empty
      <*> pure compact <*> pure 60000000 <*> pure candidateTimeout
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

-- Compiler conformance fixtures execute another compiler as their program.
-- Their explicit longer bound does not relax ordinary backend test budgets.
-- The derived context shares the same coverage ledger and binary cache.
withExecutionTimeout :: Int -> Backends -> Backends
withExecutionTimeout seconds context
  | seconds > 0 && seconds <= maxBound `div` 1000000 = context { executionTimeoutMicros = seconds * 1000000 }
  | otherwise = error "backend execution timeout must be positive and within the supported timer range"

boundedExecution :: Backends -> IO a -> IO a
boundedExecution context operation = timeout (executionTimeoutMicros context) operation >>=
  maybe (fail ("backend operation timed out after " ++ show (executionTimeoutMicros context `div` 1000000) ++ " seconds")) pure

candidateContext :: Backends -> Backends
candidateContext context = context { executionTimeoutMicros = candidateTimeoutMicros context }

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
execute context = executeWithArguments context []

executeWithArguments :: Backends -> [String] -> Entry -> Input -> X.Term -> IO Observation
executeWithArguments context arguments entry input term = do
  label <- readIORef (currentCase context)
  index <- atomicModifyIORef' (serial context) (\n -> (n+1,n))
  let row = (label,index)
  writeRow row []
  results <- forM [minBound .. maxBound] $ \kind -> do
    attempted <- try (case kind of
      Interpreter -> do
        external <- lookupEnv "MLF_BOOTSTRAP_INTERPRETER"
        case external of
          Nothing -> isolated context index (interpreted arguments entry input term)
          Just executable -> externalInterpreted context index executable arguments entry input term
      LLVM -> native context index arguments entry input term) :: IO (Either SomeException Observation)
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
  Write text -> Text.encodeUtf8 (Text.pack text); WriteBytes bytes -> bytes; _ -> BS.empty) . events

stderrOutput :: Observation -> String
stderrOutput = concatMap (\event -> case event of WriteError text -> text; _ -> "") . events

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
  status <- restore (boundedExecution context await) `onException` cleanup
  case status of
    Exited ExitSuccess -> pure ()
    _ -> fail ("interpreter process failed: " ++ show status)
  encoded <- readFile file
  case readMaybe encoded :: Maybe (Either String (Either String (),[Event],String)) of
    Just (Right (result,trace,unused)) -> pure (Observation
      (either (Left . R.RuntimeError) Right result) trace unused)
    Just (Left err) -> fail ("interpreter worker: " ++ err)
    Nothing -> fail "malformed interpreter observation"

interpreted :: [String] -> Entry -> Input -> X.Term -> IO Observation
interpreted arguments entry input term = do
  pending <- newIORef (encodedInput input)
  trace <- newIORef []
  let rawLine = do
        modifyIORef' trace (ReadLine:)
        rest <- readIORef pending
        let (line,suffix) = BS.break (== 10) rest
            complete = if BS.null suffix then line else BS.snoc line 10
        writeIORef pending (BS.drop 1 suffix)
        pure complete
      backend = R.IOBackend
        { R.readLine = do
            bytes <- rawLine
            if BS.null bytes then ioError (userError "test input exhausted") else do
              let line = if BS.last bytes == 10 then BS.init bytes else bytes
              either (const (ioError (userError "invalid UTF-8 input"))) (pure . Text.unpack) (Text.decodeUtf8' line)
        , R.readByteLine = rawLine
        , R.writeText = \text -> do
            modifyIORef' trace (Write text:)
            when (failWrites input) (ioError (userError "write failed"))
        , R.writeBytes = \bytes -> do
            modifyIORef' trace (bytesEvent bytes:)
            when (failWrites input) (ioError (userError "write failed"))
        }
      options = R.RuntimeOptions arguments (\text -> do
        modifyIORef' trace (WriteError text:)
        when (failWrites input) (ioError (userError "write failed")))
      run = case entry of IOEntry -> R.runTermWithOptions; ProgramEntry -> R.runProgramWithOptions
  result <- try (try (run options backend term)) :: IO (Either NonTermination (Either ExitCode (Either R.RuntimeError ())))
  let normalized = case result of
        Left _ -> Left (R.RuntimeError "cyclic evaluation of a recursive binding")
        Right (Left ExitSuccess) -> Right ()
        Right (Left (ExitFailure status)) -> Left (R.RuntimeError ("exit status " ++ show status))
        Right (Right value) -> either (Left . normalize) Right value
  Observation normalized <$> (reverse <$> readIORef trace) <*> (decodeInput input <$> readIORef pending)

normalize :: R.RuntimeError -> R.RuntimeError
normalize error' = R.RuntimeError $ case stripPrefix "LLVM " message of
  Just rest -> rest
  Nothing
    | "test input exhausted" `isInfixOf` message || "getLine reached EOF" `isInfixOf` message -> "IO error: test input exhausted"
    | "invalid UTF-8 input" `isInfixOf` message -> "IO error: invalid UTF-8 input"
    | message == "IO error: file write failed" -> message
    | "write failed" `isInfixOf` message || "output failed" `isInfixOf` message -> "IO error: write failed"
    | "cyclic evaluation" `isInfixOf` message -> "cyclic evaluation of a recursive binding"
    | otherwise -> message
  where message = show error'

-- The optional candidates consume serialized target syntax and make their own
-- checking decision. Never call the seed emitter first: that would mask a
-- candidate verifier that incorrectly accepts or rejects a target program.
nativeEmission :: Backends -> Int -> Entry -> X.Term -> IO (Either String String)
nativeEmission context index entry term = do
  external <- lookupEnv "MLF_BOOTSTRAP_LLVM"
  case external of
    Nothing -> pure (case (compactGC context,entry) of
      (False,IOEntry) -> emitLLVMIO term
      (False,ProgramEntry) -> emitLLVM term
      (True,IOEntry) -> emitLLVMIOForGC term
      (True,ProgramEntry) -> emitLLVMForGC term)
    Just executable -> do
      file <- transportTarget context index "llvm" term
      let mode = (case entry of IOEntry -> "--xmlf-to-llvm-io"; ProgramEntry -> "--xmlf-to-llvm") ++
            (if compactGC context then "-gc" else "")
      (status,text,errors) <- boundedExecution (candidateContext context) (readCreateProcessWithExitCode (proc executable [mode,file]) "")
      case status of
        ExitSuccess -> require (null errors) errors >> pure (Right text)
        ExitFailure 1 -> pure (Left (stripFinalNewline errors))
        _ -> fail ("bootstrap LLVM emitter crashed: " ++ show status ++ "\n" ++ text ++ errors)

externalInterpreted :: Backends -> Int -> FilePath -> [String] -> Entry -> Input -> X.Term -> IO Observation
externalInterpreted context index executable arguments entry input term = do
  file <- transportTarget context index "interpreter" term
  let mode = case entry of IOEntry -> "--run-xmlf"; ProgramEntry -> "--run-program-xmlf"
  observeExecutable (candidateContext context) index ([mode,file,"--"] ++ arguments) input executable

transportTarget :: Backends -> Int -> String -> X.Term -> IO FilePath
transportTarget context index backend term = do
  let file = directory context </> ("target-" ++ backend ++ "-" ++ show index ++ ".xmlf")
  writeFile file (prettyTerm (transportNames term))
  pure file

stripFinalNewline :: String -> String
stripFinalNewline message = if not (null message) && last message == '\n' then init message else message

-- Names in caller-built targets can use negative identities and arbitrary
-- display hints. Target text requires a printable nonnegative suffix. This
-- bijection preserves every identity, including free references and deliberate
-- reuse in disjoint scopes; it changes no binding or program structure.
transportNames :: X.Term -> X.Term
transportNames term = rewrite term
  where
    identities = Set.toAscList (Set.fromList (collect term))
    renaming = Map.fromList (zip identities [0..])
    name n = X.Name (renaming Map.! X.nameId n) (printableHint (X.nameHint n))
    printableHint hint@(first:rest)
      | isAlpha first && all (\c -> isAlphaNum c || c `elem` "_'") rest = hint
    printableHint _ = "v"
    pattern' p = case p of
      X.DefaultPattern n -> X.DefaultPattern (fmap name n)
      X.ConstructorPattern c ns -> X.ConstructorPattern c (map (fmap name) ns)
    collect expression = case expression of
      X.VarTerm n -> [X.nameId n]
      X.Abs n _ b -> X.nameId n : collect b
      X.App f a -> collect f ++ collect a
      X.TypeAbs _ _ b -> collect b
      X.TypeApp a _ -> collect a
      X.Let n a b -> X.nameId n : collect a ++ collect b
      X.LetRec ds b -> concat [X.nameId n : collect a | (n,_,a) <- ds] ++ collect b
      X.Case a _ bs -> collect a ++ concat
        [map X.nameId (X.patternNames p) ++ collect b | X.Alternative p b <- bs]
      X.WithData _ b -> collect b
      _ -> []
    rewrite expression = case expression of
      X.VarTerm n -> X.VarTerm (name n)
      X.Abs n t b -> X.Abs (name n) t (rewrite b)
      X.App f a -> X.App (rewrite f) (rewrite a)
      X.TypeAbs a t b -> X.TypeAbs a t (rewrite b)
      X.TypeApp a c -> X.TypeApp (rewrite a) c
      X.Let n a b -> X.Let (name n) (rewrite a) (rewrite b)
      X.LetRec ds b -> X.LetRec [(name n,t,rewrite a) | (n,t,a) <- ds] (rewrite b)
      X.Case a t bs -> X.Case (rewrite a) t [X.Alternative (pattern' p) (rewrite b) | X.Alternative p b <- bs]
      X.WithData ds b -> X.WithData ds (rewrite b)
      _ -> expression

native :: Backends -> Int -> [String] -> Entry -> Input -> X.Term -> IO Observation
native context index arguments entry input term = do
  emitted <- nativeEmission context index entry term
  case emitted of
    Left message -> pure (Observation (Left (normalize (R.RuntimeError message))) [] (decodeInput input (encodedInput input)))
    Right ir -> do
      known <- readIORef (binaries context)
      executable <- case Map.lookup ir known of
        Just file -> pure file
        Nothing -> do
          let file = directory context </> ("program-" ++ show index)
              source = file ++ ".ll"
          writeFile source ir
          _ <- command (clang context) (flags context ++ ["-Wno-override-module",source,
            directory context </> "runtime.o",directory context </> "trace.o","-o",file] ++ linkFlags context)
          modifyIORef' (binaries context) (Map.insert ir file)
          pure file
      observeExecutable context index arguments input executable

observeExecutable :: Backends -> Int -> [String] -> Input -> FilePath -> IO Observation
observeExecutable context index arguments input executable = do
  let traceFile = directory context </> ("trace-" ++ show index)
  inherited <- filter (\(key,_) -> key `notElem` ["MLF_TEST_TRACE","MLF_TEST_FAIL_WRITE"]) <$> getEnvironment
  let environment = ("MLF_TEST_TRACE",traceFile) :
        [("MLF_TEST_FAIL_WRITE","1") | failWrites input] ++ inherited
  let inputFile = traceFile ++ ".stdin"
      outputFile = traceFile ++ ".stdout"
      errorFile = traceFile ++ ".stderr"
  BS.writeFile inputFile (encodedInput input)
  status <- withBinaryFile inputFile ReadMode $ \hin ->
    withBinaryFile outputFile WriteMode $ \hout ->
    withBinaryFile errorFile WriteMode $ \herr -> boundedExecution context $
      withCreateProcess (proc executable arguments) { env = Just environment,
        std_in = UseHandle hin, std_out = UseHandle hout, std_err = UseHandle herr } $
        \_ _ _ process -> waitForProcess process
  stdoutBytes <- BS.readFile outputFile
  diagnostics <- readFile errorFile
  require (not ("Sanitizer" `isInfixOf` diagnostics || "runtime error:" `isInfixOf` diagnostics)) diagnostics
  (trace,unused) <- readFile traceFile >>= parseTrace input
  require (stdoutBytes == outputBytes (Observation (Right ()) trace unused)) "native stdout and write trace disagree"
  runtimeErrors <- maybe (fail "native stderr and write trace disagree") pure
    (stripPrefix (stderrOutput (Observation (Right ()) trace unused)) diagnostics)
  result <- case status of
    ExitSuccess -> require (null runtimeErrors) runtimeErrors >> pure (Right ())
    ExitFailure 1 | Just message <- stripPrefix "Runtime: " runtimeErrors ->
      pure (Left (normalize (R.RuntimeError (if not (null message) && last message == '\n' then init message else message))))
    ExitFailure code | code > 0 && code <= 255 && null runtimeErrors ->
      pure (Left (R.RuntimeError ("exit status " ++ show code)))
    _ -> fail ("native process crashed: " ++ show status ++ "\n" ++ runtimeErrors)
  pure (Observation result trace unused)

parseTrace :: Input -> String -> IO ([Event],String)
parseTrace input text = go [] (lines text)
  where
    go accumulated [line] | Just unused <- stripPrefix "U " line = do
      remainingText <- decode unused
      pure (reverse accumulated,remainingText)
    go accumulated ("R":rest) = go (ReadLine:accumulated) rest
    go accumulated (line:rest) | Just bytes <- stripPrefix "W " line = do
      value <- bytesEvent . BS.pack <$> hexBytes bytes
      go (value:accumulated) rest
    go accumulated (line:rest) | Just bytes <- stripPrefix "E " line = do
      value <- Text.unpack . Text.decodeUtf8 . BS.pack <$> hexBytes bytes
      go (WriteError value:accumulated) rest
    go _ _ = fail ("malformed native event trace: " ++ text)
    decode encoded = do
      bytes <- hexBytes encoded
      pure (decodeInput input (BS.pack bytes))
    hexBytes [] = pure []
    hexBytes (a:b:rest) = case readHex [a,b] of
      [(byte,"")] -> (byte:) <$> hexBytes rest
      _ -> fail "invalid native trace hex"
    hexBytes _ = fail "truncated native trace byte"
