-- Export deterministic, source-level parity inputs from independent oracles.
-- Build with ghc -O1 -isrc -itest -outputdir <build-dir>
--   bootstrap/ExportCorpus.hs -o <exporter>
-- Run from the repository root: <exporter> <output-directory>
module Main (main) where

import Control.Monad (forM, forM_, unless, when)
import Data.Char (isAlphaNum, ord)
import Data.List (intercalate, isInfixOf, isSuffixOf, nub, sort)
import Numeric (showHex)
import System.Directory
  ( canonicalizePath, createDirectoryIfMissing, doesDirectoryExist
  , listDirectory, copyFile )
import System.Environment (getArgs)
import System.FilePath ((</>), takeDirectory, dropExtension)
import System.IO (IOMode (WriteMode), hSetEncoding, utf8, withFile, hPutStr)
import qualified Figure12
import qualified Oracle
import qualified Readability
import qualified StateCases
import qualified Modules
import MLF.Compiler
import qualified MLF.Module.Syntax as MS
import MLF.Parser (parseExpr, parseModule)
import qualified MLF.Syntax as S
import qualified MLF.Kind as K
import qualified MLF.X.Check as XC
import qualified MLF.X.Parser as XP
import qualified MLF.X.Pretty as XPretty
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as XT

-- Case acceptance is independently specified; the seed is only the type
-- oracle and an additional consistency check. Export fails on disagreement.
data Case = Case
  { caseId :: String
  , category :: String
  , relativeSource :: FilePath
  , label :: String
  , expected :: Bool
  , acceptanceOracle :: String
  , source :: String
  , originalPath :: Maybe FilePath
  , includes :: [FilePath]
  , runtime :: Maybe (String, String)
  , preludeMode :: PreludeMode
  , rejection :: Maybe (Phase, String)
  }

data Exported = Exported Case (Either CompileError Compilation)

