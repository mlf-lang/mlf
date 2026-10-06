module Main (main) where

import Control.Exception (IOException, try)
import System.Environment (getArgs)
import System.Exit (exitFailure)
import System.IO (hPutStrLn, stderr)
import MLF.Compiler
import MLF.X.Pretty
import qualified MLF.X.Parser as X
import qualified MLF.X.Check as X

main :: IO ()
main = do
  args <- getArgs
  case args of
    ["--help"] -> putStrLn usage
    ["--expr",source] -> run "<expression>" source False
    ["--type","--expr",source] -> run "<expression>" source True
    [] -> getContents >>= \s -> run "<stdin>" s False
    ["-"] -> getContents >>= \s -> run "<stdin>" s False
    ["--type"] -> getContents >>= \s -> run "<stdin>" s True
    ["--type",file] -> readSource file True
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
    run file source onlyType = case compile file source of
      Left err -> die (show err)
      Right result -> do
        putStrLn ((if onlyType then "" else "-- type: ") ++ prettyType (inferredType result))
        if onlyType then pure () else putStrLn (prettyTerm (compiledTerm result))

die :: String -> IO a
die message = hPutStrLn stderr message >> exitFailure

usage :: String
usage = unlines
  [ "Usage: emlf [--type] [FILE | --expr SOURCE]"
  , "       emlf --check [XMLF_FILE]"
  , "With no FILE, read eMLF from standard input."
  , "Compile lambda, application, let, and annotated expressions to checked xMLF."
  , "--check reads emitted xMLF and checks it independently of type inference."
  ]
