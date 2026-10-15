module SeparateBackends (separateBackendTests) where

import Control.Monad (forM_, unless)
import Data.List (isInfixOf)
import qualified Data.Map.Strict as M
import System.Directory (canonicalizePath, createDirectory, createDirectoryIfMissing, findExecutable, removeFile, renameFile)
import System.Environment (lookupEnv)
import System.Exit (ExitCode(..))
import System.FilePath ((</>), takeDirectory)
import System.Process (readProcessWithExitCode)
import Backends
import MLF.Separate (UnitObject(..), builtinPrelude, compileUnit, linkObjects,
  encodeInterface, decodeInterface, encodeObject, decodeObject)
import MLF.Compiler (PreludeMode(..))
import MLF.Module (loadModuleMap)
import MLF.Module.Syntax (moduleIdentity)
import MLF.Parser (parseModule)
import qualified MLF.X.Parser as XP
import Modules (ModuleProgram, withScratch)
import Separate (separatePrograms, compileSeparateProgram)

separateBackendTests :: Backends -> [(String,IO ())]
separateBackendTests backends =
  [("separate runtime: " ++ label, do
      objects <- either fail pure (compileSeparateProgram mode libraries source)
      term <- either fail pure (linkObjects objects "Main")
      observed <- execute backends IOEntry (Input "" False) term
      either (fail . show) pure (outcome observed)
      unless (output observed == expected) (fail (show observed)))
    | (label,mode,libraries,source,expected) <- separatePrograms] ++
  [("separate CLI: " ++ label, cliProgram backends fixture)
    | fixture@(label,_,_,_,_) <- separatePrograms] ++
  [("separate runtime: interface-only CLI and invalidation", cliTests backends)]

selectedCompiler :: IO FilePath
selectedCompiler = do
  configured <- lookupEnv "MLF_BOOTSTRAP_COMPILER"
  nativeDrivers <- any (/= Nothing) <$> mapM lookupEnv ["MLF_BOOTSTRAP_INTERPRETER","MLF_BOOTSTRAP_LLVM"]
  selected <- case configured of
    Just candidate -> pure candidate
    Nothing -> do
      unless (not nativeDrivers) (fail "Native separate-module tests require MLF_BOOTSTRAP_COMPILER")
      pure "emlf"
  findExecutable selected >>= maybe (fail "Cannot find module compiler") canonicalizePath

cliProgram :: Backends -> ModuleProgram -> IO ()
cliProgram backends (_,mode,libraries,source,expected) = withScratch $ \directory -> do
  compiler <- selectedCompiler
  root <- either fail pure (parseModule "Main.emlf" source)
  graph <- either fail pure (loadModuleMap (M.fromList [(n,(n ++ ".emlf",s)) | (n,s) <- libraries]) root)
  let originals = M.insert "Main" source (M.fromList libraries)
      prefix name = directory </> map (\c -> if c == '.' then '/' else c) name
      options = case mode of ImplicitPrelude -> []; NoImplicitPrelude -> ["--no-prelude"]
      command args = do
        (code,out,err) <- readProcessWithExitCode compiler (options ++ ["-i",directory] ++ args) ""
        unless (code == ExitSuccess && null err) (fail (show (args,code,out,err)))
        pure out
  forM_ graph $ \m -> do
    let name = moduleIdentity m
        file = prefix name ++ ".emlf"
    text <- maybe (fail ("fixture missing " ++ name)) pure (M.lookup name originals)
    createDirectoryIfMissing True (takeDirectory file)
    writeFile file text
    _ <- command ["--compile-module",file,"-o",prefix name]
    removeFile file
  target <- command ["--link-module",prefix "Main" ++ ".mlfi"]
  term <- either fail pure (XP.parseTerm "<separate CLI corpus>" target)
  observed <- execute backends IOEntry (Input "" False) term
  either (fail . show) pure (outcome observed)
  unless (output observed == expected) (fail (show observed))

