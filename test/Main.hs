module Main (main) where

import Control.Exception (SomeException, displayException, try)
import Control.Monad (forM, forM_, unless, when)
import Data.List (isInfixOf, sort)
import qualified Data.IntMap.Strict as IM
import System.Directory (listDirectory)
import System.Exit (exitFailure)
import System.IO (BufferMode (LineBuffering), hSetBuffering, stdout)
import MLF.Compiler
import MLF.Constraint
import qualified MLF.Graph as G
import MLF.Parser
import qualified MLF.Syntax as S
import qualified MLF.X.Check as C
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import qualified MLF.X.Parser as XP
import MLF.X.Pretty
import Oracle
import Computations (computationTests, hygieneTests)
import Datatypes (datatypeTests)
import Typeclasses (typeclassTests)
import DoNotation (doTests)
import SurfaceSyntax (surfaceSyntaxTests)
import Readability (readabilityTests)
import Modules (moduleTests)
import Separate (separateTests)
import GraphValidation (graphValidationTests)
import GraphUnification (graphUnificationTests)
import GraphSolver (graphSolverTests)
import EmbeddingPruning (embeddingPruningTests)
import OptimizerQueries (optimizerQueryTests)
import StrictFieldAnalysis (strictFieldAnalysisTests)
import StateTypes (stateTypeTests)

type Test = (String, IO ())

main :: IO ()
main = do
  hSetBuffering stdout LineBuffering
  let suite = compilerTests ++ computationTests ++ hygieneTests ++ graphTests ++ graphValidationTests ++ graphUnificationTests ++ graphSolverTests ++ embeddingPruningTests ++ optimizerQueryTests ++ strictFieldAnalysisTests ++ datatypeTests ++ typeclassTests ++ doTests ++ surfaceSyntaxTests ++ readabilityTests ++
        moduleTests ++ separateTests ++ stateTypeTests ++ [("independent ML typability oracle", oracleTest), ("annotation corpus", annotationCorpus), ("example files", examplesTest)]
  outcomes <- forM suite $ \(label,test) -> do
    outcome <- try test :: IO (Either SomeException ())
    case outcome of
      Left err -> putStrLn ("FAIL " ++ label ++ "\n  " ++ displayException err) >> pure False
      Right () -> pure True
  let failures = length (filter not outcomes)
  putStrLn (show (length suite) ++ " checks; " ++ show failures ++ " failures")
  when (failures /= 0) exitFailure

assert :: Bool -> String -> IO ()
assert p message = unless p (fail message)

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

reject :: Show a => Either e a -> IO ()
reject result = case result of Left _ -> pure (); Right value -> fail ("unexpected success: " ++ show value)

v :: Int -> T.Type
v = T.Var . T.TyVar
allT :: Int -> T.Type -> T.Type -> T.Type
allT = T.Forall . T.TyVar
int, bool, identity, chooseId :: T.Type
int = T.Con "Int" []
bool = T.Con "Bool" []
identity = allT 0 T.Bot (T.Arrow (v 0) (v 0))
chooseId = allT 1 identity (T.Arrow (v 1) (v 1))

choosePrefix :: String
choosePrefix = "let choose = ((\\x y -> x) : forall a. a -> a -> a) in let id = \\x -> x in "

sameType :: T.Type -> T.Type -> IO ()
sameType actual expected = assert (T.alphaEq actual expected)
  ("expected " ++ prettyType expected ++ ", got " ++ prettyType actual)

compileOK :: String -> IO Compilation
compileOK source = do
  result <- right (compile "<test>" source)
  parsed <- right (XP.parseTerm "<generated xMLF>" (prettyTerm (compiledTerm result)))
  assert (X.erase parsed == X.erase (compiledTerm result)) "printed output changed erasure"
  ty <- right (C.checkClosed parsed)
  sameType ty (inferredType result)
  pure result

hasType :: String -> String -> T.Type -> Test
hasType label source ty = (label, compileOK source >>= \r -> sameType (inferredType r) ty)

accepts :: String -> String -> Test
accepts label source = (label, compileOK source >> pure ())

rejects :: String -> String -> Test
rejects label source = (label, case compile "<test>" source of
  Left (CompileError Inference _) -> pure ()
  Left err -> fail ("error at the wrong phase: " ++ show err)
  Right r -> fail ("unexpected type: " ++ prettyType (inferredType r)))

