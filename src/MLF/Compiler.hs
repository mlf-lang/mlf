module MLF.Compiler
  ( Compilation (..), CompileError (..), Phase (..), PreludeMode (..)
  , compile, compileExpr, compileProgram
  , compileWithPrelude, compileExprWithPrelude, compileProgramWithPrelude
  ) where

import Control.Monad (unless)
import Data.Bifunctor (first)
import MLF.Constraint
import MLF.Elaborate
import MLF.Graph
import MLF.Parser
import MLF.Prelude
import qualified MLF.Syntax as S
import qualified MLF.X.Check as X
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import MLF.Classes (lowerClassesWithImports, prettyQualified)

data Phase = Parsing | Inference | Resolution | Elaboration | Verification deriving (Eq, Show)
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
compileWithPrelude mode file input = first (CompileError Parsing) (parseProgram file input) >>= compileProgramWithPrelude mode

compileExpr :: S.Expr -> Either CompileError Compilation
compileExpr = compileExprWithPrelude ImplicitPrelude

compileExprWithPrelude :: PreludeMode -> S.Expr -> Either CompileError Compilation
compileExprWithPrelude mode = compileProgramWithPrelude mode . S.Program []

compileProgram :: S.Program -> Either CompileError Compilation
compileProgram = compileProgramWithPrelude ImplicitPrelude

compileProgramWithPrelude :: PreludeMode -> S.Program -> Either CompileError Compilation
compileProgramWithPrelude mode original = do
  let (imports,source) = withPrelude mode original
  (program,names) <- first (CompileError Inference) (lowerClassesWithImports imports source)
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