cliTests :: Backends -> IO ()
cliTests backends = withScratch $ \directory -> do
  compiler <- selectedCompiler
  let library = directory </> "compiled libraries"
      source = directory </> "Library.emlf"
      entry = directory </> "Main.emlf"
      prefix = library </> "Library"
      mainPrefix = directory </> "Main"
      command args = do
        (code,out,err) <- readProcessWithExitCode compiler args ""
        unless (code == ExitSuccess && null err) (fail (show (args,code,out,err)))
        pure out
      reject args reason = do
        (code,out,err) <- readProcessWithExitCode compiler args ""
        unless (code /= ExitSuccess && null out && reason `isInfixOf` err) (fail (show (code,out,err)))
      librarySource value = unlines ["module Library (Box(..), identity, answer) where",
          "data Box a = Box a", "identity x = x", "answer = " ++ value]
      buildLib value = do
        writeFile source (librarySource value)
        _ <- command ["--compile-module",source,"-o",prefix]
        removeFile source
      link = command ["-i",library,"--link-module",mainPrefix ++ ".mlfi"]
      runTarget expected target = do
        term <- either fail pure (XP.parseTerm "<separate CLI>" target)
        observed <- execute backends IOEntry (Input "" False) term
        either (fail . show) pure (outcome observed)
        unless (output observed == expected) (fail (show observed))
  createDirectory library
  buildLib "42"
  -- With native drivers this is a bidirectional seed/native artifact exchange.
  nativeInterface <- readFile (prefix ++ ".mlfi") >>= either fail pure . decodeInterface
  _ <- readFile (prefix ++ ".mlfo") >>= either fail pure . decodeObject nativeInterface
  sourceModule <- either fail pure (parseModule source (librarySource "42"))
  UnitObject prelude _ <- either fail pure builtinPrelude
  seedObject@(UnitObject seedInterface _) <- either fail pure (compileUnit ImplicitPrelude [prelude] sourceModule)
  writeFile (prefix ++ ".mlfo") (encodeObject seedObject)
  writeFile (prefix ++ ".mlfi") (encodeInterface seedInterface)
  originalInterface <- readFile (prefix ++ ".mlfi")
  originalObject <- readFile (prefix ++ ".mlfo")
  length originalInterface `seq` length originalObject `seq` pure ()
  renameFile (prefix ++ ".mlfo") (prefix ++ ".saved")
  writeFile entry (unlines ["module Main where", "import Library", "main = case identity (Box answer) of", "  Box n -> printInt n"])
  _ <- command ["-i",library,"--compile-module",entry,"-o",mainPrefix]
  removeFile entry
  reject ["-i",library,"--link-module",mainPrefix ++ ".mlfi"] ".mlfo"
  renameFile (prefix ++ ".saved") (prefix ++ ".mlfo")
  target <- link
  runTarget "42\n" target
  direct <- command ["-i",library,"--module-to-llvm",mainPrefix ++ ".mlfi"]
  (code,llvm,errors) <- readProcessWithExitCode compiler ["--xmlf-to-llvm"] target
  unless (code == ExitSuccess && null errors && direct == llvm) (fail "separate LLVM emission differs from checked target emission")
  -- Only the implementation changes: an existing consumer remains linkable.
  buildLib "43"
  link >>= runTarget "43\n"
  buildLib "\"changed type\""
  reject ["-i",library,"--link-module",mainPrefix ++ ".mlfi"] "stale dependency interface"
  writeFile (prefix ++ ".mlfi") originalInterface
  writeFile (prefix ++ ".mlfo") (originalObject ++ "corrupt")
  reject ["-i",library,"--link-module",mainPrefix ++ ".mlfi"] "artifact"
  writeFile (prefix ++ ".mlfo") originalObject
  writeFile (prefix ++ ".mlfi") "6:MLFI-9"
  reject ["-i",library,"--link-module",mainPrefix ++ ".mlfi"] "unsupported"
  writeFile (prefix ++ ".mlfi") originalInterface
  link >>= runTarget "42\n"
