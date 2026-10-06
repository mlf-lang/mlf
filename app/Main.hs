module Main (main) where

import Control.Exception (IOException, try)
import System.Environment (getArgs)
import System.Exit (exitFailure)
import System.IO (hPutStrLn, stderr)
import MLF.Compiler
import MLF.X.Pretty
import qualified MLF.X.Parser as X
import qualified MLF.X.Check as X
import qualified MLF.Runtime as R

main :: IO ()
main = do
  args <- getArgs
  case args of
    "--no-prelude":rest -> runArgs NoImplicitPrelude rest
    _ -> runArgs ImplicitPrelude args

runArgs :: PreludeMode -> [String] -> IO ()
runArgs mode args =
  case args of
    ["--help"] -> putStrLn usage
    ["--expr",source] -> run "<expression>" source False
    ["--type","--expr",source] -> run "<expression>" source True
    [] -> getContents >>= \s -> run "<stdin>" s False
    ["-"] -> getContents >>= \s -> run "<stdin>" s False
    ["--type"] -> getContents >>= \s -> run "<stdin>" s True
    ["--type",file] -> readSource file True
    ["--run","--expr",source] -> execute "<expression>" source
    ["--run"] -> getContents >>= execute "<stdin>"
    ["--run","-"] -> getContents >>= execute "<stdin>"
    ["--run",file] -> load file >>= execute file
    ["--run-xmlf"] -> getContents >>= executeTarget "<stdin>"
    ["--run-xmlf",file] -> load file >>= executeTarget file
    ["--check"] -> getContents >>= check "<stdin>"
    ["--check",file] -> load file >>= check file
    [file] | take 2 file /= "--" -> readSource file False
    _ -> die usage
  where
    readSource file onlyType = do
      source <- load file
      run file source onlyType
    load file = do
      source <- try (readFile file >>= \s -> length s `seq` pure s) :: IO (Either IOException String)
      either (die . show) pure source
    check file source = case X.parseTerm file source >>= X.checkClosed of
      Left err -> die err
      Right ty -> putStrLn (prettyType ty)
    run file source onlyType = case compileWithPrelude mode file source of
      Left err -> die (show err)
      Right result -> do
        putStrLn ((if onlyType then "" else "-- type: ") ++ sourceType result)
        if onlyType then pure () else putStrLn (prettyTerm (compiledTerm result))
    execute file source = case compileWithPrelude mode file source of
      Left err -> die (show err)
      Right result -> executeTerm (compiledTerm result)
    executeTarget file source = either die executeTerm (X.parseTerm file source)
    executeTerm term = do
      outcome <- R.runTerm R.consoleBackend term
      either (die . ("Runtime: " ++) . show) pure outcome

die :: String -> IO a
die message = hPutStrLn stderr message >> exitFailure

usage :: String
usage = unlines
  [ "Usage: emlf [--no-prelude] [--type] [FILE | --expr SOURCE]"
  , "       emlf --check [XMLF_FILE]"
  , "       emlf [--no-prelude] --run [FILE | --expr SOURCE]"
  , "       emlf --run-xmlf [XMLF_FILE]"
  , "With no FILE, read eMLF from standard input."
  , "Compile expressions, algebraic data types, and type classes to checked xMLF."
  , "The standard prelude supplies Monad and Monad IO; --no-prelude disables it."
  , "--check reads emitted xMLF and checks it independently of type inference."
  , "--run executes a checked IO action; program output goes to standard output."
  , "For interactive input, use --run FILE or --run --expr SOURCE."
  ]
