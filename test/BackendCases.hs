module BackendCases (backendTests) where

import Control.Monad (forM_, unless)
import Data.List (isInfixOf, isSuffixOf, sort)
import System.Directory (listDirectory)
import System.FilePath ((</>))
import Backends (Backends, Entry (..), Input (..), Event (..))
import qualified Backends as B
import MLF.Compiler
import qualified MLF.Data as D
import qualified MLF.Primitive as P
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

type Test = (String,IO ())

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

require :: Bool -> String -> IO ()
require condition message = unless condition (fail message)

checked :: String -> IO X.Term
checked source = do
  compiled <- right (compile "<backend source test>" source)
  right (XP.parseTerm "<standalone xMLF test>" (prettyTerm (compiledTerm compiled)))

checkOutput :: Backends -> X.Term -> [String] -> String -> IO ()
checkOutput backends term inputs expected = do
  (result,trace) <- B.capture backends term inputs
  right result
  let actual = concat [text | Write text <- trace]
  require (actual == expected) ("unexpected output: " ++ show actual)

backendTests :: Backends -> [Test]
backendTests backends =
  [("backend: " ++ label, checked source >>= \term -> checkOutput backends term inputs expected) |
    (label,source,inputs,expected) <- programs] ++
  [("backend target: " ++ label, do
      observed <- B.execute backends ProgramEntry (Input "" False) term
      case B.outcome observed of
        Left err -> require ("target verification failed" `isInfixOf` show err && null (B.events observed)) (show observed)
        Right () -> fail "unchecked target reached a backend") | (label,term) <- rejected] ++
  [("backend: " ++ label, checkOutput backends term [] expected) |
    (label,term,expected) <-
      [("identity capture",captureTerm,"1\n"),("cyclic data",cyclicData,"42\n"),
       ("10000 IO steps",recursiveIO,"done\n"),("mutual recursion",mutualRecursion,"42\n")]] ++
  [ ("backend: pure program entry does not print", do
      observed <- B.execute backends ProgramEntry (Input "" False) (X.IntTerm 42)
      right (B.outcome observed)
      require (null (B.events observed)) (show observed))
  , ("backend: lazy default case", checkOutput backends
      (loop (X.Case (X.VarTerm n) ioUnit [X.Alternative (X.DefaultPattern Nothing) (printInt (X.IntTerm 7))])) [] "7\n")
  , ("backend: lazy returned value", checkOutput backends
      (loop (X.App (X.Primitive P.IOReturn [int]) (X.VarTerm n))) [] "")
  , ("backend: recursive demand fails", do
      observed <- B.execute backends IOEntry (Input "" False) (loop (printInt (X.VarTerm n)))
      case B.outcome observed of
        Left err -> require ("cyclic evaluation" `isInfixOf` show err && null (B.events observed)) (show observed)
        Right () -> fail "recursive demand unexpectedly succeeded")
  , ("backend: final line without newline", do
      term <- checked "do { line <- getLine; putStrLn line }"
      observed <- B.execute backends IOEntry (Input "last line without newline" False) term
      right (B.outcome observed)
      require (B.events observed == [ReadLine,Write "last line without newline\n"] && null (B.remaining observed)) (show observed))
  , ("backend: unused input is retained", do
      term <- checked "putStrLn \"no read\""
      observed <- B.execute backends IOEntry (Input "unused\n" False) term
      right (B.outcome observed)
      require (B.events observed == [Write "no read\n"] && B.remaining observed == "unused\n") (show observed))
  , ("backend: all examples execute", do
      files <- sort . filter (".emlf" `isSuffixOf`) <$> listDirectory "examples"
      require (length files >= 16) "example corpus is unexpectedly small"
      forM_ files $ \file -> do
        term <- readFile ("examples" </> file) >>= checked
        let input = case file of "io-hello.emlf" -> "Ada\n"; "snake.emlf" -> "q\n"; _ -> ""
        observed <- B.execute backends ProgramEntry (Input input False) term
        right (B.outcome observed)
        require (null (B.remaining observed)) (file ++ ": input not consumed")
        case file of
          "io-hello.emlf" -> require (B.output observed == "What is your name? Hello, Ada\n") (show observed)
          "monad-io.emlf" -> require (B.output observed == concat (replicate 2 "Hello from Monad IO!\n")) (show observed)
          "snake.emlf" -> require ("Goodbye. Score: 0\n" `isInfixOf` B.output observed) (show observed)
          _ -> require (null (B.events observed)) ("pure example performed IO: " ++ file)
      putStrLn ("  Both backends executed all " ++ show (length files) ++ " examples"))
  , ("backend: state dictionary result", do
      term <- readFile "examples/monad-state-do.emlf" >>= checked
      let a = X.Name (-1) "value"; b = X.Name (-2) "state"
      checkOutput backends (wrap term (\body -> X.Case body ioUnit
        [X.Alternative (X.ConstructorPattern "Pair" [Just a,Just b])
          (bindUnit (printInt (X.VarTerm a)) (printInt (X.VarTerm b)))])) [] "0\n42\n")
  , ("backend: superclass dictionary result", do
      term <- readFile "examples/monad-maybe.emlf" >>= checked
      let a = X.Name (-1) "value"
      checkOutput backends (wrap term (\body -> X.Case body ioUnit
        [X.Alternative (X.ConstructorPattern "Nothing" []) (printInt (X.IntTerm 0)),
         X.Alternative (X.ConstructorPattern "Just" [Just a]) (printInt (X.VarTerm a))])) [] "42\n")
  ]
  where
    n = X.Name 900 "loop"
    loop body = X.LetRec [(n,int,X.VarTerm n)] body