main :: IO ()
main = do
  arguments <- getArgs
  output <- case arguments of
    [directory] -> createDirectoryIfMissing True directory >> canonicalizePath directory
    _ -> fail "usage: export-bootstrap-corpus OUTPUT_DIRECTORY (run in repository root)"
  repository <- canonicalizePath "."
  figureCases <- forM Figure12.cases $ \c -> do
    text <- either fail pure (Figure12.program c)
    pure $ simpleCase ("figure12-" ++ Figure12.caseId c) "figure12" (Figure12.caseId c)
      (Figure12.expectedAcceptance c)
      (if Figure12.caseId c == "A8" then "camlf reference rejection; see docs/figure12-a8-reference.txt"
       else "Figure 12 MLF column") text
  let exhaustive = Oracle.closedTerms 6
      generated = Oracle.generatedTerms 5000
      oracleCases = oracleGroup "hm-exhaustive" "Algorithm W; exhaustive closed terms through size 6" exhaustive ++
                    oracleGroup "hm-generated" "Algorithm W; 5000 deterministic seeded terms" generated
      annotationCases =
        [ simpleCase ("annotation-" ++ padded i) "annotations" ("annotation identity " ++ show i)
            True "closed annotated identity construction from test/Main.hs" (prettyExpr term)
        | (i,term) <- zip [1..] annotationTerms ]
      readabilityCases =
        [ (simpleCase ("readability-" ++ padded i) "readability" name True
              "test/Readability.hs prescribed runtime output" text)
              { runtime = Just (unlines input, outputText) }
        | (i,(name,text,input,outputText)) <- zip [1..] Readability.readabilityPrograms ]
      stateTypes =
        [ simpleCase ("state-type-" ++ padded i) "state" name accepts
            "test/StateCases.hs independently prescribed region and element typing" text
        | (i,(name,accepts,text,_)) <- zip [1..] StateCases.stateTypeCases ]
      stateRuntime =
        [ (simpleCase ("state-runtime-" ++ padded i) "state" name True
              "test/StateCases.hs prescribed state semantics and output" text)
              { runtime = Just ("",outputText) }
        | (i,(name,text,outputText)) <- zip [1..] StateCases.stateRuntimeSuccesses ]
      oracleAccepted = length (filter Oracle.hmTypable (exhaustive ++ generated))
      oracleRejected = length exhaustive + length generated - oracleAccepted
  unless (length Figure12.cases == 43) (fail "Figure 12 corpus size changed; inspect expectations")
  unless (length annotationTerms == 126) (fail "annotation corpus must contain 126 constructions")
  unless (length stateTypes == 56 && length stateRuntime == 41)
    (fail "state corpus must retain 56 source type cases and 41 runtime cases")
  unless (oracleAccepted > 100 && oracleRejected > 100) (fail "Algorithm W corpus lacks positive or negative coverage")
  -- The pretty-printer is checked against the original AST before the
  -- independent typability result is associated with a serialized source.
  forM_ (exhaustive ++ generated ++ annotationTerms) $ \term -> do
    parsed <- either fail pure (parseExpr "<corpus-printer>" (prettyExpr term))
    unless (parsed == term) (fail ("corpus source printer changed AST: " ++ show term))
  files <- concat <$> mapM (sourceFiles repository) ["examples", "benchmarks"]
  -- Preserve every module dependency at its original relative location.
  forM_ files $ \file -> do
    let destination = output </> "repository" </> file
    createDirectoryIfMissing True (takeDirectory destination)
    copyFile (repository </> file) destination
  fileCases <- mapM (fileCase repository) files
  moduleCases <- exportModules output
  let cases = figureCases ++ oracleCases ++ annotationCases ++ readabilityCases ++ stateTypes ++ stateRuntime ++ moduleCases ++ fileCases
  unless (length (nub (map caseId cases)) == length cases) (fail "duplicate corpus case identity")
  results <- mapM (exportCase output) cases
  writeUtf8 (output </> "manifest.jsonl") (unlines (map manifestRow results))
  writeUtf8 (output </> "summary.json") $ jsonObject
    [ ("schema_version", "1")
    , ("case_count", show (length results))
    , ("figure12_count", show (length figureCases))
    , ("figure12_a8_expected_accept", "false")
    , ("hm_exhaustive_count", show (length exhaustive))
    , ("hm_generated_count", show (length generated))
    , ("hm_distinct_ast_count", show (length (nub (map show (exhaustive ++ generated)))))
    , ("hm_accepted_count", show oracleAccepted)
    , ("hm_rejected_count", show oracleRejected)
    , ("annotation_count", show (length annotationCases))
    , ("readability_runtime_count", show (length readabilityCases))
    , ("state_type_count", show (length stateTypes))
    , ("state_runtime_count", show (length stateRuntime))
    , ("module_accept_count", show (length Modules.modulePrograms))
    , ("module_reject_count", show (length Modules.moduleRejections))
    , ("repository_source_count", show (length files))
    , ("repository_sources", jsonArray (map jsonString files))
    ] ++ "\n"
  writeUtf8 (output </> "README.txt") $ unlines
    [ "Bootstrap parity corpus schema 1"
    , "Each manifest.jsonl row names a source_path relative to this directory."
    , "Resolve include_dirs relative to this directory before invoking a compiler."
    , "expected_accept is independent for Figure 12, Algorithm W, annotated identities,"
    , "state region typing, and prescribed readability/state fixtures. Repository examples and benchmark workloads"
    , "are expected to compile; a seed disagreement aborts export rather than changing it."
    , "expected_type is the seed's independently checked xMLF type, not an independent"
    , "MLF principal-type oracle. Compare it by xMLF alpha equivalence."
    , "Module fixtures preserve their independent acceptance, rejection phase and diagnostic fragments."
    , "no_prelude is explicit for every case; use --no-prelude when true."
    , "expected_phase is supplied for rejected cases; expected_error_contains checks a prescribed diagnostic fragment."
    , "Runtime rows additionally have expected_stdin and expected_stdout UTF-8 strings."
    , "A library-only source gets a separate import probe; its original file is copied"
    , "unchanged and original_path identifies it. This checks all imported declarations."
    , "HM cases retain the exact enumeration, including repeated seeded ASTs. Summary"
    , "records distinct AST count separately; no test is silently skipped or deduplicated."
    , "The exporter checks source-printer AST equality and seed target round trips."
    ]
  putStrLn ("Exported " ++ show (length results) ++ " cases to " ++ output)
  putStrLn ("HM oracle: " ++ show oracleAccepted ++ " accept, " ++ show oracleRejected ++ " reject")

