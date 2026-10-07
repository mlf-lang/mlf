module IOTests (ioTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import Backends (Backends, Event (..), Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler
import qualified MLF.Data as D
import qualified MLF.Primitive as P
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

checked :: String -> IO (Compilation, X.Term)
checked source = do
  result <- right (compile "<IO test>" source)
  term <- right (XP.parseTerm "<IO xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (C.checkClosed term)
  require (T.alphaEq ty (inferredType result)) "IO round trip changed the type"
  require (X.erase term == X.erase (compiledTerm result)) "IO round trip changed erasure"
  pure (result,term)

runsOn :: Backends -> String -> String -> [String] -> [Event] -> Test
runsOn backends label source inputs expected = ("IO: " ++ label, do
  (_,term) <- checked source
  (result,trace) <- B.capture backends term inputs
  right result
  require (trace == expected) ("expected " ++ show expected ++ ", got " ++ show trace))

hasType :: String -> String -> T.Type -> Test
hasType label source expected = ("IO type: " ++ label, do
  (result,_) <- checked source
  require (T.alphaEq (inferredType result) expected) ("wrong type: " ++ sourceType result))

rejects :: String -> String -> String -> Test
rejects label source reason = ("IO rejection: " ++ label, case compile "<invalid IO>" source of
  Left err -> require (phase err == Inference && reason `isInfixOf` diagnostic err) (show err)
  Right result -> fail ("unexpected acceptance: " ++ sourceType result))

targetRejectsOn :: Backends -> String -> X.Term -> String -> Test
targetRejectsOn backends label term reason = ("IO target: " ++ label, do
  observed <- B.execute backends IOEntry (Input "" False) term
  case B.outcome observed of
    Left err -> require (reason `isInfixOf` show err && null (B.events observed)) (show err)
    Right () -> fail "invalid target accepted by both backends")

int, string, unit :: T.Type
int = T.Con "Int" []
string = T.Con "String" []
unit = T.Con "Unit" []

io :: T.Type -> T.Type
io t = T.Con "IO" [t]

monadIO :: String
monadIO = "class Monad (m : * -> *) where { return : forall a. a -> m a; bind : forall a b. m a -> (a -> m b) -> m b }; " ++
  "instance Monad IO where { return = ioReturn; bind = ioBind }; "

ioTests :: Backends -> [Test]
ioTests backends =
  [ hasType "string literal" "\"hello\"" string
  , hasType "unit literal" "()" unit
  , hasType "unit constructor" "Unit" unit
  , hasType "unit type alias" "return () : IO ()" (io unit)
  , hasType "getLine" "getLine" (io string)
  , hasType "putStrLn" "putStrLn \"hello\"" (io unit)
  , hasType "return" "return 42 : IO Int" (io int)
  , hasType "IO-specific return" "ioReturn 42" (io int)
  , hasType "pure" "pure true" (io (T.Con "Bool" []))
  , runs "greeting and input order"
      "do { putStr \"Name: \"; name <- getLine; putStrLn (concatString \"Hello, \" name) }"
      ["Ada"] [Write "Name: ",ReadLine,Write "Hello, Ada\n"]
  , runs "integer printing and string conversion"
      "do { printInt (-42); putStrLn (showInt 123456789012345678901234567890) }" []
      [Write "-42\n",Write "123456789012345678901234567890\n"]
  , runs "integer arithmetic is signed and unbounded"
      "do { printInt (addInt (-7) 3); printInt (subInt 3 7); printInt (addInt 999999999999999999999999999999 1) }" []
      [Write "-4\n",Write "-4\n",Write "1000000000000000000000000000000\n"]
  , runs "integer equality and strict ordering"
      ("let report = \\b -> printInt (ifThenElse b 1 0) in do { " ++
       "report (eqInt (-3) (-3)); report (eqInt (-3) 3); " ++
       "report (ltInt (-3) 3); report (ltInt 3 3); report (ltInt 4 3) }") []
      (map Write ["1\n","0\n","1\n","0\n","0\n"])
  , runs "string equality respects case, empty strings, and Unicode"
      ("let report = \\b -> printInt (ifThenElse b 1 0) in do { " ++
       "report (eqString \"\" \"\"); report (eqString \"w\" \"W\"); " ++
       "report (eqString \"你好\" \"你好\"); report (eqString \"a\" \"ab\") }") []
      (map Write ["1\n","0\n","1\n","0\n"])
  , runs "primitives are curried ordinary values"
      "let increment = addInt 1 in let choose = ifThenElse false in printInt (choose 0 (increment 41))" [] [Write "42\n"]
  , runs "conditional executes only the chosen IO branch"
      "do { ifThenElse true (putStrLn \"yes\") (bind getLine putStrLn); ifThenElse false (bind getLine putStrLn) (putStrLn \"no\") }" []
      [Write "yes\n",Write "no\n"]
  , runs "conditional preserves a polymorphic branch"
      "let id = ifThenElse true (\\x -> x) (\\x -> x) in do { printInt (id 42); putStrLn (id \"ok\") }" []
      [Write "42\n",Write "ok\n"]
  , runs "local bindings shadow arithmetic primitives"
      "let addInt = \\x y -> subInt x y in printInt (addInt 7 3)" [] [Write "4\n"]
  , ("IO: conditional does not force an unselected pure branch", do
      (_,term) <- checked ("data Loop a = Loop (Loop a -> a); " ++
        "let spin : Int = let go = \\r -> case r of { Loop f -> f r } in go (Loop go) in " ++
        "do { printInt (ifThenElse true 1 spin); printInt (ifThenElse false spin 2) }")
      (result,trace) <- capture term []
      right result
      require (trace == [Write "1\n",Write "2\n"]) (show trace))
  , runs "string escapes and unicode" "putStrLn \"你好\\n\\\"quoted\\\"\\t\\\\\"" [] [Write "你好\n\"quoted\"\t\\\n"]
  , runs "an action can be executed more than once"
      "let input = getLine in do { a <- input; b <- input; putStrLn (concatString a b) }"
      ["first","second"] [ReadLine,ReadLine,Write "firstsecond\n"]
  , runs "constructing unused actions has no effects"
      "let ignored = putStrLn \"wrong\" in return () : IO Unit" [] []
  , runs "return does not execute its argument" "return (putStrLn \"wrong\") : IO (IO Unit)" [] []
  , runs "extracting a nested action still needs sequencing"
      "do { action <- return (putStrLn \"once\"); action }" [] [Write "once\n"]
  , runs "unit pattern" "do { () <- putStrLn \"one\"; return () }" [] [Write "one\n"]
  , runs "polymorphic function returned by IO"
      "do { id <- return (\\x -> x); printInt (id 42) }" [] [Write "42\n"]
  , runs "local bindings shadow IO primitives"
      "let putStrLn = \\x -> ioReturn x in ioBind (putStrLn \"quiet\") (\\x -> ioReturn ())" [] []
  , runs "data fields can contain IO actions"
      "data Box a = Box a; case Box (putStrLn \"field\") of { Box action -> action }" [] [Write "field\n"]
  , runs "unselected case branch has no effects"
      "data Choice = First | Second; case First of { First -> putStrLn \"first\"; Second -> putStrLn \"wrong\" }" [] [Write "first\n"]
  , runs "constructor and case evaluation"
      "data Pair a b = Pair a b; let pair = Pair 42 in case pair true of { Pair number flag -> printInt number }" [] [Write "42\n"]
  , runs "recursive dictionary methods"
      ("data List a = Nil | Cons a (List a); class PrintList a where { printList : List a -> IO Unit }; " ++
       "instance PrintList Int where { printList = \\xs -> case xs of { Nil -> return (); Cons n rest -> do { printInt n; printList rest } } }; " ++
       "printList (Cons 1 (Cons 2 Nil))") [] [Write "1\n",Write "2\n"]
  , runs "generic Monad IO bind"
      (monadIO ++ "let twice : forall (m : * -> *) a. Monad m => m a -> m a = \\action -> do { action; value <- action; return value } in twice (putStrLn \"again\")")
      [] [Write "again\n",Write "again\n"]
  , runs "generic Monad IO input"
      (monadIO ++ "let echo : forall (m : * -> *). Monad m => m String -> (String -> m Unit) -> m Unit = \\input output -> do { line <- input; output line } in echo getLine putStrLn")
      ["generic"] [ReadLine,Write "generic\n"]
  , rejects "IO cannot be redefined" "data IO a = Fake a; Fake 42" "cannot redefine a primitive type"
  , rejects "String cannot be redefined" "data String = Text; Text" "cannot redefine a primitive type"
  , rejects "Unit cannot be redefined" "data Unit = Unit; Unit" "cannot redefine a primitive type"
  , rejects "Unit constructor cannot be forged" "data Fake = Unit; Unit" "cannot redefine a primitive constructor"
  , rejects "putStrLn expects a string" "putStrLn 42" "type constructor mismatch"
  , rejects "arithmetic expects integers" "addInt 1 \"2\"" "type constructor mismatch"
  , rejects "comparison expects integers" "ltInt false 1" "type constructor mismatch"
  , rejects "string equality expects strings" "eqString 1 1" "type constructor mismatch"
  , rejects "conditional requires a Boolean" "ifThenElse 1 2 3" "type constructor mismatch"
  , rejects "conditional branches must agree" "ifThenElse true 42 \"wrong\"" "type constructor mismatch"
  , rejects "printInt expects an integer" "printInt \"42\"" "type constructor mismatch"
  , rejects "getLine is an action rather than a function" "getLine ()" "type constructor mismatch"
  , rejects "IO action cannot be used as a pure string" "putStrLn getLine" "type constructor mismatch"
  , rejects "bind continuation must return an action" "bind getLine (\\line -> line)" "type constructor mismatch"
  , rejects "IO has a fixed arity" "(\\x -> x) : IO -> IO" "invalid type constructor arity"
  , rejects "IO cannot take two parameters" "(\\x -> x) : IO Int Bool -> IO Int Bool" "kind * cannot be applied"
  , targetRejects "primitive type arity" (X.Primitive P.IOReturn []) "primitive type argument arity mismatch"
  , targetRejects "primitive type kind" (X.Primitive P.IOReturn [T.Con "IO" []]) "primitive type argument kind mismatch"
  , targetRejects "primitive type scope" (X.Primitive P.IOReturn [T.Var (T.TyVar 0)]) "unbound type variable"
  , targetRejects "primitive value argument type" (X.App (X.Primitive P.PutStrLn []) (X.IntTerm 42)) "application type mismatch"
  , targetRejects "conditional type argument arity" (X.Primitive P.IfThenElse []) "primitive type argument arity mismatch"
  , targetRejects "conditional branch type checked independently"
      (X.App (X.App (X.App (X.Primitive P.IfThenElse [int]) (X.BoolTerm True)) (X.IntTerm 1)) (X.StringTerm "wrong")) "application type mismatch"
  , targetRejects "no IO constructor" (X.Constructor "IO" [int]) "unknown data constructor"
  , targetRejects "target IO type cannot be forged"
      (X.WithData [D.DataDecl "IO" ["a"] [D.ConstructorDecl "Fake" [D.Parameter "a"]]] (X.Constructor "Fake" [int])) "cannot redefine a primitive type"
  , ("IO: pure programs are not executable entry points", do
      (_,term) <- checked "42"
      (outcome,trace) <- capture term []
      case outcome of
        Left err -> require ("must have type IO" `isInfixOf` show err && null trace) (show (err,trace))
        Right _ -> fail "pure program was executed")
  , ("IO: target verification happens before any effects", do
      let printTerm = X.App (X.Primitive P.PutStrLn []) (X.StringTerm "must not print")
          bad = X.App (X.App (X.Primitive P.IOBind [unit,unit]) printTerm)
            (X.Abs (X.Name 0 "x") unit (X.IntTerm 42))
      (outcome,trace) <- capture bad []
      case outcome of
        Left err -> require ("target verification failed" `isInfixOf` show err && null trace) (show (err,trace))
        Right _ -> fail "ill-typed IO reached execution")
  , ("IO: EOF is reported and stops the continuation", do
      (_,term) <- checked "do { line <- getLine; putStrLn line }"
      (outcome,trace) <- capture term []
      case outcome of
        Left err -> require ("test input exhausted" `isInfixOf` show err && trace == [ReadLine]) (show (err,trace))
        Right _ -> fail "EOF did not fail")
  , ("IO: backend output errors are reported", do
      (_,term) <- checked "putStrLn \"hello\""
      observed <- B.execute backends IOEntry (Input "" True) term
      case B.outcome observed of
        Left err -> require ("write failed" `isInfixOf` show err && B.events observed == [Write "hello\n"]) (show observed)
        Right _ -> fail "output failure was swallowed")
  , ("IO: unknown target primitive is rejected", case XP.parseTerm "<unknown primitive>" "primitive unsafePerformIO()" of
      Left err -> require ("unknown primitive" `isInfixOf` err) err
      Right _ -> fail "unknown primitive parsed")
  , law "left identity" "bind (return 42) f" "f 42" [Write "42\n",Write "done\n"]
  , law "right identity" "bind action return" "action" [Write "action\n",Write "7\n"]
  , law "associativity" "bind (bind action f) g" "bind action (\\x -> bind (f x) g)"
      [Write "action\n",Write "7\n",Write "done\n",Write "end\n"]
  ]
  where
    runs = runsOn backends
    capture = B.capture backends
    targetRejects = targetRejectsOn backends
    law label left rightExpression expected = ("IO monad law: " ++ label, do
      let prefix = "let action = do { putStrLn \"action\"; return 7 } in " ++
            "let f = \\n -> do { printInt n; return \"done\" } in " ++
            "let g = \\s -> do { putStrLn s; return \"end\" } in "
          finish expression = prefix ++ "bind (" ++ expression ++ ") " ++
            (if label == "right identity" then "printInt" else "putStrLn")
      (_,a) <- checked (finish left)
      (_,b) <- checked (finish rightExpression)
      (resultA,traceA) <- capture a []
      (resultB,traceB) <- capture b []
      right resultA
      right resultB
      require (traceA == expected && traceB == expected) (show (traceA,traceB)))
