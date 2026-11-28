{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (unless)

import System.Environment (getArgs)
import System.FilePath ((</>))
import qualified Bootstrap.CompilerCore as Core
import qualified Bootstrap.SourceCrate as Source
import qualified Bootstrap.CrateSession as Session
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.Map as M
import qualified Bootstrap.Module as Mod
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.PreparedLibraries as Prepared
import qualified Bootstrap.Runtime as Runtime
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Syntax as X
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as P

ok (T.Left e) = error (H.unpack e)
ok (T.Right x) = pure x
compiled (T.Left e) = error (H.unpack (Core.prettyError e))
compiled (T.Right x) = pure x

main = do
  [dir] <- getArgs
  let file = H.literal (dir </> "library.mlfci")
      sourcePath = H.literal (dir </> "ZLib.hs")
      key = Artifact.definitionName "lib" (Mod.Entity "ZLib" "value" Mod.Value)
  closure <- Artifact.loadInterfaces [file] >>= ok
  rawObjects <- mapM (\(path,iface) -> do
    let objectPath = Artifact.objectPath path
    obj <- Artifact.readObject objectPath iface >>= ok
    Prepared.LibraryObject <$> P.fileDigest path <*> P.fileDigest objectPath <*> pure obj) closure
  input <- P.readFile sourcePath
  library <- ok (Parser.parseModule sourcePath input)
  sourceHash <- P.fileDigest sourcePath
  identity <- P.fileDigest file
  let source = Prepared.LibrarySource "ZLib" sourcePath input sourceHash (Mod.sourceSyntax library)
      mode = T.NoImplicitPrelude
  raw <- Prepared.prepareFresh identity mode [source] rawObjects >>= ok
  let check label rhs answer imports = do
        let body = H.literal ("module Root where { import qualified ZLib as L; import MLF.Primitive; " ++
                "value = 1; main = " ++ rhs ++ " }")
            path = H.literal (dir </> "Root.emlf")
        root <- ok (Parser.parseModule path body)
        let loaded = Mod.LoadedModules [Mod.LoadedModule library input,Mod.LoadedModule root body]
        result <- Prepared.compileLoaded [raw] mode loaded >>= compiled
        unless (Prepared.reused result) (error (label ++ ": prepared source route did not run"))
        let term = Checked.term (Prepared.checkedTerm result)
        (env,_) <- ok (Runtime.prepare False term)
        v <- ok (Runtime.evaluate env (Runtime.REnv M.empty) (X.erase term))
        case v of Runtime.RInteger n | n == answer -> pure (); _ -> error label
        (own,metadata) <- compiled (Prepared.nativeCrateInputsUsing Parser.parseModule raw mode loaded)
        rootObject <- Source.compile Session.MemoryQueries mode own metadata >>= compiled
        parameters <- case Session.rootObject rootObject of
          Artifact.OpenCrateObject _ package -> pure (concatMap (Open.parameters . snd) (Open.packageFragments package))
          _ -> error (label ++ ": unified source root did not produce checked declaration groups")
        let imported = M.keys (M.fromList P.compareString
              [(X.nameHint name,ty) | (name,ty) <- parameters, X.nameHint name == key])
        unless (map H.unpack imported == map H.unpack imports)
          (error (label ++ ": wrong authenticated crate import bindings"))
  check "qualified + local same spelling" "let value = 1 in addInt L.value value" 42 [key]
  check "local binding only" "let value = 7 in value" 7 []
  putStrLn "prepared source and checked crate import controls passed"