simpleCase :: String -> String -> String -> Bool -> String -> String -> Case
simpleCase identity group name accepts oracle text = Case identity group
  ("cases" </> group </> identity ++ ".emlf") name accepts oracle text Nothing [] Nothing ImplicitPrelude Nothing

-- Materialize each module graph in its own search root. These are the same
-- prescribed fixtures exercised by the seed tests, including negative lexical
-- scopes and instance visibility; seed acceptance does not define expectations.
exportModules :: FilePath -> IO [Case]
exportModules output = do
  unless (length Modules.modulePrograms == 21 && length Modules.moduleRejections == 39)
    (fail "module corpus must retain 21 runtime cases and 39 prescribed rejections")
  accepted <- forM (zip [1..] Modules.modulePrograms) $ \(i,(name,mode,libraries,input,expectedOutput)) ->
    writeCase ("module-accept-" ++ padded i) name mode libraries input True
      (Just ("",expectedOutput)) Nothing
  rejected <- forM (zip [1..] Modules.moduleRejections) $ \(i,Modules.ModuleRejection name libraries input phase reason) ->
    writeCase ("module-reject-" ++ padded i) name ImplicitPrelude libraries input False
      Nothing (Just (phase,reason))
  pure (accepted ++ rejected)
  where
    writeCase identity name mode libraries input accepts expectedOutput expectedError = do
      let directory = "cases" </> "modules" </> identity
          search = directory </> "libraries"
          -- An unused missing include root is legal. Preserve this loader
          -- regression in the full native parity gate as well as CLI tests.
          searchPaths = if identity == "module-accept-000001"
            then [directory </> "missing search root",search] else [search]
      createDirectoryIfMissing True (output </> search)
      forM_ libraries $ \(moduleName,text) -> do
        let file = output </> search </> intercalate "/" (moduleParts moduleName) ++ ".emlf"
        createDirectoryIfMissing True (takeDirectory file)
        writeUtf8 file text
      pure $ (simpleCase identity "modules" name accepts
        "test/Modules.hs prescribed module scope, typing, diagnostic and runtime outcomes" input)
        { relativeSource = directory </> "Main.emlf", includes = searchPaths
        , runtime = expectedOutput, preludeMode = mode, rejection = expectedError }

oracleGroup :: String -> String -> [S.Expr] -> [Case]
oracleGroup group oracle terms =
  [ simpleCase (group ++ "-" ++ padded i) group (group ++ " term " ++ show i)
      (Oracle.hmTypable term) oracle (prettyExpr term)
  | (i,term) <- zip [1..] terms ]

padded :: Int -> String
padded n = replicate (max 0 (6 - length text)) '0' ++ text where text = show n

sourceFiles :: FilePath -> FilePath -> IO [FilePath]
sourceFiles repository directory = do
  names <- sort <$> listDirectory (repository </> directory)
  concat <$> forM names (\name -> do
    let file = directory </> name
    isDirectory <- doesDirectoryExist (repository </> file)
    if isDirectory then sourceFiles repository file
      else pure [file | ".emlf" `isSuffixOf` file])

