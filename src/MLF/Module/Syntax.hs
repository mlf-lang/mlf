-- | Parsed module boundaries, before import/name resolution. The checked
-- compiler continues to consume the existing closed 'Program' syntax.
module MLF.Module.Syntax
  ( SourceModule (..), Import (..), Selection (..), Export (..), Members (..)
  , ValueDeclaration, moduleIdentity, standaloneProgram
  ) where

import qualified MLF.Data as D
import MLF.Syntax
import MLF.Surface (bindValues)

type ValueDeclaration = (String, Maybe Annotation, Expr)

data SourceModule = SourceModule
  { sourcePath :: FilePath
  , sourceModuleName :: Maybe String
  , sourceExports :: Maybe [Export]
  , sourceImports :: [Import]
  , sourceDatatypes :: [D.DataDecl]
  , sourceClasses :: [ClassDecl]
  , sourceInstances :: [InstanceDecl]
  , sourceValues :: [ValueDeclaration]
  , sourceBody :: Maybe Expr
  } deriving (Eq, Show)

data Import = Import
  { importedModule :: String
  , importQualified :: Bool
  , importAlias :: Maybe String
  , importSelection :: Selection
  } deriving (Eq, Show)

data Selection = Everything | Only [Export] | Hiding [Export] deriving (Eq, Show)
data Export = ExportValue String | ExportType String Members | ExportModule String deriving (Eq, Show)
data Members = Abstract | AllMembers | Members [String] deriving (Eq, Show)

moduleIdentity :: SourceModule -> String
moduleIdentity = maybe "Main" id . sourceModuleName

standaloneProgram :: SourceModule -> Either String Program
standaloneProgram m = do
  body <- case sourceBody m of
    Just e -> Right e
    Nothing | any (\(n,_,_) -> n == "main") (sourceValues m) -> Right (Var "main")
    _ -> Left "a declaration-only program needs a main binding"
  expression <- bindValues (sourceValues m) body
  pure (if null (sourceClasses m) && null (sourceInstances m)
    then Program (sourceDatatypes m) expression
    else ClassProgram (sourceDatatypes m) (sourceClasses m) (sourceInstances m) expression)