int, unit, ioUnit :: T.Type
int = T.Con "Int" []
unit = T.Con "Unit" []
ioUnit = T.Con "IO" [unit]

printInt :: X.Term -> X.Term
printInt = X.App (X.Primitive P.PrintInt [])

bindUnit :: X.Term -> X.Term -> X.Term
bindUnit action body = X.App (X.App (X.Primitive P.IOBind [unit,unit]) action)
  (X.Abs (X.Name (-99) "ignored") unit body)

wrap :: X.Term -> (X.Term -> X.Term) -> X.Term
wrap (X.WithData ds body) f = X.WithData ds (f body)
wrap body f = f body

captureTerm :: X.Term
captureTerm = X.App (X.Abs (X.Name 0 "same") int
  (X.Let (X.Name 1 "same") (X.IntTerm 2) (printInt (X.VarTerm (X.Name 0 "different-hint"))))) (X.IntTerm 1)

cyclicData :: X.Term
cyclicData = X.WithData [D.DataDecl "Stream" [] [D.ConstructorDecl "Cons" [D.Applied "Int" [],D.Applied "Stream" []]]]
  (X.LetRec [(stream,T.Con "Stream" [],X.App (X.App (X.Constructor "Cons" []) (X.IntTerm 42)) (X.VarTerm stream))]
    (X.Case (X.VarTerm stream) ioUnit [X.Alternative (X.ConstructorPattern "Cons" [Just headName,Nothing])
      (printInt (X.VarTerm headName))]))
  where stream = X.Name 10 "stream"; headName = X.Name 11 "head"

recursiveIO :: X.Term
recursiveIO = X.LetRec [(loop,T.Arrow int ioUnit,X.Abs n int body)] (X.App (X.VarTerm loop) (X.IntTerm 10000))
  where
    loop = X.Name 20 "loop"; n = X.Name 21 "n"
    done = X.App (X.Primitive P.PutStrLn []) (X.StringTerm "done")
    zero = X.App (X.App (X.Primitive P.EqInt []) (X.VarTerm n)) (X.IntTerm 0)
    previous = X.App (X.App (X.Primitive P.SubInt []) (X.VarTerm n)) (X.IntTerm 1)
    more = bindUnit (X.App (X.Primitive P.IOReturn [unit]) (X.Constructor "Unit" []))
      (X.App (X.VarTerm loop) previous)
    body = X.App (X.App (X.App (X.Primitive P.IfThenElse [ioUnit]) zero) done) more

mutualRecursion :: X.Term
mutualRecursion = X.LetRec
  [(f,T.Arrow int ioUnit,X.Abs x int (X.App (X.VarTerm g) (X.VarTerm x))),
   (g,T.Arrow int ioUnit,X.Abs y int body)] (X.App (X.VarTerm f) (X.IntTerm 100))
  where
    f = X.Name 30 "f"; g = X.Name 31 "g"; x = X.Name 32 "x"; y = X.Name 33 "y"
    zero = X.App (X.App (X.Primitive P.EqInt []) (X.VarTerm y)) (X.IntTerm 0)
    previous = X.App (X.App (X.Primitive P.SubInt []) (X.VarTerm y)) (X.IntTerm 1)
    body = X.App (X.App (X.App (X.Primitive P.IfThenElse [ioUnit]) zero)
      (printInt (X.IntTerm 42))) (X.App (X.VarTerm f) previous)

rejected :: [(String,X.Term)]
rejected =
  [ ("non-function",X.App (X.IntTerm 1) (X.BoolTerm True))
  , ("bad computation",X.TypeApp (X.IntTerm 1) X.Elim)
  , ("bad unused branch",X.Let (X.Name 1 "ignored") (X.App (X.IntTerm 0) (X.IntTerm 1)) (X.IntTerm 2))
  , ("free identity",X.VarTerm (X.Name 2 "free"))
  ]

programs :: [(String,String,[String],String)]
programs =
  [ ("unicode-input", "do { line <- getLine; putStrLn line }", ["你好🌍\0input"], "你好🌍\0input\n")
  , ("unicode", "do { putStrLn \"你好🌍\\n\\\"quoted\\\"\\t\\\\\"; printInt (ifThenElse (eqString \"你好\" \"你好\") 1 0) }", [], "你好🌍\n\"quoted\"\t\\\n1\n")
  , ("nul", "do { putStr (concatString \"a\\0b\" \"c\"); printInt (ifThenElse (eqString \"a\\0b\" \"a\\0c\") 1 0) }", [], "a\0bc0\n")
  , ("curried-closure", "let f = \\x -> let saved = x in \\y -> addInt saved y in let add = f 19 in printInt (add 23)", [], "42\n")
  , ("lazy-field", "data Loop a = Loop (Loop a -> a); data Pair a b = Pair a b; let spin : Int = let go = \\r -> case r of { Loop f -> f r } in go (Loop go) in case Pair 42 spin of { Pair x _ -> printInt x }", [], "42\n")
  , ("selected-case", "data Choice = A | B; case B of { A -> putStrLn \"wrong\"; other -> putStrLn \"right\" }", [], "right\n")
  ]
