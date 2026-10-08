module Readability (readabilityTests, readabilityPrograms) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import MLF.Compiler
import MLF.Parser (parseProgram, parseExpr)
import qualified MLF.X.Check as C
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

type Test = (String,IO ())

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

require :: Bool -> String -> IO ()
require ok message = unless ok (fail message)

checked :: String -> IO Compilation
checked source = do
  result <- right (compile "<readability>" source)
  parsed <- right (XP.parseTerm "<readability xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (C.checkClosed parsed)
  require (T.alphaEq ty (inferredType result)) "target round trip changed type"
  require (X.erase parsed == X.erase (compiledTerm result)) "target round trip changed erasure"
  pure result

sameLayout :: String -> String -> String -> Test
sameLayout label layout explicit = ("layout: " ++ label, do
  a <- right (parseProgram "<layout>" layout)
  b <- right (parseProgram "<braces>" explicit)
  require (a == b) ("layout changed AST:\n" ++ show a ++ "\n" ++ show b))

rejects :: String -> String -> Phase -> String -> Test
rejects label source expectedPhase reason = ("readability rejection: " ++ label,
  case compile "<invalid readability>" source of
    Left err -> require (phase err == expectedPhase && isInfixOf reason (diagnostic err)) (show err)
    Right result -> fail ("unexpected acceptance: " ++ sourceType result))

readabilityTests :: [Test]
readabilityTests =
  [ sameLayout "top-level data, signatures and equations"
      "data Maybe a = Nothing | Just a\nget : Maybe Int -> Int\nget Nothing = 0\nget (Just x) = x\nmain = get (Just 42)\n"
      "data Maybe a = Nothing | Just a; get : Maybe Int -> Int; get Nothing = 0; get (Just x) = x; main = get (Just 42);"
  , sameLayout "nested do with a trailing semicolon"
      "main = do\n  do\n    printInt 1;\n  printInt 2\n"
      "main = do { do { printInt 1; }; printInt 2 };"
  , sameLayout "nested case and do"
      "data Box = Box Int\nmain = case Box 42 of\n  Box x -> do\n    printInt x\n    putStrLn \"ok\"\n"
      "data Box = Box Int; main = case Box 42 of { Box x -> do { printInt x; putStrLn \"ok\" } };"
  , sameLayout "parenthesized implicit block"
      "main = ioBind (do\n  printInt 1\n  return 42) (\\x -> printInt x)\n"
      "main = ioBind (do { printInt 1; return 42 }) (\\x -> printInt x);"
  , sameLayout "implicit block in explicit block"
      "main = do {\n  case true of\n    true -> printInt 1\n    false -> printInt 0\n}\n"
      "main = do { case true of { true -> printInt 1; false -> printInt 0 } };"
  , sameLayout "same-line else closes do"
      "main = if true then do printInt 1 else do printInt 0\n"
      "main = if true then do { printInt 1 } else do { printInt 0 };"
  , sameLayout "local declaration layout"
      "main = let\n  x = 20\n  y = 22\n in printInt (x + y)\n"
      "main = let { x = 20; y = 22 } in printInt (x + y);"
  , sameLayout "do local group followed by another statement"
      "main = do\n  let\n    id x = x\n    n = id 42;\n  printInt n\n"
      "main = do { let { id x = x; n = id 42; }; printInt n };"
  , sameLayout "nested explicit let matches its own in"
      "main = let\n  x = let { y = 42 } in y\n in printInt x\n"
      "main = let { x = let { y = 42 } in y } in printInt x;"
  , sameLayout "class and instance layout"
      "class Render a where\n  render : a -> String\ninstance Render Bool where\n  render true = \"yes\"\n  render false = \"no\"\nmain = putStrLn (render true)\n"
      "class Render a where { render : a -> String }; instance Render Bool where { render true = \"yes\"; render false = \"no\" }; main = putStrLn (render true);"
  , sameLayout "explicit braces after a keyword on another line"
      "main = do\n{ printInt 42 }\n"
      "main = do { printInt 42 };"
  , sameLayout "keywords in comments and strings"
      "{- do {- where -}\n let of -}\nmain = do\n  putStrLn \"do -- case of { where }\"\n  -- } let\n  printInt 42\n"
      "main = do { putStrLn \"do -- case of { where }\"; printInt 42 };"
  , sameLayout "tabs have tab-stop indentation"
      "main = do\n\tprintInt 1\n\tprintInt 2\n"
      "main = do { printInt 1; printInt 2 };"
  , sameLayout "indented file"
      "    inc x = x + 1\n    main = printInt (inc 41)\n"
      "inc x = x + 1; main = printInt (inc 41);"
  , sameLayout "leading comment does not set the top-level column"
      "{- comment -} inc x = x + 1\nmain = printInt (inc 41)\n"
      "inc x = x + 1; main = printInt (inc 41);"
  , sameLayout "string gap ending before the closing quote"
      "main = do\n  putStrLn \"a\\\n    \\\"\n  printInt 1\n"
      "main = do { putStrLn \"a\"; printInt 1 };"
  , sameLayout "explicit top-level braces"
      "{ f x = x; main = f 42; }" "f x = x\nmain = f 42\n"
  , ("layout: parseExpr accepts an implicit do", do
      a <- right (parseExpr "<expr layout>" "do\n  x <- return 42\n  printInt x")
      b <- right (parseExpr "<expr braces>" "do { x <- return 42; printInt x }")
      require (a == b) "parseExpr layout differs")
  , ("layout: diagnostics keep original line and column", do
      case parseProgram "original.emlf" "main = do\n  printInt )\n" of
        Left err -> require (isInfixOf "line 2, column 12" err) err
        Right p -> fail (show p))
  , ("recursion: declared polymorphism is independently checked", do
      result <- checked "data Nest a = Leaf a | Step (Nest (Nest a)); depth : forall a. Nest a -> Int; depth (Leaf _) = 0; depth (Step x) = 1 + depth x; main = depth (Step (Leaf (Leaf true)));"
      require (T.alphaEq (inferredType result) (T.Con "Int" [])) (sourceType result)
      require (containsRec (X.erase (compiledTerm result))) "recursion did not reach checked target bindings")
  , ("recursion: monomorphic closure captures an outer value", do
      result <- checked "let offset = 2 in let rec count n : Int -> Int = if n == 0 then offset else count (n-1) + 1 in count 3"
      require (T.alphaEq (inferredType result) (T.Con "Int" [])) (sourceType result))
  , ("equations: parameter can shadow the function name", do
      result <- checked "identity identity = identity; main = identity 42;"
      require (T.alphaEq (inferredType result) (T.Con "Int" [])) (sourceType result))
  , rejects "recursive forall cannot specialize to Int"
      "bad : forall a. a -> a; bad x = if true then 1 else bad x; main = bad true;" Inference ""
  , rejects "mutual recursion needs every signature"
      "f : Int -> Int; f x = g x; g x = f x; main = f 0;" Parsing "requires an explicit closed signature"
  , rejects "local recursion needs a signature"
      "let rec f x = f x in f 0" Parsing "requires an explicit closed signature"
  , rejects "recursive existentials are not closed signatures"
      "f : exists a. Int -> a; f x = f x; main = f 0;" Parsing "requires an explicit closed signature"
  , rejects "recursive signature free variable"
      "f : a -> a; f x = f x; main = f 0;" Inference "unbound"
  , rejects "equation arity"
      "f 0 = 0; f x y = x; main = f 0;" Parsing "different arities"
  , rejects "equations must be contiguous"
      "f 0 = 0; g = 1; f n = n; main = f 1;" Parsing "contiguous"
  , rejects "missing constructor equation"
      "data Maybe a = Nothing | Just a; f (Just x) = x; main = f (Just 1);" Inference "non-exhaustive"
  , rejects "missing nested constructor"
      "data Maybe a = Nothing | Just a; f Nothing = 0; f (Just (Just x)) = x; main = f (Just (Just 1));" Inference "non-exhaustive"
  , rejects "integer equations need fallback"
      "f 0 = 42; main = f 1;" Inference "non-exhaustive"
  , rejects "Boolean coverage"
      "f true = 42; main = f false;" Inference "non-exhaustive"
  , rejects "mixed literal types"
      "f 0 = 1; f \"zero\" = 2; f _ = 3; main = f 0;" Inference "mixed literal"
  , rejects "nested case duplicate binder"
      "data Pair a b = Pair a b; case Pair 1 (Pair 2 3) of { Pair x (Pair x y) -> y }" Inference "duplicate pattern variable"
  , rejects "constructor arity in function pattern"
      "data Pair a b = Pair a b; f (Pair x) = x; main = f (Pair 1 2);" Inference "pattern arity mismatch"
  , rejects "pattern variable cannot escape an equation"
      "data Maybe a = Nothing | Just a; f (Just x) = x; f Nothing = x; main = f (Just 1);" Inference "unbound variable: x"
  , rejects "empty implicit do"
      "main = do\nother = 42\n" Parsing ""
  , rejects "dedent closes do before application"
      "main = do\n  printInt 1\n printInt 2\n" Inference "type constructor mismatch"
  ] ++
  [("readability checking: " ++ label, do
      result <- checked source
      require (T.alphaEq (inferredType result) (T.Con "IO" [T.Con "Unit" []])) (sourceType result))
    | (label,source,_,_) <- readabilityPrograms]
  where
    containsRec e = case e of
      X.ELetRec _ _ -> True
      X.EAbs _ b -> containsRec b
      X.EApp a b -> containsRec a || containsRec b
      X.ELet _ a b -> containsRec a || containsRec b
      X.ECase a bs -> containsRec a || any (\(X.ErasedAlternative _ b) -> containsRec b) bs
      _ -> False

-- These fixtures are executed through the shared interpreter/LLVM matrix.
readabilityPrograms :: [(String,String,[String],String)]
readabilityPrograms =
  [ ("readability: factorial equations", unlines
      ["fact : Int -> Int", "fact 0 = 1", "fact n = n * fact (n - 1)",
       "main = do", "  printInt (fact 0)", "  printInt (fact 6)"], [], "1\n720\n")
  , ("readability: mutual recursion", unlines
      ["even : Int -> Bool", "even 0 = true", "even n = odd (n - 1)",
       "odd : Int -> Bool", "odd 0 = false", "odd n = even (n - 1)",
       "main = do", "  printInt (if even 20 then 1 else 0)", "  printInt (if odd 21 then 1 else 0)"], [], "1\n1\n")
  , ("readability: recursive IO and do-local recursion", unlines
      ["main = do", "  let rec", "    count : Int -> IO Unit", "    count 0 = putStrLn \"done\"",
       "    count n = do", "      printInt n", "      count (n - 1)", "  count 3"], [], "3\n2\n1\ndone\n")
  , ("readability: qualified recursive function", unlines
      ["repeat : forall (m : * -> *) a. Monad m => Int -> m a -> m a",
       "repeat 0 action = action", "repeat n action = do", "  action", "  repeat (n - 1) action",
       "main = repeat 2 (putStrLn \"again\")"], [], "again\nagain\nagain\n")
  , ("readability: polymorphic recursion", unlines
      ["data Nest a = Leaf a | Step (Nest (Nest a))",
       "depth : forall a. Nest a -> Int", "depth (Leaf _) = 0", "depth (Step x) = 1 + depth x",
       "main = printInt (depth (Step (Step (Leaf (Leaf (Leaf true))))))"], [], "2\n")
  , ("readability: cyclic lazy value", unlines
      ["data List a = Nil | Cons a (List a)", "ones : List Int", "ones = Cons 1 ones",
       "prefix : Int -> List Int -> Int", "prefix 0 _ = 0", "prefix n Nil = 0",
       "prefix n (Cons x xs) = x + prefix (n - 1) xs", "main = printInt (prefix 100 ones)"], [], "100\n")
  , ("readability: nested patterns and fallback", unlines
      ["data Maybe a = Nothing | Just a", "data Pair a b = Pair a b",
       "pick (Pair (Just x) (Just y)) = x + y", "pick (Pair (Just x) _) = x", "pick _ = 0",
       "main = do", "  printInt (pick (Pair (Just 20) (Just 22)))",
       "  printInt (pick (Pair (Just 7) Nothing))", "  printInt (pick (Pair Nothing (Just 9)))"], [], "42\n7\n0\n")
  , ("readability: constructor equation order keeps wildcard lazy", unlines
      ["data Box = Box Int", "data Choice = Stop | Go", "spin : Box", "spin = spin",
       "select _ Stop = 42", "select (Box x) Go = x", "main = do",
       "  printInt (select spin Stop)", "  printInt (select (Box 7) Go)"], [], "42\n7\n")
  , ("readability: nested lambda and do patterns", unlines
      ["data Pair a b = Pair a b", "main = do", "  Pair x (Pair y z) <- return (Pair 10 (Pair 20 12))",
       "  printInt ((\\(Pair a (Pair b c)) -> a + b + c) (Pair x (Pair y z)))"], [], "42\n")
  , ("readability: pattern annotation imports the prelude", unlines
      ["main = case (\\x -> x) of",
       "  (f : forall (m : * -> *) a. Monad m => m a -> m a) -> ioBind (f (ioReturn 42)) printInt"], [], "42\n")
  , ("readability: pattern temporary hygiene", unlines
      ["data Box = Box Int", "matchValue0 = 40", "doValue0 = 1", "readBox (Box x) = x + matchValue0",
       "main = do", "  Box n <- return (Box 1)", "  printInt (readBox (Box n) + doValue0)"], [], "42\n")
  , ("readability: literal patterns", unlines
      ["command \"yes\" = 1", "command \"no\" = 0", "command _ = -1",
       "sign (-1) = \"negative one\"", "sign 0 = \"zero\"", "sign _ = \"other\"",
       "main = do", "  printInt (command \"yes\")", "  printInt (command \"maybe\")",
       "  putStrLn (sign (-1))", "  putStrLn (sign 0)", "  putStrLn (sign 2)"], [], "1\n-1\nnegative one\nzero\nother\n")
  , ("readability: literal case order and wildcard laziness", unlines
      ["spin : Int", "spin = spin", "first _ false = 7", "first 0 true = 0", "first _ true = 1",
       "main = do", "  printInt (first spin false)", "  printInt (case 2 of", "    1 -> 10",
       "    2 -> 20", "    _ -> 30)"], [], "7\n20\n")
  , ("readability: instance equations", unlines
      ["data Flag = Off | On", "class Render a where", "  render : a -> String",
       "instance Render Flag where", "  render Off = \"off\"", "  render On = \"on\"",
       "main = do", "  putStrLn (render Off)", "  putStrLn (render On)"], [], "off\non\n")
  , ("readability: nested conditional IO layout", unlines
      ["main = do", "  line <- getLine", "  if eqString line \"yes\" then do", "    putStrLn \"selected\"",
       "    printInt 42", "  else do", "    putStrLn \"other\"", "  putStrLn \"done\""], ["yes"], "selected\n42\ndone\n")
  , ("readability: local equation group", unlines
      ["data Maybe a = Nothing | Just a", "main = let", "  value Nothing = 0", "  value (Just x) = x",
       " in printInt (value (Just 42))"], [], "42\n")
  ]