compilerTests :: [Test]
compilerTests =
  [ hasType "identity" "\\x -> x" identity
  , hasType "constant 42" "42" int
  , hasType "boolean" "true" bool
  , hasType "identity self-application" "(\\x -> x) (\\y -> y)" identity
  , hasType "let polymorphism" "let id = \\x -> x in let number = id 42 in id true" bool
  , hasType "lambda scope is not generalized" "\\x -> let y = x in y" identity
  , hasType "lexical shadowing" "let x = true in (\\x -> x) 42" int
  , hasType "let RHS sees outer binding" "let x = true in let x = x in x" bool
  , hasType "application under an unannotated lambda" "\\f x -> f x"
      (allT 0 T.Bot (allT 1 T.Bot (T.Arrow (T.Arrow (v 0) (v 1)) (T.Arrow (v 0) (v 1)))))
  , hasType "K preserves its polymorphic return bound" "\\x y -> x"
      (allT 0 T.Bot (allT 1 (allT 2 T.Bot (T.Arrow (v 2) (v 0))) (T.Arrow (v 0) (v 1))))
  , hasType "choose id retains an MLF bound" (choosePrefix ++ "choose id") chooseId
  , hasType "g g" (choosePrefix ++ "let g = choose id in g g") chooseId
  , hasType "g g applied to identity" (choosePrefix ++ "let g = choose id in g g id 42") int
  , rejects "g g retains its identity lower bound" (choosePrefix ++ "let g = choose id in g g 42")
  , hasType "closed annotation" "(\\x -> x) : forall a. a -> a" identity
  , hasType "let annotation" "let id : forall a. a -> a = \\x -> x in id" identity
  , hasType "bounded annotation" "(\\x -> x) : forall (a >= forall b. b -> b). a -> a" chooseId
  , hasType "annotated self-application" "\\(f : forall a. a -> a) -> f f"
      (allT 1 identity (T.Arrow identity (v 1)))
  , hasType "polymorphic parameter at distinct instances"
      "(\\(f : forall a. a -> a) -> let a = f 42 in f true) (\\x -> x)" bool
  , hasType "impredicative result"
      "(\\(f : forall a. a -> a) -> f f) (\\x -> x)" identity
  , hasType "partial annotation"
      "((\\x -> \\y -> y) : exists a. a -> (forall b. b -> b)) 42" identity
  , hasType "existential root" "(\\x -> x) : exists a. a" identity
  , hasType "existential annotation shares both sides" "(\\x -> x) : exists a. a -> a" identity
  , hasType "alias bounds normalized before xMLF"
      "(\\x -> x) : forall a (b >= a). b -> b" identity
  , hasType "inert bounds inlined" "(\\x -> x) : forall (a >= Int). a -> a" (T.Arrow int int)
  , hasType "unused bounds disappear" "(\\x -> x) : forall unused a. a -> a" identity
  , hasType "forall a.a equivalent to its bound"
      "(\\x -> x) : forall (a >= forall b. b -> b). a" identity
  , hasType "annotation alpha-renaming" "(\\x -> x) : forall z. z -> z" identity
  , hasType "parameterized type constructor"
      "(\\x -> x) : forall a. List a -> List a"
      (allT 0 T.Bot (T.Arrow (T.Con "List" [v 0]) (T.Con "List" [v 0])))
  , accepts "rigid polymorphic bound"
      "(\\x -> x) : forall (a = forall b. b -> b). a -> a"
  , accepts "multiple quantified variables" "(\\x y -> x) : forall a b. a -> b -> a"
  , accepts "shared type has independent lexical binders"
      "let id = let id = \\x -> x in id in \\ignored -> (\\x y -> x) (\\x -> true)"
  , accepts "arbitrary-rank annotation"
      "\\(f : ((forall a. a -> a) -> Int) -> Int) -> f (\\(id : forall a. a -> a) -> id 42)"
  , rejects "unannotated self-application" "\\x -> x x"
  , rejects "inconsistent monomorphic argument" "\\f -> let a = f 42 in f true"
  , rejects "integer is not a function" "42 true"
  , rejects "cannot satisfy universal identity with an integer result" "(\\x -> 42) : forall a. a -> a"
  , rejects "distinct skolems cannot merge" "(\\x -> x) : forall a b. a -> b"
  , rejects "wrong closed annotation" "42 : Bool"
  , rejects "cannot invent a polymorphic value" "42 : forall a. a"
  , rejects "free source variable" "missing"
  , rejects "recursive let is not implicit" "let x = x in x"
  , rejects "type annotation has a free variable" "(\\x -> x) : a -> a"
  , rejects "constructor arity" "42 : Int Bool"
  , ("trailing input is rejected", reject (parseExpr "<test>" "42 )"))
  , ("parser handles nested comments", do
      r <- compileOK "{- outer {- inner -} -} let id = \\x -> x in -- a comment\n id 42"
      sameType (inferredType r) int)
  , ("generated computations are necessary", do
      r <- compileOK "(\\x -> x) 42"
      reject (C.checkClosed (stripComputations (compiledTerm r))))
  ]

