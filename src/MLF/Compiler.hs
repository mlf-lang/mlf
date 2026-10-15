module MLF.Compiler
  ( Compilation (..), CompileError (..), Phase (..), PreludeMode (..)
  , compile, compileExpr, compileProgram
  , compileWithPrelude, compileExprWithPrelude, compileProgramWithPrelude
  , compileModules, compileModulesWithPrelude
  , compileFile, compileFileWithPrelude, compileSourceWithImports
  , finishCompilation
  ) where

import Control.Monad (unless)
import Control.Exception (IOException, evaluate, try)
import Data.Bifunctor (first)
import qualified Data.Map.Strict as Map
import MLF.Constraint
import MLF.Elaborate
import MLF.Graph
import MLF.Parser
import MLF.Module
import MLF.Module.Syntax
import MLF.Prelude
import qualified MLF.Syntax as S
import qualified MLF.X.Check as X
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import MLF.Classes (lowerClassesWithImports, lowerClassesWithScopes, prettyQualified)

data Phase = Parsing | ModuleResolution | Inference | Resolution | Elaboration | Verification deriving (Eq, Show)
data CompileError = CompileError { phase :: Phase, diagnostic :: String } deriving (Eq)
instance Show CompileError where
  show (CompileError p message) = show p ++ ": " ++ message

data Compilation = Compilation
  { inferredType :: T.Type
  , compiledTerm :: X.Term
  , presolution :: Graph
  , sourceType :: String
  } deriving Show

compile :: FilePath -> String -> Either CompileError Compilation
compile = compileWithPrelude ImplicitPrelude

compileWithPrelude :: PreludeMode -> FilePath -> String -> Either CompileError Compilation
compileWithPrelude mode = compileModulesWithPrelude mode Map.empty

-- | Pure compilation with an explicit module-name to (path, source) map.
-- The entry source is separate, so it can also be an unnamed expression script.
compileModules :: Map.Map String (FilePath,String) -> FilePath -> String -> Either CompileError Compilation
compileModules = compileModulesWithPrelude ImplicitPrelude

compileModulesWithPrelude :: PreludeMode -> Map.Map String (FilePath,String) -> FilePath -> String
                          -> Either CompileError Compilation
compileModulesWithPrelude mode sources file input = do
  root <- first (CompileError Parsing) (parseModule file input)
  if standalone root then compileStandalone mode root else do
    modules <- first (CompileError ModuleResolution) (loadModuleMap sources root)
    compileLinked mode modules

-- | Load imports beside the entry file, from the supplied search roots, and
-- from the current directory. Each dotted name maps to a .emlf path.
compileFile :: [FilePath] -> FilePath -> IO (Either CompileError Compilation)
compileFile = compileFileWithPrelude ImplicitPrelude

compileFileWithPrelude :: PreludeMode -> [FilePath] -> FilePath -> IO (Either CompileError Compilation)
compileFileWithPrelude mode includes file = ioErrors $ do
  input <- readFile file
  _ <- evaluate (length input)
  compileSourceWithImports mode includes file input

-- | IO counterpart of compileModules, also used for stdin and --expr imports.
compileSourceWithImports :: PreludeMode -> [FilePath] -> FilePath -> String
                         -> IO (Either CompileError Compilation)
compileSourceWithImports mode includes file input = ioErrors $
  case first (CompileError Parsing) (parseModule file input) of
    Left err -> pure (Left err)
    Right root | standalone root -> pure (compileStandalone mode root)
    Right root -> do
      modules <- loadModuleFiles includes root
      pure (first (CompileError ModuleResolution) modules >>= compileLinked mode)

ioErrors :: IO (Either CompileError a) -> IO (Either CompileError a)
ioErrors action = do
  result <- try action
  pure (either (Left . CompileError ModuleResolution . showIOException) id result)
  where showIOException :: IOException -> String
        showIOException = show

standalone :: SourceModule -> Bool
standalone root = sourceModuleName root == Nothing && null (sourceImports root)

compileStandalone :: PreludeMode -> SourceModule -> Either CompileError Compilation
compileStandalone mode root = first (CompileError Parsing) (standaloneProgram root) >>= compileProgramWithPrelude mode

compileLinked :: PreludeMode -> [SourceModule] -> Either CompileError Compilation
compileLinked mode modules = do
  linked <- first (CompileError ModuleResolution) (linkModules mode modules)
  let display = displayNames (linkedNames linked)
  lowered@(_,classes) <- first (CompileError Inference . display) (lowerClassesWithScopes
    (linkedValueScopes linked) (linkedInstanceScopes linked) (linkedProgram linked))
  let diagnosticNames = Map.union (Map.map display classes) (linkedNames linked)
  result <- first (\err -> err { diagnostic = displayNames diagnosticNames (diagnostic err) })
    (finishCompilation lowered)
  pure result { sourceType = display (sourceType result) }

compileExpr :: S.Expr -> Either CompileError Compilation
compileExpr = compileExprWithPrelude ImplicitPrelude

compileExprWithPrelude :: PreludeMode -> S.Expr -> Either CompileError Compilation
compileExprWithPrelude mode = compileProgramWithPrelude mode . S.Program []

compileProgram :: S.Program -> Either CompileError Compilation
compileProgram = compileProgramWithPrelude ImplicitPrelude

compileProgramWithPrelude :: PreludeMode -> S.Program -> Either CompileError Compilation
compileProgramWithPrelude mode original = do
  let (imports,source) = withPrelude mode original
  lowered <- first (CompileError Inference) (lowerClassesWithImports imports source)
  finishCompilation lowered

finishCompilation :: (S.Program, Map.Map String String) -> Either CompileError Compilation
finishCompilation (program,names) = do
  declarations <- case program of
    S.Program ds _ -> pure ds
    _ -> Left (CompileError Inference "class translation did not produce a core program")
  constraints <- first (CompileError Inference) (generateProgram program)
  graph <- first (CompileError Inference) (solve constraints)
  evidence <- first (CompileError Resolution) (resolveEvidence graph (skeleton constraints))
  body <- first (CompileError Elaboration) (elaborateResolved graph evidence (skeleton constraints))
  let term = if null declarations then body else X.WithData declarations body
  ty <- first (CompileError Verification) (X.checkClosed term)
  let expected = schemeType graph (generalization (skeleton constraints))
  unless (T.alphaEq ty expected) (Left (CompileError Verification "elaboration changed the inferred type"))
  unless (X.erase term == eraseSourceWith evidence (skeleton constraints))
    (Left (CompileError Verification "elaboration changed source erasure"))
  pure (Compilation ty term graph (prettyQualified names ty))
