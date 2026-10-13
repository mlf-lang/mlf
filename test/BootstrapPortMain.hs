-- Every executable MLF port fixture runs through both implementations of the
-- shared backend harness. Fixed outputs are assertions, not snapshots updated
-- by the test. Independent Haskell references guard the larger corpora.
module Main (main) where

import Control.Exception (SomeException, displayException, try)
import Control.Monad (forM, unless, when)
import qualified Data.ByteString as BS
import Data.List (find, intercalate, nub)
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import System.Environment (getArgs)
import System.Exit (ExitCode (..), exitFailure)
import System.IO (BufferMode (LineBuffering), hSetBuffering, stdout)
import System.Process (readProcessWithExitCode)
import System.Timeout (timeout)
import Backends
import MLF.Compiler
import qualified MLF.Data as D
import qualified MLF.Primitive as P
import qualified MLF.X.Check as Check
import qualified MLF.X.Parser as Parser
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

data Fixture = Fixture String (Maybe FilePath)

fixtures :: [Fixture]
fixtures =
  [ Fixture "foundation" Nothing
  , Fixture "MapFolds" Nothing
  , Fixture "IntegerContainers" Nothing
  , Fixture "OptimizerQueries" Nothing
  , Fixture "ConstructorProjection" Nothing
  , Fixture "ForceReuse" Nothing
  , Fixture "StrictFields" Nothing
  , Fixture "prelude" Nothing
  , Fixture "Target" Nothing
  , Fixture "frontend" Nothing
  , Fixture "LexerCounters" Nothing
  , Fixture "LLVMBuild" Nothing
  , Fixture "RuntimeSmoke" Nothing
  , Fixture "RuntimeCases" Nothing
  , Fixture "StateRuntime" Nothing
  , Fixture "StateTypes" Nothing
  , Fixture "GraphConformance" (Just "GraphReference.hs")
  , Fixture "GraphScopes" (Just "GraphScopesReference.hs")
  , Fixture "GraphDense" (Just "GraphDenseReference.hs")
  , Fixture "OrderedTraversal" (Just "OrderedTraversalReference.hs")
  , Fixture "SolverReuse" Nothing
  , Fixture "TypeCache" Nothing
  , Fixture "GraphStack" Nothing
  , Fixture "EmbeddingPruning" (Just "EmbeddingPruningReference.hs")
  , Fixture "InferenceConformance" (Just "InferenceReference.hs")
  , Fixture "PrimitiveMetadata" Nothing
  ]

fixtureName :: Fixture -> String
fixtureName (Fixture name _) = name

selectFixtures :: [String] -> IO [Fixture]
selectFixtures [] = pure fixtures
selectFixtures ("--only":names)
  | null names = fail "--only requires at least one fixture name"
  | length names /= length (nub names) = fail "--only contains duplicate fixture names"
  | otherwise = forM names $ \name -> case find ((== name) . fixtureName) fixtures of
      Just fixture -> pure fixture
      Nothing -> fail ("unknown fixture " ++ show name ++ "; available: " ++ intercalate ", " (map fixtureName fixtures))
selectFixtures _ = fail "usage: bootstrap-port-tests [--only FIXTURE ...]"

main :: IO ()
main = do
  hSetBuffering stdout LineBuffering
  arguments <- getArgs
  selected <- selectFixtures arguments
  unless (null arguments) $ putStrLn ("Explicit fixture selection: " ++ intercalate ", " (map fixtureName selected))
  withBackends $ \backends -> do
    outcomes <- forM selected $ \fixture@(Fixture name _) ->
      inCase backends ("MLF compiler port: " ++ name) $ do
        result <- try (runFixture backends fixture) :: IO (Either SomeException ())
        case result of
          Left err -> putStrLn ("FAIL " ++ name ++ "\n  " ++ displayException err) >> pure False
          Right () -> putStrLn ("PASS " ++ name) >> pure True
    coverage <- try (auditBackends backends) :: IO (Either SomeException ())
    case coverage of
      Left err -> putStrLn ("FAIL backend coverage\n  " ++ displayException err)
      Right () -> pure ()
    let failed = length (filter not outcomes) + either (const 1) (const 0) coverage
    putStrLn (show (length selected) ++ " MLF port fixtures; " ++ show failed ++ " failures")
    when (failed /= 0) exitFailure

