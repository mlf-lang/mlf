module Main (main) where

import Control.Exception (SomeException, displayException, try)
import Control.Monad (forM, forM_, unless, when)
import Data.List (isInfixOf, nub)
import qualified Data.Set as Set
import System.Exit (exitFailure)
import Figure12
import MLF.Compiler
import qualified MLF.X.Check as Check
import qualified MLF.X.Parser as Parser
import MLF.X.Pretty (prettyTerm, prettyType)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

require :: Bool -> String -> IO ()
require ok reason = unless ok (fail reason)

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

checkOutput :: Compilation -> IO ()
checkOutput result = do
  -- A source-inference success is insufficient: persistable output must
  -- survive printing, parsing, and the independent target checker.
  parsed <- right (Parser.parseTerm "<Figure 12 xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (Check.checkClosed parsed)
  require (T.alphaEq ty (inferredType result)) "xMLF round trip changed its type"
  require (X.erase parsed == X.erase (compiledTerm result)) "xMLF round trip changed erasure"

testCase :: Case -> IO String
testCase c = do
  source <- right (program c)
  case compile ("<Figure 12 " ++ caseId c ++ ">") source of
    Left err -> do
      require (not (expectedAcceptance c)) ("expected acceptance, got " ++ show err)
      require (phase err == Inference) ("not a typing rejection: " ++ show err)
      -- A missing assumption or broken graph is not an expected negative.
      let protectedVariable = caseId c `elem` ["A8", "E1a"]
          reason = if protectedVariable then "cannot raise a protected type variable"
                   else "type constructor mismatch:"
      require (reason `isInfixOf` diagnostic err) ("unexpected rejection reason: " ++ show err)
      when (not protectedVariable) $
        require (all (`isInfixOf` diagnostic err) ["Con \"Bool\" []", "Con \"Int\" []"])
                ("expected an Int/Bool conflict: " ++ show err)
      pure ("rejected (" ++ show err ++ ")")
    Right result -> do
      require (expectedAcceptance c) ("expected rejection, got " ++ prettyType (inferredType result))
      checkOutput result
      pure "accepted; xMLF round trip checked"

typed :: String -> T.Type -> IO String
typed source expected = do
  result <- right (compile "<Figure 12 type assertion>" source)
  checkOutput result
  require (T.alphaEq (inferredType result) expected)
          ("expected " ++ prettyType expected ++ ", got " ++ prettyType (inferredType result))
  pure (prettyType (inferredType result))

identity :: T.Type
identity = T.Forall (T.TyVar 0) T.Bot (T.Arrow (T.Var (T.TyVar 0)) (T.Var (T.TyVar 0)))

typeChecks :: [(String, IO String)]
typeChecks =
  [ ("A1 principal type", typed "\\x y -> y"
      (T.Forall (T.TyVar 1) T.Bot (T.Forall (T.TyVar 2) identity
        (T.Arrow (T.Var (T.TyVar 1)) (T.Var (T.TyVar 2))))))
  , ("A2 principal type", typed
      "let choose = ((\\x y -> x) : forall a. a -> a -> a) in let id = \\x -> x in choose id"
      (T.Forall (T.TyVar 1) identity (T.Arrow (T.Var (T.TyVar 1)) (T.Var (T.TyVar 1)))))
  -- Figure 12 writes the System F instance. The compiler retains a flexible
  -- result bound for the unannotated result, so these are two separate checks,
  -- not a claim that its xMLF type is alpha-equal to the paper's notation.
  , ("A4 inferred result bound", typed "\\(x : forall a. a -> a) -> x x"
      (T.Forall (T.TyVar 1) identity (T.Arrow identity (T.Var (T.TyVar 1)))))
  , ("A4 admits paper signature", typed
      "(\\(x : forall a. a -> a) -> x x) : (forall a. a -> a) -> (forall a. a -> a)"
      (T.Arrow identity identity))
  ]

runTest :: (String, IO String) -> IO Bool
runTest (label, action) = do
  outcome <- try action :: IO (Either SomeException String)
  case outcome of
    Left err -> putStrLn ("FAIL " ++ label ++ "\n  " ++ displayException err) >> pure False
    Right result -> putStrLn ("PASS " ++ label ++ "  " ++ result) >> pure True

main :: IO ()
main = do
  -- Guard against accidentally dropping a row or an expression separated by
  -- a semicolon in the paper. Repeated expressions retain their row labels.
  let rows = Set.fromList (map (takeWhile (/= '.') . caseId) cases)
      expectedRows = Set.fromList
        (["A" ++ show i | i <- [1 :: Int .. 13]] ++
         ["B" ++ show i | i <- [1 :: Int .. 7]] ++
         ["C1a", "C1b", "C1c", "C2"] ++
         ["E" ++ show i ++ suffix | i <- [1 :: Int .. 5], suffix <- ["a", "b"]])
  require (rows == expectedRows) "Figure 12 row coverage changed"
  require (length cases == 43 && length (nub (map caseId cases)) == 43)
          "Figure 12 expression coverage changed"
  require (map caseId (filter (not . paperAcceptance) cases) == ["A11", "C1a", "C1c", "E1a"])
          "MLF paper rejection expectations changed"
  require (map caseId (filter (not . expectedAcceptance) cases) == ["A8", "A11", "C1a", "C1c", "E1a"])
          "Explicit-signature regression expectations changed"
  let discrepancies = filter (\c -> paperAcceptance c /= expectedAcceptance c) cases
  require (map caseId discrepancies == ["A8"]) "Figure 12 discrepancies changed"
  ss <- nub . concat <$> right (mapM assumptions cases)
  -- Verify each signature can be introduced and used on its own. These
  -- controls prevent an invalid prelude from masquerading as a table result.
  controls <- forM ss $ \(x,s) -> runTest ("assumption " ++ x ++ " : " ++ s, do
    result <- right (compile "<signature control>" ("\\(" ++ x ++ " : " ++ s ++ ") -> " ++ x))
    checkOutput result
    pure "checked")
  types <- mapM runTest typeChecks
  -- A tuple with inconsistent uses is repairable with the explicit parameter
  -- annotation required by MLF. No such annotation is inserted in table cases.
  repairs <- forM ["A11", "C1a", "C1c"] $ \label -> do
    c <- case filter ((== label) . caseId) cases of
      [found] -> pure found
      _ -> fail ("missing negative case " ++ label)
    let annotated = case label of
          "A11" -> "k (\\(f : forall a. a -> a) -> pair (f 1) (f True)) xs"
          "C1a" -> "\\(f : forall a. a -> a) -> pair (f 1) (f True)"
          _ -> "g (\\(f : forall a. a -> a) -> pair (f 1) (f True))"
    runTest (label ++ " explicit annotation control",
      testCase c { expression = annotated, expectedAcceptance = True })
  putStrLn "Figure 12: 34 rows / 43 expressions; explicit-signature regression expectations"
  forM_ discrepancies $ \c ->
    putStrLn ("NOTE " ++ caseId c ++ ": the MLF column says accept; the explicit signature is expected to reject (also rejected by camlf)")
  outcomes <- mapM (\c -> runTest (caseId c ++ "  " ++ expression c, testCase c)) cases
  let failures = length (filter not outcomes)
      support = controls ++ types ++ repairs
      supportFailures = length (filter not support)
  putStrLn (show (length cases - failures) ++ "/43 expressions match regression expectations; " ++ show failures ++ " failure(s)")
  putStrLn (show (length support) ++ " supplementary checks; " ++ show supportFailures ++ " failures")
  when (failures /= 0 || supportFailures /= 0) exitFailure
