module Main (main) where

import Control.Exception (IOException, try)
import Data.List (stripPrefix)
import System.Directory (doesFileExist)
import System.Environment (getArgs, getExecutablePath)
import System.Exit (exitFailure)
import System.FilePath ((</>), takeDirectory)
import System.IO (hPutStrLn, stderr)
import MLF.Compiler
import MLF.LLVM (emitLLVM, emitLLVMIO, emitLLVMForGC, emitLLVMIOForGC)
import MLF.X.Pretty
import Paths_mlf (getDataFileName)
import qualified MLF.X.Parser as X
import qualified MLF.X.Check as X
import qualified MLF.Runtime as R

main :: IO ()
main = getArgs >>= options ImplicitPrelude []
  where
    options mode paths args = case args of
      "--no-prelude":rest -> options NoImplicitPrelude paths rest
      "-i":path:rest -> options mode (paths ++ [path]) rest
      arg:rest | Just path <- stripPrefix "-i" arg, not (null path) ->
        options mode (paths ++ [path]) rest
      "-i":[] -> die "-i requires a module search directory"
      _ -> runArgs mode paths args

runArgs :: PreludeMode -> [FilePath] -> [String] -> IO ()
runArgs mode includes args =
  case commandArgs of
    ["--help"] -> putStrLn usage
    ["--llvm-runtime"] -> runtimePath >>= putStrLn
    ["--emit-llvm","--expr",source] -> emitSource "<expression>" source
    ["--emit-llvm"] -> getContents >>= emitSource "<stdin>"
    ["--emit-llvm","-"] -> getContents >>= emitSource "<stdin>"
    ["--emit-llvm",file] -> compileFileWithPrelude mode includes file >>= emitCompiled
    ["--xmlf-to-llvm"] -> getContents >>= emitTarget "<stdin>"
    ["--xmlf-to-llvm","-"] -> getContents >>= emitTarget "<stdin>"
    ["--xmlf-to-llvm",file] -> load file >>= emitTarget file
    ["--expr",source] -> run "<expression>" source False
    ["--type","--expr",source] -> run "<expression>" source True
    [] -> getContents >>= \s -> run "<stdin>" s False
    ["-"] -> getContents >>= \s -> run "<stdin>" s False
    ["--type"] -> getContents >>= \s -> run "<stdin>" s True
    ["--type","-"] -> getContents >>= \s -> run "<stdin>" s True
    ["--type",file] -> readSource file True
    ["--run","--expr",source] -> execute "<expression>" source
    ["--run"] -> getContents >>= execute "<stdin>"
    ["--run","-"] -> getContents >>= execute "<stdin>"
    ["--run",file] -> compileFileWithPrelude mode includes file >>= executeCompiled
    ["--run-xmlf"] -> getContents >>= executeTarget "<stdin>"
    ["--run-xmlf",file] -> load file >>= executeTarget file
    ["--check"] -> getContents >>= check "<stdin>"
    ["--check",file] -> load file >>= check file
    [file] | take 2 file /= "--" -> readSource file False
    _ -> die usage
  where
    (requestedArgs,argumentSuffix) = break (== "--") args
    (compact,requireIO,commandArgs) = case requestedArgs of
      "--emit-llvm-gc":rest -> (True,False,"--emit-llvm":rest)
      "--xmlf-to-llvm-gc":rest -> (True,False,"--xmlf-to-llvm":rest)
      "--xmlf-to-llvm-io":rest -> (False,True,"--xmlf-to-llvm":rest)
      "--xmlf-to-llvm-io-gc":rest -> (True,True,"--xmlf-to-llvm":rest)
      _ -> (False,False,requestedArgs)
    emit = case (compact,requireIO) of
      (False,False) -> emitLLVM
      (False,True) -> emitLLVMIO
      (True,False) -> emitLLVMForGC
      (True,True) -> emitLLVMIOForGC
    programArguments = drop 1 argumentSuffix
    readSource file onlyType = compileFileWithPrelude mode includes file >>= printCompiled onlyType
    load file = do
      source <- try (readFile file >>= \s -> length s `seq` pure s) :: IO (Either IOException String)
      either (die . show) pure source
    check file source = case X.parseTerm file source >>= X.checkClosed of
      Left err -> die err
      Right ty -> putStrLn (prettyType ty)
    run file source onlyType = compileSourceWithImports mode includes file source >>= printCompiled onlyType
    printCompiled onlyType compiled = case compiled of
      Left err -> die (show err)
      Right result -> do
        putStrLn ((if onlyType then "" else "-- type: ") ++ sourceType result)
        if onlyType then pure () else putStrLn (prettyTerm (compiledTerm result))
    execute file source = compileSourceWithImports mode includes file source >>= executeCompiled
    executeCompiled compiled = case compiled of
      Left err -> die (show err)
      Right result -> executeTerm (compiledTerm result)
    emitSource file source = compileSourceWithImports mode includes file source >>= emitCompiled
    emitCompiled result = case result of
      Left err -> die (show err)
      Right compiled -> either die putStr (emit (compiledTerm compiled))
    emitTarget file source = either die putStr (X.parseTerm file source >>= emit)
    executeTarget file source = either die executeTerm (X.parseTerm file source)
    executeTerm term = do
      outcome <- R.runTermWithArguments programArguments R.consoleBackend term
      either (die . ("Runtime: " ++) . show) pure outcome