runFixture :: Backends -> Fixture -> IO ()
runFixture backends (Fixture name reference) = do
  let source = "bootstrap/tests/" ++ name ++ ".emlf"
  expected <- if name == "PrimitiveMetadata" then pure primitiveMetadata
    else BS.readFile ("bootstrap/tests/" ++ name ++ ".expected")
  unless (not (BS.null expected)) (fail (name ++ ": empty expectation cannot demonstrate coverage"))
  case reference of
    Nothing -> pure ()
    Just file -> do
      putStrLn ("ORACLE " ++ name)
      oracle <- referenceOutput file []
      unless (oracle == expected) (fail (name ++ ": independent reference changed; review fixed expectations"))
      when (name == "InferenceConformance") $ do
        generated <- referenceOutput file ["--generate"]
        original <- BS.readFile source
        unless (generated == original) (fail "InferenceConformance source differs from independently generated inputs")
        unless (Text.encodeUtf8 (Text.pack "Fig12-A8\tREJECT Inference\n") `BS.isInfixOf` expected)
          (fail "inference corpus lost Figure 12 A8 rejection")
  putStrLn ("CHECK " ++ name ++ " source and target")
  compilation <- compileFile ["bootstrap"] source >>= either (fail . show) pure
  ty <- either fail pure (Check.checkClosed (compiledTerm compilation))
  unless (T.alphaEq ty (inferredType compilation)) (fail (name ++ ": target type differs from inferred type"))
  parsed <- either fail pure (Parser.parseTerm source (prettyTerm (compiledTerm compilation)))
  parsedType <- either fail pure (Check.checkClosed parsed)
  unless (T.alphaEq parsedType ty && X.erase parsed == X.erase (compiledTerm compilation))
    (fail (name ++ ": checked target serialization changed type or erasure"))
  let seconds = if name `elem` ["GraphConformance","GraphDense","InferenceConformance","SolverReuse","StateTypes"] then 1800 else 60
      context = withExecutionTimeout seconds backends
  putStrLn ("RUN " ++ name ++ " on both backends (" ++ show seconds ++ "s execution bound)")
  observed <- execute context IOEntry (Input "" False) parsed
  either (fail . show) pure (outcome observed)
  unless (outputBytes observed == expected)
    (fail (name ++ ": unexpected output at byte " ++ show (mismatch expected (outputBytes observed)) ++
      "; expected length " ++ show (BS.length expected) ++ ", actual " ++ show (BS.length (outputBytes observed))))
  unless (null (stderrOutput observed) && null (remaining observed))
    (fail (name ++ ": unexpected stderr or remaining input"))

referenceOutput :: FilePath -> [String] -> IO BS.ByteString
referenceOutput file arguments = do
  result <- timeout 60000000
    (readProcessWithExitCode "runghc" (["-isrc","-itest","bootstrap/tests/" ++ file] ++ arguments) "")
  case result of
    Nothing -> fail (file ++ ": independent reference timed out")
    Just (ExitSuccess,text,errors) -> do
      unless (null errors) (fail (file ++ ": reference emitted diagnostics: " ++ errors))
      pure (Text.encodeUtf8 (Text.pack text))
    Just (status,text,errors) -> fail (file ++ ": reference failed " ++ show status ++ "\n" ++ text ++ errors)

primitiveMetadata :: BS.ByteString
primitiveMetadata = Text.encodeUtf8 (Text.pack (unlines (map row [minBound .. maxBound])))
  where
    row primitive =
      let (variables,field) = P.primitiveSignature primitive in
      show (fromEnum primitive) ++ "\t" ++ P.primitiveName primitive ++ "\t" ++
      show (P.primitiveArity primitive) ++ "\t" ++
      (if P.primitiveStrict primitive then "strict" else "lazy") ++ "\t" ++
      D.prettyDeclaration (D.DataDeclK "Sig" variables [D.ConstructorDecl "M" [field]])

mismatch :: BS.ByteString -> BS.ByteString -> Int
mismatch expected actual = length (takeWhile (uncurry (==)) (BS.zip expected actual))
