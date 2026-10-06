module DoNotation (doTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import MLF.Compiler
import MLF.Desugar (desugarDo)
import MLF.Parser (parseExpr)
import qualified MLF.Syntax as S
import qualified MLF.X.Check as C
import qualified MLF.X.Parser as P
import MLF.X.Pretty (prettyTerm, prettyType)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

type Test = (String, IO ())

require :: Bool -> String -> IO ()
require ok message = unless ok (fail message)

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

checked :: String -> IO Compilation
checked source = do
  result <- right (compile "<do test>" source)
  parsed <- right (P.parseTerm "<do xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (C.checkClosed parsed)
  require (T.alphaEq ty (inferredType result)) "do xMLF round trip changed type"
  require (X.erase parsed == X.erase (compiledTerm result)) "do xMLF round trip changed erasure"
  pure result

hasType :: String -> String -> T.Type -> Test
hasType label source expected = ("do: " ++ label, do
  result <- checked source
  require (T.alphaEq (inferredType result) expected)
    ("expected " ++ prettyType expected ++ ", got " ++ sourceType result))

rejects :: String -> String -> Phase -> String -> Test
rejects label source expectedPhase reason = ("do rejection: " ++ label,
  case compile "<invalid do>" source of
    Left err -> do
      require (phase err == expectedPhase) ("wrong rejection phase: " ++ show err)
      require (reason `isInfixOf` diagnostic err) ("wrong rejection reason: " ++ show err)
    Right result -> fail ("unexpected acceptance: " ++ sourceType result))

int, bool :: T.Type
int = T.Con "Int" []
bool = T.Con "Bool" []

maybeT :: T.Type -> T.Type
maybeT t = T.Con "Maybe" [t]

-- Exercise syntax separately from instance resolution, using a normal typed
-- bind function. The MonadState example below tests their integration.
maybeDecl, maybeBind :: String
maybeDecl = "data Maybe a = Nothing | Just a; "
maybeBind = "let bind : forall a b. Maybe a -> (a -> Maybe b) -> Maybe b = " ++
  "\\value next -> case value of { Nothing -> Nothing; Just x -> next x } in let return = Just in "

doTests :: [Test]
doTests =
  [ hasType "single expression" "do { 42 }" int
  , hasType "local let needs no bind" "do { let x = 42; x }" int
  , hasType "binding" (prefix ++ "do { x <- Just 42; return x }") (maybeT int)
  , hasType "sequencing" (prefix ++ "do { Just true; Just 42 }") (maybeT int)
  , hasType "wildcard binding" (prefix ++ "do { _ <- Just true; Just 42 }") (maybeT int)
  , hasType "optional trailing semicolon" (prefix ++ "do { x <- Just 42; return x; }") (maybeT int)
  , hasType "nested blocks" (prefix ++ "do { x <- do { y <- Just 42; return y }; return x }") (maybeT int)
  , hasType "bind statement sees the outer binding"
      (prefix ++ "let x = 42 in do { x <- return x; return x }") (maybeT int)
  , hasType "local let sees the outer binding"
      (prefix ++ "let x = 42 in do { let x = return x; x }") (maybeT int)
  , hasType "local let is generalized"
      (prefix ++ "do { let id = \\x -> x; let n = id 42; return (id true) }") (maybeT bool)
  , hasType "local let annotation"
      (prefix ++ "do { let id : forall a. a -> a = \\x -> x; let n = id 42; return (id true) }") (maybeT bool)
  , hasType "let-in expression is an action"
      (prefix ++ "do { let x = 42 in return x; return true }") (maybeT bool)
  , hasType "do expression used as an argument"
      (prefix ++ "(\\x -> x) (do { x <- Just 42; return x })") (maybeT int)
  , hasType "do expression annotation"
      (prefix ++ "do { x <- Just 42; return x } : Maybe Int") (maybeT int)
  , hasType "constructor pattern"
      (maybeDecl ++ "data Pair a b = Pair a b; " ++ maybeBind ++ "do { Pair n b <- Just (Pair 42 true); return n }") (maybeT int)
  , hasType "constructor wildcard field"
      (maybeDecl ++ "data Pair a b = Pair a b; " ++ maybeBind ++ "do { Pair _ b <- Just (Pair 42 true); return b }") (maybeT bool)
  , hasType "discarded action cannot capture an outer name"
      (prefix ++ "let doValue0 = true in do { Just 42; return doValue0 }") (maybeT bool)
  , hasType "pattern temporary cannot capture an outer name"
      (maybeDecl ++ "data Box a = Box a; " ++ maybeBind ++ "let doValue0 = true in do { Box n <- Just (Box 42); return doValue0 }") (maybeT bool)
  , hasType "uses the lexical bind function"
      "let bind = \\action next -> next action in do { x <- 42; x }" int
  , rejects "empty block" "do {}" Parsing "unexpected"
  , rejects "final statement must be an expression" (prefix ++ "do { x <- Just 42 }") Parsing "must end with an expression"
  , rejects "cannot end with a local declaration" "do { let x = 42 }" Parsing "must end with an expression"
  , rejects "statements need separators" (prefix ++ "do { x <- Just 42 return x }") Parsing "must end with an expression"
  , rejects "default IO bind requires an action" "do { 42; 43 }" Inference "type constructor mismatch"
  , rejects "bound variable cannot escape"
      (prefix ++ "let result = do { x <- Just 42; return x } in x") Inference "unbound variable: x"
  , rejects "binding is not recursive" (prefix ++ "do { x <- return x; return x }") Inference "unbound variable: x"
  , rejects "later binding is unavailable" (prefix ++ "do { x <- return y; y <- Just 42; return x }") Inference "unbound variable: y"
  , rejects "action type mismatch" (prefix ++ "do { x <- 42; return x }") Inference "type constructor mismatch"
  , rejects "final action has the right monadic type"
      (prefix ++ "do { x <- Just 42; x }") Inference "type constructor mismatch"
  , rejects "refutable pattern requires an explicit case"
      (prefix ++ "do { Just x <- Just (Just 42); return x }") Inference "non-exhaustive case"
  , rejects "pattern binder duplicates"
      (maybeDecl ++ "data Pair a b = Pair a b; " ++ maybeBind ++ "do { Pair x x <- Just (Pair 1 2); return x }") Inference "duplicate pattern variable"
  , ("do: parser preserves statement forms", do
      parsed <- right (parseExpr "<do syntax>" "do { x <- action; let y = x; finish y }")
      let expected = S.Do [S.DoBind (S.DefaultPattern (Just "x")) (S.Var "action"), S.DoLet "y" Nothing (S.Var "x")]
            (S.App (S.Var "finish") (S.Var "y"))
      require (parsed == expected) ("unexpected do AST: " ++ show parsed))
  , ("do: lowering preserves binding order and the final action", do
      parsed <- right (parseExpr "<do lowering>" "do { x <- first; y <- second x; finish y }")
      let bind action name body = S.App (S.App (S.Var "bind") action) (S.Lam name Nothing body)
          expected = bind (S.Var "first") "x" (bind (S.App (S.Var "second") (S.Var "x")) "y" (S.App (S.Var "finish") (S.Var "y")))
      require (desugarDo parsed == expected) "do did not lower to the expected nested bind applications")
  , ("do: multiparameter MonadState example", do
      source <- readFile "examples/monad-state-do.emlf"
      result <- checked source
      require (T.alphaEq (inferredType result) (T.Con "Pair" [int,int])) "wrong State result")
  ]
  where prefix = maybeDecl ++ maybeBind
