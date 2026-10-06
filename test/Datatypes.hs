module Datatypes (datatypeTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import MLF.Compiler
import qualified MLF.Data as D
import MLF.Parser (parseProgram)
import qualified MLF.Syntax as S
import qualified MLF.X.Check as C
import qualified MLF.X.Parser as P
import MLF.X.Pretty (prettyTerm, prettyType)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

type Test = (String, IO ())

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

require :: Bool -> String -> IO ()
require ok message = unless ok (fail message)

checked :: String -> IO Compilation
checked source = do
  result <- right (compile "<data test>" source)
  parsed <- right (P.parseTerm "<data xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (C.checkClosed parsed)
  require (T.alphaEq ty (inferredType result)) "data xMLF round trip changed type"
  require (X.erase parsed == X.erase (compiledTerm result)) "data xMLF round trip changed erasure"
  pure result

hasType :: String -> String -> T.Type -> Test
hasType label source expected = ("data: " ++ label, do
  result <- checked source
  require (T.alphaEq (inferredType result) expected)
    ("expected " ++ prettyType expected ++ ", got " ++ prettyType (inferredType result)))

rejects :: String -> String -> String -> Test
rejects label source reason = ("data: " ++ label, case compile "<data rejection>" source of
  Left err -> do
    require (phase err == Inference) ("wrong rejection phase: " ++ show err)
    require (reason `isInfixOf` diagnostic err) ("wrong rejection reason: " ++ show err)
  Right result -> fail ("unexpected acceptance: " ++ prettyType (inferredType result)))

targetRejects :: String -> X.Term -> String -> Test
targetRejects label term reason = ("data target: " ++ label, case C.checkClosed term of
  Left err -> require (reason `isInfixOf` err) ("wrong target rejection: " ++ err)
  Right ty -> fail ("unexpected target type: " ++ prettyType ty))

int, bool, identity :: T.Type
int = T.Con "Int" []
bool = T.Con "Bool" []
identity = T.Forall (T.TyVar 0) T.Bot (T.Arrow (v 0) (v 0))

v :: Int -> T.Type
v = T.Var . T.TyVar

allT :: Int -> T.Type -> T.Type
allT n = T.Forall (T.TyVar n) T.Bot

maybeT :: T.Type -> T.Type
maybeT t = T.Con "Maybe" [t]

maybeDecl, listDecl, pairDecl :: String
maybeDecl = "data Maybe a = Nothing | Just a; "
listDecl = "data List a = Nil | Cons a (List a); "
pairDecl = "data Pair a b = Pair a b; "

maybeData :: D.DataDecl
maybeData = D.DataDecl "Maybe" ["a"]
  [D.ConstructorDecl "Nothing" [], D.ConstructorDecl "Just" [D.Parameter "a"]]

withMaybe :: X.Term -> X.Term
withMaybe = X.WithData [maybeData]

justInt :: X.Term
justInt = X.App (X.Constructor "Just" [int]) (X.IntTerm 42)

x :: X.Name
x = X.Name 1 "x"

nothing, just :: X.Term -> X.Alternative
nothing = X.Alternative (X.ConstructorPattern "Nothing" [])
just = X.Alternative (X.ConstructorPattern "Just" [Just x])

datatypeTests :: [Test]
datatypeTests =
  [ hasType "nullary constructor" "data Color = Red | Green | Blue; Red" (T.Con "Color" [])
  , hasType "polymorphic nullary constructor" (maybeDecl ++ "Nothing") (allT 0 (maybeT (v 0)))
  , hasType "constructor is a first-class function" (maybeDecl ++ "Just")
      (allT 0 (T.Arrow (v 0) (maybeT (v 0))))
  , hasType "constructor application" (maybeDecl ++ "Just 42") (maybeT int)
  , hasType "partial constructor application" (pairDecl ++ "Pair 42")
      (allT 0 (T.Arrow (v 0) (T.Con "Pair" [int,v 0])))
  , hasType "multiple parameters" (pairDecl ++ "Pair 42 true") (T.Con "Pair" [int,bool])
  , hasType "let-bound constructor has independent instances"
      (maybeDecl ++ "let make = Just in let a = make 42 in make true") (maybeT bool)
  , hasType "phantom parameter" "data Phantom a = Phantom; Phantom : Phantom Int" (T.Con "Phantom" [int])
  , hasType "exhaustive case" (maybeDecl ++ "case Just 42 of { Nothing -> 0; Just x -> x }") int
  , hasType "reordered alternatives" (maybeDecl ++ "case Just 42 of { Just x -> x; Nothing -> 0; }") int
  , hasType "case constrains scrutinee"
      (maybeDecl ++ "\\m -> case m of { Nothing -> 0; Just x -> x }") (T.Arrow (maybeT int) int)
  , hasType "case returns its polymorphic scrutinee"
      (maybeDecl ++ "\\m -> case m of { Nothing -> m; Just _ -> m }")
      (allT 0 (T.Arrow (maybeT (v 0)) (maybeT (v 0))))
  , hasType "case rebuilds polymorphic data"
      (maybeDecl ++ "\\m -> case m of { Nothing -> Nothing; Just x -> Just x }")
      (allT 0 (T.Arrow (maybeT (v 0)) (maybeT (v 0))))
  , hasType "case generalizes an unconstrained result"
      (maybeDecl ++ "case Nothing of { Nothing -> Nothing; Just _ -> Nothing }")
      (allT 0 (maybeT (v 0)))
  , hasType "case retains an MLF result bound"
      (maybeDecl ++ "\\m -> case m of { Nothing -> (\\x -> x); Just f -> f }")
      (T.Forall (T.TyVar 1) identity (T.Arrow (maybeT (v 1)) (v 1)))
  , hasType "generalized case function"
      (maybeDecl ++ "let get = \\d m -> case m of { Nothing -> d; Just x -> x } in let n = get 0 (Just 42) in get true Nothing") bool
  , hasType "pattern field order" (pairDecl ++ "case Pair 42 true of { Pair n b -> b }") bool
  , hasType "wildcard field" (pairDecl ++ "case Pair 42 true of { Pair _ b -> b }") bool
  , hasType "multiple wildcard fields" (pairDecl ++ "case Pair 42 true of { Pair _ _ -> 0 }") int
  , hasType "wildcard alternative" (maybeDecl ++ "case Just 42 of { Nothing -> 0; _ -> 1 }") int
  , hasType "variable alternative and nested case"
      (maybeDecl ++ "case Just 42 of { Nothing -> 0; rest -> case rest of { Nothing -> 0; Just n -> n } }") int
  , hasType "wildcard-only case" "case 42 of { _ -> true }" bool
  , hasType "variable-only case" "case 42 of { n -> n }" int
  , hasType "pattern shadows outer variable"
      (maybeDecl ++ "let x = true in case Just 42 of { Nothing -> 0; Just x -> x }") int
  , hasType "recursive list" (listDecl ++ "Cons 1 (Cons 2 Nil)") (T.Con "List" [int])
  , hasType "recursive list deconstruction"
      (listDecl ++ "case Cons 1 (Cons 2 Nil) of { Nil -> 0; Cons x xs -> case xs of { Nil -> x; Cons y _ -> y } }") int
  , hasType "recursive tree"
      "data Tree a = Leaf a | Node (Tree a) (Tree a); Node (Leaf 1) (Leaf 2)" (T.Con "Tree" [int])
  , hasType "mutually recursive declarations"
      "data A = MkA B; data B = End | MkB A; case MkA (MkB (MkA End)) of { MkA b -> b }" (T.Con "B" [])
  , hasType "non-regular recursive declaration"
      "data Nested a = Stop a | More (Nested (Nested a)); More (Stop (Stop 42))" (T.Con "Nested" [int])
  , hasType "function field"
      "data Fn a b = Fn (a -> b); case Fn (\\x -> x) of { Fn f -> f 42 }" int
  , hasType "polymorphic type argument"
      (maybeDecl ++ "Just (\\x -> x) : Maybe (forall a. a -> a)") (maybeT identity)
  , hasType "polymorphic case result"
      (maybeDecl ++ "case Just (\\x -> x) of { Nothing -> (\\x -> x); Just f -> f }") identity
  , hasType "polymorphic field used with an explicit annotation"
      (maybeDecl ++ "case (Just (\\x -> x) : Maybe (forall a. a -> a)) of { Nothing -> true; Just f -> let p = (f : forall a. a -> a) in let n = p 42 in p true }") bool
  , hasType "declaration parameter is not a target keyword"
      "data Box id = Box id; Box 42" (T.Con "Box" [int])
  , hasType "explicitly polymorphic field"
      "data Box = Box (forall a. a -> a); case Box (\\x -> x) of { Box f -> let id = f : forall a. a -> a in let n = id 1 in id true }" bool
  , rejects "unknown constructor" "Just 42" "unknown data constructor: Just"
  , rejects "wrong field type" (listDecl ++ "Cons true (Cons 42 Nil)") "type constructor mismatch"
  , rejects "pattern fields are not implicitly generalized"
      (maybeDecl ++ "case Just (\\x -> x) of { Nothing -> true; Just f -> let n = f 1 in f true }") "type constructor mismatch"
  , rejects "overapplied nullary constructor" (maybeDecl ++ "Nothing 42") "type constructor mismatch"
  , rejects "wrong scrutinee type"
      (maybeDecl ++ "case 42 of { Nothing -> 0; Just x -> x }") "type constructor mismatch"
  , rejects "inconsistent branch results"
      (maybeDecl ++ "case Just 42 of { Nothing -> true; Just x -> x }") "type constructor mismatch"
  , rejects "non-exhaustive case" (maybeDecl ++ "case Just 42 of { Just x -> x }") "non-exhaustive case; missing: Nothing"
  , rejects "too few pattern fields" (maybeDecl ++ "case Just 42 of { Nothing -> 0; Just -> 1 }") "constructor pattern arity mismatch"
  , rejects "too many pattern fields" (maybeDecl ++ "case Just 42 of { Nothing x -> x; Just x -> x }") "constructor pattern arity mismatch"
  , rejects "duplicate constructor alternative"
      (maybeDecl ++ "case Just 42 of { Nothing -> 0; Just x -> x; Just y -> y }") "duplicate constructor alternative"
  , rejects "mixed datatype alternatives"
      (maybeDecl ++ "case Just 42 of { Nothing -> 0; Just x -> x; Unit -> 0 }") "different data types"
  , rejects "default must be last" (maybeDecl ++ "case Just 42 of { _ -> 0; Just x -> x }") "default alternative must be last"
  , rejects "duplicate pattern variable" (pairDecl ++ "case Pair 1 2 of { Pair x x -> x }") "duplicate pattern variable"
  , rejects "pattern variables do not escape"
      (maybeDecl ++ "let v = case Just 42 of { Nothing -> 0; Just x -> x } in x") "unbound variable: x"
  , rejects "pattern variable unavailable in sibling branch"
      (maybeDecl ++ "case Just 42 of { Just x -> x; Nothing -> x }") "unbound variable: x"
  , rejects "duplicate datatype" "data T = A; data T = B; A" "duplicate data type"
  , rejects "duplicate constructor across datatypes" "data T = A; data U = A; A" "duplicate data constructor"
  , rejects "duplicate constructor within datatype" "data T = A | A; A" "duplicate data constructor"
  , rejects "duplicate type parameter" "data T a a = A a; A 1" "duplicate type parameter"
  , rejects "free field type parameter" "data T a = A b; A 1" "unbound data type parameter: b"
  , rejects "unknown field type" "data T = A Missing; A" "unknown field type: Missing"
  , rejects "recursive type arity" "data T a = A (T a a); A" "invalid type constructor arity: T"
  , rejects "declared annotation arity" (maybeDecl ++ "(\\x -> x) : Maybe -> Maybe") "invalid type constructor arity: Maybe"
  , rejects "primitive type redefinition" "data Int = Number; Number" "cannot redefine a primitive type"
  , rejects "reserved datatype name" "data True = MkTrue; MkTrue" "reserved data type name"
  , rejects "primitive constructor redefinition" "data T = True; True" "cannot redefine a primitive constructor"
  , ("data: declaration and case parse tree", do
      program <- right (parseProgram "<data syntax>" (maybeDecl ++ "case Just 1 of { Nothing -> 0; Just x -> x }"))
      let expected = S.Program [maybeData] (S.Case (S.App (S.Constructor "Just") (S.IntLit 1))
            [S.Alternative (S.ConstructorPattern "Nothing" []) (S.IntLit 0),
             S.Alternative (S.ConstructorPattern "Just" [Just "x"]) (S.Var "x")])
      require (program == expected) "unexpected declaration or case AST")
  , ("data: empty declaration rejected by AST API", case compileProgram (S.Program [D.DataDecl "Void" [] []] (S.IntLit 1)) of
      Left err -> require (phase err == Inference && "no constructors" `isInfixOf` diagnostic err) (show err)
      Right _ -> fail "empty declaration accepted")
  , ("data: constructor and case erasure", do
      result <- checked (maybeDecl ++ "case Just 42 of { Nothing -> 0; Just x -> x }")
      case X.erase (compiledTerm result) of
        X.ECase (X.EApp (X.EConstructor "Just") (X.EInt 42))
          [X.ErasedAlternative (X.ConstructorPattern "Nothing" []) (X.EInt 0),
           X.ErasedAlternative (X.ConstructorPattern "Just" [Just n]) (X.EVar m)] ->
            require (n == m) "case erasure changed the pattern binder"
        other -> fail ("unexpected case erasure: " ++ show other))
  , ("data target: independent constructor and case typing", do
      ty <- right (C.checkClosed (withMaybe (X.Case justInt int [nothing (X.IntTerm 0), just (X.VarTerm x)])))
      require (T.alphaEq ty int) "wrong target case type")
  , targetRejects "unknown constructor" (X.Constructor "Just" [int]) "unknown data constructor"
  , targetRejects "constructor type argument count" (withMaybe (X.Constructor "Just" [])) "type argument arity mismatch"
  , targetRejects "constructor type argument is well formed" (withMaybe (X.Constructor "Just" [v 0])) "unbound type variable"
  , targetRejects "constructor field type" (withMaybe (X.App (X.Constructor "Just" [bool]) (X.IntTerm 42))) "application type mismatch"
  , targetRejects "non-exhaustive case" (withMaybe (X.Case justInt int [just (X.VarTerm x)])) "non-exhaustive case"
  , targetRejects "empty case" (withMaybe (X.Case justInt int [])) "case has no alternatives"
  , targetRejects "case result type" (withMaybe (X.Case justInt bool [nothing (X.BoolTerm True), just (X.VarTerm x)])) "alternative result type mismatch"
  , targetRejects "case scrutinee type"
      (withMaybe (X.Case (X.IntTerm 42) int [nothing (X.IntTerm 0), just (X.VarTerm x)])) "wrong data type"
  , targetRejects "pattern field count"
      (withMaybe (X.Case justInt int [nothing (X.IntTerm 0), X.Alternative (X.ConstructorPattern "Just" []) (X.IntTerm 1)])) "pattern arity mismatch"
  , targetRejects "repeated alternative"
      (withMaybe (X.Case justInt int [nothing (X.IntTerm 0), just (X.VarTerm x), just (X.VarTerm x)])) "duplicate constructor alternative"
  , targetRejects "pattern binder freshness"
      (withMaybe (X.Abs x int (X.Case justInt int [nothing (X.IntTerm 0), just (X.VarTerm x)]))) "pattern binder already in scope"
  , targetRejects "pattern scope"
      (withMaybe (X.Case justInt int [nothing (X.VarTerm x), just (X.VarTerm x)])) "unbound term variable"
  , targetRejects "declared arity in an annotation"
      (withMaybe (X.Abs x (T.Con "Maybe" []) (X.VarTerm x))) "invalid type constructor arity"
  , targetRejects "declared arity inside a type computation"
      (withMaybe (X.TypeApp (X.TypeAbs (T.TyVar 0) T.Bot (X.IntTerm 1)) (X.Inner (X.Bottom (T.Con "Maybe" []))))) "invalid type constructor arity"
  , targetRejects "invalid declaration"
      (X.WithData [D.DataDecl "T" [] [D.ConstructorDecl "T" [D.Parameter "a"]]] (X.IntTerm 1)) "unbound data type parameter"
  , targetRejects "nested declaration scope"
      (X.Abs x int (withMaybe (X.VarTerm x))) "outermost level"
  ] ++
  [ ("data syntax: " ++ label, case parseProgram "<invalid data syntax>" source of
      Left _ -> pure ()
      Right parsed -> fail ("unexpected parse: " ++ show parsed))
  | (label,source) <-
      [ ("declaration separator required", "data T = T T")
      , ("lowercase constructor", "data T = bad; bad")
      , ("empty case", maybeDecl ++ "case Nothing of {}")
      , ("nested patterns require nested cases", maybeDecl ++ "case Just Nothing of { Just (Just x) -> x; _ -> 0 }")
      , ("wildcard token boundary", pairDecl ++ "case Pair 1 2 of { Pair _x -> 0 }")
      ]
  ]