fileCase :: FilePath -> FilePath -> IO Case
fileCase repository file = do
  text <- readFile (repository </> file)
  parsed <- either fail pure (parseModule file text)
  let group = if take 11 file == "benchmarks/" then "benchmarks" else "examples"
      identity = "file-" ++ map (\c -> if isAlphaNum c then c else '-') (dropExtension file)
      copied = "repository" </> file
      -- Module paths derive from their dotted module name and source path.
      root = foldl (\p _ -> takeDirectory p) (takeDirectory copied)
        [2..maybe 1 (length . moduleParts) (MS.sourceModuleName parsed)]
      library = MS.sourceBody parsed == Nothing &&
        not (any (\(n,_,_) -> n == "main") (MS.sourceValues parsed))
      search = nub [takeDirectory copied,root,"repository/examples/modules","repository/examples"]
  when library $ unless (MS.sourceModuleName parsed /= Nothing)
    (fail ("declaration-only source has no module identity or entry: " ++ file))
  let name = maybe "Main" id (MS.sourceModuleName parsed)
      probe = "import qualified " ++ name ++ "\nmain = ioReturn Unit\n"
      relative = if library then "cases" </> group </> identity ++ "-import.emlf" else copied
      input = if library then probe else text
  pure $ Case identity group relative file True
    (if library then "repository library import must compile" else "repository example or benchmark must compile")
    input (Just file) search Nothing ImplicitPrelude Nothing

moduleParts :: String -> [String]
moduleParts name = case break (== '.') name of
  (part,[]) -> [part]
  (part,_:rest) -> part : moduleParts rest

exportCase :: FilePath -> Case -> IO Exported
exportCase output c = do
  let path = output </> relativeSource c
  createDirectoryIfMissing True (takeDirectory path)
  unless (originalPath c == Just (drop 11 (relativeSource c)) && take 11 (relativeSource c) == "repository/")
    (writeUtf8 path (source c ++ "\n"))
  result <- compileFileWithPrelude (preludeMode c) (map (output </>) (includes c)) path
  case result of
    Left err -> do
      when (expected c) (fail ("seed rejects independently expected acceptance " ++ caseId c ++ ": " ++ show err))
      when (category c `elem` ["hm-exhaustive","hm-generated","state"] && phase err /= Inference)
        (fail ("Typing negative failed outside inference: " ++ caseId c ++ ": " ++ show err))
      case rejection c of
        Just (expectedPhase,reason) -> unless (phase err == expectedPhase && reason `isInfixOf` diagnostic err)
          (fail ("seed disagrees with prescribed rejection " ++ caseId c ++ ": " ++ show err))
        Nothing -> pure ()
    Right compilation -> do
      unless (expected c) (fail ("seed accepts independently expected rejection " ++ caseId c))
      ty <- either fail pure (XC.checkClosed (compiledTerm compilation))
      unless (XT.alphaEq ty (inferredType compilation)) (fail ("seed target type differs: " ++ caseId c))
      parsed <- either fail pure (XP.parseTerm path (XPretty.prettyTerm (compiledTerm compilation)))
      parsedType <- either fail pure (XC.checkClosed parsed)
      unless (XT.alphaEq parsedType ty && X.erase parsed == X.erase (compiledTerm compilation))
        (fail ("seed target printer roundtrip differs: " ++ caseId c))
  pure (Exported c result)

manifestRow :: Exported -> String
manifestRow (Exported c result) = jsonObject $
  [ ("schema_version","1")
  , ("id",jsonString (caseId c))
  , ("category",jsonString (category c))
  , ("label",jsonString (label c))
  , ("source_path",jsonString (relativeSource c))
  , ("expected_accept",if expected c then "true" else "false")
  , ("acceptance_oracle",jsonString (acceptanceOracle c))
  , ("include_dirs",jsonArray (map jsonString (includes c)))
  , ("no_prelude",if preludeMode c == NoImplicitPrelude then "true" else "false")
  ] ++ maybe [] (\path -> [("original_path",jsonString path)]) (originalPath c) ++
  maybe [] (\(_,reason) -> [("expected_error_contains",jsonString reason)]) (rejection c) ++
  (case result of
    Left err -> [("expected_phase",jsonString (show (phase err)))]
    Right compilation -> [("expected_type",jsonString (XPretty.prettyType (inferredType compilation))),
                          ("type_oracle",jsonString "Haskell seed, independently checked target")]) ++
  maybe [] (\(input,output) -> [("expected_stdin",jsonString input),("expected_stdout",jsonString output)]) (runtime c)

