{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import System.IO (hSetBuffering, stdout, BufferMode(LineBuffering))
import qualified Bootstrap.Types as T
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Map as M
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Type as XT
import qualified MLF.Host.Base as B

compile source = C.compile "SourceValueScope.emlf" (B.literal source) >>= \outcome -> pure $ case outcome of
  T.Left e -> Left (B.unpack (C.prettyError e))
  T.Right c -> case Check.checkClosed (C.compiledTerm c) of
    T.Left e -> Left (B.unpack e)
    T.Right _ -> Right c
integer label source expected = do
  putStrLn ("BEGIN " ++ label)
  outcome <- compile source
  case outcome of
    Left e -> error (label ++ ": " ++ e)
    Right c -> case R.prepare False (C.compiledTerm c) of
      T.Left e -> error (B.unpack e)
      T.Right (env,_) -> case R.evaluate env (R.REnv M.empty) (X.erase (C.compiledTerm c)) of
        T.Right (R.RInteger n) | n == expected -> putStrLn ("PASS " ++ label)
        T.Left e -> error (B.unpack e)
        _ -> error (label ++ ": wrong result")
reject label source = do
  putStrLn ("BEGIN " ++ label)
  outcome <- compile source
  case outcome of
    Left _ -> putStrLn ("PASS " ++ label)
    Right _ -> error (label ++ ": unexpectedly accepted")
header = "class C a where { c :: a -> Int };\n"
main = do
  hSetBuffering stdout LineBuffering
  source <- readFile "examples/monad-state-do.emlf"
  putStrLn "BEGIN exact State standalone source"
  outcome <- compile source
  case outcome of
    Left e -> error e
    Right c -> if B.unpack (C.sourceType c) == "Pair Int Int" then putStrLn "PASS exact State standalone source" else error ("State type: " ++ B.unpack (C.sourceType c))
  integer "transitive source kernels close over instance" (header ++ "kernel x = 42;\nhelper = kernel;\ninstance C Int where { c = helper };\nc (0 :: Int)") 42
  integer "source helper shadows facade value" (header ++ "pure x = 42;\ninstance C Int where { c = pure };\nc (0 :: Int)") 42
  integer "instance lambda shadow does not capture source helper" (header ++ "helper x = 42;\ninstance C Int where { c helper = helper };\nc (7 :: Int)") 7
  integer "signed recursive source SCC remains supported" (header ++ "helper :: Int -> Int;\nhelper x = if eqInt x 0 then 42 else helper (subInt x 1);\ninstance C Int where { c = helper };\nc (2 :: Int)") 42
  integer "unsigned recursive source SCC infers and evaluates" (header ++ "helper x = if eqInt x 0 then 42 else helper (subInt x 1);\ninstance C Int where { c = helper };\nc (2 :: Int)") 42
  reject "final-expression let is not instance source scope" (header ++ "instance C Int where { c = hidden };\nlet hidden x = 42 in c (0 :: Int)")

  let rawClass = T.SClassDecl "RawC" [("a",T.Star)] [] [("rawC",T.SArrow (T.STVar "a") (T.SCon "Int" []))]
      rawInstance = T.SInstanceDecl [] [] "RawC" [T.SCon "Int" []] [("rawC",T.SVar "hidden")]
      rawBody = T.SLet "hidden" (T.SLam "x" T.Nothing (T.SIntLit 42)) (T.SApp (T.SVar "rawC") (T.SIntLit 0))
  raw <- C.compileProgram (T.SClassProgram [] [rawClass] [rawInstance] rawBody)
  case raw of
    T.Left _ -> putStrLn "PASS raw body-only let cannot supply instance scope"
    T.Right _ -> error "raw body-only let unexpectedly captured by instance"
  let identity = T.SLam "x" T.Nothing (T.SVar "x")
  plain <- C.compileExpr identity
  marked <- C.compileExpr (T.SSourceDefinition identity)
  case (plain,marked) of
    (T.Right a,T.Right b) | XT.alphaEq (C.inferredType a) (C.inferredType b)
      && X.equalErased (X.erase (C.compiledTerm a)) (X.erase (C.compiledTerm b)) -> putStrLn "PASS source-definition marker preserves ordinary MLF type and erasure"
    _ -> error "ordinary MLF source-definition marker changed inference"
