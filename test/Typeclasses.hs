module Typeclasses (typeclassTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import qualified Data.Map.Strict as Map
import MLF.Compiler
import qualified MLF.Data as D
import MLF.Evidence (resolveDictionary)
import MLF.Kind
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
  result <- right (compile "<class test>" source)
  parsed <- right (P.parseTerm "<class xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (C.checkClosed parsed)
  require (T.alphaEq ty (inferredType result)) "class xMLF round trip changed type"
  require (X.erase parsed == X.erase (compiledTerm result)) "class xMLF round trip changed erasure"
  pure result

hasType :: String -> String -> T.Type -> Test
hasType label source expected = ("class: " ++ label, do
  result <- checked source
  require (T.alphaEq (inferredType result) expected)
    ("expected " ++ prettyType expected ++ ", got " ++ sourceType result))

rejects :: String -> String -> Phase -> String -> Test
rejects label source expectedPhase reason = ("class rejection: " ++ label,
  case compile "<class rejection>" source of
    Left err -> do
      require (phase err == expectedPhase) ("wrong rejection phase: " ++ show err)
      require (reason `isInfixOf` diagnostic err) ("wrong rejection reason: " ++ show err)
    Right result -> fail ("unexpected acceptance: " ++ sourceType result))

targetRejects :: String -> X.Term -> String -> Test
targetRejects label term reason = ("class target: " ++ label, case C.checkClosed term of
  Left err -> require (reason `isInfixOf` err) ("wrong target rejection: " ++ err)
  Right ty -> fail ("unexpected target type: " ++ prettyType ty))

int, bool :: T.Type
int = T.Con "Int" []
bool = T.Con "Bool" []

inspectClass, inspectBool, inspectInt, maybeDecl, functorClass, maybeFunctor :: String
inspectClass = "class Inspect a where { inspect : a -> Bool }; "
inspectBool = "instance Inspect Bool where { inspect = \\x -> x }; "
inspectInt = "instance Inspect Int where { inspect = \\x -> true }; "
maybeDecl = "data Maybe a = Nothing | Just a; "
functorClass = "class Functor (f : * -> *) where { fmap : forall a b. (a -> b) -> f a -> f b }; "
maybeFunctor = "instance Functor Maybe where { fmap = \\f value -> case value of { Nothing -> Nothing; Just x -> Just (f x) } }; "

typeclassTests :: [Test]
typeclassTests = singleParameterTests ++ multiParameterTests

singleParameterTests :: [Test]
singleParameterTests =
  [ hasType "concrete method" (inspectClass ++ inspectBool ++ "inspect true") bool
  , hasType "inferred constrained let at distinct instances"
      (inspectClass ++ inspectBool ++ inspectInt ++ "let f = \\x -> inspect x in let b = f true in f 42") bool
  , hasType "implicit method quantification"
      "class Keep a where { keep : a -> b -> a }; instance Keep Int where { keep = \\x ignored -> x }; keep 42 true" int
  , hasType "explicit qualified function"
      (inspectClass ++ inspectBool ++ "let f : forall a. Inspect a => a -> Bool = \\x -> inspect x in f true") bool
  , hasType "qualified expression in function position"
      (inspectClass ++ inspectBool ++ "((\\x -> inspect x) : forall a. Inspect a => a -> Bool) true") bool
  , hasType "qualified function parameter"
      (inspectClass ++ inspectBool ++ inspectInt ++
       "(\\(f : forall a. Inspect a => a -> Bool) -> let n = f 42 in f true) ((\\x -> inspect x) : forall a. Inspect a => a -> Bool)") bool
  , hasType "two givens of the same class"
      (inspectClass ++ inspectBool ++ inspectInt ++
       "let both : forall a b. (Inspect a, Inspect b) => a -> b -> Bool = \\x y -> (\\first -> inspect y) (inspect x) in both 42 true") bool
  , hasType "concrete call inside a generic constraint"
      (inspectClass ++ inspectBool ++ inspectInt ++
       "let both : forall a. Inspect a => a -> Bool = \\x -> (\\fixed -> inspect x) (inspect true) in both 42") bool
  , hasType "lambda shadows method" (inspectClass ++ "(\\inspect -> inspect 42) (\\x -> x)") int
  , hasType "let shadows method" (inspectClass ++ "let inspect = \\x -> x in inspect 42") int
  , hasType "pattern shadows method"
      (inspectClass ++ "data Box a = Box a; case Box 42 of { Box inspect -> inspect }") int
  , hasType "higher-kinded method" (maybeDecl ++ functorClass ++ maybeFunctor ++ "fmap (\\x -> true) (Just 42)") (T.Con "Maybe" [bool])
  , hasType "partial type constructor instance"
      ("data Either e a = Left e | Right a; " ++ functorClass ++
       "instance Functor (Either e) where { fmap = \\f value -> case value of { Left err -> Left err; Right x -> Right (f x) } }; " ++
       "fmap (\\x -> true) (Right 42 : Either Int Int)") (T.Con "Either" [int,bool])
  , hasType "instance definitions are order independent"
      (inspectClass ++ "class Inspect a => Test a where { test : a -> Bool }; " ++
       "instance Test Bool where { test = \\x -> inspect x }; " ++ inspectBool ++ "test true") bool
  , hasType "superclass given without concrete instances"
      (inspectClass ++ "class Inspect a => Test a where { test : a -> Bool }; " ++
       "let f : forall a. Test a => a -> Bool = \\x -> inspect x in 42") int
  , hasType "mutually recursive methods"
      "class Loop a where { first : a -> a; second : a -> a }; instance Loop Int where { first = \\x -> second x; second = \\x -> first x }; first 42" int
  , hasType "higher-kinded datatype application"
      (maybeDecl ++ "data Wrap (f : * -> *) a = Wrap (f a); case Wrap (Just 42) of { Wrap value -> value }") (T.Con "Maybe" [int])
  , hasType "higher-kinded annotation"
      (maybeDecl ++ "let id : forall (f : * -> *) a. f a -> f a = \\x -> x in id (Just 42)") (T.Con "Maybe" [int])
  , ("class: Monad hierarchy example", do
      source <- readFile "examples/monad-maybe.emlf"
      result <- checked source
      require (T.alphaEq (inferredType result) (T.Con "Maybe" [int])) "wrong Monad example result")
  , ("class: contextual recursive instance example", do
      source <- readFile "examples/contextual-instance.emlf"
      result <- checked source
      require (T.alphaEq (inferredType result) bool) "wrong contextual example result")
  , ("class: qualified result is displayed using its class name", do
      result <- checked (inspectClass ++ "(\\x -> inspect x) : forall a. Inspect a => a -> Bool")
      require ("Inspect " `isInfixOf` sourceType result && "=>" `isInfixOf` sourceType result)
        ("missing source constraint: " ++ sourceType result)
      require (not ("DictInspect" `isInfixOf` sourceType result)) "internal dictionary name leaked")
  , rejects "missing concrete instance" (inspectClass ++ "inspect 42") Resolution "no instance or given constraint"
  , rejects "does not pick the only instance for an unknown type"
      (inspectClass ++ inspectBool ++ "inspect") Resolution "ambiguous"
  , rejects "wrong instance body" (inspectClass ++ "instance Inspect Bool where { inspect = \\x -> 42 }; true") Inference "type constructor mismatch"
  , rejects "method body is checked polymorphically"
      "class Keep a where { keep : forall b. a -> b -> b }; instance Keep Int where { keep = \\x ignored -> 42 }; true" Inference "Skolem"
  , rejects "missing method" (inspectClass ++ "instance Inspect Bool where {}; true") Inference "missing [\"inspect\"]"
  , rejects "extra method" (inspectClass ++ "instance Inspect Bool where { inspect = \\x -> x; extra = true }; true") Inference "unexpected [\"extra\"]"
  , rejects "duplicate method implementation" (inspectClass ++ "instance Inspect Bool where { inspect = \\x -> x; inspect = \\x -> x }; true") Inference "duplicate instance method"
  , rejects "duplicate class" (inspectClass ++ inspectClass ++ "true") Inference "duplicate class"
  , rejects "methods share a global namespace"
      (inspectClass ++ "class Other a where { inspect : a -> Int }; true") Inference "duplicate class method"
  , rejects "method must mention its class parameter" "class Ambiguous a where { number : Int }; true" Inference "ambiguous class method"
  , rejects "unknown class" "instance Missing Bool where {}; true" Inference "unknown class"
  , rejects "duplicate instance" (inspectClass ++ inspectBool ++ inspectBool ++ "true") Inference "overlapping instances"
  , rejects "overlapping generic and concrete instances"
      (maybeDecl ++ inspectClass ++ "instance Inspect (Maybe a) where { inspect = \\x -> true }; instance Inspect (Maybe Int) where { inspect = \\x -> false }; true") Inference "overlapping instances"
  , rejects "variable instance head" (inspectClass ++ "instance Inspect a where { inspect = \\x -> true }; true") Inference "named type constructor"
  , rejects "nondecreasing instance context"
      (inspectClass ++ "instance Inspect Bool => Inspect Bool where { inspect = \\x -> x }; true") Inference "structurally smaller"
  , rejects "instance context variable absent from head"
      (inspectClass ++ "instance Inspect a => Inspect Bool where { inspect = \\x -> x }; true") Inference "variable absent from the head"
  , rejects "cyclic superclasses"
      "class B a => A a where {}; class A a => B a where {}; true" Inference "cyclic superclass hierarchy"
  , rejects "missing superclass instance"
      (inspectClass ++ "class Inspect a => Test a where { test : a -> Bool }; instance Test Bool where { test = \\x -> x }; true") Resolution "no instance or given constraint"
  , rejects "class instance kind" (functorClass ++ "instance Functor Int where { fmap = \\f x -> x }; true") Inference "class parameter kind mismatch"
  , rejects "class context kind"
      (functorClass ++ "let f : forall a. Functor a => a -> a = \\x -> x in true") Inference "class parameter kind mismatch"
  , rejects "higher-kinded argument must have the declared kind"
      "data Wrap (f : * -> *) a = Wrap (f a); (\\x -> x) : Wrap Int Bool -> Wrap Int Bool" Inference "kind mismatch"
  , rejects "ordinary type variable cannot be applied"
      "(\\x -> x) : forall f a. f a -> f a" Inference "kind * cannot be applied"
  , rejects "method constraints require supported signatures"
      (inspectClass ++ "class Nested a where { nested : Inspect a => a -> Bool }; true") Inference "constraints"
  , targetRejects "recursive dictionary body has wrong declared type"
      (X.LetRec [(X.Name 0 "d",bool,X.IntTerm 1)] (X.VarTerm (X.Name 0 "d"))) "declared type"
  , targetRejects "recursive binders must be unique"
      (X.LetRec [(X.Name 0 "d",bool,X.BoolTerm True),(X.Name 0 "d",bool,X.BoolTerm False)] (X.BoolTerm True)) "duplicate recursive binder"
  , targetRejects "recursive binding cannot reuse an outer binder"
      (X.Abs (X.Name 0 "d") bool (X.LetRec [(X.Name 0 "d",bool,X.BoolTerm True)] (X.BoolTerm True))) "already in scope"
  , targetRejects "term annotation has kind star"
      (X.TypeAbs (T.TyVar 0) (T.BotKind (KArrow Star Star)) (X.Abs (X.Name 1 "x") (T.Var (T.TyVar 0)) (X.VarTerm (X.Name 1 "x")))) "kind *"
  , targetRejects "constructor checks the kind of a type argument"
      (X.WithData [D.DataDeclK "Wrap" [("f",KArrow Star Star)] [D.ConstructorDecl "Wrap" []]]
        (X.Constructor "Wrap" [int])) "type argument kind mismatch"
  , ("class target: compact and general application spines agree", do
      let applied = T.Apply (T.Con "Box" []) int
      require (T.alphaEq applied (T.Con "Box" [int])) "equivalent application representations differ"
      require (not (T.alphaEq applied (T.Con "Box" [bool]))) "different arguments were equated"
      require (T.alphaEq T.Bot (T.BotKind Star)) "explicit kind * changed bottom")
  , ("class target: Inst-Bot cannot change kinds", do
      case C.checkComputation Map.empty (X.Bottom int) (T.BotKind (KArrow Star Star)) of
        Left err -> require ("kind mismatch" `isInfixOf` err) err
        Right _ -> fail "ill-kinded type computation was accepted")
  , ("class evidence: chooses the given by its type", do
      ds <- right (D.validateDeclarations [D.DataDecl "Dict" ["a"] [D.ConstructorDecl "MkDict" []]])
      let first = X.Name 1 "first"
          second = X.Name 2 "second"
          evidence = [(S.GivenEvidence,first,T.Con "Dict" [int]),(S.GivenEvidence,second,T.Con "Dict" [bool])]
      term <- right (resolveDictionary ds Map.empty evidence (T.Con "Dict" [bool]))
      require (term == X.VarTerm second) "selected the wrong same-class dictionary")
  ]

convertClass, convertIntBool :: String
convertClass = "class Convert a b where { convert : a -> b }; "
convertIntBool = "instance Convert Int Bool where { convert = \\x -> true }; "

multiParameterTests :: [Test]
multiParameterTests =
  [ hasType "two parameters" (convertClass ++ convertIntBool ++ "convert 42 : Bool") bool
  , hasType "instances with the same first parameter are disjoint"
      (convertClass ++ convertIntBool ++ "instance Convert Int Int where { convert = \\x -> x }; convert 42 : Int") int
  , hasType "instances with the same second parameter are disjoint"
      (convertClass ++ convertIntBool ++ "instance Convert Bool Bool where { convert = \\x -> x }; convert true : Bool") bool
  , hasType "repeated variables are shared across instance arguments"
      (convertClass ++ "instance Convert a a where { convert = \\x -> x }; " ++ convertIntBool ++
       "let first = convert true : Bool in convert 42 : Bool") bool
  , hasType "class parameter substitution is simultaneous"
      (convertClass ++ "instance Convert b Bool where { convert = \\x -> true }; convert 42 : Bool") bool
  , hasType "inferred multiparameter constraint"
      (convertClass ++ convertIntBool ++ "let f = \\x -> convert x in f 42 : Bool") bool
  , hasType "explicit multiparameter constraint"
      (convertClass ++ convertIntBool ++ "let f : forall a b. Convert a b => a -> b = \\x -> convert x in f 42 : Bool") bool
  , hasType "three parameters"
      "class Choose a b c where { choose : a -> b -> c }; instance Choose Int Bool Bool where { choose = \\x y -> y }; choose 42 true : Bool" bool
  , hasType "superclass can discard a parameter"
      (inspectClass ++ "class Inspect b => Two a b where { two : a -> b -> Bool }; " ++
       "let f : forall a b. Two a b => a -> b -> Bool = \\x y -> inspect y in 42") int
  , hasType "superclass can reorder parameters"
      (convertClass ++ "class Convert b a => Reverse a b where { reverse : a -> b -> Bool }; " ++
       "let f : forall a b. Reverse a b => b -> a = \\x -> convert x in 42") int
  , hasType "same class givens with different second arguments"
      (convertClass ++ convertIntBool ++ "instance Convert Int Int where { convert = \\x -> x }; " ++
       "let f : forall a b c. (Convert a b, Convert a c) => a -> b -> c = \\x ignored -> convert x in f 42 true : Int") int
  , ("class: recursive multiparameter instance example", do
      source <- readFile "examples/multiparameter.emlf"
      result <- checked source
      require (T.alphaEq (inferredType result) (T.Con "Box" [T.Con "Box" [bool]])) "wrong conversion result")
  , ("class: multi-parameter constraint display", do
      result <- checked (convertClass ++ "(\\x -> convert x) : forall a b. Convert a b => a -> b")
      require ("Convert " `isInfixOf` sourceType result && "=>" `isInfixOf` sourceType result) (sourceType result)
      require (not ("DictConvert" `isInfixOf` sourceType result)) "dictionary name leaked")
  , rejects "instance is missing a parameter"
      (convertClass ++ "instance Convert Int where { convert = \\x -> x }; true") Inference "arity mismatch"
  , rejects "instance has an extra parameter"
      (convertClass ++ "instance Convert Int Bool Int where { convert = \\x -> true }; true") Inference "arity mismatch"
  , rejects "constraint is missing a parameter"
      (convertClass ++ "let f : forall a. Convert a => a -> Bool = \\x -> true in true") Inference "arity mismatch"
  , rejects "duplicate class parameter" "class Relation a a where { relate : a -> a }; true" Inference "duplicate class parameter"
  , rejects "method omits a class parameter" "class Relation a b where { relate : a -> Bool }; true" Inference "ambiguous class method"
  , rejects "does not infer an output parameter from the only instance"
      (convertClass ++ convertIntBool ++ "convert 42") Resolution "ambiguous"
  , rejects "matches every repeated parameter"
      (convertClass ++ "instance Convert a a where { convert = \\x -> x }; convert 42 : Bool") Resolution "no instance or given constraint"
  , rejects "overlap needs joint unification across parameters"
      (convertClass ++ "instance Convert a a where { convert = \\x -> x }; instance Convert Int Int where { convert = \\x -> x }; true") Inference "overlapping instances"
  , rejects "overlapping variable and concrete argument"
      (convertClass ++ "instance Convert a Bool where { convert = \\x -> true }; " ++ convertIntBool ++ "true") Inference "overlapping instances"
  , rejects "context must decrease across the whole argument tuple"
      (convertClass ++ "instance Convert b a => Convert a b where { convert = \\x -> convert x }; true") Inference "structurally smaller"
  , rejects "context cannot duplicate a variable"
      ("data Box a = Box a; " ++ convertClass ++
       "instance Convert a a => Convert (Box a) Bool where { convert = \\x -> true }; true") Inference "structurally smaller"
  , rejects "later parameter kind is checked"
      "class Relation a (f : * -> *) where { relate : a -> f a }; instance Relation Int Bool where { relate = \\x -> true }; true" Inference "class parameter kind mismatch"
  , ("class evidence: superclass projection preserves caller variable identities", do
      ds <- right (D.validateDeclarations
        [D.DataDecl "PairDict" ["a","b"] [D.ConstructorDecl "MkPairDict" []],
         D.DataDecl "OneDict" ["a"] [D.ConstructorDecl "MkOneDict" []]])
      let a = T.TyVar 0
          b = T.TyVar 1
          given = X.Name 1 "given"
          super = X.Name 2 "super"
          pair x y = T.Con "PairDict" [x,y]
          one x = T.Con "OneDict" [x]
          superType = T.Forall a T.Bot (T.Forall b T.Bot (T.Arrow (pair (T.Var a) (T.Var b)) (one (T.Var b))))
          givenType = pair (T.Var b) (T.Var a)
          wanted = one (T.Var a)
          gamma = Map.fromList [(a,T.Bot),(b,T.Bot)]
          candidates = [(S.GivenEvidence,given,givenType),(S.SuperclassEvidence,super,superType)]
      proof <- right (resolveDictionary ds gamma candidates wanted)
      actual <- right (C.inferWithData ds (C.Env gamma (Map.fromList [(given,givenType),(super,superType)])) proof)
      require (T.alphaEq actual wanted) "superclass projection changed a parameter identity")
  ]