die :: String -> IO a
die message = hPutStrLn stderr message >> exitFailure

-- Cabal installs the runtime as package data. Also support a directly invoked
-- dist-newstyle executable, where Cabal's data-directory environment is absent.
runtimePath :: IO FilePath
runtimePath = do
  installed <- getDataFileName "runtime/mlf_runtime.c"
  executable <- getExecutablePath
  choose (installed : [directory </> "runtime" </> "mlf_runtime.c" |
    directory <- ancestors (takeDirectory executable)])
  where
    ancestors directory = directory :
      if takeDirectory directory == directory then [] else ancestors (takeDirectory directory)
    choose [] = die "Cannot find the LLVM runtime; set mlf_datadir to the package data directory."
    choose (file:rest) = do
      source <- doesFileExist file
      header <- doesFileExist (takeDirectory file </> "mlf_runtime.h")
      if source && header then pure file else choose rest

usage :: String
usage = unlines
  [ "Usage: emlf [--no-prelude] [-i DIR ...] [--type] [FILE | --expr SOURCE]"
  , "       emlf --check [XMLF_FILE]"
  , "       emlf [--no-prelude] [-i DIR ...] --run [FILE | --expr SOURCE] [-- ARGS...]"
  , "       emlf --run-xmlf [XMLF_FILE] [-- ARGS...]"
  , "       emlf [--no-prelude] [-i DIR ...] --emit-llvm [FILE | --expr SOURCE]"
  , "       emlf --xmlf-to-llvm [XMLF_FILE]"
  , "       emlf [--no-prelude] [-i DIR ...] --emit-llvm-gc [FILE | --expr SOURCE]"
  , "       emlf --xmlf-to-llvm[-io]-gc [XMLF_FILE]"
  , "       emlf --llvm-runtime"
  , "With no FILE, read eMLF from standard input."
  , "Compile expressions, algebraic data types, classes, and modules to checked xMLF."
  , "Imports load Foo.Bar from Foo/Bar.emlf beside the entry or in -i search roots."
  , "Place --no-prelude and -i options before the command; imports also work with --expr."
  , "The standard prelude supplies Monad and Monad IO; --no-prelude disables it."
  , "--check reads emitted xMLF and checks it independently of type inference."
  , "--run executes a checked IO action; program output goes to standard output."
  , "For interactive input, use --run FILE or --run --expr SOURCE."
  , "--xmlf-to-llvm independently checks xMLF, then emits native LLVM IR."
  , "--emit-llvm compiles eMLF through checked xMLF to LLVM IR."
  , "Link IR with clang, the C file printed by --llvm-runtime, and GMP."
  , "The -gc commands require the runtime built with MLF_USE_BDWGC and MLF_COMPACT_BDWGC."
  ]