jsonObject :: [(String,String)] -> String
jsonObject fields = "{" ++ intercalate "," [jsonString k ++ ":" ++ v | (k,v) <- fields] ++ "}"
jsonArray :: [String] -> String
jsonArray values = "[" ++ intercalate "," values ++ "]"
jsonString :: String -> String
jsonString input = '"' : concatMap escape input ++ "\""
  where
    escape '"' = "\\\""
    escape '\\' = "\\\\"
    escape '\b' = "\\b"
    escape '\f' = "\\f"
    escape '\n' = "\\n"
    escape '\r' = "\\r"
    escape '\t' = "\\t"
    escape c | ord c < 32 = let h = showHex (ord c) "" in "\\u" ++ replicate (4-length h) '0' ++ h
             | otherwise = [c]

writeUtf8 :: FilePath -> String -> IO ()
writeUtf8 path text = withFile path WriteMode $ \handle -> hSetEncoding handle utf8 >> hPutStr handle text

-- Explicit syntax only, independent of the source parser's pretty printing.
-- Failure on an unexpected AST extension prevents accidental fixture loss.
prettyExpr :: S.Expr -> String
prettyExpr expression = case expression of
  S.Var name -> name
  S.Lam name annotation body -> "(\\" ++ parameter name annotation ++ " -> " ++ prettyExpr body ++ ")"
  S.App function argument -> "(" ++ prettyExpr function ++ " " ++ prettyExpr argument ++ ")"
  S.Let name value body -> "(let " ++ name ++ " = " ++ prettyExpr value ++ " in " ++ prettyExpr body ++ ")"
  S.Ann value annotation -> "(" ++ prettyExpr value ++ " : " ++ prettyAnnotation annotation ++ ")"
  S.IntLit n -> "(" ++ show n ++ ")"
  S.BoolLit b -> if b then "true" else "false"
  _ -> error ("unsupported oracle AST in corpus source printer: " ++ show expression)
  where
    parameter n Nothing = n
    parameter n (Just annotation) = "(" ++ n ++ " : " ++ prettyAnnotation annotation ++ ")"

prettyAnnotation :: S.Annotation -> String
prettyAnnotation (S.Annotation variables ty) =
  (if null variables then "" else "exists " ++ unwords variables ++ ". ") ++ prettySourceType ty

prettySourceType :: S.Type -> String
prettySourceType ty = case ty of
  S.TVar name -> name
  S.Bottom -> "bot"
  S.BottomKind kind -> "(bot : " ++ K.prettyKind kind ++ ")"
  S.Arrow a b -> "(" ++ prettySourceType a ++ " -> " ++ prettySourceType b ++ ")"
  S.Con name [] -> name
  S.Con name arguments -> "(" ++ unwords (name : map prettySourceType arguments) ++ ")"
  S.TypeApp function argument -> "(" ++ prettySourceType function ++ " " ++ prettySourceType argument ++ ")"
  S.Forall flag name bound body -> "(forall " ++ parameter flag name bound ++ ". " ++ prettySourceType body ++ ")"
  S.Qualified _ _ -> error "qualified type is not part of the independent annotation corpus"
  where
    parameter S.Flexible name S.Bottom = name
    parameter flag name bound = "(" ++ name ++ (if flag == S.Flexible then " >= " else " = ") ++ prettySourceType bound ++ ")"

annotationTerms :: [S.Expr]
annotationTerms = concat
  [ [ S.Ann identityExpr (S.Annotation [] (S.Arrow ty ty))
    , S.Lam "x" (Just (S.Annotation [] ty)) (S.Var "x")
    , S.Let "f" (S.Ann identityExpr (S.Annotation [] (S.Arrow ty ty))) (S.Var "f")
    ] | ty <- nested ]
  where
    identityExpr = S.Lam "x" Nothing (S.Var "x")
    identityType = S.Forall S.Flexible "a" S.Bottom (S.Arrow (S.TVar "a") (S.TVar "a"))
    types = [S.Bottom, S.Con "Int" [], S.Con "Bool" [], identityType,
             S.Forall S.Flexible "a" S.Bottom (S.Con "List" [S.TVar "a"]),
             S.Forall S.Flexible "a" identityType (S.Arrow (S.TVar "a") (S.TVar "a"))]
    nested = types ++ [S.Arrow a b | a <- types, b <- types]
