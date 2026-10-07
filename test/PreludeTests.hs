module PreludeTests (preludeTests) where

import Control.Monad (forM_, unless)
import Data.List (isInfixOf)
import Backends (Backends, Event (..))
import qualified Backends as B
import MLF.Compiler
import MLF.Parser (parseExpr, parseProgram)
import qualified MLF.X.Check as C
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

type Test = (String, IO ())

require :: Bool -> String -> IO ()
require condition message = unless condition (fail message)

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

checked :: String -> IO Compilation
checked source = do
  result <- right (compile "<prelude>" source)
  parsed <- right (XP.parseTerm "<prelude xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (C.checkClosed parsed)
  require (T.alphaEq ty (inferredType result)) "prelude xMLF changed type"
  require (X.erase parsed == X.erase (compiledTerm result)) "prelude xMLF changed erasure"
  pure result

hasType :: String -> String -> T.Type -> Test
hasType label source ty = ("prelude: " ++ label, do
  result <- checked source
  require (T.alphaEq ty (inferredType result)) (sourceType result))

rejects :: String -> String -> Phase -> String -> Test
rejects label source expectedPhase reason = ("prelude rejection: " ++ label,
  case compile "<invalid prelude use>" source of
    Left err -> require (phase err == expectedPhase && reason `isInfixOf` diagnostic err) (show err)
    Right result -> fail ("unexpected acceptance: " ++ sourceType result))

runsOn :: Backends -> String -> String -> [String] -> String -> Test
runsOn backends label source inputs expected = ("prelude runtime: " ++ label, do
  result <- checked source
  term <- right (XP.parseTerm "<prelude runtime>" (prettyTerm (compiledTerm result)))
  (outcome,trace) <- B.capture backends term inputs
  right outcome
  let actual = concat [text | Write text <- trace]
  require (actual == expected) (show actual))

int, bool :: T.Type
int = T.Con "Int" []
bool = T.Con "Bool" []

maybeDecl, maybeInstance, twice, explicitMonad :: String
maybeDecl = "data Maybe a = Nothing | Just a; "
maybeInstance = "instance Monad Maybe where { return = Just; " ++
  "bind = \\value next -> case value of { Nothing -> Nothing; Just x -> next x } }; "
twice = "let twice : forall (m : * -> *) a. Monad m => m a -> m a = " ++
  "\\action -> do { action; value <- action; return value } in "
explicitMonad = "class Monad (m : * -> *) where { return : forall a. a -> m a; " ++
  "bind : forall a b. m a -> (a -> m b) -> m b }; "

preludeTests :: Backends -> [Test]
preludeTests backends =
  [ runs "IO sequencing without declarations"
      "do { putStr \"Name: \"; line <- getLine; putStrLn line }" ["Ada"] "Name: Ada\n"
  , runs "qualified generic IO function" (twice ++ "twice (putStrLn \"again\")") [] "again\nagain\n"
  , runs "one generic function at IO and a user instance"
      (maybeDecl ++ maybeInstance ++ twice ++
       "do { twice (putStrLn \"twice\"); case twice (Just 42) of { Nothing -> printInt 0; Just n -> printInt n } }")
      [] "twice\ntwice\n42\n"
  , hasType "user Monad instance needs no class declaration"
      (maybeDecl ++ maybeInstance ++ "do { x <- Just 42; return x }") (T.Con "Maybe" [int])
  , hasType "inferred constraints use the imported methods"
      (maybeDecl ++ maybeInstance ++ "let roundTrip = \\value -> bind value return in roundTrip (Just 42)")
      (T.Con "Maybe" [int])
  , hasType "qualified annotation alone imports the class"
      "let identityM : forall (m : * -> *) a. Monad m => m a -> m a = \\x -> x in identityM (ioReturn 42)"
      (T.Con "IO" [int])
  , hasType "superclass alone imports Monad"
      "class Monad m => Marker (m : * -> *) where { mark : forall a. m a -> m a }; true" bool
  , hasType "instance context alone imports Monad"
      ("data Wrapped (m : * -> *) a = Wrapped (m a); " ++
       "class Tag (m : * -> *) where { tag : forall a. m a -> Bool }; " ++
       "instance forall (m : * -> *). Monad m => Tag (Wrapped m) where { tag = \\x -> true }; true") bool
  , runs "prelude implementation uses primitive identities"
      ("class Hijack a where { ioReturn : a -> IO a }; " ++
       "instance Hijack Int where { ioReturn = \\x -> do { printInt 0; pure x } }; " ++
       "do { x <- return 42; printInt x }") [] "42\n"
  , runs "given dictionary and lexical shadowing coexist"
      (twice ++ "let return = \\x -> x in do { twice (putStrLn \"ok\"); printInt (return 42) }")
      [] "ok\nok\n42\n"
  , runs "local class method shadows only the imported method"
      ("class Keep a where { return : a -> a }; instance Keep Int where { return = \\x -> x }; " ++
       "do { printInt (return 42); putStrLn \"done\" }") [] "42\ndone\n"
  , rejects "import shadowing does not allow duplicate local methods"
      ("class Keep a where { return : a -> a }; class Other a where { return : a -> a }; " ++
       "do { putStrLn \"one\"; putStrLn \"two\" }") Inference "duplicate class method"
  , hasType "local Monad declaration shadows the imported class"
      "class Monad a where { tag : a -> Bool }; instance Monad Int where { tag = \\x -> true }; tag 42" bool
  , rejects "local Monad also hides imported IO instance"
      (explicitMonad ++ "do { putStrLn \"one\"; putStrLn \"two\" }") Resolution "no instance or given constraint"
  , rejects "duplicate imported instance"
      "instance Monad IO where { return = ioReturn; bind = ioBind }; true" Inference "overlapping instances"
  , rejects "user instance is still checked"
      (maybeDecl ++ "instance Monad Maybe where { return = \\x -> true; bind = \\x f -> x }; true")
      Inference "type constructor mismatch"
  , rejects "missing user instance"
      (maybeDecl ++ "return 42 : Maybe Int") Resolution "no instance or given constraint"
  , rejects "no implicit monad defaulting" "return 42" Resolution "ambiguous uses need a type annotation"
  , ("prelude: every compiler API imports the prelude", do
      let source = "do { putStrLn \"one\"; putStrLn \"two\" }"
      textResult <- checked source
      ast <- right (parseExpr "<prelude AST>" source)
      astResult <- right (compileExpr ast)
      program <- right (parseProgram "<prelude program>" source)
      programResult <- right (compileProgram program)
      forM_ [astResult,programResult] $ \result ->
        require (compiledTerm result == compiledTerm textResult) "compiler entry points disagree")
  , ("prelude: every compiler API supports explicit opt-out", do
      let source = "return 42"
      textResult <- right (compileWithPrelude NoImplicitPrelude "<no prelude>" source)
      ast <- right (parseExpr "<no prelude AST>" source)
      astResult <- right (compileExprWithPrelude NoImplicitPrelude ast)
      program <- right (parseProgram "<no prelude program>" source)
      programResult <- right (compileProgramWithPrelude NoImplicitPrelude program)
      forM_ [textResult,astResult,programResult] $ \result -> do
        require (T.alphaEq (inferredType result) (T.Con "IO" [int])) "opt-out lost primitive IO defaults"
        require (compiledTerm result == compiledTerm textResult) "opt-out entry points disagree")
  , ("prelude: opt-out removes implicit class declarations", do
      case compileWithPrelude NoImplicitPrelude "<no prelude class>" (maybeDecl ++ maybeInstance ++ "Just 42") of
        Left err -> require (phase err == Inference && "unknown class: Monad" `isInfixOf` diagnostic err) (show err)
        Right _ -> fail "Monad was imported despite opt-out")
  ] ++
  [ ("prelude: unused imports preserve " ++ label, do
      ordinary <- checked source
      explicit <- right (compileWithPrelude NoImplicitPrelude "<unused prelude>" source)
      require (compiledTerm ordinary == compiledTerm explicit) "unused prelude changed xMLF"
      require (presolution ordinary == presolution explicit) "unused prelude changed the graph")
  | (label,source) <-
      [ ("pure programs", "let id = \\x -> x in id 42")
      , ("lambda shadowing", "(\\return -> return 42) (\\x -> x)")
      , ("pattern shadowing", "data Box a = Box a; case Box 42 of { Box return -> return }")
      , ("do-let shadowing", "do { let bind = \\x f -> f x; let return = \\x -> x; n <- 42; return n }")
      , ("do-pattern shadowing", "let bind = \\x f -> f x in do { return <- (\\x -> x); return 42 }")
      , ("single-expression do", "do { 42 }")
      , ("unrelated class method", "class Keep a where { return : a -> a }; instance Keep Int where { return = \\x -> x }; return 42")
      ]
  ]
  where runs = runsOn backends
