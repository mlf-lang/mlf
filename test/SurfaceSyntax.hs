module SurfaceSyntax (surfaceSyntaxTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import MLF.Compiler
import MLF.Parser (parseExpr, parseProgram)
import qualified MLF.Primitive as P
import qualified MLF.Syntax as S
import qualified MLF.X.Check as C
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

type Test = (String, IO ())

require :: Bool -> String -> IO ()
require ok message = unless ok (fail message)

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

sameParse :: String -> String -> S.Expr -> Test
sameParse label source expected = ("surface parser: " ++ label, do
  actual <- right (parseExpr "<surface expression>" source)
  require (actual == expected) ("unexpected AST: " ++ show actual))

sameProgram :: String -> String -> S.Expr -> Test
sameProgram label source expected = ("surface program: " ++ label, do
  actual <- right (parseProgram "<surface declarations>" source)
  require (actual == S.Program [] expected) ("unexpected program: " ++ show actual))

hasType :: String -> String -> T.Type -> Test
hasType label source expected = ("surface checking: " ++ label, do
  result <- right (compile "<surface test>" source)
  term <- right (XP.parseTerm "<surface xMLF>" (prettyTerm (compiledTerm result)))
  actual <- right (C.checkClosed term)
  require (T.alphaEq actual expected && T.alphaEq actual (inferredType result))
    ("wrong type: " ++ sourceType result)
  require (X.erase term == X.erase (compiledTerm result)) "xMLF round trip changed erasure")

rejects :: String -> String -> Phase -> String -> Test
rejects label source expectedPhase reason = ("surface rejection: " ++ label,
  case compile "<invalid surface syntax>" source of
    Left err -> require (phase err == expectedPhase && isInfixOf reason (diagnostic err))
      ("wrong rejection: " ++ show err)
    Right result -> fail ("unexpected acceptance: " ++ sourceType result))

int, bool :: T.Type
int = T.Con "Int" []
bool = T.Con "Bool" []

var :: String -> S.Expr
var = S.Var

lit :: Integer -> S.Expr
lit = S.IntLit

prim :: P.Primitive -> S.Expr -> S.Expr -> S.Expr
prim p a b = S.App (S.App (S.Primitive p) a) b

choose :: S.Expr -> S.Expr -> S.Expr -> S.Expr
choose a b c = S.App (prim P.IfThenElse a b) c

lam :: String -> S.Expr -> S.Expr
lam n = S.Lam n Nothing

surfaceSyntaxTests :: [Test]
surfaceSyntaxTests =
  [ sameParse "multiplication binds above addition" "x * 4 + y"
      (prim P.AddInt (prim P.MulInt (var "x") (lit 4)) (var "y"))
  , sameParse "application binds above arithmetic" "f x + g y * 2"
      (prim P.AddInt (S.App (var "f") (var "x"))
        (prim P.MulInt (S.App (var "g") (var "y")) (lit 2)))
  , sameParse "subtraction associates left" "10-3-2"
      (prim P.SubInt (prim P.SubInt (lit 10) (lit 3)) (lit 2))
  , sameParse "quotient and remainder associate left" "20 / 3 % 4"
      (prim P.RemInt (prim P.QuotInt (lit 20) (lit 3)) (lit 4))
  , sameParse "parentheses override precedence" "(x + y) * 4"
      (prim P.MulInt (prim P.AddInt (var "x") (var "y")) (lit 4))
  , sameParse "Boolean precedence" "x < 3 || y == 4 && z"
      (choose (prim P.LtInt (var "x") (lit 3)) (S.BoolLit True)
        (choose (prim P.EqInt (var "y") (lit 4)) (var "z") (S.BoolLit False)))
  , sameParse "concatenation associates right" "\"a\" ++ \"b\" ++ \"c\""
      (prim P.ConcatString (S.StringLit "a")
        (prim P.ConcatString (S.StringLit "b") (S.StringLit "c")))
  , sameParse "subtraction without spaces is not signed application" "f x-1"
      (prim P.SubInt (S.App (var "f") (var "x")) (lit 1))
  , sameParse "negative argument is parenthesized" "f (-1)"
      (S.App (var "f") (lit (-1)))
  , sameParse "unary minus applies after function application" "-f x * 2"
      (prim P.MulInt (prim P.SubInt (lit 0) (S.App (var "f") (var "x"))) (lit 2))
  , sameParse "signed Double exponent" "-2.5e-2" (S.DoubleLit (-0.025))
  , sameParse "signed hexadecimal integer" "-0x20" (lit (-32))
  , sameParse "plus sign and negative right operand" "+1 + -2"
      (prim P.AddInt (lit 1) (lit (-2)))
  , sameParse "comments at operators" "1 {- outer {- nested -} -} + 2 -- comment\n * 3"
      (prim P.AddInt (lit 1) (prim P.MulInt (lit 2) (lit 3)))
  , sameParse "nearest else" "if a then if b then x else y else z"
      (choose (var "a") (choose (var "b") (var "x") (var "y")) (var "z"))
  , sameParse "arithmetic inside branches" "if x < 0 then 0 else x + 1"
      (choose (prim P.LtInt (var "x") (lit 0)) (lit 0) (prim P.AddInt (var "x") (lit 1)))
  , sameParse "control expression as right operand" "1 + if a then 2 else 3"
      (prim P.AddInt (lit 1) (choose (var "a") (lit 2) (lit 3)))
  , sameParse "annotation covers the infix expression" "x + 1 : Int"
      (S.Ann (prim P.AddInt (var "x") (lit 1)) (S.Annotation [] (S.Con "Int" [])))
  , sameParse "local parameters lower to lambdas" "let f x y = x + y in f 1 2"
      (S.Let "f" (lam "x" (lam "y" (prim P.AddInt (var "x") (var "y"))))
        (S.App (S.App (var "f") (lit 1)) (lit 2)))
  , sameProgram "declarations have ordered let scopes" "id x = x; value = id 42; value"
      (S.Let "id" (lam "x" (var "x")) (S.Let "value" (S.App (var "id") (lit 42)) (var "value")))
  , sameProgram "implicit main with trailing semicolon" "main = 42;"
      (S.Let "main" (lit 42) (var "main"))
  , sameProgram "implicit main without trailing semicolon" "main = 42"
      (S.Let "main" (lit 42) (var "main"))
  , sameProgram "explicit entry overrides main" "main = 42; true"
      (S.Let "main" (lit 42) (S.BoolLit True))
  , sameProgram "separate signature covers the whole function"
      "id : forall a. a -> a; id x = x; id 42"
      (S.Let "id" (S.Ann (lam "x" (var "x")) identityAnnotation) (S.App (var "id") (lit 42)))
  , hasType "declarations generalize" "id x = x; n = id 42; main = id true;" bool
  , hasType "annotated function parameter"
      "apply (f : forall a. a -> a) = f f; id x = x; main = apply id 42;" int
  , hasType "inline whole-function signature"
      "id x : forall a. a -> a = x; n = id true; main = id 42;" int
  , hasType "annotated local function"
      "let id x : forall a. a -> a = x in let n = id true in id 42" int
  , hasType "do-local function generalizes"
      "do { let id x : forall a. a -> a = x; let n = id 42; id true }" bool
  , hasType "do-local function sees outer binding"
      "let f x = x + 1 in do { let f x = f x + 1; f 40 }" int
  , hasType "conditional returns polymorphic function"
      "id x = x; main = (if true then id else id) 42;" int
  , hasType "conditional works in a case scrutinee"
      "data Maybe a = Nothing | Just a; case if true then Just 42 else Nothing of { Just x -> x; Nothing -> 0 }" int
  , hasType "keyword prefixes remain identifiers"
      "iffy thenValue elsewhere = thenValue + elsewhere; main = iffy 20 22;" int
  , hasType "instance method parameters"
      "class Convert a b where { convert : a -> b }; instance Convert Int Bool where { convert x = x > 0 }; main = convert 42 : Bool;" bool
  , hasType "qualified function declaration"
      "twice : forall (m : * -> *) a. Monad m => m a -> m a; twice action = do { action; action }; main = twice (return 42 : IO Int);"
      (T.Con "IO" [int])
  , ("surface checking: syntax needs no implicit prelude", do
      result <- right (compileWithPrelude NoImplicitPrelude "<surface without prelude>"
        "inc x = x + 1; main = if true then inc 41 else 0;")
      require (T.alphaEq (inferredType result) int) (sourceType result))
  , rejects "recursion needs a signature" "loop x = loop x; main = loop 42;" Parsing "requires an explicit closed signature"
  , hasType "forward value references" "main = later 42; later x = x;" int
  , rejects "branch types must agree" "if true then 42 else false" Inference "type constructor mismatch"
  , rejects "condition must be Bool" "if 1 then 2 else 3" Inference "type constructor mismatch"
  , rejects "arithmetic does not overload Double" "1.0 + 2.0" Inference "type constructor mismatch"
  , rejects "unary plus requires a number" "+true" Inference "type constructor mismatch"
  , rejects "unary minus requires a number" "-true" Inference "type constructor mismatch"
  , rejects "comparisons do not overload String" "\"a\" == \"a\"" Inference "type constructor mismatch"
  , rejects "whole function signature is checked" "f : Int -> Bool; f x = x + 1; main = f 42;" Inference "type constructor mismatch"
  , rejects "chained comparisons" "1 < 2 < 3" Parsing "ambiguous"
  , rejects "mixed chained comparisons" "1 == 2 < 3" Parsing "ambiguous"
  , rejects "missing else" "if true then 42" Parsing "else"
  , rejects "missing then" "if true 42 else 0" Parsing "unexpected"
  , hasType "layout declaration separator" "f x = x\nmain = f 42" int
  , rejects "declaration-only file needs main" "answer = 42;" Parsing "main"
  , rejects "unreachable equation" "f x = x; f y = y; main = f 42;" Inference "unreachable"
  , rejects "duplicate function parameters" "f x x = x; main = f 1 2;" Parsing "duplicate function parameter"
  , rejects "signature must name its next definition" "f : Int; g = 42; main = g;" Parsing "expected a definition of f"
  , rejects "duplicate signatures" "f : Int; f : Int = 42; main = f;" Parsing "duplicate signature"
  , rejects "signature without equation" "f : Int;" Parsing "unexpected"
  , rejects "reserved conditional word" "let then = 42 in then" Parsing "reserved word"
  , rejects "reserved word in datatype parameter" "data Box if = Box if; main = 42;" Parsing "reserved word"
  ]
  where
    identityAnnotation = S.Annotation []
      (S.Forall S.Flexible "a" S.Bottom (S.Arrow (S.TVar "a") (S.TVar "a")))