graphTests :: [Test]
graphTests =
  [ ("expansion resets scheme flag and binding", do
      c <- right (parseExpr "<test>" "\\x -> x" >>= generate)
      g <- right (solve c)
      let gen = generalization (skeleton c)
          s = G.genRoot g gen
      ((r,_,es),expanded) <- right (G.runBuild g (G.expand gen gen))
      assert (G.flag (G.nodeAt g s) == S.Rigid) "scheme root not normalized"
      assert (G.flag (G.nodeAt expanded r) == S.Flexible) "flag was not reset"
      assert (null es) "closed identity has a frontier"
      let locals = [n | (n,vn) <- IM.toList (G.nodes expanded), G.binder vn == Just r]
      assert (length locals == 1) "generalized variable was not rebound to expansion root")
  , ("all inert nodes normalized", do
      r <- compileOK "\\f x -> f x"
      let g = presolution r
      forM_ (IM.toList (G.nodes g)) $ \(n,vn) -> case G.tag vn of
        G.Gen _ -> pure ()
        _ -> when (G.inert g n) (assert (G.flag vn == S.Rigid) "inert flexible node escaped"))
  , ("well-domination enforced", do
      let g = G.Graph (IM.fromList
            [(0,G.Node (G.Gen 1) Nothing S.Flexible)
            ,(1,G.Node (G.Arr 2 3) (Just 0) S.Rigid)
            ,(2,G.Node (G.Arr 3 3) (Just 1) S.Rigid)
            ,(3,G.Node G.Bot (Just 2) S.Flexible)]) IM.empty 4
      reject (G.validateGraph g))
  ]

oracleTest :: IO ()
oracleTest = do
  let terms = closedTerms 6 ++ generatedTerms 5000
      typed = length (filter hmTypable terms)
  assert (typed > 100 && typed < length terms) "oracle corpus lacks positive or negative cases"
  forM_ (zip [(1 :: Int)..] terms) $ \(i,e) -> case compileExpr e of
    Right _ -> assert (hmTypable e) ("accepted non-ML term " ++ show i ++ ": " ++ show e)
    Left err -> do
      assert (phase err == Inference) ("compiler failure on " ++ show e ++ ": " ++ show err)
      assert (not (hmTypable e)) ("rejected ML term " ++ show i ++ ": " ++ show e ++ "\n" ++ show err)
  putStrLn ("Oracle: " ++ show (length terms) ++ " closed terms (exhaustive through size 6, plus 5000 seeded terms); " ++ show typed ++ " typable")

annotationCorpus :: IO ()
annotationCorpus = do
  let identityExpr = S.Lam "x" Nothing (S.Var "x")
      identityType = S.Forall S.Flexible "a" S.Bottom (S.Arrow (S.TVar "a") (S.TVar "a"))
      types = [S.Bottom, S.Con "Int" [], S.Con "Bool" [], identityType,
               S.Forall S.Flexible "a" S.Bottom (S.Con "List" [S.TVar "a"]),
               S.Forall S.Flexible "a" identityType (S.Arrow (S.TVar "a") (S.TVar "a"))]
      nested = types ++ [S.Arrow a b | a <- types, b <- types]
      programs = concat
        [ [ S.Ann identityExpr (S.Annotation [] (S.Arrow t t))
          , S.Lam "x" (Just (S.Annotation [] t)) (S.Var "x")
          , S.Let "f" (S.Ann identityExpr (S.Annotation [] (S.Arrow t t))) (S.Var "f")
          ] | t <- nested ]
  forM_ programs $ \e -> case compileExpr e of
    Left err -> fail ("failed annotated identity " ++ show e ++ "\n" ++ show err)
    Right r -> do
      parsed <- right (XP.parseTerm "<annotation xMLF>" (prettyTerm (compiledTerm r)))
      ty <- right (C.checkClosed parsed)
      sameType ty (inferredType r)
  putStrLn ("Annotations: " ++ show (length programs) ++ " typed programs")

examplesTest :: IO ()
examplesTest = do
  files <- sort . filter (".emlf" `isInfixOf`) <$> listDirectory "examples"
  assert (length files >= 6) "example files are missing"
  forM_ files $ \file -> readFile ("examples/" ++ file) >>= compileOK >> pure ()

stripComputations :: X.Term -> X.Term
stripComputations t = case t of
  X.TypeApp a _ -> stripComputations a
  X.Abs n ty b -> X.Abs n ty (stripComputations b)
  X.App a b -> X.App (stripComputations a) (stripComputations b)
  X.TypeAbs a ty b -> X.TypeAbs a ty (stripComputations b)
  X.Let n a b -> X.Let n (stripComputations a) (stripComputations b)
  X.LetRec ds b -> X.LetRec [(n,ty,stripComputations a) | (n,ty,a) <- ds] (stripComputations b)
  X.WithData ds b -> X.WithData ds (stripComputations b)
  X.Case a ty bs -> X.Case (stripComputations a) ty
    [X.Alternative p (stripComputations b) | X.Alternative p b <- bs]
  _ -> t
