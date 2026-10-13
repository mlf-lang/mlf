module ModuleBackends (moduleBackendTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import System.Directory (canonicalizePath, createDirectory, createDirectoryLink, findExecutable)
import System.Environment (lookupEnv)
import System.Exit (ExitCode (..))
import System.FilePath ((</>))
import System.Process (readProcessWithExitCode)
import Backends
import MLF.Compiler
import qualified MLF.X.Parser as X
import Modules (modulePrograms, checkModule, withScratch)

moduleBackendTests :: Backends -> [(String,IO ())]
moduleBackendTests backends =
  [ ("modules runtime: " ++ label, do
      compiled <- checkModule mode libraries input
      observed <- execute backends IOEntry (Input "" False) (compiledTerm compiled)
      either (fail . show) pure (outcome observed)
      unless (output observed == expected) (fail ("unexpected output: " ++ show (output observed))))
    | (label,mode,libraries,input,expected) <- modulePrograms ] ++
  [ ("modules runtime: multi-file example", do
      compiled <- compileFile [] "examples/modules/Main.emlf" >>= either (fail . show) pure
      observed <- execute backends IOEntry (Input "" False) (compiledTerm compiled)
      either (fail . show) pure (outcome observed)
      unless (output observed == "25\n") (fail (show observed)))
  , ("modules runtime: CLI imports and output paths", cliTests backends) ]

-- Compile via the installed executable, independently parse its target output,
-- and execute every resulting program with both backends. Also compare direct
-- LLVM emission with the separately parsed xMLF-to-LLVM command.
cliTests :: Backends -> IO ()
cliTests backends = withScratch $ \directory -> do
  configured <- lookupEnv "MLF_BOOTSTRAP_COMPILER"
  nativeDrivers <- any (/= Nothing) <$> mapM lookupEnv ["MLF_BOOTSTRAP_INTERPRETER","MLF_BOOTSTRAP_LLVM"]
  selected <- case configured of
    Just candidate -> pure candidate
    Nothing -> do
      unless (not nativeDrivers) (fail "Native backend CLI tests require MLF_BOOTSTRAP_COMPILER; refusing seed fallback")
      pure "emlf"
  compiler <- findExecutable selected >>= maybe (fail ("Cannot execute selected module CLI compiler: " ++ selected)) canonicalizePath
  putStrLn ("Module CLI compiler: " ++ compiler)
  let libraries = directory </> "library files"
      entry = directory </> "Main.emlf"
      command args input = do
        (status,text,errors) <- readProcessWithExitCode compiler args input
        unless (status == ExitSuccess) (fail (show args ++ "\n" ++ text ++ errors))
        pure text
      equal expected actual = unless (actual == expected) (fail ("unexpected CLI output: " ++ show actual))
      runTarget source = do
        term <- either fail pure (X.parseTerm "<CLI xMLF>" source)
        observed <- execute backends IOEntry (Input "" False) term
        either (fail . show) pure (outcome observed)
        equal "42\n" (output observed)
      reject args reason = do
        (status,text,errors) <- readProcessWithExitCode compiler args ""
        unless (status /= ExitSuccess && null text && reason `isInfixOf` errors)
          (fail (show (status,text,errors)))
  createDirectory libraries
  writeFile (libraries </> "Helpers.emlf") "module Helpers (inc) where\ninc x = x + 1\n"
  writeFile entry "module Main where\nimport Helpers (inc)\nmain = printInt (inc 41)\n"
  command ["-i",libraries,"--type",entry] "" >>= equal "IO Unit\n"
  command ["-i",directory </> "missing search root","-i",libraries,"--type",entry] "" >>= equal "IO Unit\n"
  target <- command ["-i",libraries,entry] ""
  runTarget target
  command ["--check"] target >>= equal "IO Unit\n"
  direct <- command ["-i" ++ libraries,"--emit-llvm",entry] ""
  command ["--xmlf-to-llvm"] target >>= equal direct
  command ["-i",libraries,"--run",entry] "" >>= equal "42\n"
  command ["-i",libraries </> ".." </> "library files","--run",entry] "" >>= equal "42\n"
  let alias = directory </> "module alias"
  createDirectoryLink libraries alias
  command ["-i",alias,"--run",entry] "" >>= equal "42\n"
  let hierarchy = libraries </> "Geometry"
      nestedEntry = hierarchy </> "Main.emlf"
  createDirectory hierarchy
  writeFile (hierarchy </> "Support.emlf") "module Geometry.Support (inc) where\ninc x = x + 1\n"
  writeFile nestedEntry "module Geometry.Main where\nimport Geometry.Support\nmain = printInt (inc 41)\n"
  command ["--run",nestedEntry] "" >>= equal "42\n"
  command ["--run-xmlf"] target >>= equal "42\n"
  let expression = "import Helpers (inc)\nprintInt (inc 41)"
  command ["-i",libraries,"--expr",expression] "" >>= runTarget
  command ["-i",libraries] expression >>= runTarget
  command ["-i",libraries,"--type","-"] expression >>= equal "IO Unit\n"
  command ["--no-prelude","-i",libraries,"--type","--expr",
    "import Prelude (Monad(..), IO, Int)\n(return 42 : IO Int)"] "" >>= equal "IO Int\n"
  reject ["--type",entry] "cannot find module Helpers"
  reject ["-i",directory </> "missing search root","--type",entry] "ModuleResolution: cannot find module Helpers"
  reject ["-i"] "-i requires a module search directory"
