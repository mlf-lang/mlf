module MLF.Compiler
  ( Compilation (..), CompileError (..), Phase (..), compile, compileExpr ) where

import Control.Monad (unless)
import Data.Bifunctor (first)
import MLF.Constraint
import MLF.Elaborate
import MLF.Graph
import MLF.Parser
import qualified MLF.Syntax as S
import qualified MLF.X.Check as X
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

data Phase = Parsing | Inference | Elaboration | Verification deriving (Eq, Show)
data CompileError = CompileError { phase :: Phase, diagnostic :: String } deriving (Eq)
instance Show CompileError where
  show (CompileError p message) = show p ++ ": " ++ message

data Compilation = Compilation
  { inferredType :: T.Type
  , compiledTerm :: X.Term
  , presolution :: Graph
  } deriving Show

compile :: FilePath -> String -> Either CompileError Compilation
compile file input = first (CompileError Parsing) (parseExpr file input) >>= compileExpr

compileExpr :: S.Expr -> Either CompileError Compilation
compileExpr expr = do
  constraints <- first (CompileError Inference) (generate expr)
  graph <- first (CompileError Inference) (solve constraints)
  term <- first (CompileError Elaboration) (elaborate graph (skeleton constraints))
  ty <- first (CompileError Verification) (X.checkClosed term)
  let expected = schemeType graph (generalization (skeleton constraints))
  unless (T.alphaEq ty expected) (Left (CompileError Verification "elaboration changed the inferred type"))
  unless (X.erase term == eraseSource (skeleton constraints))
    (Left (CompileError Verification "elaboration changed source erasure"))
  pure (Compilation ty term graph)

