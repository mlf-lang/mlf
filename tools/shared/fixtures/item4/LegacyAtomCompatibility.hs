{-# LANGUAGE OverloadedStrings #-}
-- Unchanged legacy atom forms: independent AST expectations and old public
-- direct-AST versus textual entry-point target type/erasure equivalence.
module Main where
import qualified Prelude as H
import Prelude (IO, ($), (.), (==), (++), error, putStrLn)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Parser as P
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.SourceEquality as E
import qualified Bootstrap.X.Type as X
import qualified Bootstrap.X.Syntax as X
import qualified MLF.Host.Base as B
strip e = case e of
  T.SCallSite _ _ x -> strip x
  T.SApp f x -> T.SApp (strip f) (strip x)
  T.SLam n a x -> T.SLam n a (strip x)
  T.SAnn x a -> T.SAnn (strip x) a
  T.SLet n x y -> T.SLet n (strip x) (strip y)
  T.SSharedBind p x y b f -> T.SSharedBind p (strip x) (strip y) (strip b) (strip f)
  T.SCase x bs -> T.SCase (strip x) [T.SAlternative p (strip y) | T.SAlternative p y <- bs]
  _ -> e
parse s = case P.parseExpr "LegacyAtoms.emlf" (B.literal s) of
  T.Left e -> error (B.unpack e)
  T.Right e -> strip e
ast label source expected = if E.eqExpr (parse source) expected
  then putStrLn ("PASS AST " ++ label) else error ("AST mismatch: " ++ label)
closed label source expected = do
  ast label source expected
  case (C.compile "LegacyAtoms.emlf" (B.literal source), C.compileExpr expected) of
    (T.Right a, T.Right b) | X.alphaEq (C.inferredType a) (C.inferredType b)
      H.&& X.equalErased (X.erase (C.compiledTerm a)) (X.erase (C.compiledTerm b)) -> putStrLn ("PASS type/erasure " ++ label)
    (T.Left e, _) -> error (B.unpack (C.prettyError e))
    (_, T.Left e) -> error (B.unpack (C.prettyError e))
    _ -> error ("type/erasure mismatch: " ++ label)
var = T.SVar
lit = T.SIntLit
main :: IO ()
main = do
  closed "natural" "42" (lit 42)
  closed "negative integer" "-42" (lit (-42))
  closed "positive integer" "+42" (lit 42)
  closed "parenthesized negative integer" "(-42)" (lit (-42))
  closed "negative double" "-0.025" (T.SDoubleLit (-0.025))
  closed "parenthesized negative double" "(-0.025)" (T.SDoubleLit (-0.025))
  closed "signed exponent" "-2.5e-2" (T.SDoubleLit (-0.025))
  closed "positive double" "+0.025" (T.SDoubleLit 0.025)
  closed "legacy lowercase true" "true" (T.SBoolLit H.True)
  closed "legacy uppercase false" "False" (T.SBoolLit H.False)
  ast "parenthesized expression" "(f x)" (T.SApp (var "f") (var "x"))
  ast "negative application" "(-f x)" (T.SApp (T.SApp (T.SPrimitive T.PSubInt) (lit 0)) (T.SApp (var "f") (var "x")))
  ast "operator value" "(==)" (var "==")
  ast "negative pattern" "case n of { -1 -> 42; _ -> 0 }" (T.SCase (var "n") [T.SAlternative (T.SIntPattern (-1)) (lit 42), T.SAlternative (T.SDefaultPattern T.Nothing) (lit 0)])
  ast "positive pattern" "case n of { +1 -> 42; _ -> 0 }" (T.SCase (var "n") [T.SAlternative (T.SIntPattern 1) (lit 42), T.SAlternative (T.SDefaultPattern T.Nothing) (lit 0)])
  ast "Boolean pattern" "case b of { true -> 42; false -> 0 }" (T.SCase (var "b") [T.SAlternative (T.SBoolPattern H.True) (lit 42), T.SAlternative (T.SBoolPattern H.False) (lit 0)])
  let annotation = T.SAnnotation [] (T.SForall T.Flexible "a" T.SBottom (T.SArrow (T.STVar "a") (T.STVar "a")))
  closed "forall typed lambda" "\\(x : forall a. a -> a) -> x x" (T.SLam "x" (T.Just annotation) (T.SApp (var "x") (var "x")))
  let failure = T.SApp (var "$MLF.Primitive.fail") (T.SApp (T.SPrimitive T.PTextToChars) (T.SStringLit "Pattern match failure in do expression"))
      binding action name body = T.SSharedBind (T.SDefaultPattern (T.Just name)) action body (var "$MLF.Primitive.>>=") failure
      fromString text = T.SApp (var "$MLF.Primitive.fromString") (T.SApp (T.SPrimitive T.PTextToChars) (T.SStringLit text))
      concatString a b = T.SApp (T.SApp (T.SPrimitive T.PConcatString) a) b
  ast "canonical delayed do statements" "do { x <- action; let y = x; finish y }" (binding (var "action") "x" (T.SLet "y" (var "x") (T.SApp (var "finish") (var "y"))))
  ast "canonical do order" "do { x <- first; y <- second x; finish y }" (binding (var "first") "x" (binding (T.SApp (var "second") (var "x")) "y" (T.SApp (var "finish") (var "y"))))
  ast "source strings retain concat associativity" "\"a\" ++ \"b\" ++ \"c\"" (concatString (fromString "a") (concatString (fromString "b") (fromString "c")))
  ast "ordinary Eq operator" "x == 4" (T.SApp (T.SApp (var "==") (var "x")) (lit 4))
  ast "canonical cons variable tail wins colon ambiguity" "case xs of { (x:rest) -> x; _ -> 0 }" (T.SCase (var "xs") [T.SAlternative (T.SConstructorPattern ":" [T.Just "x", T.Just "rest"]) (var "x"), T.SAlternative (T.SDefaultPattern T.Nothing) (lit 0)])
  ast "canonical cons constructor tail wins colon ambiguity" "case xs of { (x:Nil) -> x; _ -> 0 }" (T.SCase (var "xs") [T.SAlternative (T.SNestedPattern ":" [T.SDefaultPattern (T.Just "x"), T.SConstructorPattern "Nil" []]) (var "x"), T.SAlternative (T.SDefaultPattern T.Nothing) (lit 0)])
  closed "explicit unambiguous legacy annotation" "\\(x :: Int) -> x" (T.SLam "x" (T.Just (T.SAnnotation [] (T.SCon "Int" []))) (var "x"))
  let cons x xs = T.SApp (T.SApp (T.SConstructor ":") x) xs
      nil = T.SConstructor "[]"
  ast "canonical cons expression associates right" "1 : 2 : []" (cons (lit 1) (cons (lit 2) nil))
  ast "canonical cons expression constructor tail" "x : Nil" (cons (var "x") (T.SConstructor "Nil"))
  ast "cons expression stops before comparison" "1 : [] == ys" (T.SApp (T.SApp (var "==") (cons (lit 1) nil)) (var "ys"))
  ast "unambiguous arrow annotation fallback" "f : Int -> Int" (T.SAnn (var "f") (T.SAnnotation [] (T.SArrow (T.SCon "Int" []) (T.SCon "Int" []))))
  ast "unambiguous forall annotation fallback" "f : forall a. a -> a" (T.SAnn (var "f") annotation)
  closed "explicit value annotation" "42 :: Int" (T.SAnn (lit 42) (T.SAnnotation [] (T.SCon "Int" [])))
